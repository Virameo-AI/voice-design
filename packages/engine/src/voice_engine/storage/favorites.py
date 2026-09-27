from __future__ import annotations

from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Favorites:
    def __init__(self, storage) -> None:
        self.storage = storage

    def list(self) -> list[dict]:
        rows = self.storage.query(
            """
            SELECT f.voice_id, f.note AS profile_note, f.created_at AS profile_created_at,
                   v.name, v.notes, v.created_at, v.language, v.from_job, v.candidate,
                   v.seed, v.design_backend, v.sample_rate
            FROM favorites f
            JOIN voices v ON v.voice_id = f.voice_id
            ORDER BY f.created_at DESC
            """
        )
        return [dict(row) for row in rows]

    def put(self, voice_id: str, note: str | None) -> dict:
        if not self.storage.voices.exists(voice_id):
            raise LookupError(voice_id)
        now = _now()
        self.storage.execute(
            """
            INSERT INTO favorites (voice_id, note, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(voice_id) DO UPDATE SET note = excluded.note
            """,
            (voice_id, note, now),
        )
        found = next(item for item in self.list() if item["voice_id"] == voice_id)
        return found

    def delete(self, voice_id: str) -> None:
        with self.storage.transaction() as conn:
            cursor = conn.execute("DELETE FROM favorites WHERE voice_id = ?", (voice_id,))
            if cursor.rowcount == 0:
                raise LookupError(voice_id)
