from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from voice_engine import __version__
from voice_engine.backends import Backend, create_backend
from voice_engine.config import Settings
from voice_engine.jobs import JobStore
from voice_engine.library import Library
from voice_engine.schemas import (
    DesignRequest,
    FavoriteWrite,
    Job,
    JobSpec,
    LockRequest,
    RenderRequest,
    SpeakRequest,
    TemplateDuplicate,
    TemplatePatch,
    TemplateSample,
    TemplateWrite,
)
from voice_engine.routes_library import TAGS as LIBRARY_TAGS
from voice_engine.routes_library import register as register_library
from voice_engine.storage import open_storage

DESCRIPTION = """
Standalone voice service. A frontend, script, or this page only needs the
server address (`http://host:port`). Nothing else is shared.

## Try it here, end to end

1. **POST /v1/jobs** — pick the **design** example, Execute. Copy `id` from the response.
2. **GET /v1/jobs/{job_id}** — Execute until `status` is `succeeded`. Each output has a `url`.
3. **GET /v1/jobs/{job_id}/files/{name}** — pass that file name (`candidate-01.wav`). The response is a downloadable WAV.
4. **POST /v1/jobs** — **lock** example. Set `from_job` to the design id and `candidate` to the one you liked.
5. **POST /v1/jobs** — **speak** example, with the same `voice_id`. Download `audio.wav` the same way.

If the server was started with a token, click **Authorize** and paste it first.
`GET /health` never needs a token; use it to confirm the address is right.

The machine-readable spec is `/openapi.json`.
"""

TAGS = [
    {
        "name": "Health",
        "description": "Open. Confirms this address is the voice server and which GPU backend it is using.",
    },
    {
        "name": "Voice design",
        "description": "Create candidate speakers from a description, then download and compare them.",
    },
    {
        "name": "Voices",
        "description": "Lock one candidate into a permanent voice id, and read that library.",
    },
    {
        "name": "Speech",
        "description": "Generate audio from text with a locked voice, then download the WAV.",
    },
    {
        "name": "Jobs",
        "description": "The shared queue behind the three sections. The web UI uses this.",
    },
    {
        "name": "Templates",
        "description": "Saved voice recipes and the sample clip for each one.",
    },
    {
        "name": "Profile",
        "description": "Locked voices kept on the user's shelf.",
    },
    *LIBRARY_TAGS,
]

EXAMPLES = {
    "design": {
        "summary": "1. Design candidate voices",
        "description": "Writes candidate-01.wav onward. Poll the job, then download a candidate.",
        "value": {
            "type": "design",
            "instruct": "An adult male narrator in his mid-thirties with a warm, low-mid voice. Calm and curious.",
            "text": "Give it a second. Ordinary things get interesting when they refuse to behave.",
            "language": "English",
            "candidates": 2,
            "seed_start": 1000,
            "params": {"temperature": 0.9},
        },
    },
    "lock": {
        "summary": "2. Lock one candidate",
        "description": "Replace from_job with the design job id. candidate is 1 for candidate-01.wav.",
        "value": {
            "type": "lock",
            "voice_id": "narrator-male-v1",
            "from_job": "job_REPLACE_ME",
            "candidate": 1,
            "name": "Narrator (male)",
        },
    },
    "speak": {
        "summary": "3. Speak new text with the locked voice",
        "description": "Download audio.wav from the finished job.",
        "value": {
            "type": "speak",
            "voice_id": "narrator-male-v1",
            "text": "What actually happens inside a combustion engine? Let's slow it down and look.",
            "language": "English",
            "seed": 1,
            "params": {"temperature": 0.8},
        },
    },
    "render": {
        "summary": "4. Long script in one voice",
        "description": "Up to about ten minutes. [pause 0.8s] sets the gap after a beat. Download audio.wav.",
        "value": {
            "type": "render",
            "voice_id": "narrator-male-v1",
            "style": "narration",
            "text": "The room went quiet.\n\n[pause 0.8s] Then someone at the back started it.",
            "language": "English",
            "seed": 1,
        },
    },
}

WAV = {
    200: {
        "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
        "description": "WAV file. The browser and Swagger UI offer it as a download.",
    }
}


def _with_urls(job: Job) -> Job:
    shown = job.model_copy(deep=True)
    for output in shown.outputs:
        output.url = f"/v1/jobs/{job.id}/files/{output.file}"
    return shown


def _attachment(content: bytes, media_type: str, filename: str) -> Response:
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def create_app(settings: Settings, backend: Backend | None = None) -> FastAPI:
    backend = backend or create_backend(settings.backend)
    storage = open_storage(settings.data_dir)
    library = Library(storage)
    store = JobStore(storage, backend, library)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        store.start(preload=settings.preload)
        yield
        store.stop()

    app = FastAPI(
        title="voice-engine",
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS,
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True},
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origin_list(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.store = store

    bearer = HTTPBearer(
        auto_error=False,
        description="Set this only when the server was started with a token.",
    )

    def require_token(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
        if not settings.token:
            return
        supplied = creds.credentials if creds else ""
        if not supplied or not secrets.compare_digest(supplied, settings.token):
            raise HTTPException(401, "missing or wrong bearer token", headers={"WWW-Authenticate": "Bearer"})

    auth = [Depends(require_token)]

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.get("/health", tags=["Health"], summary="Check that this address is the voice server")
    def health() -> dict:
        return {
            "status": "error" if store.worker_error else "ok",
            "version": __version__,
            "backend": backend.name,
            "device": backend.device,
            "models_loaded": backend.loaded(),
            "running_job": store.running_id,
            "queued_jobs": store.queued(),
            "docs": "/docs",
            "openapi": "/openapi.json",
            "error": store.worker_error,
        }

    @app.post(
        "/v1/jobs",
        status_code=202,
        tags=["Jobs"],
        summary="Submit a design, lock, or speak job",
        dependencies=auth,
    )
    def submit_job(spec: JobSpec = Body(openapi_examples=EXAMPLES)) -> Job:
        try:
            return _with_urls(store.submit(spec))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/v1/jobs", tags=["Jobs"], summary="List jobs, newest first", dependencies=auth)
    def list_jobs(
        status: str | None = None,
        type: str | None = None,
        limit: int = Query(50, ge=1, le=500),
    ) -> list[Job]:
        return [_with_urls(job) for job in store.list(status, type, limit)]

    @app.get("/v1/jobs/{job_id}", tags=["Jobs"], summary="Read a job, including download URLs", dependencies=auth)
    def get_job(job_id: str) -> Job:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, f"job {job_id} not found")
        return _with_urls(job)

    @app.delete("/v1/jobs/{job_id}", tags=["Jobs"], summary="Cancel a job that is still queued", dependencies=auth)
    def cancel_job(job_id: str) -> Job:
        try:
            return _with_urls(store.cancel(job_id))
        except LookupError as exc:
            raise HTTPException(404, f"job {job_id} not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.delete("/v1/jobs/{job_id}/record", tags=["Jobs"], summary="Delete a job and its audio", dependencies=auth, status_code=204)
    def delete_job(job_id: str) -> None:
        try:
            store.delete(job_id)
        except LookupError as exc:
            raise HTTPException(404, f"job {job_id} not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get(
        "/v1/jobs/{job_id}/files/{name}",
        tags=["Jobs"],
        summary="Download a job WAV",
        dependencies=auth,
        responses=WAV,
    )
    def download_job_file(job_id: str, name: str) -> Response:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, f"job {job_id} not found")
        wav = store.wav(job_id, name)
        if wav is None:
            if job.status in {"queued", "running"}:
                done = f"{job.progress.completed} of {job.progress.total}" if job.progress.total else job.status
                raise HTTPException(409, f"job is {job.status} ({done}). {job.progress.detail} Poll the job, then download a file that is listed on it.")
            raise HTTPException(404, "file not found")
        return _attachment(wav, "audio/wav", name)

    def accept(spec: JobSpec) -> Job:
        try:
            return _with_urls(store.submit(spec))
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except FileExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def typed(job_id: str, kind: str) -> Job:
        job = store.get(job_id)
        if job is None or job.type != kind:
            raise HTTPException(404, f"{kind} {job_id} not found")
        return _with_urls(job)

    @app.post("/v1/designs", status_code=202, tags=["Voice design"], summary="Design candidate voices", dependencies=auth)
    def create_design(body: DesignRequest) -> Job:
        return accept(body.spec())

    @app.get("/v1/designs", tags=["Voice design"], summary="List voice designs", dependencies=auth)
    def list_designs(limit: int = Query(50, ge=1, le=500)) -> list[Job]:
        return [_with_urls(job) for job in store.list(type_="design", limit=limit)]

    @app.get("/v1/designs/{design_id}", tags=["Voice design"], summary="Read a design and its candidates", dependencies=auth)
    def get_design(design_id: str) -> Job:
        return typed(design_id, "design")

    @app.get(
        "/v1/designs/{design_id}/files/{name}",
        tags=["Voice design"],
        summary="Download a candidate WAV",
        dependencies=auth,
        responses=WAV,
    )
    def download_candidate(design_id: str, name: str) -> Response:
        typed(design_id, "design")
        return download_job_file(design_id, name)

    @app.post("/v1/voices", status_code=202, tags=["Voices"], summary="Lock a candidate as a voice", dependencies=auth)
    def lock_voice(body: LockRequest) -> Job:
        return accept(body.spec())

    @app.get("/v1/voices", tags=["Voices"], summary="List locked voices", dependencies=auth)
    def list_voices(include_archived: bool = False) -> list[dict]:
        return library.list(include_archived)

    @app.get("/v1/voices/{voice_id}", tags=["Voices"], summary="Read one locked voice", dependencies=auth)
    def get_voice(voice_id: str) -> dict:
        voice = library.get(voice_id)
        if voice is None:
            raise HTTPException(404, f"voice {voice_id} not found")
        return voice

    @app.delete("/v1/voices/{voice_id}", tags=["Voices"], summary="Delete a locked voice", dependencies=auth, status_code=204)
    def delete_voice(voice_id: str) -> None:
        try:
            library.delete(voice_id)
        except LookupError as exc:
            raise HTTPException(404, f"voice {voice_id} not found") from exc
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get(
        "/v1/voices/{voice_id}/files/{name}",
        tags=["Voices"],
        summary="Download a voice file",
        description="master.wav is audio. preview.txt, instruct.txt, and voice.json are text.",
        dependencies=auth,
        responses={
            200: {
                "content": {
                    "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                    "text/plain": {"schema": {"type": "string"}},
                    "application/json": {"schema": {"type": "object"}},
                },
                "description": "master.wav, preview.txt, instruct.txt, or voice.json.",
            }
        },
    )
    def download_voice_file(voice_id: str, name: str) -> Response:
        found = library.file(voice_id, name)
        if found is None:
            raise HTTPException(404, "file not found")
        content, media = found
        return _attachment(content, media, name)

    @app.post("/v1/renders", status_code=202, tags=["Speech"], summary="Render a long script in one voice", dependencies=auth)
    def create_render(body: RenderRequest) -> Job:
        return accept(body.spec())

    @app.post("/v1/speech", status_code=202, tags=["Speech"], summary="Speak text with a locked voice", dependencies=auth)
    def create_speech(body: SpeakRequest) -> Job:
        return accept(body.spec())

    @app.get("/v1/speech", tags=["Speech"], summary="List speech jobs", dependencies=auth)
    def list_speech(limit: int = Query(50, ge=1, le=500)) -> list[Job]:
        return [_with_urls(job) for job in store.list(type_="speak", limit=limit)]

    @app.get("/v1/speech/{speech_id}", tags=["Speech"], summary="Read a speech job", dependencies=auth)
    def get_speech(speech_id: str) -> Job:
        return typed(speech_id, "speak")

    @app.get(
        "/v1/speech/{speech_id}/audio",
        tags=["Speech"],
        summary="Download the spoken WAV",
        dependencies=auth,
        responses=WAV,
    )
    def download_speech(speech_id: str) -> Response:
        job = typed(speech_id, "speak")
        if job.status != "succeeded":
            raise HTTPException(409, f"speech is {job.status}")
        return download_job_file(speech_id, "audio.wav")

    def candidate_wav(job_id: str, candidate: int) -> tuple[bytes, int]:
        name = f"candidate-{candidate:02d}.wav"
        wav = store.wav(job_id, name)
        job = store.get(job_id)
        if wav is None or job is None:
            raise HTTPException(404, "candidate not found")
        seed = next((output.seed for output in job.outputs if output.file == name and output.seed is not None), 0)
        return wav, seed

    def template_call(func, *args):
        try:
            return func(*args)
        except LookupError as exc:
            raise HTTPException(404, "template not found") from exc
        except PermissionError as exc:
            raise HTTPException(409, "built-in templates stay as shipped") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/v1/templates", tags=["Templates"], summary="List built-in and saved templates", dependencies=auth)
    def list_templates() -> list[dict]:
        return storage.templates.list()

    @app.post("/v1/templates", status_code=201, tags=["Templates"], summary="Save a user template", dependencies=auth)
    def create_template(body: TemplateWrite) -> dict:
        if (body.from_job is None) != (body.candidate is None):
            raise HTTPException(400, "from_job and candidate are sent together")
        sample = candidate_wav(body.from_job, body.candidate) if body.from_job and body.candidate else None
        try:
            return storage.templates.insert_user(body.fields(), sample)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/v1/templates/{template_id}", tags=["Templates"], summary="Read one template", dependencies=auth)
    def get_template(template_id: str) -> dict:
        row = storage.templates.get(template_id)
        if row is None:
            raise HTTPException(404, "template not found")
        return row

    @app.get(
        "/v1/templates/{template_id}/sample",
        tags=["Templates"],
        summary="Play a template's sample clip",
        dependencies=auth,
        responses=WAV,
    )
    def download_template_sample(template_id: str) -> Response:
        if storage.templates.get(template_id) is None:
            raise HTTPException(404, "template not found")
        wav = storage.templates.wav(template_id)
        if wav is None:
            raise HTTPException(404, "sample not found")
        return _attachment(wav, "audio/wav", f"{template_id}.wav")

    @app.patch("/v1/templates/{template_id}", tags=["Templates"], summary="Edit a user template", dependencies=auth)
    def update_template(template_id: str, body: TemplatePatch) -> dict:
        return template_call(storage.templates.update_user, template_id, body.fields())

    @app.put(
        "/v1/templates/{template_id}/sample",
        tags=["Templates"],
        summary="Replace a user template's sample from a design take",
        dependencies=auth,
    )
    def replace_template_sample(template_id: str, body: TemplateSample) -> dict:
        row = storage.templates.get(template_id)
        if row is None:
            raise HTTPException(404, "template not found")
        if row["origin"] == "builtin":
            raise HTTPException(409, "built-in templates stay as shipped")
        wav, seed = candidate_wav(body.from_job, body.candidate)
        return storage.templates.set_sample(template_id, wav, seed)

    @app.delete("/v1/templates/{template_id}", tags=["Templates"], summary="Delete a user template", dependencies=auth, status_code=204)
    def delete_template(template_id: str) -> None:
        template_call(storage.templates.delete_user, template_id)

    @app.post("/v1/templates/{template_id}/duplicate", status_code=201, tags=["Templates"], summary="Copy a template", dependencies=auth)
    def duplicate_template(template_id: str, body: TemplateDuplicate | None = None) -> dict:
        return template_call(storage.templates.duplicate, template_id, body.name if body else None)

    @app.get("/v1/favorites", tags=["Profile"], summary="List profile voices", dependencies=auth)
    def list_favorites() -> list[dict]:
        return storage.favorites.list()

    @app.put("/v1/favorites/{voice_id}", tags=["Profile"], summary="Keep a voice on the profile", dependencies=auth)
    def put_favorite(voice_id: str, body: FavoriteWrite | None = None) -> dict:
        try:
            return storage.favorites.put(voice_id, body.note if body else None)
        except LookupError as exc:
            raise HTTPException(404, f"voice {voice_id} not found") from exc

    @app.delete("/v1/favorites/{voice_id}", tags=["Profile"], summary="Remove a voice from the profile", dependencies=auth, status_code=204)
    def delete_favorite(voice_id: str) -> None:
        try:
            storage.favorites.delete(voice_id)
        except LookupError as exc:
            raise HTTPException(404, f"voice {voice_id} not found") from exc

    register_library(
        app,
        storage=storage,
        library=library,
        store=store,
        auth=auth,
        accept=accept,
        with_urls=_with_urls,
        attachment=_attachment,
        backend=backend,
    )
    return app
