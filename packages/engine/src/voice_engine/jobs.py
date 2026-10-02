from __future__ import annotations

import logging
import queue
import secrets
import threading

import numpy as np
from datetime import datetime, timezone

from voice_engine.audio import analyze, wav_bytes
from voice_engine.backends import Backend
from voice_engine.library import Library
from voice_engine.pipeline.plan import plan_script
from voice_engine.pipeline.stitch import match_level, stitch, trim_silence
from voice_engine.pipeline.styles import get_style
from voice_engine.schemas import DesignSpec, Job, LockSpec, Progress, RenderSpec, SpeakSpec

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
            job.progress.detail = "Interrupted by restart. Submit the same request again."
            self.storage.jobs.save(job)
        pending = self.storage.jobs.list(status="queued", limit=500)
        for job in sorted(pending, key=lambda item: item.created_at):
            self._queue.put(job.id)

    def submit(self, spec: DesignSpec | LockSpec | SpeakSpec | RenderSpec) -> Job:
        self._check(spec)
        job = Job(
            id=_new_id(),
            type=spec.type,
            status="queued",
            spec=spec.model_dump(exclude_none=True),
            created_at=_now(),
        )
        self.storage.jobs.save(job)
        if isinstance(spec, DesignSpec) and spec.playground_id:
            self.storage.playgrounds.add_run(spec.playground_id, job.id, spec.model_dump(exclude_none=True, exclude={"type", "playground_id"}))
        if isinstance(spec, RenderSpec) and spec.narration_id:
            self.storage.narrations.set_job(spec.narration_id, job.id, "rendering")
        self._queue.put(job.id)
        return job

    def _check(self, spec) -> None:
        if isinstance(spec, LockSpec):
            self._candidate(spec)
            if self.library.exists(spec.voice_id):
                raise FileExistsError(f"voice {spec.voice_id} already exists. Use a new version id.")
        elif isinstance(spec, DesignSpec):
            if spec.playground_id and self.storage.playgrounds.get(spec.playground_id) is None:
                raise LookupError(f"playground {spec.playground_id} not found")
        elif isinstance(spec, (SpeakSpec, RenderSpec)):
            self.library.resolve_version(spec.voice_id, spec.version_id)
            if isinstance(spec, RenderSpec):
                get_style(spec.style, self.storage)

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
            elif job.type == "render":
                self._render(job, RenderSpec.model_validate(job.spec))
            else:
                self._speak(job, SpeakSpec.model_validate(job.spec))
            job.progress = Progress(phase="done", detail="Finished.", completed=job.progress.total or job.progress.completed, total=job.progress.total)
            job.status = "succeeded"
        except Exception as exc:
            log.exception("job %s failed", job.id)
            job.status, job.error = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            job.finished_at = _now()
            self.running_id = None
            self.storage.jobs.save(job)
            narration = self.storage.narrations.for_job(job.id)
            if narration is not None:
                self.storage.narrations.set_job(narration["id"], job.id, "rendered" if job.status == "succeeded" else "failed")

    def _design(self, job: Job, spec: DesignSpec) -> None:
        params, job.applied, job.deferred = self.backend.split(spec.params.given(), "design")
        for index in range(spec.candidates):
            self._report(job, "design", f"Take {index + 1} of {spec.candidates}.", index, spec.candidates)
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
        run = self.storage.playgrounds.run_for_job(source.id)
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
            "duration_s": picked.checks.duration_s,
            "playground_id": run["playground_id"] if run else design.playground_id,
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
        version = self.library.resolve_version(spec.voice_id, spec.version_id)
        job.version_id = version["id"]
        params, job.applied, job.deferred = self.backend.split(spec.params.given(), "speak")
        self._report(job, "speak", "Speaking the text.", 0, 1)
        with self.library.stage(spec.voice_id, version["id"]) as voice_dir:
            ref_text = (voice_dir / "preview.txt").read_text().strip()
            audio, rate = self.backend.speak(voice_dir, ref_text, spec.text, spec.language, spec.seed, params)
        self.storage.outputs.add(job.id, "audio.wav", spec.seed, rate, analyze(audio, rate, spec.text), wav_bytes(audio, rate))
        job.voice_id = spec.voice_id
        saved = self.get(job.id)
        if saved is not None:
            job.outputs = saved.outputs

    def _render(self, job: Job, spec: RenderSpec) -> None:
        style = get_style(spec.style, self.storage)
        version = self.library.resolve_version(spec.voice_id, spec.version_id)
        job.version_id = version["id"]
        segments = plan_script(spec.text, style)
        params, job.applied, job.deferred = self.backend.split({**spec.params.given(), "temperature": spec.params.temperature or style.temperature}, "speak")
        job.applied = sorted(set(job.applied) | {"style"})
        deferred_tags: list[str] = []
        self._report(job, "render", f"0 of {len(segments)} beats.", 0, len(segments))
        parts = []
        rate = 24000
        with self.library.stage(spec.voice_id, version["id"]) as voice_dir:
            ref_text = (voice_dir / "preview.txt").read_text().strip()
            for index, segment in enumerate(segments, start=1):
                self._report(job, "render", f"Beat {index} of {len(segments)}.", index - 1, len(segments))
                if segment.spoken:
                    audio, rate, seed, checks = self._segment(voice_dir, ref_text, segment.spoken, spec, params, index)
                else:
                    audio = np.zeros(int(rate * 0.05), dtype="float32")
                    seed = spec.seed
                    checks = analyze(audio, rate, "")
                deferred_tags.extend(tag for tag in segment.tags if tag != "pause")
                leveled = match_level(trim_silence(audio, rate), style.loudness_dbfs)
                name = f"segment-{index:02d}.wav"
                self.storage.outputs.add(job.id, name, seed, rate, checks, wav_bytes(leveled, rate))
                job.outputs.append(_output(name, seed, rate, checks))
                self.storage.jobs.save(job)
                parts.append((leveled, segment.pause_after_s))
        if deferred_tags:
            job.deferred = sorted(set(job.deferred) | {f"tag:{tag}" for tag in deferred_tags})
        self._report(job, "stitch", "Joining the beats.", len(segments), len(segments))
        audio = stitch(parts, rate, style.crossfade_s)
        checks = analyze(audio, rate, spec.text)
        self.storage.outputs.add(job.id, "audio.wav", spec.seed, rate, checks, wav_bytes(audio, rate))
        job.voice_id = spec.voice_id
        saved = self.get(job.id)
        if saved is not None:
            job.outputs = saved.outputs

    def _segment(self, voice_dir, ref_text, text, spec: RenderSpec, params: dict, index: int):
        last = None
        for attempt in range(3):
            seed = spec.seed + index * 10 + attempt
            audio, rate = self.backend.speak(voice_dir, ref_text, text, spec.language, seed, params)
            checks = analyze(audio, rate, text)
            last = (audio, rate, seed, checks)
            if checks.ok or not set(checks.warnings) & {"too_short", "clipping", "too_quiet", "pace_fast", "pace_slow"}:
                break
        assert last is not None
        return last


    def _report(self, job: Job, phase: str, detail: str, completed: int, total: int) -> None:
        job.progress = Progress(phase=phase, detail=detail, completed=completed, total=total)
        self.storage.jobs.save(job)


def _output(name, seed, rate, checks):
    from voice_engine.schemas import Output

    return Output(file=name, seed=seed, sample_rate=rate, checks=checks)
