#!/usr/bin/env python3
"""Write the engine's OpenAPI document to common/openapi.json.

Uses the fake backend, so it does not load a model.
"""

from __future__ import annotations

import json
from pathlib import Path

from voice_engine.app import create_app
from voice_engine.config import Settings


def main() -> None:
    import tempfile

    root = Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory() as folder:
        app = create_app(Settings(data_dir=Path(folder), backend="fake"))
    target = root / "common" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
