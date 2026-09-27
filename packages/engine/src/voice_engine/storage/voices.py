from __future__ import annotations

from voice_engine.storage.blobs import compress, decompress


class Voices:
    def __init__(self, storage) -> None:
        self.storage = storage

    def exists(self, voice_id: str) -> bool:
        return bool(self.storage.query("SELECT 1 FROM voices WHERE voice_id = ?", (voice_id,)))

    def get(self, voice_id: str) -> dict | None:
        rows = self.storage.query(
            """
            SELECT voice_id, name, notes, created_at, language, from_job, candidate,
                   seed, design_backend, sample_rate
            FROM voices WHERE voice_id = ?
            """,
            (voice_id,),
        )
        return dict(rows[0]) if rows else None

    def list(self) -> list[dict]:
        rows = self.storage.query(
            """
            SELECT voice_id, name, notes, created_at, language, from_job, candidate,
                   seed, design_backend, sample_rate
            FROM voices ORDER BY created_at
            """
        )
        return [dict(row) for row in rows]

    def text(self, voice_id: str, column: str) -> str | None:
        if column not in {"preview", "instruct"}:
            raise ValueError(column)
        rows = self.storage.query(f"SELECT {column} AS value FROM voices WHERE voice_id = ?", (voice_id,))
        return rows[0]["value"] if rows else None

    def master_wav(self, voice_id: str) -> bytes | None:
        rows = self.storage.query("SELECT master FROM voices WHERE voice_id = ?", (voice_id,))
        return decompress(rows[0]["master"]) if rows else None

    def prompt(self, voice_id: str) -> bytes | None:
        rows = self.storage.query("SELECT prompt FROM voices WHERE voice_id = ?", (voice_id,))
        if not rows or rows[0]["prompt"] is None:
            return None
        return rows[0]["prompt"]

    def set_prompt(self, voice_id: str, prompt: bytes) -> None:
        self.storage.execute("UPDATE voices SET prompt = ? WHERE voice_id = ?", (prompt, voice_id))

    def insert(self, meta: dict, preview: str, instruct: str, master: bytes, prompt: bytes | None) -> None:
        packed = compress(master)
        self.storage.execute(
            """
            INSERT INTO voices (
                voice_id, name, notes, created_at, language, from_job, candidate, seed,
                design_backend, sample_rate, preview, instruct, master, prompt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                meta["voice_id"],
                meta["name"],
                meta.get("notes"),
                meta["created_at"],
                meta["language"],
                meta["from_job"],
                meta["candidate"],
                meta.get("seed"),
                meta.get("design_backend"),
                meta["sample_rate"],
                preview,
                instruct,
                packed,
                prompt,
            ),
        )

    def delete(self, voice_id: str) -> bool:
        with self.storage.transaction() as conn:
            cursor = conn.execute("DELETE FROM voices WHERE voice_id = ?", (voice_id,))
            return cursor.rowcount > 0
