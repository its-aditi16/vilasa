"""FastAPI app: courier dashboard + simulated customer call.

Run:  uvicorn vilasa.app:app --reload     then open http://127.0.0.1:8000
"""

from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .audio import to_wav
from .callflow import CallSession
from .config import ROOT, settings
from .gnani import GnaniError, get_clients, usage_summary
from .normalize import detect_language
from .pincodes import PinDirectory
from .prompts import PROMPTS

app = FastAPI(title="Vilasa", version="0.1.0")
STATIC = ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")

PINS = PinDirectory.load(settings.pin_file)
DELIVERIES = {d["id"]: d for d in json.loads((ROOT / "data" / "deliveries.json").read_text(encoding="utf-8"))["deliveries"]}
STT, TTS = get_clients(settings)
SESSIONS: dict[str, CallSession] = {}
SPEECH: dict[str, tuple[str, str]] = {}  # audio key → (text, language)


class PromptWarmer:
    """Makes a language's fixed prompts ahead of time, so the disk cache can answer during the call.

    One worker, because Timbre takes one request at a time. The newest language goes first: it's the one the call is in now.
    """

    def __init__(self, tts):
        self.tts = tts
        self.queue: queue.PriorityQueue = queue.PriorityQueue()
        self.lock = threading.Lock()
        self.seen: set[str] = set()
        self.batch = 0
        self.worker: threading.Thread | None = None

    def add(self, language: str):
        with self.lock:
            if language in self.seen or language not in PROMPTS:
                return
            self.seen.add(language)
            self.batch += 1
            fixed = [t for t in PROMPTS[language].values() if "{" not in t]
            for i, text in enumerate(fixed):
                self.queue.put((-self.batch, i, text, language))
            if self.worker is None:
                self.worker = threading.Thread(target=self._run, daemon=True)
                self.worker.start()

    def _run(self):
        while True:
            _, _, text, language = self.queue.get()
            try:
                self.tts.synthesize(text, language=language)
            except GnaniError:
                self.seen.discard(language)  # the next call in this language tries again
            finally:
                self.queue.task_done()


WARMER = PromptWarmer(TTS)


def _speech_url(text: str, language: str) -> str:
    key = hashlib.sha1(f"{language}|{text}".encode()).hexdigest()[:16]
    SPEECH[key] = (text, language)
    return f"/api/speech/{key}.wav"


def _turn_payload(session: CallSession, turn) -> dict:
    if not settings.mock:
        WARMER.add(session.language)
    return {
        "session_id": session.id,
        "state": session.state,
        "finished": session.finished,
        "reply": {"text": turn.text, "language": turn.language, "audio_url": _speech_url(turn.text, turn.language)},
        "card": session.card(),
    }


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    return {**settings.redacted(), "usage": usage_summary(settings), "demo_pin_data": bool(PINS.meta.get("demo")),
            "pins_loaded": len(PINS.pins)}


@app.get("/api/deliveries")
def deliveries():
    out = []
    for d in DELIVERIES.values():
        info = PINS.get(d["pin"])
        out.append({k: v for k, v in d.items() if k != "mock_answers"} | {"taluk": info.taluk if info else None})
    return out


class StartCall(BaseModel):
    delivery_id: str


@app.post("/api/calls")
def start_call(body: StartCall):
    d = DELIVERIES.get(body.delivery_id)
    if not d:
        raise HTTPException(404, "Unknown delivery")
    s = CallSession(d, PINS)
    SESSIONS[s.id] = s
    return _turn_payload(s, s.start())


@app.post("/api/calls/{sid}/turn")
async def call_turn(sid: str, audio: UploadFile | None = File(None), text: str | None = Form(None), no_speech: bool = Form(False)):
    began = time.perf_counter()
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "Unknown call")
    if s.finished:
        raise HTTPException(409, "Call already finished")

    source = "no speech" if no_speech else "typed"  # hands-free mode heard nothing, so this counts as a silent turn
    heard = {"source": source, "text": (text or "").strip(), "language": None, "latency": 0.0, "cached": False, "stt_ms": 0}
    if audio is not None and not heard["text"]:
        raw = await audio.read()
        if not raw:
            raise HTTPException(400, "Empty audio")
        try:
            wav = to_wav(raw)
        except RuntimeError as exc:
            raise HTTPException(415, str(exc)) from exc
        ctx = s.stt_context()
        hint = (s.delivery.get("mock_answers") or {}).get(s.state, "")  # mock mode only
        stt_began = time.perf_counter()
        try:
            r = STT.transcribe(
                wav, filename="turn.wav", language_code=ctx["language_code"], keyterms=ctx["keyterms"],
                topic=ctx["topic"], hint=hint,
            )
        except GnaniError as exc:
            return JSONResponse({"error": exc.code, "message": exc.message}, status_code=502)
        heard = {"source": "mock" if settings.mock else "prisma", "text": r.text, "language": r.language,
                 "latency": r.latency, "cached": r.cached, "keyterms": len(ctx["keyterms"]),
                 "stt_ms": round((time.perf_counter() - stt_began) * 1000)}

    turn = s.handle(heard["text"], heard["language"], meta={"source": heard["source"]})
    payload = _turn_payload(s, turn)
    payload["heard"] = heard
    payload["turn_ms"] = round((time.perf_counter() - began) * 1000)
    return payload


@app.post("/api/calls/{sid}/scripted")
def scripted_turn(sid: str):
    """Demo helper: answer with the delivery's scripted (synthetic) reply for the current step."""
    began = time.perf_counter()
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "Unknown call")
    if s.finished:
        raise HTTPException(409, "Call already finished")
    text = (s.delivery.get("mock_answers") or {}).get(s.state, "")
    turn = s.handle(text, detect_language(text), meta={"source": "scripted"})
    payload = _turn_payload(s, turn)
    payload["heard"] = {"source": "scripted", "text": text, "language": detect_language(text), "latency": 0.0, "cached": False, "stt_ms": 0}
    payload["turn_ms"] = round((time.perf_counter() - began) * 1000)
    return payload


@app.get("/api/calls/{sid}")
def call_detail(sid: str):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "Unknown call")
    return {"card": s.card(), "transcript": s.transcript(), "state": s.state}


@app.get("/api/speech/{key}.wav")
def speech(key: str):
    if key not in SPEECH:
        raise HTTPException(404, "Unknown audio")
    text, language = SPEECH[key]
    try:
        audio = TTS.synthesize(text, language=language)
    except GnaniError as exc:
        return JSONResponse({"error": exc.code, "message": exc.message}, status_code=502)
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "max-age=86400"})
