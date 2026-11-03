"""Settings loaded from environment / .env. The API key is read here and nowhere else."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _flag(name: str) -> bool | None:
    raw = os.getenv(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


@dataclass
class Settings:
    api_key: str = field(default_factory=lambda: os.getenv("GNANI_API_KEY", "").strip())
    stt_url: str = field(default_factory=lambda: os.getenv("GNANI_STT_URL", "https://api.vachana.ai/stt/v3"))
    stt_model: str = field(default_factory=lambda: os.getenv("GNANI_STT_MODEL", "prisma-v3.0"))
    stt_format: str = field(default_factory=lambda: os.getenv("GNANI_STT_FORMAT", "transcribe"))
    tts_url: str = field(default_factory=lambda: os.getenv("GNANI_TTS_URL", "https://api.vachana.ai/api/v1/tts/inference"))
    tts_model: str = field(default_factory=lambda: os.getenv("GNANI_TTS_MODEL", "timbre-v3.0"))
    tts_voice: str = field(default_factory=lambda: os.getenv("GNANI_TTS_VOICE", "Chetana"))
    tts_sample_rate: int = field(default_factory=lambda: int(os.getenv("GNANI_TTS_SAMPLE_RATE", "16000")))
    pin_file: Path = field(default_factory=lambda: ROOT / os.getenv("VILASA_PIN_FILE", "data/pincodes_tumakuru.json"))
    cache_dir: Path = field(default_factory=lambda: ROOT / ".cache")
    _mock: bool | None = field(default_factory=lambda: _flag("VILASA_MOCK"))

    @property
    def mock(self) -> bool:
        if self._mock is not None:
            return self._mock
        return not self.api_key

    def redacted(self) -> dict:
        """Safe-to-print summary. Never includes the key itself."""
        return {
            "mode": "mock" if self.mock else "live",
            "api_key_set": bool(self.api_key),
            "stt": f"{self.stt_model} ({self.stt_format})",
            "tts": f"{self.tts_model} / {self.tts_voice} @ {self.tts_sample_rate} Hz",
            "pin_file": str(self.pin_file.relative_to(ROOT)) if self.pin_file.is_relative_to(ROOT) else str(self.pin_file),
        }


settings = Settings()
