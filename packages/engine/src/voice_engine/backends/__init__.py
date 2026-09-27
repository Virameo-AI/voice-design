from __future__ import annotations

import logging
import platform

from voice_engine.backends.base import Backend

log = logging.getLogger(__name__)


def _importable(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


def detect() -> str | None:
    """Best backend this machine can run real models on, or None.

    mlx on Apple Silicon, cuda when torch sees an NVIDIA GPU, otherwise cpu when
    torch and qwen-tts are installed.
    """
    if platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return "mlx"
    try:
        import torch
    except ImportError:
        return None
    if torch.cuda.is_available():
        return "cuda"
    return "cpu" if _importable("qwen_tts") else None


def create_backend(name: str) -> Backend:
    if name == "auto":
        name = detect() or ""
        if not name:
            raise RuntimeError(
                "No Apple Silicon or CUDA GPU found, and the CPU model libraries are not installed. "
                "Install with `uv sync --extra cpu` to run on the CPU, or use backend=fake to run without models."
            )
        if name == "cpu":
            log.warning("No NVIDIA GPU found. Running the models on the CPU; generation is slow.")
    if name == "mlx":
        from voice_engine.backends.mlx_backend import MlxBackend

        return MlxBackend()
    if name == "cuda":
        from voice_engine.backends.torch_backend import CudaBackend

        return CudaBackend()
    if name == "cpu":
        from voice_engine.backends.torch_backend import CpuBackend

        return CpuBackend()
    if name == "fake":
        from voice_engine.backends.fake_backend import FakeBackend

        return FakeBackend()
    raise ValueError(f"unknown backend {name!r}")


__all__ = ["Backend", "create_backend", "detect"]
