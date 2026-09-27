"""Built-in voice templates. The page reads these through the API."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path

from voice_engine.storage.blobs import compress

PREVIEW = "Give it a second. Ordinary things get interesting when they refuse to behave the way we expect."
SAMPLE_DIR = Path(__file__).resolve().parent / "catalog_samples"


@dataclass(frozen=True)
class Builtin:
    id: str
    name: str
    role: str
    instruct: str
    seed_start: int


CATALOG: tuple[Builtin, ...] = (
    Builtin(
        "builtin-warm-narrator",
        "Warm narrator",
        "Adult narrator, warm low-mid voice, calm and curious",
        "An adult male narrator in his mid-thirties with a warm, low-mid voice. Neutral international English, clear diction, calm and curious, like a science explainer who enjoys the topic.",
        1000,
    ),
    Builtin(
        "builtin-documentary",
        "Documentary",
        "Measured, clear, unhurried, the voice of a filmed essay",
        "A documentary narrator in their forties. Measured pace, clear mid voice, curious but never breathless, as if walking through a filmed essay. Neutral English, close and steady.",
        1100,
    ),
    Builtin(
        "builtin-cinematic",
        "Cinematic narrator",
        "Low and wide, the voice in a trailer",
        "A cinematic trailer narrator. Adult, low and wide, controlled power, short pauses, serious but not shouted. Neutral English, the voice over a wide shot.",
        1200,
    ),
    Builtin(
        "builtin-news",
        "News anchor",
        "Crisp, even, confident, no rush",
        "A television news anchor. Adult, crisp mid voice, even pace, confident and neutral, clear consonants, no smile in the voice and no rush.",
        1300,
    ),
    Builtin(
        "builtin-podcast",
        "Podcast host",
        "Close and conversational, talking to one person",
        "A podcast host in their thirties. Close-mic, conversational, warm, talking to one listener. Light curiosity, natural breaths, friendly without performing.",
        1400,
    ),
    Builtin(
        "builtin-storyteller",
        "Storyteller",
        "Slow, soft, a bedtime story told nearby",
        "A storyteller sitting nearby. Adult, soft medium-low voice, slow pace, gentle and unhurried, like a bedtime story told to one child. Clear, never whispery.",
        1500,
    ),
    Builtin(
        "builtin-teacher",
        "Teacher",
        "Patient and bright, explaining one idea at a time",
        "A patient teacher. Adult, bright clear voice, explains one idea at a time, encouraging, precise diction, a small smile, never condescending.",
        1600,
    ),
    Builtin(
        "builtin-commercial",
        "Commercial",
        "Polished, friendly, an ad read with a smile",
        "A commercial voiceover. Adult, polished and friendly, a smile in the voice, bright mid range, confident and clean, like a short ad read.",
        1700,
    ),
    Builtin(
        "builtin-animated",
        "Animated character",
        "Expressive cartoon lead, big energy, clear diction",
        "An animated lead character. Youthful adult, expressive and bright, big energy without shouting, clear diction, playful lifts at the ends of phrases, like a cartoon hero introducing themselves.",
        1800,
    ),
    Builtin(
        "builtin-sidekick",
        "Sidekick",
        "Smaller, quicker, playful, reacts more than it explains",
        "A cartoon sidekick. Smaller brighter voice, quicker pace, playful and reactive, a little breathless with delight, clear words, never shrill.",
        1900,
    ),
    Builtin(
        "builtin-songwriter",
        "Songwriter",
        "Young adult speaking with a lyrical, rhythmic cadence",
        "A young songwriter talking through a thought. Warm, close, slightly rhythmic cadence, musical phrasing, intimate and unforced, spoken not sung.",
        2000,
    ),
    Builtin(
        "builtin-vlogger",
        "Vlogger",
        "Casual, close, thinking out loud",
        "A young adult vlogger. Casual, close, thinking out loud, friendly and quick, modern conversational English, like a camera on a desk.",
        2100,
    ),
    Builtin(
        "builtin-sports",
        "Sports commentator",
        "Fast, excited, still easy to follow",
        "A sports commentator. Adult, bright and forward, fast but intelligible, excited without screaming, clear consonants, the energy of a live call.",
        2200,
    ),
    Builtin(
        "builtin-mystery",
        "Mystery",
        "Quiet, low, leaving room around the words",
        "A mystery narrator. Adult, quiet low voice, leaving space around the words, calm tension, close and dry, never a whisper and never a shout.",
        2300,
    ),
    Builtin(
        "builtin-elder",
        "Elder",
        "Older, kind, unhurried, a story they have told before",
        "An older storyteller around seventy. Kind, unhurried, a gently worn voice, warm and steady, telling a story they have told before. Clear enough to follow.",
        2400,
    ),
    Builtin(
        "builtin-villain",
        "Villain",
        "Controlled, cool, theatrical, never shouting",
        "A theatrical villain. Adult, cool controlled voice, low-mid, precise and amused, a little larger than life, never shouting, every word placed.",
        2500,
    ),
)


def _tiny_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(b"\x00\x00" * 2400)
    return buffer.getvalue()


TINY_WAV = _tiny_wav()


def sample_wav(template_id: str) -> bytes:
    path = SAMPLE_DIR / f"{template_id}.wav"
    if path.is_file():
        data = path.read_bytes()
        if data[:4] == b"RIFF":
            return data
    return TINY_WAV


def ensure_catalog(storage) -> None:
    """Insert any built-in row or sample that is missing. Leave user rows alone."""
    for index, item in enumerate(CATALOG):
        found = storage.query("SELECT 1 FROM templates WHERE id = ?", (item.id,))
        if not found:
            storage.execute(
                """
                INSERT INTO templates (
                    id, origin, name, role, notes, instruct, text, language,
                    candidates, seed_start, params, sort_order, created_at, updated_at
                ) VALUES (?, 'builtin', ?, ?, NULL, ?, ?, 'English', 4, ?, '{}', ?, NULL, NULL)
                """,
                (item.id, item.name, item.role, item.instruct, PREVIEW, item.seed_start, index),
            )
        has_sample = storage.query("SELECT 1 FROM template_samples WHERE template_id = ?", (item.id,))
        if not has_sample:
            packed = compress(sample_wav(item.id))
            storage.execute(
                """
                INSERT INTO template_samples (template_id, seed, sample_rate, audio, nbytes)
                VALUES (?, ?, 24000, ?, ?)
                """,
                (item.id, item.seed_start, packed, len(packed)),
            )
