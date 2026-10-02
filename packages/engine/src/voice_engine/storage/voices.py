from __future__ import annotations

from voice_engine.storage.blobs import compress, decompress

COLUMNS = """
    voice_id, name, notes, created_at, language, from_job, candidate,
    seed, design_backend, sample_rate, playground_id, origin_job_id, origin_candidate,
    current_version_id, favorite, archived, copied_from
"""
EDITABLE = {"name", "notes", "favorite", "archived", "current_version_id"}


def _voice(row) -> dict:
    data = dict(row)
    data["favorite"] = bool(data.get("favorite"))
    data["archived"] = bool(data.get("archived"))
    return data


class Voices:
    def __init__(self, storage) -> None:
        self.storage = storage

    def exists(self, voice_id: str) -> bool:
        return bool(self.storage.query("SELECT 1 FROM voices WHERE voice_id = ?", (voice_id,)))

    def get(self, voice_id: str) -> dict | None:
        rows = self.storage.query(f"SELECT {COLUMNS} FROM voices WHERE voice_id = ?", (voice_id,))
        return _voice(rows[0]) if rows else None

    def list(self, include_archived: bool = False) -> list[dict]:
        sql = f"SELECT {COLUMNS} FROM voices"
        if not include_archived:
            sql += " WHERE archived = 0"
        rows = self.storage.query(sql + " ORDER BY created_at")
        return [_voice(row) for row in rows]

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
                design_backend, sample_rate, preview, instruct, master, prompt,
                playground_id, origin_job_id, origin_candidate, favorite, archived, copied_from
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
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
                meta.get("playground_id"),
                meta.get("origin_job_id", meta["from_job"]),
                meta.get("origin_candidate", meta["candidate"]),
                meta.get("copied_from"),
            ),
        )

    def update(self, voice_id: str, **fields) -> dict:
        if not self.exists(voice_id):
            raise LookupError(voice_id)
        changes = {k: v for k, v in fields.items() if k in EDITABLE and v is not None}
        if "current_version_id" in changes:
            owner = self.storage.query("SELECT voice_id FROM voice_versions WHERE id = ?", (changes["current_version_id"],))
            if not owner or owner[0]["voice_id"] != voice_id:
                raise ValueError(f"version {changes['current_version_id']} does not belong to {voice_id}")
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            values = [int(v) if isinstance(v, bool) else v for v in changes.values()]
            self.storage.execute(f"UPDATE voices SET {sets} WHERE voice_id = ?", (*values, voice_id))
        return self.get(voice_id)

    def delete(self, voice_id: str) -> bool:
        with self.storage.transaction() as conn:
            cursor = conn.execute("DELETE FROM voices WHERE voice_id = ?", (voice_id,))
            return cursor.rowcount > 0
