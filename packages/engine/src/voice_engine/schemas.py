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


class SpeakRequest(_Spec):
    """Synthesize text with a locked voice."""

    voice_id: str = Field(pattern=VOICE_ID)
    text: str = Field(min_length=1, max_length=5000)
    language: str = "English"
    seed: int = Field(1, ge=0)
    params: GenParams = GenParams()

    def spec(self) -> SpeakSpec:
        return SpeakSpec(type="speak", **self.model_dump())


JobSpec = Annotated[Union[DesignSpec, LockSpec, SpeakSpec], Field(discriminator="type")]


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


class Job(BaseModel):
    id: str
    type: Literal["design", "lock", "speak"]
    status: JobStatus
    spec: dict
    backend: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    applied: list[str] = []
    deferred: list[str] = []
    outputs: list[Output] = []
    voice_id: str | None = None
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
