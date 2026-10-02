from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

VOICE_ID = r"^[a-z0-9][a-z0-9-]{1,62}$"
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class GenParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float | None = Field(None, gt=0, le=2)
    top_p: float | None = Field(None, gt=0, le=1)
    top_k: int | None = Field(None, ge=1, le=1000)
    repetition_penalty: float | None = Field(None, ge=1, le=2)
    max_tokens: int | None = Field(None, ge=64, le=8192)
    speed: float | None = Field(None, ge=0.5, le=2)

    def given(self) -> dict:
        return self.model_dump(exclude_none=True)


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DesignSpec(_Spec):
    type: Literal["design"]
    instruct: str = Field(min_length=1, max_length=2000)
    text: str = Field(min_length=1, max_length=1000)
    language: str = "English"
    candidates: int = Field(4, ge=1, le=8)
    seed_start: int = Field(1000, ge=0)
    params: GenParams = GenParams()
    playground_id: str | None = None


class LockSpec(_Spec):
    type: Literal["lock"]
    voice_id: str = Field(pattern=VOICE_ID)
    from_job: str
    candidate: int = Field(ge=1)
    name: str | None = None
    notes: str | None = None


class SpeakSpec(_Spec):
    type: Literal["speak"]
    voice_id: str = Field(pattern=VOICE_ID)
    version_id: str | None = None
    text: str = Field(min_length=1, max_length=5000)
    language: str = "English"
    seed: int = Field(1, ge=0)
    params: GenParams = GenParams()


class DesignRequest(_Spec):
    """Create candidate voices from a description. No job type field."""

    instruct: str = Field(min_length=1, max_length=2000)
    text: str = Field(min_length=1, max_length=1000)
    language: str = "English"
    candidates: int = Field(4, ge=1, le=8)
    seed_start: int = Field(1000, ge=0)
    params: GenParams = GenParams()
    playground_id: str | None = Field(None, description="Record this run under an existing playground.")

    def spec(self) -> DesignSpec:
        return DesignSpec(type="design", **self.model_dump())


class LockRequest(_Spec):
    """Save one design candidate as a permanent voice."""

    voice_id: str = Field(pattern=VOICE_ID)
    from_design: str
    candidate: int = Field(ge=1)
    name: str | None = None
    notes: str | None = None

    def spec(self) -> LockSpec:
        data = self.model_dump()
        data["from_job"] = data.pop("from_design")
        return LockSpec(type="lock", **data)


class RenderSpec(_Spec):
    """Speak a long script in short beats, then stitch one WAV."""

    type: Literal["render"]
    voice_id: str = Field(pattern=VOICE_ID)
    version_id: str | None = None
    text: str = Field(min_length=1, max_length=20000)
    language: str = "English"
    style: str = Field("narration", pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    seed: int = Field(1, ge=0)
    params: GenParams = GenParams()
    narration_id: str | None = None


class SpeakRequest(_Spec):
    """Synthesize text with a locked voice."""

    voice_id: str = Field(pattern=VOICE_ID)
    version_id: str | None = Field(None, description="A voice version id such as narrator@2. Default: the current version.")
    text: str = Field(min_length=1, max_length=5000)
    language: str = "English"
    seed: int = Field(1, ge=0)
    params: GenParams = GenParams()

    def spec(self) -> SpeakSpec:
        return SpeakSpec(type="speak", **self.model_dump())


class RenderRequest(_Spec):
    """Long script. Same locked voice, one style, one stitched WAV."""

    voice_id: str = Field(pattern=VOICE_ID)
    version_id: str | None = Field(None, description="A voice version id such as narrator@2. Default: the current version.")
    text: str = Field(min_length=1, max_length=20000)
    language: str = "English"
    style: str = Field("narration", pattern=r"^[a-z0-9][a-z0-9-]{0,62}$", description="A style id from GET /v1/styles.")
    seed: int = Field(1, ge=0)
    params: GenParams = GenParams()

    def spec(self) -> RenderSpec:
        return RenderSpec(type="render", **self.model_dump())


JobSpec = Annotated[Union[DesignSpec, LockSpec, SpeakSpec, RenderSpec], Field(discriminator="type")]


class Checks(BaseModel):
    duration_s: float
    peak: float
    rms_dbfs: float
    clipped_ratio: float
    lead_silence_s: float
    tail_silence_s: float
    chars_per_s: float | None = None
    ok: bool
    warnings: list[str] = []


class Output(BaseModel):
    file: str
    url: str | None = Field(None, description="GET this path to download the WAV.")
    seed: int | None = None
    sample_rate: int
    checks: Checks


class Progress(BaseModel):
    """Where a running job is. Agents poll this instead of guessing."""

    phase: Literal["queued", "design", "lock", "speak", "render", "stitch", "done"] = "queued"
    detail: str = "Waiting for the worker."
    completed: int = 0
    total: int = 0


class Job(BaseModel):
    id: str
    type: Literal["design", "lock", "speak", "render"]
    status: JobStatus
    progress: Progress = Progress()
    spec: dict
    backend: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    applied: list[str] = []
    deferred: list[str] = []
    outputs: list[Output] = []
    voice_id: str | None = None
    version_id: str | None = Field(None, description="The voice version this job used.")
    error: str | None = None


class TemplateWrite(_Spec):
    """Save the current Create form as a user template."""

    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(None, max_length=500)
    instruct: str = Field(min_length=1, max_length=2000)
    text: str = Field(min_length=1, max_length=1000)
    language: str = "English"
    candidates: int = Field(4, ge=1, le=8)
    seed_start: int = Field(1000, ge=0)
    params: GenParams = GenParams()
    from_job: str | None = None
    candidate: int | None = Field(None, ge=1)

    def fields(self) -> dict:
        data = self.model_dump()
        for key in ("name", "role", "instruct", "text"):
            data[key] = data[key].strip()
            if not data[key]:
                raise ValueError(f"{key} is empty")
        data["params"] = self.params.given()
        data.pop("from_job")
        data.pop("candidate")
        return data


class TemplatePatch(_Spec):
    name: str | None = Field(None, min_length=1, max_length=80)
    role: str | None = Field(None, min_length=1, max_length=120)
    notes: str | None = Field(None, max_length=500)
    instruct: str | None = Field(None, min_length=1, max_length=2000)
    text: str | None = Field(None, min_length=1, max_length=1000)
    language: str | None = None
    candidates: int | None = Field(None, ge=1, le=8)
    seed_start: int | None = Field(None, ge=0)
    params: GenParams | None = None

    def fields(self) -> dict:
        sent = self.model_dump(exclude_unset=True)
        for key in ("name", "role", "instruct", "text"):
            if key in sent and sent[key] is not None:
                sent[key] = sent[key].strip()
                if not sent[key]:
                    raise ValueError(f"{key} is empty")
        if "params" in sent and sent["params"] is not None:
            sent["params"] = self.params.given() if self.params else {}
        return sent


class TemplateDuplicate(_Spec):
    name: str | None = Field(None, max_length=80)


class TemplateSample(_Spec):
    from_job: str
    candidate: int = Field(ge=1)


class FavoriteWrite(_Spec):
    note: str | None = Field(None, max_length=500)


class PlaygroundWrite(_Spec):
    """A saved design workspace. config holds the form the way the dashboard shows it."""

    name: str = Field(min_length=1, max_length=80)
    notes: str | None = Field(None, max_length=1000)
    template_id: str | None = None
    config: dict = Field(default_factory=dict, description="instruct, text, language, candidates, seed_start, params. Unknown keys are kept.")


class PlaygroundPatch(_Spec):
    name: str | None = Field(None, min_length=1, max_length=80)
    notes: str | None = Field(None, max_length=1000)
    template_id: str | None = None
    config: dict | None = None


class CopyRequest(_Spec):
    name: str | None = Field(None, max_length=80)


class PlaygroundRun(_Spec):
    """Queue a design job from this playground. Fields override the saved config for this run only."""

    instruct: str | None = Field(None, min_length=1, max_length=2000)
    text: str | None = Field(None, min_length=1, max_length=1000)
    language: str | None = None
    candidates: int | None = Field(None, ge=1, le=8)
    seed_start: int | None = Field(None, ge=0)
    params: GenParams | None = None
    save: bool = Field(True, description="Also write the overrides back to the playground draft.")


class VoicePatch(_Spec):
    name: str | None = Field(None, min_length=1, max_length=80)
    notes: str | None = Field(None, max_length=1000)
    favorite: bool | None = None
    archived: bool | None = None
    current_version_id: str | None = None


class VoiceCopy(_Spec):
    voice_id: str = Field(pattern=VOICE_ID)
    name: str | None = Field(None, max_length=80)
    version_id: str | None = Field(None, description="Which version becomes version 1 of the copy. Default: current.")


class VersionPatch(_Spec):
    label: str = Field(min_length=1, max_length=80)


class StyleWrite(_Spec):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    name: str | None = Field(None, max_length=80)
    copy_of: str | None = Field(None, description="Start from this style's values.")
    temperature: float | None = Field(None, gt=0, le=2)
    pause_comma_s: float | None = Field(None, ge=0, le=3)
    pause_period_s: float | None = Field(None, ge=0, le=3)
    pause_paragraph_s: float | None = Field(None, ge=0, le=5)
    loudness_dbfs: float | None = Field(None, ge=-40, le=0)
    crossfade_s: float | None = Field(None, ge=0, le=0.5)
    emotion: str | None = None


class StylePatch(_Spec):
    name: str | None = Field(None, max_length=80)
    temperature: float | None = Field(None, gt=0, le=2)
    pause_comma_s: float | None = Field(None, ge=0, le=3)
    pause_period_s: float | None = Field(None, ge=0, le=3)
    pause_paragraph_s: float | None = Field(None, ge=0, le=5)
    loudness_dbfs: float | None = Field(None, ge=-40, le=0)
    crossfade_s: float | None = Field(None, ge=0, le=0.5)
    emotion: str | None = None


class NarrationWrite(_Spec):
    """A narration draft. Render it when the script is ready."""

    title: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(None, max_length=1000)
    voice_id: str = Field(pattern=VOICE_ID)
    version_id: str | None = Field(None, description="Default: the voice's current version, frozen into the draft.")
    style_id: str = "narration"
    script: str = Field(min_length=1, max_length=20000)
    language: str = "English"
    params: GenParams = GenParams()
    seed: int = Field(1, ge=0)


class NarrationPatch(_Spec):
    title: str | None = Field(None, min_length=1, max_length=120)
    notes: str | None = Field(None, max_length=1000)
    voice_id: str | None = Field(None, pattern=VOICE_ID)
    version_id: str | None = None
    style_id: str | None = None
    script: str | None = Field(None, min_length=1, max_length=20000)
    language: str | None = None
    params: GenParams | None = None
    seed: int | None = Field(None, ge=0)
