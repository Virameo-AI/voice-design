# Contributing

Voice Design is three packages behind one command. Change the package that
owns the behavior, and keep the browser talking only to the studio.

| Package | Owns | Language |
| --- | --- | --- |
| `packages/engine` | models, jobs, library, SQLite, the HTTP API | Python 3.12, uv |
| `packages/studio` | the dashboard and the proxy | TypeScript, Bun |
| `packages/mcp` | the tools served at `/mcp` | TypeScript, Bun |

## Setup

```bash
bun setup.ts                     # or --backend=mlx | cuda | cpu
uv sync --project packages/engine --extra dev    # adds pytest and httpx to the engine env
bun install --cwd packages/studio
bun install --cwd packages/mcp
```

## Checks

Run these before opening a change:

```bash
uv run --project packages/engine --extra dev pytest packages/engine/tests   # fake backend
bun test packages/mcp/tests
bun run --cwd packages/studio typecheck
```

When a route or a schema changes, regenerate the contract and commit it:

```bash
uv run --project packages/engine python packages/engine/scripts/export_openapi.py
```

`common/openapi.json` is the document the studio serves at `/openapi.json`
and the one a client generator reads.

## Running

`bun start.ts` starts both. `bun start.ts --dev` reloads the studio when its
TypeScript or CSS changes; the engine keeps running, so the models stay
loaded.

To work on the engine or the dashboard without models:

```bash
uv run --project packages/engine voice-engine serve --backend fake --port 8100
PORT=8180 VOICE_ENGINE_URL=http://127.0.0.1:8100 bun --cwd packages/studio server.ts
```

The fake backend produces tones with the right duration, so the whole flow
runs: generate, keep, render, download.

## Screenshots

`docs/images/*.png` are captured from the fake backend at 1440×900, device
pixel ratio 2, light theme (plus one dark Studio shot). Recapture them when a
page changes; keep the capture script outside the repository.

## Where things go

- A new job type: `schemas.py` (spec), `jobs.py` (`_check` and `_execute`),
  a route in `app.py` or `routes_library.py`, an MCP tool in `packages/mcp/src`,
  then `export_openapi.py`.
- A new table: a numbered step in `storage/migrations.py`, a class in
  `storage/`, a section in `docs/database.md`.
- A new page or control: `index.html`, `src/main.ts`, `src/api.ts` if it
  needs a call, and the mapping table on the Connect page.

## What not to commit

- `data/` holds the database and exported audio.
- Model weights. Qwen downloads into the Hugging Face cache.
- `.venv/`, `node_modules/`, `packages/studio/dist/`.
- Access tokens. `voice-generator.toml` in the repository has none.
