"""Thin clients for Gnani's Prisma (STT) and Timbre (TTS) REST APIs, plus mock stand-ins.

Live endpoints (docs.gnani.ai):
  STT  POST https://api.vachana.ai/stt/v3                 multipart, header X-API-Key-ID
  TTS  POST https://api.vachana.ai/api/v1/tts/inference   JSON, returns raw WAV bytes

Both clients cache results on disk (.cache/) so re-running a benchmark or replaying a
demo does not spend credits twice, and log every billable call to .cache/usage.jsonl.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .config import Settings, settings as default_settings
from .normalize import detect_language

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_KEYTERMS = 200


class GnaniError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"[{status}] {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


@dataclass
class SttResult:
    text: str
    language: str | None
    latency: float = 0.0
    cached: bool = False
    raw: dict = field(default_factory=dict)


def _parse_error(resp: requests.Response) -> GnaniError:
    code, message = "HTTP_ERROR", resp.text[:300]
    try:
        body = resp.json()
        if isinstance(body.get("error"), dict):
            code = body["error"].get("type", code)
            message = body["error"].get("message", message)
        elif isinstance(body.get("detail"), dict):
            code = body["detail"].get("error_code", code)
            message = body["detail"].get("message", message)
        elif "code" in body:
            code = str(body["code"])
            message = body.get("message", message)
        elif "detail" in body:
            code, message = "VALIDATION_ERROR", json.dumps(body["detail"], ensure_ascii=False)[:300]
    except ValueError:
        pass
    return GnaniError(resp.status_code, code, message)


def _with_retries(send, tries: int = 4):
    delay = 1.0
    for attempt in range(tries):
        try:
            resp = send()
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == tries - 1:
                raise GnaniError(0, "NETWORK_ERROR", str(exc)) from exc
            time.sleep(delay)
            delay *= 2
            continue
        if resp.status_code in RETRY_STATUS and attempt < tries - 1:
            retry_after = resp.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else delay)
            delay *= 2
            continue
        return resp
    return resp  # pragma: no cover


class _Usage:
    def __init__(self, cache_dir: Path):
        self.path = cache_dir / "usage.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, **entry):
        entry["ts"] = round(time.time(), 1)
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def summary(self) -> dict:
        out = {"stt_calls": 0, "stt_seconds": 0.0, "tts_calls": 0, "tts_chars": 0}
        if not self.path.exists():
            return out
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("cached") or e.get("mock"):
                continue
            if e.get("kind") == "stt":
                out["stt_calls"] += 1
                out["stt_seconds"] += e.get("seconds", 0.0)
            elif e.get("kind") == "tts":
                out["tts_calls"] += 1
                out["tts_chars"] += e.get("chars", 0)
        out["stt_seconds"] = round(out["stt_seconds"], 1)
        return out


def wav_seconds(data: bytes) -> float:
    buf = io.BytesIO(data)
    try:
        with wave.open(buf) as w:
            # Timbre streams its WAVs with a placeholder 0xFFFFFFFF size, so cap by the bytes present.
            # wave stops reading at the start of the audio, so buf.tell() is the header length.
            frames = min(w.getnframes(), (len(data) - buf.tell()) // (w.getsampwidth() * w.getnchannels()))
            return frames / float(w.getframerate())
    except (wave.Error, EOFError):
        return 0.0


def _hash(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True, ensure_ascii=False).encode())
    return h.hexdigest()[:24]


def clean_keyterms(terms) -> list[str]:
    seen, out = set(), []
    for t in terms or []:
        t = " ".join(str(t).split())
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
        if len(out) >= MAX_KEYTERMS:
            break
    return out


# --------------------------------------------------------------------------- STT


class PrismaSTT:
    def __init__(self, cfg: Settings | None = None, use_cache: bool = True):
        self.cfg = cfg or default_settings
        self.use_cache = use_cache
        self.cache = self.cfg.cache_dir / "stt"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.usage = _Usage(self.cfg.cache_dir)

    def transcribe(
        self,
        audio: bytes,
        filename: str = "audio.wav",
        language_code: str = "indic-auto",
        fmt: str | None = None,
        keyterms=None,
        topic: str | None = None,
        previous_text: str | None = None,
        hint: str | None = None,  # used only by the mock
    ) -> SttResult:
        fmt = fmt or self.cfg.stt_format
        terms = clean_keyterms(keyterms)
        data = {"model": self.cfg.stt_model, "language_code": language_code, "format": fmt}
        if terms:
            data["keyterms"] = json.dumps(terms, ensure_ascii=False)
        if topic:
            data["topic"] = topic[:1600]
        if previous_text:
            data["previous_text"] = previous_text[-600:]

        key = _hash(audio, data)
        cached_file = self.cache / f"{key}.json"
        seconds = wav_seconds(audio)
        if self.use_cache and cached_file.exists():
            body = json.loads(cached_file.read_text(encoding="utf-8"))
            self.usage.log(kind="stt", seconds=seconds, cached=True)
            return self._result(body, cached=True)

        if not self.cfg.api_key:
            raise GnaniError(401, "MISSING_API_KEY", "Set GNANI_API_KEY in .env (or run in mock mode).")

        def send():
            return requests.post(
                self.cfg.stt_url,
                headers={"X-API-Key-ID": self.cfg.api_key},
                data=data,
                files={"audio_file": (filename, audio)},
                timeout=60,
            )

        resp = _with_retries(send)
        if resp.status_code != 200:
            raise _parse_error(resp)
        body = resp.json()
        if not body.get("success", True):
            err = body.get("error") or {}
            raise GnaniError(200, err.get("type", "STT_FAILED"), err.get("message", str(body)[:300]))
        if self.use_cache:
            cached_file.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        self.usage.log(kind="stt", seconds=seconds, cached=False, keyterms=len(terms))
        return self._result(body, cached=False)

    @staticmethod
    def _result(body: dict, cached: bool) -> SttResult:
        text = body.get("transcript") or ""
        lang = body.get("detected_language_code") or detect_language(text)
        return SttResult(text=text, language=lang, latency=body.get("end_to_end_latency", 0.0) or 0.0, cached=cached, raw=body)


class MockSTT:
    """Returns the `hint` text as if Prisma had heard it. Lets the whole flow run with no key."""

    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or default_settings
        self.usage = _Usage(self.cfg.cache_dir)

    def transcribe(self, audio: bytes = b"", hint: str | None = None, **_) -> SttResult:
        text = hint or ""
        self.usage.log(kind="stt", seconds=wav_seconds(audio), mock=True)
        return SttResult(text=text, language=detect_language(text), latency=0.05, raw={"mock": True, "transcript": text})


# --------------------------------------------------------------------------- TTS


class TimbreTTS:
    _lock = threading.Lock()  # Timbre may serve one request per account at a time

    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or default_settings
        self.cache = self.cfg.cache_dir / "tts"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.usage = _Usage(self.cfg.cache_dir)

    def synthesize(self, text: str, language: str = "kn-IN", voice: str | None = None, speed: float = 1.0) -> bytes:
        body = {
            "text": text,
            "voice": voice or self.cfg.tts_voice,
            "model": self.cfg.tts_model,
            "language": language,
            "speed": speed,
            "audio_config": {
                "sample_rate": self.cfg.tts_sample_rate,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        }
        path = self.cache / f"{_hash(body)}.wav"
        if path.exists():
            self.usage.log(kind="tts", chars=len(text), cached=True)
            return path.read_bytes()
        if not self.cfg.api_key:
            raise GnaniError(401, "MISSING_API_KEY", "Set GNANI_API_KEY in .env (or run in mock mode).")

        def send():
            return requests.post(
                self.cfg.tts_url,
                headers={"X-API-Key-ID": self.cfg.api_key, "Content-Type": "application/json"},
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                timeout=60,
            )

        with self._lock:
            resp = _with_retries(send)
        if resp.status_code != 200:
            raise _parse_error(resp)
        audio = resp.content
        if not audio.startswith(b"RIFF"):
            raise GnaniError(200, "UNEXPECTED_TTS_BODY", resp.headers.get("Content-Type", "?") + " " + resp.text[:200])
        path.write_bytes(audio)
        self.usage.log(kind="tts", chars=len(text), cached=False)
        return audio


class MockTTS:
    """Makes a short, quiet two-note chime so the UI audio path still works offline."""

    def __init__(self, cfg: Settings | None = None):
        self.cfg = cfg or default_settings

    def synthesize(self, text: str, language: str = "kn-IN", voice: str | None = None, speed: float = 1.0) -> bytes:
        rate = 16000
        frames = bytearray()
        for freq, dur in ((660, 0.12), (880, 0.18)):
            n = int(rate * dur)
            for i in range(n):
                env = math.sin(math.pi * i / n)
                frames += struct.pack("<h", int(4000 * env * math.sin(2 * math.pi * freq * i / rate)))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))
        return buf.getvalue()


def get_clients(cfg: Settings | None = None):
    cfg = cfg or default_settings
    if cfg.mock:
        return MockSTT(cfg), MockTTS(cfg)
    return PrismaSTT(cfg), TimbreTTS(cfg)


def usage_summary(cfg: Settings | None = None) -> dict:
    return _Usage((cfg or default_settings).cache_dir).summary()
