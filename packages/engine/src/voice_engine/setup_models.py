"""Download the Qwen weights this machine will speak with."""

from __future__ import annotations

import platform
import shutil


MLX_REPOS = (
    "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-4bit",
    "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
)
TORCH_REPOS = (
    "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
)


def choose_backend(requested: str | None = None) -> str:
    if requested and requested != "auto":
        return requested
    if platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return "mlx"
    if shutil.which("nvidia-smi"):
        return "cuda"
    return "cpu"


def repos_for(backend: str) -> tuple[str, ...]:
    if backend == "mlx":
        return MLX_REPOS
    if backend in {"cuda", "cpu"}:
        return TORCH_REPOS
    raise ValueError(f"setup downloads weights for mlx, cuda, or cpu, not {backend!r}")


def prefetch(backend: str | None = None) -> list[str]:
    chosen = choose_backend(backend)
    repos = repos_for(chosen)
    from huggingface_hub import snapshot_download

    print(f"backend={chosen}")
    paths = []
    for repo in repos:
        print(f"downloading {repo}")
        paths.append(snapshot_download(repo))
        print(f"ready {repo}")
    print("Qwen weights are on disk.")
    return paths
