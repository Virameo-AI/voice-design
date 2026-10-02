from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import soundfile as sf

from voice_engine.schemas import Checks

SILENCE_DBFS = -45.0


def to_mono(audio) -> np.ndarray:
    data = np.asarray(audio, dtype="float32")
    return data.reshape(-1) if data.ndim > 1 else data


def join(chunks: list, sample_rate: int, gap_s: float = 0.25) -> np.ndarray:
    parts = [to_mono(c) for c in chunks if c is not None]
    if not parts:
        return np.zeros(0, dtype="float32")
    gap = np.zeros(int(sample_rate * gap_s), dtype="float32")
    out = [parts[0]]
    for part in parts[1:]:
        out += [gap, part]
    return np.concatenate(out)


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    audio, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    return audio.mean(axis=1).astype("float32"), int(rate)


def wav_bytes(audio, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, to_mono(audio), sample_rate, format="WAV")
    return buffer.getvalue()


def write_wav(path: Path, audio, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav_bytes(audio, sample_rate))


def _silent_run(frames_db: np.ndarray, hop_s: float) -> float:
    loud = np.nonzero(frames_db > SILENCE_DBFS)[0]
    if loud.size == 0:
        return len(frames_db) * hop_s
    return float(loud[0]) * hop_s


def analyze(audio, sample_rate: int, text: str | None = None) -> Checks:
    data = to_mono(audio)
    duration = len(data) / sample_rate if sample_rate else 0.0
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    rms = float(np.sqrt(np.mean(data**2))) if data.size else 0.0
    rms_dbfs = 20 * np.log10(rms) if rms > 0 else -120.0
    clipped = float(np.mean(np.abs(data) >= 0.999)) if data.size else 0.0

    hop = max(1, int(sample_rate * 0.02))
    usable = (len(data) // hop) * hop
    if usable:
        frames = data[:usable].reshape(-1, hop)
        frame_rms = np.sqrt(np.mean(frames**2, axis=1))
        frames_db = 20 * np.log10(np.maximum(frame_rms, 1e-9))
        hop_s = hop / sample_rate
        lead = _silent_run(frames_db, hop_s)
        tail = _silent_run(frames_db[::-1], hop_s)
    else:
        lead = tail = duration

    warnings = []
    if duration < 0.5:
        warnings.append("too_short")
    if clipped > 0.001:
        warnings.append("clipping")
    if rms_dbfs < -40:
        warnings.append("too_quiet")
    if lead > 1.5:
        warnings.append("long_lead")
    if tail > 1.5:
        warnings.append("long_tail")

    chars_per_s = None
    if text and duration > 0:
        chars_per_s = round(len(text.strip()) / duration, 2)
        if chars_per_s > 30:
            warnings.append("pace_fast")
        elif chars_per_s < 6:
            warnings.append("pace_slow")

    return Checks(
        duration_s=round(duration, 3),
        peak=round(peak, 4),
        rms_dbfs=round(float(rms_dbfs), 2),
        clipped_ratio=round(clipped, 5),
        lead_silence_s=round(lead, 3),
        tail_silence_s=round(tail, 3),
        chars_per_s=chars_per_s,
        ok=not warnings,
        warnings=warnings,
    )
