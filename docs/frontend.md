# Studio

`packages/studio` is the public HTTP server and the dashboard. A browser
never connects to the engine. `start.ts` starts the engine on
`127.0.0.1:8100`, then this server on the host and port in
`voice-generator.toml` (default `127.0.0.1:8180`).

`server.ts` serves the page and proxies `/health`, `/v1/*`, `/docs`,
`/redoc`, and `/openapi.json` to the engine, and answers `/mcp` itself. When
`server.token` is set, the proxy rejects API and MCP calls that do not carry
it. The page loads without a token; **Connect** has a field for it, stored
in `localStorage`.

## Files

```text
packages/studio/
  server.ts        Bun.serve: static page, /v1 proxy, /mcp
  index.html       the dashboard markup (six pages, player bar, toast)
  src/main.ts      state, rendering, events. Vanilla TypeScript, no framework.
  src/api.ts       the only module that knows the HTTP API. Same-origin paths.
  src/config.ts    token in localStorage
  src/styles.css   design tokens and components, light and dark
design/dashboard.html   the standalone mock the dashboard was built from
```

`bun build ./index.html` bundles the script and the stylesheet. In
development Bun serves them from source.

## Pages

Keyboard: `1`–`5` switch pages, `⌘↵` runs the current page's main action,
`Space` plays or pauses.

**Playground.** The template chips fill the description and the sample line
(`GET /v1/templates`). The first Generate creates a playground named after
the template and queues a run (`POST /v1/playgrounds/{id}/runs`). Later
Generates on the same playground add runs; the picker at the top of the form
reopens an earlier playground with its last successful takes. Takes play
through the real WAV. **Keep** locks a take (`POST /v1/voices`) with an id
derived from the template name (`warm-narrator-v1`, `-v2`, …).

**Voices.** `GET /v1/voices`, with the version count and the current
version id. ★ toggles favorite (`PATCH`). The style buttons open Studio with
the voice and that style selected.

**Studio.** Voice strip, version select, style segment (`GET /v1/styles`),
title, a `[pause 0.8s]` button, and the script. Beats are parsed in the page
the same way the engine splits them, so the count, an unknown tag, and the
ten-minute warning update as you type. Render creates a narration draft
(`POST /v1/narrations`) and renders it (`POST …/render`); progress from the
job drives the bar and the beat statuses. When it finishes the player plays
`GET /v1/narrations/{id}/audio.wav` and any setting the backend deferred is
listed under the bar. Temperature defaults to the style; the Qwen speak
settings are under a disclosure.

**Downloads.** `GET /v1/downloads`: narrations, voice version masters, and
speech, newest first, filterable. Play, WAV (saves through a blob so the
token travels), Copy URL.

**Connect.** `GET /health` and an MCP `initialize` round-trip decide the
status dots. The token field, the curl example, the MCP client config, and
the table that maps every control to its stage, model, API field, and MCP
tool.

## One library, two doors

The dashboard and MCP call the same engine, and the engine writes one
SQLite file, so a voice an agent locks or a narration it renders is the
same row the dashboard reads. The page polls `GET /health` every 30 s and
the library (templates, voices, styles, playgrounds, downloads) every 8 s,
and again when the tab regains focus. Only the lists whose data changed are
re-rendered, so typing and paging are undisturbed. `data/out` is the
agent's export copy; the dashboard never reads it.

## Player

One hidden `<audio>` element. Protected WAVs are fetched with the token and
played from an object URL, cached per path for the session. The bottom bar
shows the title, the scrubber, and a Download button for whatever is loaded.
Autoplay after a render works because the user pressed Render; if a browser
refuses it, the clip is loaded and the play button is ready.

## Theme

`data-theme` on `<html>` is `light` or `dark`, following the system on first
load and remembered in `localStorage`. Tokens live on `:root` and
`[data-theme="dark"]` in `src/styles.css`: `--bg`, `--panel`, `--ink`,
`--muted`, `--line`, `--soft`, `--brand` (the violet–pink–orange gradient),
`--ok`, `--warn`, `--bad`, `--tag`. Orbs take their three colours from a
palette chosen by a hash of the voice id, so a voice keeps its colour across
pages.

## Commands

```bash
bun install --cwd packages/studio
bun run --cwd packages/studio typecheck
bun run --cwd packages/studio build     # static files in packages/studio/dist
```

Day to day, run `bun start.ts` or `bun start.ts --dev` from the repository
root. To try the dashboard without models:

```bash
uv run --project packages/engine voice-engine serve --backend fake --port 8100
PORT=8180 VOICE_ENGINE_URL=http://127.0.0.1:8100 bun --cwd packages/studio server.ts
```
