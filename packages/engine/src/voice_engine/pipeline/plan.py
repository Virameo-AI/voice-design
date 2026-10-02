from __future__ import annotations

import re
from dataclasses import dataclass, field

# About 13 characters per second of speech. A segment stays under 20 seconds
# so Qwen does not drift.
CHARS_PER_SECOND = 13
MAX_SEGMENT_SECONDS = 20
MAX_SEGMENT_CHARS = CHARS_PER_SECOND * MAX_SEGMENT_SECONDS

TAG = re.compile(r"\[([a-z][a-z0-9 ]*(?:\s+\d+(?:\.\d+)?s)?)\]", re.IGNORECASE)
SENTENCE = re.compile(r".+?(?:[.!?](?=\s|$)|$)", re.DOTALL)


@dataclass
class Segment:
    text: str
    tags: list[str] = field(default_factory=list)
    pause_after_s: float = 0.35

    @property
    def spoken(self) -> str:
        return TAG.sub("", self.text).strip()


def _pause_after(text: str, style) -> float:
    stripped = text.rstrip()
    if stripped.endswith("\n\n") or text.endswith("\n\n"):
        return style.pause_paragraph_s
    if stripped.endswith((",", ";", ":")):
        return style.pause_comma_s
    return style.pause_period_s


def _explicit_pause(tag: str) -> float | None:
    match = re.fullmatch(r"pause\s+(\d+(?:\.\d+)?)s", tag.strip().lower())
    if not match:
        return None
    return float(match.group(1))


def plan_script(text: str, style) -> list[Segment]:
    """Split a script into short beats. [pause 0.8s] sets the gap after a beat."""
    if not text.strip():
        raise ValueError("text is empty")
    segments: list[Segment] = []
    block = ""

    def flush() -> None:
        nonlocal block
        spoken = TAG.sub("", block).strip()
        block = ""
        if not spoken:
            return
        for piece in _pieces(spoken):
            segments.append(Segment(piece, pause_after_s=_pause_after(piece, style)))

    for part in re.split(r"(\[[^\[\]]+\])", text):
        if not part:
            continue
        match = TAG.fullmatch(part.strip())
        if match and part.strip().startswith("["):
            flush()
            tag = match.group(1).strip().lower()
            pause = _explicit_pause(tag)
            if pause is None:
                raise ValueError(f"unknown tag [{tag}]. The only tag is [pause 0.8s], with the gap in seconds.")
            if segments:
                segments[-1].pause_after_s = pause
            else:
                segments.append(Segment("", ["pause"], pause))
            continue
        block += part
    flush()
    if not segments:
        raise ValueError("text is empty")
    return segments


def _pieces(text: str) -> list[str]:
    sentences = [part.strip() for part in SENTENCE.findall(text) if part.strip()]
    if not sentences:
        sentences = [text.strip()]
    pieces: list[str] = []
    buf = ""
    for sentence in sentences:
        if buf and len(buf) + 1 + len(sentence) > MAX_SEGMENT_CHARS:
            pieces.append(buf)
            buf = sentence
        else:
            buf = f"{buf} {sentence}".strip()
        while len(buf) > MAX_SEGMENT_CHARS:
            pieces.append(buf[:MAX_SEGMENT_CHARS].rsplit(" ", 1)[0] or buf[:MAX_SEGMENT_CHARS])
            buf = buf[len(pieces[-1]):].strip()
    if buf:
        pieces.append(buf)
    return pieces
