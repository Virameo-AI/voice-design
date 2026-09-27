from __future__ import annotations

import json
from pathlib import Path

from voice_engine.schemas import Job
from voice_engine.storage.blobs import compress

MARKER = "legacy_import_v1"


def import_legacy(storage) -> bool:
    """Copy data/jobs and data/voices once. Returns True when this call performed the import."""
    if storage.metadata(MARKER) == "complete":
        return False
    jobs_root = storage.data_dir / "jobs"
    voices_root = storage.data_dir / "voices"
    with storage.transaction() as conn:
        if jobs_root.is_dir():
            for path in sorted(jobs_root.glob("*/job.json")):
                _job(conn, path)
        if voices_root.is_dir():
            for path in sorted(p for p in voices_root.iterdir() if (p / "voice.json").is_file()):
                _voice(conn, path)
        storage.set_metadata(MARKER, "complete", conn)
    return True


def _job(conn, path: Path) -> None:
    job = Job.model_validate_json(path.read_text())
    folder = path.parent
    conn.execute(
        """
        INSERT INTO jobs (
            id, type, status, spec, backend, created_at, started_at, finished_at,
            applied, deferred, voice_id, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    for output in job.outputs:
        wav = folder / output.file
        if not wav.is_file():
            continue
        packed = compress(wav.read_bytes())
        conn.execute(
            """
            INSERT INTO outputs (job_id, name, seed, sample_rate, checks, audio, nbytes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job.id, output.file, output.seed, output.sample_rate, output.checks.model_dump_json(), packed, len(packed)),
        )


def _voice(conn, folder: Path) -> None:
    meta = json.loads((folder / "voice.json").read_text())
    master = folder / "master.wav"
    if not master.is_file():
        return
    packed = compress(master.read_bytes())
    prompt_path = folder / "voice_prompt.pt"
    prompt = prompt_path.read_bytes() if prompt_path.is_file() else None
    conn.execute(
        """
        INSERT INTO voices (
            voice_id, name, notes, created_at, language, from_job, candidate, seed,
            design_backend, sample_rate, preview, instruct, master, prompt
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            meta["voice_id"],
            meta.get("name") or meta["voice_id"],
            meta.get("notes"),
            meta["created_at"],
            meta.get("language") or "English",
            meta["from_job"],
            meta["candidate"],
            meta.get("seed"),
            meta.get("design_backend"),
            meta.get("sample_rate") or 24000,
            (folder / "preview.txt").read_text() if (folder / "preview.txt").is_file() else "",
            (folder / "instruct.txt").read_text() if (folder / "instruct.txt").is_file() else "",
            packed,
            prompt,
        ),
    )
