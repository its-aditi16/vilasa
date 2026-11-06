"""Audio helpers: make uploads Prisma-friendly, and degrade clean audio to 'village phone' quality for the benchmark."""

from __future__ import annotations

import io
import shutil
import struct
import subprocess
import wave

import numpy as np

MAX_SECONDS = 29.5  # Prisma REST accepts up to 30 s per request


def is_wav(data: bytes) -> bool:
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def with_real_sizes(data: bytes) -> bytes:
    """Timbre streams its WAVs with 0xFFFFFFFF as both sizes. Browsers should be told the real length."""
    pos = data.find(b"data", 12)
    if not is_wav(data) or pos < 0 or data[pos + 4:pos + 8] != b"\xff\xff\xff\xff":
        return data
    fixed = bytearray(data)
    fixed[4:8] = struct.pack("<I", len(data) - 8)
    fixed[pos + 4:pos + 8] = struct.pack("<I", len(data) - pos - 8)
    return bytes(fixed)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def to_wav(data: bytes, rate: int = 16000) -> bytes:
    """Any format → mono 16-bit WAV via ffmpeg. WAV input is passed through (and trimmed)."""
    if is_wav(data):
        return trim(data)
    if not ffmpeg_available():
        raise RuntimeError("This audio is not WAV and ffmpeg is not installed. Install ffmpeg or upload WAV.")
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(rate),
         "-t", str(MAX_SECONDS), "-f", "wav", "pipe:1"],
        input=data, capture_output=True, check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError("ffmpeg could not decode the audio: " + proc.stderr.decode(errors="replace")[:200])
    return proc.stdout


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width {width}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, rate


def write_wav(x: np.ndarray, rate: int) -> bytes:
    x = np.clip(x, -1.0, 1.0)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def trim(data: bytes, seconds: float = MAX_SECONDS) -> bytes:
    x, rate = read_wav(data)
    if len(x) <= seconds * rate:
        return data
    return write_wav(x[: int(seconds * rate)], rate)


def resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return x
    if dst < src:  # crude anti-alias low-pass before decimating
        x = bandlimit(x, src, 0, dst * 0.45)
    n = int(round(len(x) * dst / src))
    t_src = np.arange(len(x)) / src
    t_dst = np.arange(n) / dst
    return np.interp(t_dst, t_src, x).astype(np.float32)


def bandlimit(x: np.ndarray, rate: int, lo: float, hi: float) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1.0 / rate)
    spec[(freqs < lo) | (freqs > hi)] = 0
    return np.fft.irfft(spec, n=len(x)).astype(np.float32)


def phone_quality(data: bytes) -> bytes:
    """Narrow-band phone line: 8 kHz, 300–3400 Hz, light companding-like clipping."""
    x, rate = read_wav(data)
    x = resample(x, rate, 8000)
    x = bandlimit(x, 8000, 300, 3400)
    x = np.tanh(2.0 * x) / np.tanh(2.0)
    return write_wav(x, 8000)


def _noise(kind: str, n: int, rate: int, rng: np.random.Generator) -> np.ndarray:
    white = rng.standard_normal(n).astype(np.float32)
    if kind == "white":
        return white
    if kind == "traffic":  # rumbling low-frequency noise (brown-ish)
        brown = np.cumsum(white)
        brown -= np.convolve(brown, np.ones(400) / 400, mode="same")
        return bandlimit(brown.astype(np.float32), rate, 40, 1200)
    if kind == "crowd":  # babble-like: band-limited noise with slow loudness swings
        band = bandlimit(white, rate, 250, 3000)
        swing = 0.6 + 0.4 * np.sin(2 * np.pi * rng.uniform(0.5, 2.0) * np.arange(n) / rate)
        return (band * swing).astype(np.float32)
    raise ValueError(kind)


def add_noise(data: bytes, snr_db: float, kind: str = "crowd", seed: int = 7, noise_wav: bytes | None = None) -> bytes:
    """Mix noise at a target signal-to-noise ratio. Pass a real recording as noise_wav if you have one."""
    x, rate = read_wav(data)
    rng = np.random.default_rng(seed)
    if noise_wav:
        nz, nrate = read_wav(noise_wav)
        nz = resample(nz, nrate, rate)
        nz = np.resize(nz, len(x))
    else:
        nz = _noise(kind, len(x), rate, rng)
    p_sig = float(np.mean(x ** 2)) or 1e-9
    p_noise = float(np.mean(nz ** 2)) or 1e-9
    nz *= np.sqrt(p_sig / (p_noise * 10 ** (snr_db / 10)))
    y = x + nz
    peak = np.max(np.abs(y)) or 1.0
    if peak > 0.99:
        y = y / peak * 0.99
    return write_wav(y, rate)
