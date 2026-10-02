# Local database

This is the design for jobs, voices, and audio in one SQLite file. It is
what the engine runs.

The HTTP API, the studio, and MCP stay as they are. `JobStore` and `Library`
keep the methods the routes already call. SQL lives in a storage layer
under them. Downloads are still WAV.

## Why SQLite

Jobs, locked voices, and their audio are one user's local data. Today each
job is a directory (`job.json` plus one WAV per candidate) and each voice is
another directory (`voice.json`, `master.wav`, `instruct.txt`, `preview.txt`,
and on the torch backends, CUDA and CPU, `voice_prompt.pt`). Creating, listing, and deleting that means
managing many files and their permissions.

SQLite is a single file, `data/studio.db`. Python's standard library speaks
it, so there is no database server and no new package. A minute of 24 kHz
mono speech is about 3 MB of WAV. Clips in this project are usually
100–400 KB. Those fit in SQLite blobs. WAL mode lets the worker thread write
while HTTP requests read.

`voice-generator.toml` stays a file. The process reads the host, port, and
token before it opens the database. Model weights stay in the Hugging Face
cache. They are gigabytes and are not this user's data. The browser token in
`localStorage` stays in the browser.

`data/out` stays a folder. MCP `speak` writes a WAV there so the next tool
can open a path. That file is an export of a row, not the library itself.

## File

```text
data/studio.db          the database (gitignored with the rest of data/)
data/studio.db-wal      SQLite write-ahead log, while the process is up
data/studio.db-shm
```

Open flags:

- `journal_mode = WAL`
- `foreign_keys = ON`
- `busy_timeout = 5000`

One connection per thread, or one shared connection guarded by the lock
`JobStore` already uses. The worker is the only writer of audio. Request
threads read, cancel, and delete.

## Layout

HTTP, the studio, and MCP talk to the engine. The engine's public objects
stay `JobStore` and `Library`. Those two call a storage layer, and only
that layer opens SQLite.

```text
HTTP / Studio / MCP
        |
        v
 Engine routes
        |
   +----+----+
   |         |
JobStore   Library
   |         |
   +----+----+
        |
        v
  voice_engine/storage
        |
        v
    data/studio.db
      schema_version
      metadata
      jobs
      outputs
      voices
      voice_versions        v4
      playgrounds           v4
      playground_runs       v4
      styles                v4
      narrations            v4
      templates
      template_samples
      favorites
```

```text
packages/engine/src/voice_engine/
  jobs.py                 JobStore. Queue, worker, generation.
  library.py              Library. Lock and speak against a voice.
  storage/
    database.py           Connection, WAL, transactions.
    migrations.py         schema_version scripts, applied in order.
    jobs.py               SQL for the jobs table.
    outputs.py            SQL for audio rows.
    voices.py             SQL for voices (metadata; audio lives in versions).
    library_tables.py     Playgrounds, Versions, Styles, Narrations.
    schema_v4.py          v4 DDL, built-in styles, backfill from v3 rows.
    templates.py          SQL for voice recipes and their samples.
    favorites.py          SQL for the profile shelf.
```

`JobStore.get` and `Library.create` do not contain SQL. A later schema,
search, cleanup, or backup changes the storage package. Routes stay put.

```python
class JobStore:
    def __init__(self, storage):
        self.storage = storage

    def get(self, job_id):
        return self.storage.jobs.get(job_id)

    def list(self, **filters):
        return self.storage.jobs.list(**filters)

    def delete(self, job_id):
        return self.storage.jobs.delete(job_id)
```

## Tables

`schema_version` is a single integer, starting at 1. Later changes are
numbered scripts in `storage/migrations.py`, applied once, in order, before
anything else runs.

`metadata` records facts about the database that are not schema versions.
The legacy import flag lives here. An empty `jobs` table is not a signal:
someone may have deleted every job on purpose.

```sql
CREATE TABLE metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

After the first successful import of the old folders:

```text
legacy_import_v1 = complete
```

### jobs

One row per design, lock, or speak job. This is today's `job.json` without
the `outputs` list.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text, primary key | `job_YYYYMMDDTHHMMSS_<hex>`, unchanged |
| `type` | text | `design`, `lock`, or `speak` |
| `status` | text | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| `spec` | text | JSON object. The request body as stored today |
| `backend` | text, nullable | `mlx`, `cuda`, or `fake` |
| `created_at` | text | ISO 8601 UTC |
| `started_at` | text, nullable | |
| `finished_at` | text, nullable | |
| `applied` | text | JSON array of setting names the backend used |
| `deferred` | text | JSON array of setting names the backend ignored |
| `voice_id` | text, nullable | plain text. The voice used for a lock or a speak. Not a foreign key |
| `error` | text, nullable | |

Index `(status, created_at)` for the queue and the activity list.

### outputs

One row per WAV. Design jobs have `candidate-01.wav` and so on. Speak jobs
have `audio.wav`. Lock jobs have none.

| Column | Type | Notes |
| --- | --- | --- |
| `job_id` | text | references `jobs(id)` on delete cascade. The job owns these files |
| `name` | text | `candidate-01.wav` or `audio.wav` |
| `seed` | integer, nullable | |
| `sample_rate` | integer | 24000 |
| `checks` | text | JSON. Duration, peak, RMS, warnings. Same object as today |
| `audio` | blob | zlib-compressed WAV bytes |
| `nbytes` | integer | size of `audio` after compression |

Primary key `(job_id, name)`.

### voices

One row per locked voice. Replaces the voice folder.

| Column | Type | Notes |
| --- | --- | --- |
| `voice_id` | text, primary key | immutable, same pattern as today |
| `name` | text | display name |
| `notes` | text, nullable | |
| `created_at` | text | |
| `language` | text | |
| `from_job` | text | plain text. The design job id at lock time. Not a foreign key |
| `candidate` | integer | 1-based candidate index |
| `seed` | integer, nullable | |
| `design_backend` | text, nullable | |
| `sample_rate` | integer | |
| `preview` | text | the preview script, today's `preview.txt` |
| `instruct` | text | the voice description, today's `instruct.txt` |
| `master` | blob | zlib-compressed `master.wav` |
| `prompt` | blob, nullable | raw `voice_prompt.pt` bytes. Torch backends (CUDA, CPU) only. Null on Mac until a torch run builds it |

Voice ids stay permanent. Version 4 moved the audio into `voice_versions`
and added to this row: `playground_id`, `origin_job_id`, `origin_candidate`,
`current_version_id`, `favorite`, `archived`, `copied_from`. `master` and
`prompt` remain for rows written before v4 and are no longer read; the
current version's blobs are. `PATCH` may change `name`, `notes`,
`favorite`, `archived`, and `current_version_id` (which must belong to the
voice).

## Version 4: playgrounds, versions, styles, narrations

Schema version 4 adds the tables behind the dashboard's Playground, Refine,
and Studio pages. The DDL and the built-in styles are in
`storage/schema_v4.py`; `migrations.py` applies it after v3.

```text
playgrounds ──< playground_runs >── jobs (design)
voices ──< voice_versions (tree through parent_version_id)
styles
narrations ── voices, voice_versions, styles, jobs (render)
```

### playgrounds and playground_runs

| Column | Notes |
| --- | --- |
| `playgrounds.id` | `pg_<timestamp>_<hex>` |
| `name`, `notes`, `template_id` | the template a playground started from, if any |
| `config` | JSON draft: instruct, text, language, candidates, seed_start, params |
| `copied_from` | the playground this was copied from |
| `playground_runs.id` | `run_<timestamp>_<hex>` |
| `playground_id` | cascades on playground delete |
| `run_no` | 1, 2, 3… unique per playground |
| `job_id` | the design job; cascades on job delete |
| `config` | the config as submitted, frozen |

Deleting a playground deletes its runs and leaves the voices kept from it;
their `playground_id` becomes null.

### voice_versions

| Column | Notes |
| --- | --- |
| `id` | `<voice_id>@<version_no>` |
| `voice_id` | cascades on voice delete |
| `version_no` | 1 is the kept take |
| `parent_version_id` | null for version 1 |
| `kind` | `original` for the kept take and for version 1 of a copy |
| `label` | free text, editable |
| `sample_rate`, `duration_s` | |
| `audio` | zlib-compressed WAV |
| `prompt` | torch prompt bytes, built on first use by a torch backend |
| `ref_text` | the text that audio speaks (the design sample) |
| `edits` | JSON, empty for a kept take |
| `job_id` | the lock job |

### styles

One row per narration preset. `builtin = 1` rows are seeded (narration,
comedy, commercial, kids) and refuse `PATCH` and `DELETE`. A style in use
by any narration refuses `DELETE`. Fields: `temperature`, `pause_comma_s`,
`pause_period_s`, `pause_paragraph_s`, `loudness_dbfs`, `crossfade_s`,
`emotion`, `copied_from`.

### narrations

| Column | Notes |
| --- | --- |
| `id` | `nar_<timestamp>_<hex>` |
| `title`, `notes` | editable at any time |
| `voice_id`, `version_id`, `style_id` | `ON DELETE RESTRICT`: a voice or style in use cannot be deleted |
| `script`, `language`, `params`, `seed` | editable while `status = draft` |
| `status` | `draft`, `rendering`, `rendered`, `failed` |
| `job_id` | the render job; `SET NULL` when the job is deleted |
| `copied_from` | |

Deleting a narration deletes its render job and that job's audio. Deleting
one that is rendering is refused.

### Migration and backfill

`upgrade_v4` creates the tables, adds the new voice columns and
`jobs.version_id`, seeds the built-in styles, then backfills:

- each voice gets `<voice_id>@1` from its `master`, `prompt`, and `preview`,
  and becomes current;
- each row in `favorites` sets `voices.favorite = 1`;
- each design job gets a playground `pg_<job_id>` with one run, and the
  voices locked from that job point at it.

The backfill is idempotent and also runs after the legacy folder import, so
a database created from `data/jobs` and `data/voices` ends up in the same
shape as a fresh one.

## Ownership and history

Cascade deletion only where one row owns another.

```text
jobs
  |
  +-- outputs     the job owns its WAVs. ON DELETE CASCADE
```

These two links are history. They stay plain `TEXT`, with no foreign key, so
deleting one side does not delete or null the other.

```text
voices.from_job  ---->  the design job id at the time of the lock
jobs.voice_id    ---->  the voice id used when that job ran
```

Deleting a voice removes the voice row. A later speak for that id is "not
found". Old speak jobs remain, still carrying that `voice_id`. Deleting a
design job removes that job and its candidate WAVs. A voice locked from it
remains, and `from_job` still holds the original id.

### presets

Placeholder from version 1. The running schema drops it and uses
`templates`, `template_samples`, and `favorites`, described in
[templates.md](templates.md).

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text, primary key | |
| `name` | text | |
| `kind` | text | `design` or `speak` |
| `params` | text | JSON. temperature, top-p, top-k, repetition penalty, max tokens, speed |
| `updated_at` | text | |

## Audio bytes

The engine still builds a WAV in memory with the current `write_wav` path,
then stores `zlib.compress(wav_bytes, level=6)`. A download reads the blob,
decompresses it, and responds with `audio/wav` and the same
`Content-Disposition` as today. Callers never see the compression.

The torch prompt is stored as the bytes `torch.save` would have written.
`torch.load` reads those bytes from a buffer. It is not compressed, because
it is already a packed tensor and it is only present on CUDA and CPU locks.

## What the engine does

`JobStore` and `Library` keep the methods the routes already call: submit,
get, list, cancel, file download, voice create, voice get, voice list.
They pass those calls to `storage`. The worker still generates audio. The
storage package writes the rows.

Restart behavior stays the same. On startup, a job left `running` becomes
`failed` with `interrupted by restart`. Jobs left `queued` go back on the
worker queue.

Speak still needs the reference text and the master audio (and, on CUDA and CPU, the
prompt). The library returns those from the row. The backend can keep
receiving a temporary directory for the duration of one call if that is the
smallest change to `mlx` and `cuda`. The temporary directory is deleted when
the call returns. It is not the stored voice.

Delete, which the folders make awkward, is two storage calls:

- Delete a job that is not `running`. Cascade removes its output rows. A
  running job cannot be deleted. Cancelling a `queued` job stays as it is.
  A voice whose `from_job` names this id is left alone.
- Delete a voice. Speak jobs whose `voice_id` names it stay in the activity
  list. A later speak for that id fails with "not found", as it does today
  for an unknown id.

Those two deletes are `DELETE /v1/jobs/{id}/record` and
`DELETE /v1/voices/{id}`. `DELETE /v1/jobs/{id}` stays "cancel a queued job",
which the studio already calls. Existing request bodies and response JSON
stay the same. The studio proxy forwards `/v1/*`, so the new routes are
reachable without a studio change. The page does not grow a delete button
in this change.

## Import

Startup does not look at whether `jobs` is empty. Deleting every job would
make it empty again, and the next start would copy the old folders back.

```text
open database
    |
    v
apply schema migrations
    |
    v
metadata["legacy_import_v1"]
    |
    +-- complete --> skip
    |
    +-- missing --> import data/jobs and data/voices
                        |
                        v
                   one transaction
                        |
                        v
                   legacy_import_v1 = complete
```

The import reads `data/jobs/*/job.json` and `data/voices/*/`. For each job
folder: insert the job row, then one output row per WAV named in `outputs`,
compressed. For each voice folder: insert the row from `voice.json`,
`preview.txt`, `instruct.txt`, `master.wav`, and `voice_prompt.pt` when that
file exists.

That work and the metadata write are one transaction. If it fails, the
transaction rolls back, the marker stays absent, and the folders are still
the source. After the marker is committed, `data/jobs` and `data/voices`
are removed. The engine does not write those folders again. `data/out`
is left alone.

Missing folders count as an empty import: the marker is still set, so a
fresh install does not wait forever for directories that were never there.

## Tests

The fake-backend API tests keep using a temporary data directory. They
assert the same HTTP results and also that a succeeded design has compressed
rows, a download decompresses to a valid WAV, a restart marks a `running`
job failed, and deleting a voice removes the row without removing old speak
jobs. Deleting a design job leaves a voice that names it in `from_job`.

One fixture test builds a tiny `data/jobs` and `data/voices` tree, starts
the store, and checks the rows match the files and that
`legacy_import_v1` is `complete`. A second open, after a new folder is
dropped beside the database, does not import it again.

`test_library_tables.py` covers the v4 classes directly: playground runs
and copy, the version tree and current-version rule, built-in style
freezing and in-use deletes, narration edit rules and the rendering guard.
`test_library_api.py` runs the same rules over HTTP with the fake backend.

```bash
uv run --project packages/engine --extra dev pytest packages/engine/tests
```

## Out of scope

- Model weights, `voice-generator.toml`, and the browser token.
- Replacing `data/out` for MCP. The tool still writes a WAV for the agent.
- Accounts, remote replication, or more than one database file.
- Changing generation, quality checks, or the job state machine.
