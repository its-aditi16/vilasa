import io
import threading
import wave

from fastapi.testclient import TestClient

from vilasa.app import PromptWarmer, app
from vilasa.gnani import GnaniError
from vilasa.prompts import PROMPTS, say

client = TestClient(app)


def _silence_wav(seconds=1.0, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def test_status_never_leaks_key():
    r = client.get("/api/status").json()
    assert r["mode"] == "mock"
    assert "api_key" not in r and "GNANI_API_KEY" not in str(r)


def test_full_call_over_http_with_audio_and_text():
    deliveries = client.get("/api/deliveries").json()
    assert deliveries and "mock_answers" not in deliveries[0]
    start = client.post("/api/calls", json={"delivery_id": "VIL-1001"}).json()
    sid = start["session_id"]
    assert start["reply"]["audio_url"].endswith(".wav")
    assert client.get(start["reply"]["audio_url"]).headers["content-type"] == "audio/wav"

    # audio turn (mock STT returns the scripted answer)
    p = client.post(f"/api/calls/{sid}/turn", files={"audio": ("t.wav", _silence_wav(), "audio/wav")}).json()
    assert p["heard"]["source"] == "mock" and p["state"] == "landmark"
    # typed turn
    p = client.post(f"/api/calls/{sid}/turn", data={"text": "ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ"}).json()
    assert p["state"] == "house"
    p = client.post(f"/api/calls/{sid}/scripted").json()
    assert p["state"] == "confirm"
    p = client.post(f"/api/calls/{sid}/scripted").json()
    assert p["finished"] and p["card"]["status"] == "confirmed"
    assert p["card"]["pin_corrected"] == "572104"
    assert "maps" in p["card"]["maps_url"]
    assert client.post(f"/api/calls/{sid}/scripted").status_code == 409


def _call(delivery="VIL-1001"):
    return client.post("/api/calls", json={"delivery_id": delivery}).json()["session_id"]


def test_turn_reports_how_long_it_took():
    sid = _call()
    p = client.post(f"/api/calls/{sid}/turn", files={"audio": ("t.wav", _silence_wav(), "audio/wav")}).json()
    assert isinstance(p["heard"]["stt_ms"], int) and p["turn_ms"] >= p["heard"]["stt_ms"]
    p = client.post(f"/api/calls/{sid}/turn", data={"text": "ಆಂಜನೇಯ ಗುಡಿ ಹಿಂದೆ"}).json()
    assert p["heard"]["stt_ms"] == 0 and p["turn_ms"] >= 0
    p = client.post(f"/api/calls/{sid}/scripted").json()
    assert p["turn_ms"] >= 0


def test_no_speech_asks_again_then_ends_the_call_rather_than_looping_forever():
    sid = _call()
    p = client.post(f"/api/calls/{sid}/turn", data={"no_speech": "true"}).json()
    assert p["state"] == "village" and p["heard"]["source"] == "no speech"
    assert p["reply"]["text"] == say("kn-IN", "retry")
    for _ in range(20):
        if p["finished"]:
            break
        p = client.post(f"/api/calls/{sid}/turn", data={"no_speech": "true"}).json()
    assert p["finished"] and p["card"]["status"] == "needs rider call"


def test_card_says_how_long_the_call_took_once_it_is_over():
    sid = _call()
    for _ in range(3):
        p = client.post(f"/api/calls/{sid}/scripted").json()
        assert p["card"]["call_seconds"] is None
    p = client.post(f"/api/calls/{sid}/scripted").json()
    assert p["card"]["call_seconds"] >= 0 and p["card"]["turns"] == 4


class FakeTTS:
    def __init__(self, fail=False):
        self.said = []
        self.fail = fail
        self.release = threading.Event()
        self.release.set()

    def synthesize(self, text, language="kn-IN"):
        self.release.wait(5)
        self.said.append((language, text))
        if self.fail:
            raise GnaniError(500, "DOWN", "down")
        return b"RIFF"


def test_warmer_makes_only_the_fixed_prompts():
    tts = FakeTTS()
    w = PromptWarmer(tts)
    w.add("hi-IN")
    w.add("hi-IN")  # no second round for the same language
    w.queue.join()
    assert {t for _, t in tts.said} == {t for k, t in PROMPTS["hi-IN"].items() if k != "confirm"}
    assert len(tts.said) == len(PROMPTS["hi-IN"]) - 1


def test_warmer_does_the_language_the_call_just_switched_to_first():
    tts = FakeTTS()
    tts.release.clear()  # hold the worker on the first Kannada prompt
    w = PromptWarmer(tts)
    w.add("kn-IN")
    w.add("hi-IN")
    tts.release.set()
    w.queue.join()
    order = [lang for lang, _ in tts.said]
    assert order[0] == "kn-IN" and order[1] == "hi-IN" and order[-1] == "kn-IN"


def test_warmer_survives_a_failure_and_tries_again_next_time():
    tts = FakeTTS(fail=True)
    w = PromptWarmer(tts)
    w.add("kn-IN")
    w.queue.join()
    assert "kn-IN" not in w.seen and w.worker.is_alive()
