# API contract

`openapi.json` is generated from the engine. It is the document served at
`/openapi.json` while Voice Generator is running.

Regenerate it after a route or schema change:

```bash
uv run --project packages/engine python scripts/export_openapi.py
```
