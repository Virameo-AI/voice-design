from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

SAMPLING = frozenset({"temperature", "top_p", "top_k", "repetition_penalty", "max_tokens"})


class Backend(ABC):
    """Owns the models. Only the worker thread calls these methods."""

    name: str
    device: str
    supports: frozenset[str] = SAMPLING

    def split(self, params: dict, kind: str) -> tuple[dict, list[str], list[str]]:
        """Return (params to pass, applied names, deferred names) for this backend."""
        usable = self.supports if kind == "speak" else self.supports - {"speed"}
        applied = {k: v for k, v in params.items() if k in usable}
        deferred = sorted(k for k in params if k not in usable)
        return applied, sorted(applied), deferred

    def load(self) -> None:
        """Load models up front. Default is lazy loading on first use."""

    def loaded(self) -> list[str]:
        return []

    @abstractmethod
    def design(
        self, text: str, instruct: str, language: str, seed: int, params: dict
    ) -> tuple[np.ndarray, int]: ...

    @abstractmethod
    def lock(self, master: Path, ref_text: str, voice_dir: Path) -> None:
        """Write any backend-specific artifacts next to master.wav."""

    @abstractmethod
    def speak(
        self,
        voice_dir: Path,
        ref_text: str,
        text: str,
        language: str,
        seed: int,
        params: dict,
    ) -> tuple[np.ndarray, int]: ...
