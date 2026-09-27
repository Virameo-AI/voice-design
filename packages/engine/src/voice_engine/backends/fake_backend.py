from __future__ import annotations

import zlib
from pathlib import Path

import numpy as np

from voice_engine.backends.base import SAMPLING, Backend

SAMPLE_RATE = 24000


def _tone(key: str, text: str) -> np.ndarray:
    freq = 110 + zlib.crc32(key.encode()) % 220
    seconds = max(0.8, len(text.strip()) / 15)
    t = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (0.3 * np.sin(2 * np.pi * freq * t)).astype("float32")


class FakeBackend(Backend):
    """Deterministic tones so the service can be tested without a GPU."""

    name = "fake"
    device = "cpu"
    supports = SAMPLING | {"speed"}

    def design(self, text, instruct, language, seed, params):
        return _tone(f"{instruct}:{seed}", text), SAMPLE_RATE

    def lock(self, master: Path, ref_text: str, voice_dir: Path) -> None:
        return None

    def speak(self, voice_dir, ref_text, text, language, seed, params):
        return _tone(f"{voice_dir.name}:{seed}", text), SAMPLE_RATE
