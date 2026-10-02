# Voice Engine

The engine is the Python process in `packages/engine`. It owns the models, the
job queue, the voice library, and the output files. In the packaged tool it
binds to `127.0.0.1` and the studio in `packages/studio` is the address a
browser uses. Scripts can also call the engine directly. Nothing else loads
weights.

```text
 client (curl / CLI / script / MCP / UI later)
        |
        |  HTTP JSON   Authorization: Bearer <token>   (required off-loopback)
        v
 +--------------------------------------------------------------+
 | voice-engine serve          default http://127.0.0.1:8100    |
 |                                                              |
 |  FastAPI routes --> JobStore --> storage (SQLite) --> one worker thread |
 |                                          |                   |
 |                                          v                   |
 |                              Backend: mlx | cuda | cpu | fake |
 |                              (models loaded once, cached)    |
 |                                          |                   |
 |                                          v                   |
 |                              audio checks -> job.json        |
 +--------------------------------------------------------------+
        |
        v
 data/  studio.db   (jobs, voices, and WAV bytes)
```

## Why this shape

- **One worker thread.** One GPU, one model owner. Jobs run in order. MLX and torch
  models are not shared across threads.
- **Jobs, not blocking calls.** Design with four candidates takes about a minute.
  `POST` returns a job id at once; clients poll or pass `--wait`.
- **Jobs and voices in SQLite.** `data/studio.db` holds the queue, the locked
  voices, and the WAV bytes. A restart keeps history; queued jobs are re-queued,
  jobs that were mid-run are marked `failed` with `interrupted`. The layout is
  in [database.md](database.md).
- **Same API on every machine.** Mac uses `mlx`, Linux and Windows with NVIDIA use
  `cuda`, a machine without a GPU uses `cpu`, tests use `fake`. Clients never know
  which one ran.
- **Validation is part of every job.** Each output WAV gets measured and flagged
  before the job is marked `succeeded`.

## Folder structure

```text
voice-design/
  setup.ts                 installs the right extra and downloads weights
  start.ts                 starts engine, then studio
  voice-generator.toml
  common/openapi.json
  packages/engine/         this service
    pyproject.toml         uv project; extras: mac, cuda, cpu, dev
    config/engine.example.toml
    examples/              design.json, lock.json, speak.json
    scripts/smoke.py       design -> lock -> speak over HTTP
    scripts/export_openapi.py
    src/voice_engine/
      cli.py app.py        serve, doctor, setup, submit; FastAPI app and job routes
      routes_library.py    playgrounds, versions, styles, narrations, downloads
      jobs.py              JobStore: queue, worker, design/lock/speak/render
      library.py           Library: voices and versions, prompt staging
      schemas.py           pydantic specs and request bodies
      pipeline/            script parsing, beats, styles, stitching
      backends/            mlx, cuda, cpu, fake
      storage/             SQLite layer, see database.md
    tests/                 test_api, test_library_tables, test_library_api, test_templates
  packages/studio/         the public UI and proxy
  packages/mcp/            tools served at /mcp by the studio
  data/studio.db           every job, voice, and WAV; not committed
```

## Configuration

Order of precedence: CLI flag, then `VOICE_ENGINE_*` env var, then `engine.toml`,
then the default.

| Key        | Env var                 | Default      | Notes                                        |
|------------|-------------------------|--------------|----------------------------------------------|
| host       | VOICE_ENGINE_HOST       | 127.0.0.1    | `0.0.0.0` for a remote GPU server            |
| port       | VOICE_ENGINE_PORT       | 8100         |                                              |
| token      | VOICE_ENGINE_TOKEN      | none         | required when host is not loopback           |
| data_dir   | VOICE_ENGINE_DATA_DIR   | ./data       |                                              |
| backend    | VOICE_ENGINE_BACKEND    | auto         | auto, mlx, cuda, cpu, fake                   |
| preload    | VOICE_ENGINE_PRELOAD    | false        | load both models at startup                  |
| cors_origins | VOICE_ENGINE_CORS_ORIGINS | *          | browser origins allowed to call the API    |

Client commands read `VOICE_ENGINE_URL` (default `http://127.0.0.1:8100`) and
`VOICE_ENGINE_TOKEN`.

## HTTP API

| Method | Path                                  | Purpose                                  |
|--------|---------------------------------------|------------------------------------------|
| GET    | /health                               | backend, device, loaded models, queue    |
| POST   | /v1/jobs                              | submit design, lock, or speak; returns 202 |
| GET    | /v1/jobs?status=&type=&limit=         | list jobs, newest first                  |
| GET    | /v1/jobs/{job_id}                     | job record with outputs and checks       |
| DELETE | /v1/jobs/{job_id}                     | cancel a queued job                      |
| GET    | /v1/jobs/{job_id}/files/{name}        | download a WAV                           |
| POST   | /v1/designs, /v1/speech, /v1/renders  | typed submits, same job record            |
| GET    | /v1/voices?include_archived=          | list voices with version counts          |
| POST   | /v1/voices                            | keep a take (lock), returns the job      |
| GET / PATCH / DELETE | /v1/voices/{voice_id}   | metadata; name, notes, favorite, archived, current_version_id; delete refused (409) while narrations use it |
| POST   | /v1/voices/{voice_id}/copy            | a new voice whose version 1 is any version |
| GET    | /v1/voices/{voice_id}/files/{name}    | master.wav of the current version, preview.txt, instruct.txt |
| GET    | /v1/voices/{voice_id}/versions    | the version list                             |
| GET / PATCH | /v1/voices/{voice_id}/versions/{version_id} | one version; label              |
| GET    | /v1/voices/{voice_id}/versions/{version_id}/master.wav | that version's audio    |
| GET / POST | /v1/playgrounds                   | saved design workspaces                  |
| GET / PATCH / DELETE | /v1/playgrounds/{id}    | draft config, runs, voices kept from them |
| POST   | /v1/playgrounds/{id}/copy             | copy the draft                           |
| POST   | /v1/playgrounds/{id}/runs             | queue a design job from the draft; `overrides`, `save` |
| GET / POST | /v1/styles                        | narration presets                        |
| GET / PATCH / DELETE | /v1/styles/{id}         | built-ins frozen (409); in use blocks delete (409) |
| GET / POST | /v1/narrations                    | drafts and rendered narrations           |
| GET / PATCH / DELETE | /v1/narrations/{id}     | GET includes `job` and `audio_url`; delete removes the render job |
| POST   | /v1/narrations/{id}/render            | queue the render, freeze the draft; 409 while rendering |
| POST   | /v1/narrations/{id}/copy              | a new draft from this one                |
| GET    | /v1/narrations/{id}/audio.wav         | the stitched WAV; 409 until rendered     |
| GET    | /v1/downloads                         | every WAV with a url, newest first       |
| GET / POST / PATCH / DELETE | /v1/templates…  | voice recipes, see templates.md          |

`/health` is open. Everything under `/v1` needs the bearer token when one is set.

Error mapping is the same across the library routes: a missing row is
`404`, a rule the row refuses (frozen built-in, voice in use, duplicate id,
render already running) is `409` with a sentence that names the cause, and
a bad value is `400`.

## Library objects

```text
playground  ──runs──▶  design job  ──takes──▶  candidate-NN.wav
                                         │ keep
                                         ▼
                             voice ──▶ voice@1
                                         │ current_version_id
                                         ▼
style  +  script  ──▶  narration (draft) ──render──▶ render job ──▶ audio.wav
```

- A **playground** holds a design draft (`config`: instruct, sample text,
  language, takes, Qwen params). Each Generate is a **run** with a `run_no`
  and the job id. Voices kept from a run remember the playground.
- A **voice** is the id people use. Its audio is version 1, `voice@1`, the
  kept take. `current_version_id` decides which master
  `GET /v1/voices/{id}/files/master.wav` and a speak without `version_id` use.
- A **style** is a narration preset: temperature, top-p, top-k, repetition
  penalty, max tokens, pause scale, target loudness, trim, emotion. Four are
  built in (narration, comedy, commercial, kids) and read-only; `copy_of`
  creates an editable one.
- A **narration** is a title, a voice, a version (optional), a style, and a
  script. A draft is fully editable. Render freezes it; afterwards only
  `title` and `notes` change. Copy makes a new draft.

## Swagger, and how a frontend connects

The server is standalone. Open `http://<host>:<port>/` and it lands on Swagger UI
at `/docs`. The same page can run design, lock, speak, and download the WAV.
`/openapi.json` is the spec a frontend can generate a client from.

A frontend does not share a process or a folder with this server. Its only setting
is the base URL, for example `http://127.0.0.1:8100` or `http://gpu-box:8100`,
plus the token when the server requires one. Requests from a browser are allowed
from any origin unless `cors_origins` lists specific ones.

Each finished output includes `url`, a path such as
`/v1/jobs/<job_id>/files/audio.wav`. `GET` that path and the response is the WAV
with `Content-Disposition: attachment`, so Swagger and the browser both download it.

## Job specs

All three share `POST /v1/jobs`; `type` picks the kind.

### design: description to candidate voices

```json
{
  "type": "design",
  "instruct": "Adult male narrator, mid-thirties, warm low-mid voice, calm and curious.",
  "text": "Give it a second. Ordinary things get interesting when they refuse to behave.",
  "language": "English",
  "candidates": 4,
  "seed_start": 1000,
  "params": { "temperature": 0.9, "top_p": 1.0, "top_k": 50 }
}
```

Writes `candidate-01.wav` ... `candidate-NN.wav`, one seed each.

### lock: one candidate to a permanent voice

```json
{ "type": "lock", "voice_id": "narrator-male-v1", "from_job": "job_...", "candidate": 2 }
```

Copies the candidate to `voices/<voice_id>/master.wav` with the preview text and
the description. On CUDA and CPU it also writes `voice_prompt.pt`. Voice ids are immutable:
locking to an existing id fails. Make `-v2` instead.

### speak: text to audio with a locked voice

```json
{
  "type": "speak",
  "voice_id": "narrator-male-v1",
  "text": "What actually happens inside a combustion engine? Let's slow it down.",
  "seed": 1,
  "params": { "temperature": 0.8, "speed": 1.0 }
}
```

Writes `audio.wav`. Multi-line text is generated line by line and joined.
`version_id` picks a version other than the current one.

### render: a long script to one WAV

```json
{
  "type": "render",
  "voice_id": "warm-narrator-v1",
  "version_id": "warm-narrator-v1@2",
  "style": "comedy",
  "text": "Okay, so this is the part nobody tells you. [pause 0.6s] Welcome back.",
  "params": { "temperature": 0.95 }
}
```

The script is split into beats on blank lines and sentence ends.
Each beat is spoken with the voice. `[pause 1.2s]` sets the gap after a beat.
Any other bracket tag is rejected. Beats are loudness-matched to the
style target, trimmed, and stitched into `audio.wav`. `progress` counts
beats, so a client can show "beat 7 of 23" while it runs. Scripts over about
ten minutes are refused.

`POST /v1/narrations/{id}/render` builds this spec from a saved narration
and links the job to it; the narration's `status` follows the job
(`rendering`, `rendered`, `failed`).

### Generation params

| Param              | Default | mlx | cuda / cpu | Meaning                          |
|--------------------|---------|-----|------------|----------------------------------|
| temperature        | 0.9     | yes | yes        | lower is steadier, higher is livelier |
| top_p              | 1.0     | yes | yes        |                                  |
| top_k              | 50      | yes | yes        |                                  |
| repetition_penalty | 1.05    | yes | yes        |                                  |
| max_tokens         | 4096    | yes | yes        | caps runaway generation          |
| speed              | 1.0     | yes | no         | speak only                       |

The job record lists which params were `applied` and which were `deferred` by the
backend that ran it, so a script can see if a setting was ignored.

## Job record

```json
{
  "id": "job_20260927T051700_ab12cd",
  "type": "speak",
  "status": "succeeded",
  "spec": { "...": "as submitted" },
  "backend": "mlx",
  "created_at": "...", "started_at": "...", "finished_at": "...",
  "applied": ["temperature", "speed"],
  "deferred": [],
  "outputs": [
    {
      "file": "audio.wav",
      "url": "/v1/jobs/job_20260927T051700_ab12cd/files/audio.wav",
      "seed": 1,
      "sample_rate": 24000,
      "checks": {
        "duration_s": 4.7, "peak": 0.80, "rms_dbfs": -21.3,
        "clipped_ratio": 0.0, "lead_silence_s": 0.08, "tail_silence_s": 0.21,
        "chars_per_s": 16.8,
        "ok": true, "warnings": []
      }
    }
  ],
  "error": null
}
```

Statuses: `queued`, `running`, `succeeded`, `failed`, `cancelled`.

While a job runs, `progress` carries `phase` (`queued`, `design`, `lock`,
`speak`, `render`, `stitch`, `done`), a `detail` sentence, and
`completed` / `total` when the phase has countable steps. Speak and render
jobs also carry `version_id`. Downloading an output before it exists
returns `409` with the current detail.

## Validation

Each WAV is checked right after it is written. A warning does not fail the job; it
tells the caller to listen or regenerate.

| Check           | Warning when                         | Usual cause                    |
|-----------------|--------------------------------------|--------------------------------|
| too_short       | duration under 0.5 s                 | empty or broken generation     |
| clipping        | over 0.1% of samples at full scale   | too hot, needs normalizing     |
| too_quiet       | RMS under -40 dBFS                   | near-silent output             |
| long_lead / long_tail | over 1.5 s of silence at an end | stalled generation             |
| pace_fast / pace_slow | speak only: chars per second outside 6 to 30 | truncated or runaway audio |

Next step for validation (not in this version): transcribe each output with an ASR
model and compare to the input text, so missing or invented words are caught
automatically.

## Automation

Everything is scriptable without a UI:

```bash
bun start.ts
uv run --project packages/engine voice-engine submit examples/design.json --wait --download out/
uv run --project packages/engine python scripts/smoke.py
```

The submit command talks to the engine on port 8100. The same calls work through
the studio on port 8180, which is what a browser and a remote client use.

```bash
curl -s -X POST localhost:8180/v1/jobs -H 'content-type: application/json' \
  -d @packages/engine/examples/speak.json
curl -s localhost:8180/v1/jobs/<job_id>
curl -s -o line.wav localhost:8180/v1/jobs/<job_id>/files/audio.wav
```

## Remote GPU server

Set `server.host` to `0.0.0.0` and `server.token` in `voice-generator.toml`, then
run `bun start.ts` on the server. The studio refuses to publish itself without a
token. The engine stays on `127.0.0.1`. From another machine, call
`http://<server>:8180` and send `Authorization: Bearer <token>`. The MCP
endpoint is `http://<server>:8180/mcp` with that same header.

## Install

`bun setup.ts` at the repository root runs the right pair of commands for
the machine. By hand:

```bash
uv sync --python 3.12 --project packages/engine --extra mac --extra dev    # Apple Silicon
uv sync --python 3.12 --project packages/engine --extra cuda --extra dev   # NVIDIA
uv sync --python 3.12 --project packages/engine --extra cpu --extra dev    # no GPU
uv run --project packages/engine voice-engine setup --backend mlx          # downloads the Qwen repos
uv run --project packages/engine voice-engine doctor
uv run --project packages/engine --extra dev pytest packages/engine/tests
```

## Later

- ASR check on each beat, comparing the transcript to the script.
- Streaming the render as beats finish instead of one WAV at the end.
- A second worker when two GPUs are present.
