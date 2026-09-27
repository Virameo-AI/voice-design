# Studio

`packages/studio` is the public HTTP server and the web UI. A browser never
connects to the engine. `start.ts` at the repository root starts the engine
on `127.0.0.1:8100`, then this server on the host and port in
`voice-generator.toml` (default `127.0.0.1:8180`).

`server.ts` serves the page and proxies `/health`, `/v1/*`, `/docs`,
`/redoc`, and `/openapi.json` to the engine. When `server.token` is set, the
proxy rejects API calls that do not carry it. The page itself loads without
a token, and the UI asks for one.

`src/api.ts` is the only module that knows the HTTP API. It calls same-origin
paths. Types follow `common/openapi.json`.

Screens:

- **Create**: description, preview text, language, candidate count, first
  seed, and the model settings. A template gallery sits under the hero.
  Candidates play in the page and can be locked.
- **My voices**: locked voices, the reference clip, and the speak form.
- **Activity**: every job, with timings, the submitted spec, and downloads.
- **Templates**: the sixteen built-in recipes and any you save, each with a
  sample clip.
- **Profile**: locked voices you have marked to keep in front.

The recipe and profile design is in [templates.md](templates.md).

The page scrolls. Create keeps the description and the candidates side by
side on a wide screen, and stacks them on a narrow one.

Visual tokens live on `:root` in `packages/studio/src/styles.css`:

| Token | Value | Use |
| --- | --- | --- |
| `--paper` | `#fbf6ee` | Page |
| `--white` | `#fffdf8` | Cards |
| `--ink` | `#493227` | Text |
| `--muted` | `#806b5d` | Secondary text |
| `--line` | `#eadbd0` | Borders |
| `--accent` | `#c65228` | Actions and the active tab |
| `--accent-soft` | `#fff0e3` | Active tab and play button |
| `--coral` | `#eb7a4b` | Busy and warning emphasis |
| `--sage` / `--sage-soft` | `#728b5d` / `#eef3e6` | Ready status |

Audio uses one component, `SoundClip`, for candidates, reference clips,
takes, and job outputs. The wave is a bright center line with a glowing band
and four contours mirrored above and below it. The band follows the loudness
of the decoded WAV: the clip is split into stretches about 110px wide,
ranked from quietest to loudest, and joined with a Catmull-Rom spline, so
the curve stays continuous. The SVG is drawn at the element's real size and
92px height, so a narrow card and a wide reference clip keep the same
proportions. During playback the contours
sway gently, unless the system asks for reduced motion.

The color comes from the seed: Sunset, Prism, Silk, or Aura. A saved voice
keeps its candidate's palette on its reference clip and takes.

Clips load when they scroll into view. On Activity, a clip loads when you ask
for it. One clip plays at a time. The wave is a keyboard slider: the arrow
keys move 2 seconds, and Home and End jump to the start and end. If the
browser cannot decode a file, the native audio player appears instead.

On Create, **Select voice** marks a candidate, and the Save row under the
grid saves it with a voice id. Seed, peak, and RMS are under **Details** on
each card. The first seed is under **Advanced model settings**.

```bash
bun install --cwd packages/studio
bun run --cwd packages/studio typecheck
bun run --cwd packages/studio build     # static files in packages/studio/dist
```

Day to day, run `bun start.ts` or `bun start.ts --dev` from the repository
root rather than starting the studio by itself.
