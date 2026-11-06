"""The live API can't be reached from CI, so check the request we build and how we read replies."""

import io
import json
import wave

import pytest

from vilasa import gnani
from vilasa.audio import add_noise, phone_quality, read_wav, trim
from vilasa.config import Settings


def wav(seconds=1.0, rate=16000):
    import math
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(int(8000 * math.sin(i / 8)).to_bytes(2, "little", signed=True) for i in range(int(seconds * rate))))
    return buf.getvalue()


class FakeResp:
    def __init__(self, status=200, body=None, content=b"", headers=None):
        self.status_code = status
        self._body = body
        self.content = content
        self.headers = headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


@pytest.fixture
def cfg(tmp_path):
    c = Settings()
    c.api_key = "test-key"
    c.cache_dir = tmp_path
    c._mock = False
    return c


def test_stt_request_shape(monkeypatch, cfg):
    seen = {}

    def fake_post(url, headers, data, files, timeout):
        seen.update(url=url, headers=headers, data=data, files=files)
        return FakeResp(body={"success": True, "transcript": "ಕ್ಯಾತಸಂದ್ರ", "detected_language_code": "kn-IN", "end_to_end_latency": 0.7})

    monkeypatch.setattr(gnani.requests, "post", fake_post)
    r = gnani.PrismaSTT(cfg).transcribe(wav(), keyterms=["Kyathsandra", "kyathsandra", "Hirehalli"], topic="village")
    assert seen["url"].endswith("/stt/v3")
    assert seen["headers"] == {"X-API-Key-ID": "test-key"}
    assert seen["data"]["model"] == "prisma-v3.0" and seen["data"]["language_code"] == "indic-auto"
    assert json.loads(seen["data"]["keyterms"]) == ["Kyathsandra", "Hirehalli"]  # de-duplicated
    assert "audio_file" in seen["files"]
    assert (r.text, r.language) == ("ಕ್ಯಾತಸಂದ್ರ", "kn-IN")


def test_stt_cache_avoids_second_call(monkeypatch, cfg):
    calls = []
    monkeypatch.setattr(gnani.requests, "post", lambda *a, **k: calls.append(1) or FakeResp(body={"success": True, "transcript": "x"}))
    stt = gnani.PrismaSTT(cfg)
    audio = wav()
    stt.transcribe(audio)
    r = stt.transcribe(audio)
    assert len(calls) == 1 and r.cached


def test_stt_error_envelope(monkeypatch, cfg):
    monkeypatch.setattr(gnani.requests, "post", lambda *a, **k: FakeResp(400, {"success": False, "error": {"type": "INVALID_LANGUAGE_CODE", "message": "bad"}}))
    with pytest.raises(gnani.GnaniError) as e:
        gnani.PrismaSTT(cfg, use_cache=False).transcribe(wav())
    assert e.value.code == "INVALID_LANGUAGE_CODE"


def test_rate_limit_is_retried(monkeypatch, cfg):
    replies = [FakeResp(429, {"detail": {"error_code": "RATE_LIMITED"}}), FakeResp(body={"success": True, "transcript": "ok"})]
    monkeypatch.setattr(gnani.requests, "post", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(gnani.time, "sleep", lambda s: None)
    assert gnani.PrismaSTT(cfg, use_cache=False).transcribe(wav()).text == "ok"


def test_tts_returns_wav_and_caches(monkeypatch, cfg):
    calls = []

    def fake_post(url, headers, data, timeout):
        body = json.loads(data)
        calls.append(body)
        return FakeResp(content=wav(0.2), headers={"Content-Type": "audio/wav"})

    monkeypatch.setattr(gnani.requests, "post", fake_post)
    tts = gnani.TimbreTTS(cfg)
    a = tts.synthesize("ನಮಸ್ಕಾರ", language="kn-IN")
    b = tts.synthesize("ನಮಸ್ಕಾರ", language="kn-IN")
    assert a[:4] == b"RIFF" and a == b and len(calls) == 1
    assert calls[0]["model"] == "timbre-v3.0" and calls[0]["audio_config"]["container"] == "wav"


def test_missing_key_is_a_clear_error(cfg):
    cfg.api_key = ""
    with pytest.raises(gnani.GnaniError) as e:
        gnani.PrismaSTT(cfg, use_cache=False).transcribe(wav())
    assert e.value.code == "MISSING_API_KEY"


def test_phone_and_noise_degradation():
    x, rate = read_wav(add_noise(phone_quality(wav(1.0)), 5))
    assert rate == 8000 and abs(len(x) - 8000) < 5


def placeholder_header(data):
    """How Timbre streams its WAVs: both size fields are 0xFFFFFFFF."""
    data = bytearray(data)
    data[4:8] = data[40:44] = b"\xff\xff\xff\xff"
    return bytes(data)


def test_wav_seconds_uses_real_length_when_header_size_is_impossible():
    assert gnani.wav_seconds(placeholder_header(wav(seconds=1.0))) == 1.0


def test_wav_seconds_trusts_a_valid_header_over_trailing_chunks():
    assert gnani.wav_seconds(wav(seconds=1.0) + b"LIST\x04\x00\x00\x00abcd") == 1.0


def test_read_wav_and_trim_handle_placeholder_header():
    data = placeholder_header(wav(seconds=2.0))
    x, rate = read_wav(data)
    assert rate == 16000 and len(x) == 32000
    assert trim(data, seconds=3.0) == data
    assert len(read_wav(trim(data, seconds=1.0))[0]) == 16000
