"""Playgrounds, voice versions, styles, narrations, downloads.

Mounted by create_app. Drafts are PATCHable; a queued job freezes its snapshot.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response

from voice_engine.schemas import (
    CopyRequest,
    DesignSpec,
    GenParams,
    Job,
    NarrationPatch,
    NarrationWrite,
    PlaygroundPatch,
    PlaygroundRun,
    PlaygroundWrite,
    RenderSpec,
    StylePatch,
    StyleWrite,
    VersionPatch,
    VoiceCopy,
    VoicePatch,
)

TAGS = [
    {"name": "Playgrounds", "description": "Saved design workspaces. Each run is one design job with its frozen settings."},
    {"name": "Versions", "description": "Version 1 is the kept take. A copy of a voice starts again at version 1."},
    {"name": "Styles", "description": "Delivery presets for narrations. Built-ins are frozen; copy one to tune it."},
    {"name": "Narrations", "description": "Long scripts rendered with one voice version and one style. Drafts until rendered."},
    {"name": "Downloads", "description": "Everything that produced a WAV, newest first."},
]

WAV = {200: {"content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}, "description": "WAV file."}}


def _call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def register(app: FastAPI, *, storage, library, store, auth, accept, with_urls, attachment, backend) -> None:
    # ----- playgrounds -------------------------------------------------------

    @app.get("/v1/playgrounds", tags=["Playgrounds"], summary="List playgrounds", dependencies=auth)
    def list_playgrounds(limit: int = Query(100, ge=1, le=500)) -> list[dict]:
        return storage.playgrounds.list(limit)

    @app.post("/v1/playgrounds", status_code=201, tags=["Playgrounds"], summary="Create a playground draft", dependencies=auth)
    def create_playground(body: PlaygroundWrite) -> dict:
        if body.template_id and storage.templates.get(body.template_id) is None:
            raise HTTPException(404, f"template {body.template_id} not found")
        return storage.playgrounds.create(body.name, body.config, body.notes, body.template_id)

    @app.get("/v1/playgrounds/{playground_id}", tags=["Playgrounds"], summary="Read a playground with its runs", dependencies=auth)
    def get_playground(playground_id: str) -> dict:
        found = storage.playgrounds.get(playground_id)
        if found is None:
            raise HTTPException(404, f"playground {playground_id} not found")
        for run in found["runs"]:
            job = store.get(run["job_id"])
            run["job"] = with_urls(job).model_dump() if job else None
        found["voices"] = [v for v in library.list(include_archived=True) if v.get("playground_id") == playground_id]
        return found

    @app.patch("/v1/playgrounds/{playground_id}", tags=["Playgrounds"], summary="Edit the playground draft", dependencies=auth)
    def update_playground(playground_id: str, body: PlaygroundPatch) -> dict:
        return _call(storage.playgrounds.update, playground_id, **body.model_dump(exclude_unset=True))

    @app.post("/v1/playgrounds/{playground_id}/copy", status_code=201, tags=["Playgrounds"], summary="Copy a playground", dependencies=auth)
    def copy_playground(playground_id: str, body: CopyRequest | None = None) -> dict:
        return _call(storage.playgrounds.copy, playground_id, body.name if body else None)

    @app.delete("/v1/playgrounds/{playground_id}", status_code=204, tags=["Playgrounds"], summary="Delete a playground; kept voices stay", dependencies=auth)
    def delete_playground(playground_id: str) -> None:
        _call(storage.playgrounds.delete, playground_id)

    @app.post("/v1/playgrounds/{playground_id}/runs", status_code=202, tags=["Playgrounds"], summary="Run the playground: queue a design job", dependencies=auth)
    def run_playground(playground_id: str, body: PlaygroundRun | None = None) -> Job:
        found = storage.playgrounds.get(playground_id)
        if found is None:
            raise HTTPException(404, f"playground {playground_id} not found")
        body = body or PlaygroundRun()
        overrides = body.model_dump(exclude_unset=True, exclude={"save"})
        if "params" in overrides and body.params is not None:
            overrides["params"] = body.params.given()
        config = {**found["config"], **{k: v for k, v in overrides.items() if v is not None}}
        if body.save and overrides:
            storage.playgrounds.update(playground_id, config=config)
        try:
            spec = DesignSpec(
                type="design",
                instruct=config.get("instruct", ""),
                text=config.get("text", ""),
                language=config.get("language", "English"),
                candidates=int(config.get("candidates", 4)),
                seed_start=int(config.get("seed_start", 1000)),
                params=GenParams.model_validate(config.get("params") or {}),
                playground_id=playground_id,
            )
        except Exception as exc:  # pydantic
            raise HTTPException(400, f"playground config is incomplete: {exc}") from exc
        return accept(spec)

    # ----- voices: patch, copy, versions -----------------------------------

    @app.patch("/v1/voices/{voice_id}", tags=["Voices"], summary="Rename, note, favorite, archive, or pick the current version", dependencies=auth)
    def update_voice(voice_id: str, body: VoicePatch) -> dict:
        return _call(library.update, voice_id, **body.model_dump(exclude_unset=True))

    @app.post("/v1/voices/{voice_id}/copy", status_code=201, tags=["Voices"], summary="Copy a voice (one version becomes version 1)", dependencies=auth)
    def copy_voice(voice_id: str, body: VoiceCopy) -> dict:
        source = library.get(voice_id)
        if source is None:
            raise HTTPException(404, f"voice {voice_id} not found")
        version = _call(library.resolve_version, voice_id, body.version_id)
        ref_text = version["ref_text"]
        return _call(
            library.copy, voice_id, body.voice_id, body.name, body.version_id,
            lambda master, folder: backend.lock(master, ref_text, folder),
        )

    @app.get("/v1/voices/{voice_id}/versions", tags=["Versions"], summary="List versions of a voice", dependencies=auth)
    def list_versions(voice_id: str) -> list[dict]:
        if not library.exists(voice_id):
            raise HTTPException(404, f"voice {voice_id} not found")
        return storage.versions.list(voice_id)

    @app.get("/v1/voices/{voice_id}/versions/{version_id}", tags=["Versions"], summary="Read one version", dependencies=auth)
    def get_version(voice_id: str, version_id: str) -> dict:
        version = storage.versions.get(version_id)
        if version is None or version["voice_id"] != voice_id:
            raise HTTPException(404, f"version {version_id} not found")
        return version

    @app.patch("/v1/voices/{voice_id}/versions/{version_id}", tags=["Versions"], summary="Relabel a version", dependencies=auth)
    def relabel_version(voice_id: str, version_id: str, body: VersionPatch) -> dict:
        get_version(voice_id, version_id)
        return _call(storage.versions.relabel, version_id, body.label)

    @app.get("/v1/voices/{voice_id}/versions/{version_id}/master.wav", tags=["Versions"], summary="Download a version's master WAV", dependencies=auth, responses=WAV)
    def download_version(voice_id: str, version_id: str) -> Response:
        wav = library.version_wav(voice_id, version_id)
        if wav is None:
            raise HTTPException(404, f"version {version_id} not found")
        return attachment(wav, "audio/wav", f"{version_id.replace('@', '-v')}.wav")

    # ----- styles ------------------------------------------------------------

    @app.get("/v1/styles", tags=["Styles"], summary="List styles", dependencies=auth)
    def list_styles() -> list[dict]:
        return storage.styles.list()

    @app.post("/v1/styles", status_code=201, tags=["Styles"], summary="Create a style, usually by copying a built-in", dependencies=auth)
    def create_style(body: StyleWrite) -> dict:
        fields = body.model_dump(exclude_unset=True, exclude={"id", "copy_of"})
        return _call(storage.styles.create, body.id, body.copy_of, **fields)

    @app.get("/v1/styles/{style_id}", tags=["Styles"], summary="Read one style", dependencies=auth)
    def get_style_row(style_id: str) -> dict:
        found = storage.styles.get(style_id)
        if found is None:
            raise HTTPException(404, f"style {style_id} not found")
        return found

    @app.patch("/v1/styles/{style_id}", tags=["Styles"], summary="Edit a user style", dependencies=auth)
    def update_style(style_id: str, body: StylePatch) -> dict:
        return _call(storage.styles.update, style_id, **body.model_dump(exclude_unset=True))

    @app.delete("/v1/styles/{style_id}", status_code=204, tags=["Styles"], summary="Delete a user style nobody uses", dependencies=auth)
    def delete_style(style_id: str) -> None:
        _call(storage.styles.delete, style_id)

    # ----- narrations --------------------------------------------------------

    def _narration(narration_id: str) -> dict:
        found = storage.narrations.get(narration_id)
        if found is None:
            raise HTTPException(404, f"narration {narration_id} not found")
        if found["job_id"]:
            job = store.get(found["job_id"])
            found["job"] = with_urls(job).model_dump() if job else None
            if job and job.status == "succeeded":
                found["audio_url"] = f"/v1/narrations/{narration_id}/audio.wav"
        return found

    @app.get("/v1/narrations", tags=["Narrations"], summary="List narrations", dependencies=auth)
    def list_narrations(voice_id: str | None = None, status: str | None = None, limit: int = Query(100, ge=1, le=500)) -> list[dict]:
        return storage.narrations.list(voice_id, status, limit)

    @app.post("/v1/narrations", status_code=201, tags=["Narrations"], summary="Create a narration draft", dependencies=auth)
    def create_narration(body: NarrationWrite) -> dict:
        version = _call(library.resolve_version, body.voice_id, body.version_id)
        if storage.styles.get(body.style_id) is None:
            raise HTTPException(404, f"style {body.style_id} not found")
        data = body.model_dump()
        data["version_id"] = version["id"]
        data["params"] = body.params.given()
        return storage.narrations.create(**data)

    @app.get("/v1/narrations/{narration_id}", tags=["Narrations"], summary="Read a narration, its job, and its audio URL", dependencies=auth)
    def get_narration(narration_id: str) -> dict:
        return _narration(narration_id)

    @app.patch("/v1/narrations/{narration_id}", tags=["Narrations"], summary="Edit a draft (title and notes stay editable after render)", dependencies=auth)
    def update_narration(narration_id: str, body: NarrationPatch) -> dict:
        fields = body.model_dump(exclude_unset=True)
        if "params" in fields and body.params is not None:
            fields["params"] = body.params.given()
        current = storage.narrations.get(narration_id)
        if current is None:
            raise HTTPException(404, f"narration {narration_id} not found")
        if "voice_id" in fields or "version_id" in fields:
            voice_id = fields.get("voice_id") or current["voice_id"]
            version = _call(library.resolve_version, voice_id, fields.get("version_id"))
            fields["voice_id"], fields["version_id"] = voice_id, version["id"]
        if "style_id" in fields and storage.styles.get(fields["style_id"]) is None:
            raise HTTPException(404, f"style {fields['style_id']} not found")
        _call(storage.narrations.update, narration_id, **fields)
        return _narration(narration_id)

    @app.post("/v1/narrations/{narration_id}/render", status_code=202, tags=["Narrations"], summary="Render the narration: queue the job and freeze the draft", dependencies=auth)
    def render_narration(narration_id: str) -> Job:
        found = storage.narrations.get(narration_id)
        if found is None:
            raise HTTPException(404, f"narration {narration_id} not found")
        if found["status"] == "rendering" and found["job_id"]:
            job = store.get(found["job_id"])
            if job and job.status in {"queued", "running"}:
                raise HTTPException(409, f"narration is already rendering as job {job.id}. Poll it; do not submit again.")
        if found["status"] == "rendered":
            raise HTTPException(409, "narration is rendered. Copy it to render a new version.")
        spec = RenderSpec(
            type="render",
            voice_id=found["voice_id"],
            version_id=found["version_id"],
            text=found["script"],
            language=found["language"],
            style=found["style_id"],
            seed=found["seed"],
            params=GenParams.model_validate(found["params"] or {}),
            narration_id=narration_id,
        )
        return accept(spec)

    @app.post("/v1/narrations/{narration_id}/copy", status_code=201, tags=["Narrations"], summary="Copy a narration as a new draft", dependencies=auth)
    def copy_narration(narration_id: str, body: CopyRequest | None = None) -> dict:
        return _call(storage.narrations.copy, narration_id, body.name if body else None)

    @app.delete("/v1/narrations/{narration_id}", status_code=204, tags=["Narrations"], summary="Delete a narration and its rendered audio", dependencies=auth)
    def delete_narration(narration_id: str) -> None:
        job_id = _call(storage.narrations.delete, narration_id)
        if job_id:
            try:
                store.delete(job_id)
            except (LookupError, ValueError):
                pass

    @app.get("/v1/narrations/{narration_id}/audio.wav", tags=["Narrations"], summary="Download the rendered WAV", dependencies=auth, responses=WAV)
    def download_narration(narration_id: str) -> Response:
        found = storage.narrations.get(narration_id)
        if found is None:
            raise HTTPException(404, f"narration {narration_id} not found")
        if not found["job_id"]:
            raise HTTPException(409, "narration is a draft. POST /render first.")
        job = store.get(found["job_id"])
        if job is None:
            raise HTTPException(404, "render job is gone")
        if job.status != "succeeded":
            raise HTTPException(409, f"render is {job.status}: {job.progress.detail}")
        wav = store.wav(job.id, "audio.wav")
        if wav is None:
            raise HTTPException(404, "audio not found")
        return attachment(wav, "audio/wav", f"{found['title'][:60].replace(' ', '-') or narration_id}.wav")

    # ----- downloads ---------------------------------------------------------

    @app.get("/v1/downloads", tags=["Downloads"], summary="Everything downloadable, newest first", dependencies=auth)
    def list_downloads(limit: int = Query(100, ge=1, le=500)) -> list[dict]:
        items: list[dict] = []
        for narration in storage.narrations.list(status="rendered", limit=limit):
            job = store.get(narration["job_id"]) if narration["job_id"] else None
            if job and job.status == "succeeded":
                final = next((o for o in job.outputs if o.file == "audio.wav"), None)
                items.append({
                    "kind": "narration", "id": narration["id"], "title": narration["title"], "voice_id": narration["voice_id"],
                    "version_id": narration["version_id"], "style_id": narration["style_id"], "created_at": job.finished_at or narration["updated_at"],
                    "duration_s": final.checks.duration_s if final else None, "url": f"/v1/narrations/{narration['id']}/audio.wav",
                })
        for voice in library.list(include_archived=True):
            for version in storage.versions.list(voice["voice_id"]):
                items.append({
                    "kind": "voice", "id": version["id"], "title": f"{voice['name']} · {version['label']}", "voice_id": voice["voice_id"],
                    "version_id": version["id"], "style_id": None, "created_at": version["created_at"], "duration_s": version.get("duration_s"),
                    "url": f"/v1/voices/{voice['voice_id']}/versions/{version['id']}/master.wav",
                })
        for job in store.list(type_="speak", limit=limit):
            if job.status == "succeeded":
                final = next((o for o in job.outputs if o.file == "audio.wav"), None)
                items.append({
                    "kind": "speech", "id": job.id, "title": (job.spec.get("text") or "")[:60], "voice_id": job.voice_id, "version_id": job.version_id,
                    "style_id": None, "created_at": job.finished_at or job.created_at, "duration_s": final.checks.duration_s if final else None,
                    "url": f"/v1/jobs/{job.id}/files/audio.wav",
                })
        items.sort(key=lambda item: item["created_at"] or "", reverse=True)
        return items[:limit]
