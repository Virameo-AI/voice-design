from __future__ import annotations

import json

from voice_engine.schemas import Job, Output


def _job(row, outputs: list[Output]) -> Job:
    return Job(
        id=row["id"],
        type=row["type"],
        status=row["status"],
        spec=json.loads(row["spec"]),
        backend=row["backend"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        applied=json.loads(row["applied"]),
        deferred=json.loads(row["deferred"]),
        outputs=outputs,
        voice_id=row["voice_id"],
        error=row["error"],
    )


class Jobs:
    def __init__(self, storage) -> None:
        self.storage = storage

    def _outputs(self, job_id: str) -> list[Output]:
        rows = self.storage.query(
            "SELECT name, seed, sample_rate, checks FROM outputs WHERE job_id = ? ORDER BY name",
            (job_id,),
        )
        return [
            Output(file=row["name"], seed=row["seed"], sample_rate=row["sample_rate"], checks=json.loads(row["checks"]))
            for row in rows
        ]

    def get(self, job_id: str) -> Job | None:
        rows = self.storage.query("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return _job(rows[0], self._outputs(job_id)) if rows else None

    def list(self, status: str | None = None, type_: str | None = None, limit: int = 50) -> list[Job]:
        sql = "SELECT * FROM jobs WHERE 1 = 1"
        params: list = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if type_:
            sql += " AND type = ?"
            params.append(type_)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.storage.query(sql, tuple(params))
        return [_job(row, self._outputs(row["id"])) for row in rows]

    def save(self, job: Job) -> None:
        with self.storage.transaction() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, type, status, spec, backend, created_at, started_at, finished_at,
                    applied, deferred, voice_id, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    spec = excluded.spec,
                    backend = excluded.backend,
                    started_at = excluded.started_at,
                    finished_at = excluded.finished_at,
                    applied = excluded.applied,
                    deferred = excluded.deferred,
                    voice_id = excluded.voice_id,
                    error = excluded.error
                """,
                (
                    job.id,
                    job.type,
                    job.status,
                    json.dumps(job.spec),
                    job.backend,
                    job.created_at,
                    job.started_at,
                    job.finished_at,
                    json.dumps(job.applied),
                    json.dumps(job.deferred),
                    job.voice_id,
                    job.error,
                ),
            )

    def delete(self, job_id: str) -> bool:
        with self.storage.transaction() as conn:
            cursor = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            return cursor.rowcount > 0

    def count_status(self, status: str) -> int:
        rows = self.storage.query("SELECT COUNT(*) AS n FROM jobs WHERE status = ?", (status,))
        return int(rows[0]["n"])
