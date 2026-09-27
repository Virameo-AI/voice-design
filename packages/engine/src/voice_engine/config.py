from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
BACKENDS = {"auto", "mlx", "cuda", "cpu", "fake"}


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8100
    token: str | None = None
    data_dir: Path = Path("data")
    backend: str = "auto"
    preload: bool = False
    cors_origins: str = "*"

    def origin_list(self) -> list[str]:
        origins = [part.strip() for part in self.cors_origins.split(",") if part.strip()]
        return origins or ["*"]

    def validate(self) -> None:
        if self.backend not in BACKENDS:
            raise ValueError(f"backend must be one of {sorted(BACKENDS)}, got {self.backend!r}")
        if self.host not in LOOPBACK and not self.token:
            raise ValueError(
                f"host {self.host} is reachable from other machines. Set VOICE_ENGINE_TOKEN."
            )


def _coerce(name: str, value):
    if name == "port":
        return int(value)
    if name == "preload":
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}
    if name == "data_dir":
        return Path(value)
    if name == "token":
        return value or None
    return value


def load_settings(config_path: Path | None = None, **overrides) -> Settings:
    names = {f.name for f in fields(Settings)}
    values: dict = {}
    if config_path:
        with open(config_path, "rb") as fh:
            values.update(tomllib.load(fh).get("engine", {}))
    for name in names:
        env = os.environ.get(f"VOICE_ENGINE_{name.upper()}")
        if env is not None:
            values[name] = env
    values.update({k: v for k, v in overrides.items() if v is not None})
    settings = Settings(**{k: _coerce(k, v) for k, v in values.items() if k in names})
    settings.validate()
    return settings
