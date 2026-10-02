from __future__ import annotations

from dataclasses import dataclass

STYLES = ("narration", "comedy", "commercial", "kids")


@dataclass(frozen=True)
class Style:
    """Delivery for one locked voice. The voice itself stays the locked WAV."""

    name: str
    temperature: float
    pause_comma_s: float
    pause_period_s: float
    pause_paragraph_s: float
    loudness_dbfs: float
    crossfade_s: float
    emotion: str | None


PRESETS: dict[str, Style] = {
    "narration": Style("narration", 0.7, 0.15, 0.35, 0.7, -20.0, 0.02, None),
    "comedy": Style("comedy", 0.95, 0.1, 0.28, 0.45, -18.0, 0.015, "excited"),
    "commercial": Style("commercial", 0.65, 0.12, 0.3, 0.4, -16.0, 0.02, "calm"),
    "kids": Style("kids", 0.85, 0.18, 0.4, 0.6, -18.0, 0.02, "happy"),
}


def get_style(name: str, storage=None) -> Style:
    """Saved styles win over the shipped presets so a user copy can be tuned."""
    if storage is not None:
        row = storage.styles.get(name)
        if row is not None:
            return style_from_row(row)
    try:
        return PRESETS[name]
    except KeyError:
        raise ValueError(f"style {name!r} not found. GET /v1/styles lists the saved ones.") from None


def style_from_row(row: dict) -> Style:
    return Style(
        row["id"],
        float(row["temperature"]),
        float(row["pause_comma_s"]),
        float(row["pause_period_s"]),
        float(row["pause_paragraph_s"]),
        float(row["loudness_dbfs"]),
        float(row["crossfade_s"]),
        row.get("emotion") or None,
    )
