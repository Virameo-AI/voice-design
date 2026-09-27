from __future__ import annotations

import logging
import queue
import secrets
import threading
from datetime import datetime, timezone

from voice_engine.audio import analyze, wav_bytes
from voice_engine.backends import Backend
from voice_engine.library import Library
from voice_engine.schemas import DesignSpec, Job, LockSpec, SpeakSpec

log = logging.getLogger("voice_engine.jobs")
TERMINAL = {"succeeded", "failed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"job_{stamp}_{secrets.token_hex(3)}"


class JobStore:
    """The queue and the single worker. Rows live in the storage layer."""

    def __init__(self, storage, backend: Backend, library: Library) -> None:
        self.storage = storage
        self.backend = backend
        self.library = library
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self.running_id: str | None = None
        self.worker_error: str | None = None
        self._recover()

    def _recover(self) -> None:
        for job in self.storage.jobs.list(status="running", limit=500):
            job.status, job.error, job.finished_at = "failed", "interrupted by restart", _now()
            self.storage.jobs.save(job)
        pending = self.storage.jobs.list(status="queued", limit=500)
        for job in sorted(pending, key=lambda item: item.created_at):
            self._queue.put(job.id)

    def submit(self, spec: DesignSpec | LockSpec | SpeakSpec) -> Job:
        self._check(spec)
        job = Job(
            id=_new_id(),
            type=spec.type,
            status="queued",
            spec=spec.model_dump(exclude_none=True),
            created_at=_now(),
        )
        self.storage.jobs.save(job)
        self._queue.put(job.id)
        return job

    def _check(self, spec) -> None:
        if isinstance(spec, LockSpec):
            self._candidate(spec)
            if self.library.exists(spec.voice_id):
                raise FileExistsError(f"voice {spec.voice_id} already exists. Use a new version id.")
        elif isinstance(spec, SpeakSpec) and not self.library.exists(spec.voice_id):
            raise LookupError(f"voice {spec.voice_id} not found")

    def get(self, job_id: str) -> Job | None:
        return self.storage.jobs.get(job_id)

    def list(self, status: str | None = None, type_: str | None = None, limit: int = 50) -> list[Job]:
        return self.storage.jobs.list(status, type_, limit)

    def queued(self) -> int:
        return self.storage.jobs.count_status("queued")

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise LookupError(job_id)
        if job.status != "queued":
            raise ValueError(f"job is {job.status}; only queued jobs can be cancelled")
        job.status, job.finished_at = "cancelled", _now()
        self.storage.jobs.save(job)
        return job

    def delete(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            raise LookupError(job_id)
        if job.status == "running":
            raise ValueError("a running job cannot be deleted")
        self.storage.jobs.delete(job_id)

    def wav(self, job_id: str, name: str) -> bytes | None:
        job = self.get(job_id)
        if job is None or name not in {item.file for item in job.outputs}:
            return None
        return self.storage.outputs.wav(job_id, name)

    def start(self, preload: bool = False) -> None:
        self._thread = threading.Thread(target=self._worker, args=(preload,), name="voice-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout)

    def _worker(self, preload: bool) -> None:
        if preload:
            try:
                self.backend.load()
            except Exception as exc:
                log.exception("preload failed")
                self.worker_error = f"preload failed: {exc}"
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            job = self.get(job_id)
            if job is None or job.status != "queued":
                continue
            self._execute(job)

    def _execute(self, job: Job) -> None:
        job.status, job.started_at, job.backend = "running", _now(), self.backend.name
        self.running_id = job.id
        self.storage.jobs.save(job)
        try:
            if job.type == "design":
                self._design(job, DesignSpec.model_validate(job.spec))
            elif job.type == "lock":
                self._lock_voice(job, LockSpec.model_validate(job.spec))
            else:
                self._speak(job, SpeakSpec.model_validate(job.spec))
            job.status = "succeeded"
        except Exception as exc:
            log.exception("job %s failed", job.id)
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = _now()
            self.running_id = None
            self.storage.jobs.save(job)

    def _design(self, job: Job, spec: DesignSpec) -> None:
        params, job.applied, job.deferred = self.backend.split(spec.params.given(), "design")
        for index in range(spec.candidates):
            seed = spec.seed_start + index
            audio, rate = self.backend.design(spec.text, spec.instruct, spec.language, seed, params)
            name = f"candidate-{index + 1:02d}.wav"
            checks = analyze(audio, rate, spec.text)
            self.storage.outputs.add(job.id, name, seed, rate, checks, wav_bytes(audio, rate))
            job.outputs.append(_output(name, seed, rate, checks))
            self.storage.jobs.save(job)

    def _candidate(self, spec: LockSpec) -> bytes:
        source = self.get(spec.from_job)
        if source is None or source.type != "design":
            raise LookupError(f"design job {spec.from_job} not found")
        if source.status != "succeeded":
            raise ValueError(f"design job {spec.from_job} is {source.status}")
        if spec.candidate > len(source.outputs):
            raise ValueError(f"design job has {len(source.outputs)} candidates, asked for {spec.candidate}")
        wav = self.storage.outputs.wav(source.id, source.outputs[spec.candidate - 1].file)
        if wav is None:
            raise LookupError(f"candidate {spec.candidate} audio is missing")
        return wav

    def _lock_voice(self, job: Job, spec: LockSpec) -> None:
        wav = self._candidate(spec)
        source = self.get(spec.from_job)
        assert source is not None
        design = DesignSpec.model_validate(source.spec)
        picked = source.outputs[spec.candidate - 1]
        meta = {
            "name": spec.name or spec.voice_id,
            "notes": spec.notes,
            "created_at": _now(),
            "language": design.language,
            "from_job": source.id,
            "candidate": spec.candidate,
            "seed": picked.seed,
            "design_backend": source.backend,
            "sample_rate": picked.sample_rate,
        }
        self.library.create(
            spec.voice_id,
            wav,
            preview_text=design.text,
            instruct=design.instruct,
            meta=meta,
            prepare=lambda master, folder: self.backend.lock(master, design.text, folder),
        )
        job.voice_id = spec.voice_id

    def _speak(self, job: Job, spec: SpeakSpec) -> None:
        if not self.library.exists(spec.voice_id):
            raise LookupError(f"voice {spec.voice_id} not found")
        params, job.applied, job.deferred = self.backend.split(spec.params.given(), "speak")
        with self.library.stage(spec.voice_id) as voice_dir:
            ref_text = (voice_dir / "preview.txt").read_text().strip()
            audio, rate = self.backend.speak(voice_dir, ref_text, spec.text, spec.language, spec.seed, params)
        self.storage.outputs.add(job.id, "audio.wav", spec.seed, rate, analyze(audio, rate, spec.text), wav_bytes(audio, rate))
        job.voice_id = spec.voice_id
        saved = self.get(job.id)
        if saved is not None:
            job.outputs = saved.outputs


def _output(name, seed, rate, checks):
    from voice_engine.schemas import Output

    return Output(file=name, seed=seed, sample_rate=rate, checks=checks)
