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
audio/
  start.ts                 starts engine, then studio
  voice-generator.toml
  common/openapi.json
  packages/engine/         this service
    pyproject.toml         uv project; extras: mac, cuda, cpu, dev
    config/engine.example.toml
    examples/              design.json, lock.json, speak.json
    scripts/smoke.py       design -> lock -> speak over HTTP
    scripts/export_openapi.py
    src/voice_engine/      cli, app, jobs, library, backends
    tests/test_api.py
  packages/studio/         the public UI and proxy
  data/                    jobs/<job_id>/ and voices/<voice_id>/, not committed
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
| GET    | /v1/voices                            | list locked voices                       |
| GET    | /v1/voices/{voice_id}                 | voice metadata                           |
| GET    | /v1/voices/{voice_id}/files/{name}    | master.wav, preview.txt, instruct.txt    |

`/health` is open. Everything under `/v1` needs the bearer token when one is set.

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
`http://<server>:8180` and send `Authorization: Bearer <token>`.

## Install

```bash
uv sync --python 3.12 --project packages/engine --extra mac --extra dev    # Apple Silicon
uv sync --python 3.12 --project packages/engine --extra cuda --extra dev   # NVIDIA
uv sync --python 3.12 --project packages/engine --extra cpu --extra dev    # no GPU
uv run --project packages/engine voice-engine doctor
uv run --project packages/engine pytest
```

## Later

- Studio: `packages/studio`, served by `bun start.ts` (see frontend.md and the repository README).
- MCP server: a thin wrapper whose tools map to these endpoints.
- ASR check, loudness normalization, long-script chunking, emotion engines.
