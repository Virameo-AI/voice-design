from __future__ import annotations

import numpy as np

from voice_engine.audio import to_mono


def trim_silence(audio, sample_rate: int, thresh_db: float = -45.0) -> np.ndarray:
    data = to_mono(audio)
    if data.size == 0:
        return data
    hop = max(1, int(sample_rate * 0.02))
    usable = (len(data) // hop) * hop
    if usable == 0:
        return data
    frames = data[:usable].reshape(-1, hop)
    loud = 20 * np.log10(np.maximum(np.sqrt(np.mean(frames**2, axis=1)), 1e-9)) > thresh_db
    if not loud.any():
        return data
    start = int(np.argmax(loud)) * hop
    end = (int(len(loud) - np.argmax(loud[::-1]))) * hop
    return data[start:end]


def match_level(audio, target_dbfs: float) -> np.ndarray:
    data = to_mono(audio)
    rms = float(np.sqrt(np.mean(data**2))) if data.size else 0.0
    if rms <= 1e-8:
        return data
    current = 20 * np.log10(rms)
    gain = 10 ** ((target_dbfs - current) / 20)
    return np.clip(data * gain, -1.0, 1.0).astype("float32")


def _fade(n: int) -> np.ndarray:
    if n <= 1:
        return np.ones(max(n, 0), dtype="float32")
    return np.linspace(0.0, 1.0, n, dtype="float32")


def stitch(parts: list[tuple[np.ndarray, float]], sample_rate: int, crossfade_s: float) -> np.ndarray:
    """Join beats. Each item is audio plus the silence that should follow it."""
    fade_n = int(sample_rate * crossfade_s)
    chunks: list[np.ndarray] = []
    for audio, pause_s in parts:
        data = to_mono(audio)
        if chunks and fade_n > 1 and len(chunks[-1]) > fade_n and len(data) > fade_n:
            ramp = _fade(fade_n)
            previous = chunks[-1]
            previous[-fade_n:] = previous[-fade_n:] * (1 - ramp) + data[:fade_n] * ramp
            data = data[fade_n:]
        chunks.append(data)
        if pause_s > 0:
            chunks.append(np.zeros(int(sample_rate * pause_s), dtype="float32"))
    if not chunks:
        return np.zeros(0, dtype="float32")
    return np.concatenate(chunks).astype("float32")
