# Changelog

## 0.2.0 — branch `dev/qwen`

The 0.1 tool designed a voice, locked it, and spoke a line. 0.2 adds the
library around that: playgrounds that remember runs, a kept take as version
1, saved narration drafts rendered as one WAV, a downloads list, and a
dashboard built from `design/dashboard.html`. Qwen does the speaking. Tags
in a script mark a beat; the words are what get spoken.

### Engine (`packages/engine`)

- Schema version 4: `playgrounds`, `playground_runs`, `voice_versions`,
  `styles`, `narrations`; `voices` gains `playground_id`, `origin_job_id`,
  `origin_candidate`, `current_version_id`, `favorite`, `archived`,
  `copied_from`; `jobs` gains `version_id`. Migration backfills version 1
  of every voice, a playground per design job, and favorites.
- Four built-in styles: narration, comedy, commercial, kids. Read-only;
  copy to edit. The render pipeline reads them from the database.
- `render` and `speak` accept `version_id`; `render` takes a style id. A
  render submitted from a saved narration updates its status.
- `Library` resolves the current version, copies a voice, and stages that
  version for the backend. Deleting a voice is refused while a narration
  uses it.
- New routes in `routes_library.py`: playgrounds, voice patch/copy/versions,
  styles, narrations, `GET /v1/downloads`.

### MCP (`packages/mcp`)

- Library tools in `src/tools_library.ts`: playgrounds, voice update/copy,
  versions, styles, narrations, `render_saved_narration`,
  `download_voice_version`, `download_narration`, `list_downloads`.
- Server instructions describe create → run → lock → narrate → render →
  download.

### Studio (`packages/studio`)

- React removed. The dashboard is `index.html`, `src/main.ts`, `src/api.ts`,
  `src/config.ts`, `src/styles.css`.
- Five pages: Playground, Voices, Studio, Downloads, Connect.

### Documentation

- `README.md`, `docs/frontend.md`, `docs/mcp.md`, `docs/backend.md`, and
  `docs/database.md` describe the library. `CONTRIBUTING.md` lists the three
  packages and their checks.

### Not in this branch

- Docker. The tool runs from `bun setup.ts` and `bun start.ts`.
- Breeze TTS. The proof of concept stays on `dev/breeze-tts`.
- ASR verification of rendered beats.

## 0.1.0

Design, lock, speak. SQLite library, templates, favorites, MCP tools for
the three job types, React studio.
