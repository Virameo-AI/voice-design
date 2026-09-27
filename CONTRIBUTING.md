# Contributing

Voice Generator is two packages behind one command. Change the package that
owns the behavior, and keep the browser talking only to the studio.

## Setup

```bash
# Apple Silicon
uv sync --python 3.12 --project packages/engine --extra mac --extra dev
# Linux or Windows with NVIDIA
uv sync --python 3.12 --project packages/engine --extra cuda --extra dev
# Linux or Mac without a GPU (CPU-only torch, slow but complete)
uv sync --python 3.12 --project packages/engine --extra cpu --extra dev

bun install --cwd packages/studio
```

## Checks

```bash
uv run --project packages/engine pytest
uv run --project packages/engine python scripts/export_openapi.py
bun run --cwd packages/studio typecheck
```

`common/openapi.json` is generated from the engine. Regenerate it when you
change a route or a schema, and commit the result.

## Running

`bun start.ts` starts both. `bun start.ts --dev` reloads the studio when its
TypeScript changes. The engine keeps running, so the models stay loaded.

To work on the engine alone:

```bash
uv run --project packages/engine voice-engine serve --backend fake --port 8100
```

## What not to commit

- `data/` holds generated audio and locked voices.
- Model weights. They download into the Hugging Face cache.
- `.venv/` and `node_modules/`.
- Access tokens. `voice-generator.toml` in the repository has none.
