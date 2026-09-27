from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from voice_engine.audio import join
from voice_engine.backends.base import Backend

DESIGN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
BASE_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
PROMPT_FILE = "voice_prompt.pt"

log = logging.getLogger(__name__)


class TorchBackend(Backend):
    """Upstream Qwen weights through qwen-tts. Subclasses pick the device."""

    name = "torch"
    device = "cpu"
    device_map = "cpu"
    dtype_name = "float32"

    def __init__(self) -> None:
        self._models: dict[str, object] = {}

    def _model(self, repo: str):
        if repo not in self._models:
            import torch
            from qwen_tts import Qwen3TTSModel

            log.info("loading %s on %s (%s)", repo, self.device_map, self.dtype_name)
            self._models[repo] = Qwen3TTSModel.from_pretrained(
                repo,
                device_map=self.device_map,
                dtype=getattr(torch, self.dtype_name),
                attn_implementation="sdpa",
            )
        return self._models[repo]

    def load(self) -> None:
        self._model(DESIGN_MODEL)
        self._model(BASE_MODEL)

    def loaded(self) -> list[str]:
        return list(self._models)

    @staticmethod
    def _seed(seed: int) -> None:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    @staticmethod
    def _kwargs(params: dict) -> dict:
        kwargs = dict(params)
        if "max_tokens" in kwargs:
            kwargs["max_new_tokens"] = kwargs.pop("max_tokens")
        return kwargs

    def design(self, text, instruct, language, seed, params):
        self._seed(seed)
        wavs, sample_rate = self._model(DESIGN_MODEL).generate_voice_design(
            text=text, language=language, instruct=instruct, **self._kwargs(params)
        )
        return np.asarray(wavs[0], dtype="float32"), int(sample_rate)

    def _prompt(self, voice_dir: Path, ref_text: str):
        import torch

        path = voice_dir / PROMPT_FILE
        if path.is_file():
            return torch.load(path, map_location="cpu", weights_only=False)
        # Voices locked on another backend have no prompt yet; build and cache it.
        self.lock(voice_dir / "master.wav", ref_text, voice_dir)
        return torch.load(path, map_location="cpu", weights_only=False)

    def lock(self, master: Path, ref_text: str, voice_dir: Path) -> None:
        import torch

        prompt = self._model(BASE_MODEL).create_voice_clone_prompt(
            ref_audio=str(master), ref_text=ref_text, x_vector_only_mode=False
        )
        torch.save(prompt, voice_dir / PROMPT_FILE)

    def speak(self, voice_dir, ref_text, text, language, seed, params):
        prompt = self._prompt(voice_dir, ref_text)
        model = self._model(BASE_MODEL)
        self._seed(seed)
        chunks, sample_rate = [], 24000
        for line in [ln for ln in text.splitlines() if ln.strip()]:
            wavs, sample_rate = model.generate_voice_clone(
                text=line,
                language=language,
                voice_clone_prompt=prompt,
                **self._kwargs(params),
            )
            chunks.append(wavs[0])
        return join(chunks, int(sample_rate)), int(sample_rate)


class CudaBackend(TorchBackend):
    """NVIDIA on Linux or Windows."""

    name = "cuda"
    device = "cuda"
    device_map = "cuda:0"
    dtype_name = "bfloat16"


class CpuBackend(TorchBackend):
    """Same models on the CPU. Works anywhere torch runs, several times slower than a GPU.

    float32 is used because most CPUs have no fast bfloat16 path. Each model takes
    about 7 GB of RAM at that width, so both loaded together need about 14 GB.
    """

    name = "cpu"
    device = "cpu"
    device_map = "cpu"
    dtype_name = "float32"
