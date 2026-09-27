from __future__ import annotations

from pathlib import Path

import numpy as np

from voice_engine.audio import join
from voice_engine.backends.base import SAMPLING, Backend

DESIGN_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit"
BASE_MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"


class MlxBackend(Backend):
    """Apple Silicon. Clones from master.wav + preview text on every speak call."""

    name = "mlx"
    device = "metal"
    supports = SAMPLING | {"speed"}

    def __init__(self) -> None:
        self._models: dict[str, object] = {}

    def _model(self, repo: str):
        if repo not in self._models:
            from mlx_audio.tts.utils import load_model

            self._models[repo] = load_model(repo)
        return self._models[repo]

    def load(self) -> None:
        self._model(DESIGN_MODEL)
        self._model(BASE_MODEL)

    def loaded(self) -> list[str]:
        return list(self._models)

    @staticmethod
    def _collect(results) -> tuple[np.ndarray, int]:
        chunks, sample_rate = [], 24000
        for result in results:
            chunks.append(np.asarray(result.audio, dtype="float32"))
            sample_rate = int(getattr(result, "sample_rate", sample_rate))
        if not chunks:
            raise RuntimeError("model returned no audio")
        return join(chunks, sample_rate), sample_rate

    def design(self, text, instruct, language, seed, params):
        import mlx.core as mx

        mx.random.seed(seed)
        results = self._model(DESIGN_MODEL).generate_voice_design(
            text=text, instruct=instruct, language=language.lower(), **params
        )
        return self._collect(results)

    def lock(self, master: Path, ref_text: str, voice_dir: Path) -> None:
        return None

    def speak(self, voice_dir, ref_text, text, language, seed, params):
        import mlx.core as mx

        mx.random.seed(seed)
        results = self._model(BASE_MODEL).generate(
            text=text,
            lang_code=language.lower(),
            ref_audio=str(voice_dir / "master.wav"),
            ref_text=ref_text,
            **params,
        )
        return self._collect(results)
