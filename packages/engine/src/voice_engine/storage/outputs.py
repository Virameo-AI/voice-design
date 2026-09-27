from __future__ import annotations

from voice_engine.schemas import Checks
from voice_engine.storage.blobs import compress, decompress


class Outputs:
    def __init__(self, storage) -> None:
        self.storage = storage

    def add(self, job_id: str, name: str, seed: int | None, sample_rate: int, checks: Checks, wav: bytes) -> None:
        packed = compress(wav)
        self.storage.execute(
            """
            INSERT INTO outputs (job_id, name, seed, sample_rate, checks, audio, nbytes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, name, seed, sample_rate, checks.model_dump_json(), packed, len(packed)),
        )

    def wav(self, job_id: str, name: str) -> bytes | None:
        rows = self.storage.query("SELECT audio FROM outputs WHERE job_id = ? AND name = ?", (job_id, name))
        return decompress(rows[0]["audio"]) if rows else None

    def compressed_size(self, job_id: str, name: str) -> int | None:
        rows = self.storage.query("SELECT nbytes FROM outputs WHERE job_id = ? AND name = ?", (job_id, name))
        return int(rows[0]["nbytes"]) if rows else None
