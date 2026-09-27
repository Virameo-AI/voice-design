"""Backend detection and selection. No model is loaded here."""

from __future__ import annotations

import sys
import types

import pytest

from voice_engine import backends
from voice_engine.backends.torch_backend import CpuBackend, CudaBackend
from voice_engine.config import Settings, load_settings


def _fake_torch(monkeypatch, cuda: bool):
    torch = types.ModuleType("torch")
    torch.cuda = types.SimpleNamespace(is_available=lambda: cuda)
    monkeypatch.setitem(sys.modules, "torch", torch)


def _no_module(monkeypatch, name: str):
    monkeypatch.setitem(sys.modules, name, None)  # import raises ImportError


@pytest.fixture(autouse=True)
def not_apple_silicon(monkeypatch):
    monkeypatch.setattr(backends.platform, "system", lambda: "Linux")
    monkeypatch.setattr(backends.platform, "machine", lambda: "x86_64")


def test_detect_prefers_cuda(monkeypatch):
    _fake_torch(monkeypatch, cuda=True)
    assert backends.detect() == "cuda"


def test_detect_falls_back_to_cpu_without_gpu(monkeypatch):
    _fake_torch(monkeypatch, cuda=False)
    monkeypatch.setitem(sys.modules, "qwen_tts", types.ModuleType("qwen_tts"))
    assert backends.detect() == "cpu"


def test_detect_none_without_model_libraries(monkeypatch):
    _fake_torch(monkeypatch, cuda=False)
    _no_module(monkeypatch, "qwen_tts")
    assert backends.detect() is None
    _no_module(monkeypatch, "torch")
    assert backends.detect() is None


def test_detect_mlx_on_apple_silicon(monkeypatch):
    monkeypatch.setattr(backends.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(backends.platform, "machine", lambda: "arm64")
    assert backends.detect() == "mlx"


def test_auto_uses_cpu_when_no_gpu(monkeypatch, caplog):
    _fake_torch(monkeypatch, cuda=False)
    monkeypatch.setitem(sys.modules, "qwen_tts", types.ModuleType("qwen_tts"))
    with caplog.at_level("WARNING"):
        backend = backends.create_backend("auto")
    assert isinstance(backend, CpuBackend)
    assert "CPU" in caplog.text


def test_auto_explains_how_to_install_cpu(monkeypatch):
    _no_module(monkeypatch, "torch")
    with pytest.raises(RuntimeError, match="--extra cpu"):
        backends.create_backend("auto")


def test_cpu_and_cuda_share_the_torch_code():
    cpu, cuda = CpuBackend(), CudaBackend()
    assert (cpu.name, cpu.device, cpu.device_map, cpu.dtype_name) == ("cpu", "cpu", "cpu", "float32")
    assert (cuda.name, cuda.device, cuda.device_map, cuda.dtype_name) == ("cuda", "cuda", "cuda:0", "bfloat16")
    assert cpu.loaded() == [] and cuda.loaded() == []
    # speed is an MLX-only knob; both torch backends defer it.
    applied, names, deferred = cpu.split({"temperature": 0.8, "speed": 1.2}, "speak")
    assert applied == {"temperature": 0.8} and names == ["temperature"] and deferred == ["speed"]


def test_cpu_is_a_valid_configured_backend(tmp_path, monkeypatch):
    assert Settings(backend="cpu").backend == "cpu"
    monkeypatch.setenv("VOICE_ENGINE_BACKEND", "cpu")
    assert load_settings().backend == "cpu"
    with pytest.raises(ValueError):
        Settings(backend="gpu").validate()
