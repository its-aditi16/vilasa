import io
import wave

from fastapi.testclient import TestClient

from vilasa.app import app

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
