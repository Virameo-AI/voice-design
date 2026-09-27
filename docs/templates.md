# Templates and profile

This is how saved voice recipes and the profile shelf work. The engine and
the studio both run it.

Creating a voice already stores a full recipe on the design job: description,
preview script, language, candidate count, first seed, and the model
settings. That recipe disappears from the form when Activity is cleared, and
the only way back is "reuse" on a job that still exists. A locked voice is
the audio that came out. It is not the recipe, and My voices has no way to
mark the few that should stay easy to find.

Two new things, kept apart:

- A **template** is a tested voice configuration: the Create settings, plus
  one sample clip of that voice reading a short line. The user plays the
  sample before generating anything. Loading the template fills the Create
  form. They can change the seed, the candidate count, or any other field,
  then generate as they do today.
- A **profile** entry is a locked voice the user has marked as a keeper. It
  is a row in its own table. It does not copy the audio.

This app stays one local user. Profile is that user's shelf, not an account.

The current page stays. The warm layout, the hero, and the candidate player
are unchanged. Templates are a gallery added above the Create form.

## What a template stores

The same fields `POST /v1/jobs` already accepts for `type: design`:

| Field | Meaning | Limits, unchanged |
| --- | --- | --- |
| `instruct` | Voice description | 1–2000 characters |
| `text` | Preview script every candidate reads | 1–1000 characters |
| `language` | Language | the studio list, default English |
| `candidates` | How many voices to generate | 1–8 |
| `seed_start` | First seed. Candidate n uses seed + n − 1 | integer ≥ 0 |
| `params` | Temperature, top-p, top-k, repetition penalty, max tokens | only the keys the user set. Empty means server defaults. Speed stays off for design |

A template also has a name, a one-line role, optional notes, an origin
(`builtin` or `user`), and timestamps.

It also has one **sample**: a single WAV of this configuration, made with
`seed_start` and the preview script. The sample is what the gallery plays.
It is not a locked voice, and it is not a design job. Loading the template
does not speak this file again. Generating still runs a new design job, so
a new seed or a new candidate count produces new takes.

The job's `spec` is a snapshot of what was submitted. Editing or deleting a
template later does not change past jobs, candidates, or locked voices.
Replacing a sample does not change a voice that was already locked.

Every catalog template reads the same preview line, so the gallery is a fair
comparison:

> Give it a second. Ordinary things get interesting when they refuse to behave the way we expect.

That is the line Create already uses. A user template may use a different
line, because it stores whatever script was on the form when it was saved.

The songwriter template is a person speaking with a musical sense of phrase.
The sample is speech, the same kind of clip as the others.

## The catalog

Sixteen built-in templates ship with the app. They replace the hard-coded
description Create shows on an empty form, and the four chips that only
append a phrase. The chips go away. Each built-in is English, asks for 4
candidates, and leaves model settings empty. The seeds are 100 apart, so a
later batch from the same template does not repeat the sample's seed.

| Name | Role | First seed |
| --- | --- | --- |
| Warm narrator | Adult narrator, warm low-mid voice, calm and curious, like a science explainer | 1000 |
| Documentary | Measured, clear, unhurried, the voice of a filmed essay | 1100 |
| Cinematic narrator | Low and wide, the voice in a trailer | 1200 |
| News anchor | Crisp, even, confident, no rush | 1300 |
| Podcast host | Close and conversational, talking to one person | 1400 |
| Storyteller | Slow, soft, a bedtime story told nearby | 1500 |
| Teacher | Patient and bright, explaining one idea at a time | 1600 |
| Commercial | Polished, friendly, an ad read with a smile | 1700 |
| Animated character | Expressive cartoon lead, big energy, clear diction | 1800 |
| Sidekick | Smaller, quicker, playful, reacts more than it explains | 1900 |
| Songwriter | Young adult speaking with a lyrical, rhythmic cadence | 2000 |
| Vlogger | Casual, close, thinking out loud | 2100 |
| Sports commentator | Fast, excited, still easy to follow | 2200 |
| Mystery | Quiet, low, leaving room around the words | 2300 |
| Elder | Older, kind, unhurried, a story they have told before | 2400 |
| Villain | Controlled, cool, theatrical, never shouting | 2500 |

The description sentences live in
`packages/engine/src/voice_engine/catalog.py`. The page reads them from the
API, so the gallery and the form stay on the same words. Sixteen is the set
that ships. The table can grow or shrink inside ten to twenty without a
schema change.

Built-in rows are read-only. The user can open one, change anything, and
save that as their own template. They cannot rename, overwrite, or delete a
built-in, and they cannot replace its sample.

**User templates** are the configurations the user saves. They have the same
fields and the same kind of sample. The user renames them, edits them, and
deletes them.

## Where the samples come from

Built-in samples are made once, on this machine, while the feature is built.
For each catalog row the engine runs a one-candidate design at that row's
seed, using the shared preview line. The take that sounds like the role is
kept. Those WAVs are stored in the database and also packaged with the
engine, under the catalog module, so a new or emptied database gets the same
clips back on startup. Opening the app does not generate them again.

A user template gets its sample from a take the user already made. After a
design succeeds, Save as template can attach the selected candidate. That
copies the WAV into the template. It does not run the model a second time.
A template saved from the form alone has no sample yet. The card says so,
and Replace sample appears once a later design has a take to attach.

Duplicate copies the sample as well as the settings, so the copy can be
played immediately. Editing the description does not regenerate the sample.
The card keeps playing the saved take until the user replaces it.

## Hearing them, then loading one

The gallery sits at the top of Create, under the hero and above the form.
The heading is Templates. A "See all" control opens the Templates tab.

```text
hero                         unchanged
        |
        v
template gallery             play a sample, or load the recipe
        |
        v
Create form                  filled from the chosen template
        |
        v
user edits seed, count, wording
        |
        v
Generate voice previews      existing design job
        |
        v
listen, lock one             existing lock
        |
        +-- stays in My voices
        |
        +-- optional: add to profile
```

Each card shows the name, the one-line role, a Default or Yours tag, and the
same waveform player used everywhere else. The shape comes from the sample
WAV. Color still comes from the sample's seed. One clip plays at a time.
Nothing autoplays. A card with no sample yet shows the name and the role,
and the player is absent.

Clicking the card loads that template into the form and scrolls to it.
Pressing play does not load it and does not start a job. The loaded card
stays highlighted.

The gallery is a horizontal row. Built-ins come first, in the order above,
then the user's templates by name. On a phone the row still scrolls sideways,
so sixteen cards do not push the form down the page.

Loading a template does not start a job. Generate still requires a
description and a preview script, and it still returns a job to poll.

Two small actions sit next to the seed field once a template is loaded:

- **New seed** sets the first seed to the saved seed plus the candidate
  count, so the next batch does not repeat the sample or the previous seeds.
  It does not write the template.
- **Save template** writes the form as it is now, under a name the user
  types. If a candidate is selected, that take is stored as the sample. If
  the form was loaded from a built-in, this always creates a user template.
  If it was loaded from a user template, the user chooses Update or Save as
  new.

The Templates tab lists the same cards in a wrapping grid, with rename,
edit, duplicate, delete, and replace sample. Create is the place to listen
and load. The tab is the place to manage a longer list.

## Profile

A locked voice already lives in `voices`, with its reference audio. Profile
is a second list of those voices: the ones the user wants in front.

```text
voices                         favorites
  voice_id  <---- owns ----    voice_id
  name, language, seed         created_at
  master audio, preview        note, optional
```

Adding to profile inserts one `favorites` row. It does not copy `master` or
the recipe. Taking a voice off the profile deletes that row. The voice
stays in My voices and can still speak.

Deleting the voice deletes the profile row with it. The profile mark belongs
to the voice.

Old jobs are left alone. A speak job that used the voice still shows in
Activity after the voice is deleted, as it does today.

The user can add a voice to the profile from My voices, and from the save
step on Create after a lock succeeds. Profile itself only lists favorites.
Each card plays the same reference clip, shows the voice id, language, and
seed, and offers Speak (the existing My voices form, opened on that voice)
and Remove from profile.

An empty profile says the shelf is empty and points at My voices.

There is no login and no second user. "My profile" is the name of this list.

A template sample and a profile voice are different. The sample is a preview
of a recipe. The profile entry is a locked voice the user can speak with
again.

## Where it sits in the page

The nav gains two tabs, after the three that exist:

| Tab | What it shows |
| --- | --- |
| Create | The hero, then the template gallery, then the form |
| My voices | Every locked voice, with an add-to-profile control |
| Activity | Unchanged |
| Templates | Built-ins, then user templates, each with its sample |
| Profile | Favorite voices only |

The page keeps the current warm palette, the scrolling layout, and the
candidate player. Phone width stays usable: the nav already wraps, and the
gallery scrolls sideways under 600px.

## Database

`schema_version` moves from 1 to 2. The migration runs once, in order,
before the app serves requests. Version 1 databases already exist
(`data/studio.db`). The script adds tables, inserts the sixteen built-in
rows, and loads their packaged samples. It does not import folders and it
does not touch jobs, outputs, or voices.

The `presets` table from version 1 was a placeholder for model numbers only.
It is empty and unused. Version 2 drops it. A new database is created at
version 2 directly, so it never contains `presets`.

`storage/migrations.py` has to apply numbered steps. Today it creates
version 1 and then returns because the version table exists. That return is
what this change replaces with "apply every missing version."

On every startup after that, the engine checks the catalog. A missing
built-in row is inserted again. A missing sample blob is filled from the
packaged WAV. Existing user templates are left alone. Clearing the database
brings the sixteen samples back. It does not bring user templates back.

### templates

Built-ins and user templates live in this table. The text of a built-in is
defined in the catalog module. The row is the copy the API reads.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | text, primary key | `builtin-warm-narrator`, or `tpl_` plus a short id. Not a voice id |
| `origin` | text | `builtin` or `user` |
| `name` | text | required, trimmed, 1–80 characters |
| `role` | text | one line for the card, max 120 characters |
| `notes` | text, nullable | |
| `instruct` | text | the voice description |
| `text` | text | the preview script |
| `language` | text | |
| `candidates` | integer | 1–8 |
| `seed_start` | integer | ≥ 0 |
| `params` | text | JSON object, same shape as a design job's `params` |
| `sort_order` | integer | catalog order for built-ins. User rows sort by name |
| `created_at` | text, nullable | null for a built-in |
| `updated_at` | text, nullable | set on edit of a user template |

No foreign key to jobs or voices. A template does not own either.

### template_samples

One sample clip per template. The template owns it.

| Column | Type | Notes |
| --- | --- | --- |
| `template_id` | text, primary key | references `templates(id)` on delete cascade |
| `seed` | integer | the seed this clip was made with |
| `sample_rate` | integer | 24000 |
| `audio` | blob | zlib-compressed WAV, same as job outputs |
| `nbytes` | integer | size of `audio` after compression |

```text
jobs
  |
  +-- outputs            unchanged. The job owns its WAVs

templates
  |
  +-- template_samples   the template owns its preview clip

voices
  |
  +-- favorites          the profile mark belongs to the voice
```

`voices.from_job` and `jobs.voice_id` stay plain text, as they are now.
Templates do not point at either. A sample copied from a design candidate
is a new blob. Deleting that job later does not remove the sample.

## API

The studio proxy already forwards `/v1/*`. These routes are engine routes.
Generation, lock, and speak request bodies stay the same. Downloads of a
sample are `audio/wav`, the same as a candidate download.

### Templates

`GET /v1/templates`

Returns built-ins first, in catalog order, then user templates by name.
Each item:

```json
{
  "id": "builtin-warm-narrator",
  "name": "Warm narrator",
  "role": "Adult narrator, warm low-mid voice, calm and curious",
  "origin": "builtin",
  "notes": null,
  "instruct": "...",
  "text": "Give it a second. Ordinary things get interesting when they refuse to behave the way we expect.",
  "language": "English",
  "candidates": 4,
  "seed_start": 1000,
  "params": {},
  "has_sample": true,
  "sample_url": "/v1/templates/builtin-warm-narrator/sample",
  "created_at": null,
  "updated_at": null
}
```

A user item has `"origin": "user"`, an id starting with `tpl_`, and
timestamps. `has_sample` is false and `sample_url` is null until a take is
attached.

`POST /v1/templates` creates a user template from that body, without `id`,
`origin`, timestamps, or sample fields. Optional `from_job` and `candidate`
copy that candidate's WAV in as the sample during the same call. `201` and
the stored row. An unknown job or a missing candidate is `404`, and the
template is not created.

`GET /v1/templates/{id}` returns one. Unknown id is `404`.

`GET /v1/templates/{id}/sample` returns the WAV. `404` when the template is
unknown or has no sample. `Content-Type` is `audio/wav`.

`PATCH /v1/templates/{id}` updates a user template's text fields. It does
not change the sample. A builtin id is `409`.

`PUT /v1/templates/{id}/sample` replaces a user template's sample. Body
`{ "from_job": "...", "candidate": 1 }`. A builtin id is `409`.

`DELETE /v1/templates/{id}` deletes a user template and its sample. `204`.
A builtin id is `409`.

`POST /v1/templates/{id}/duplicate` copies a built-in or a user template,
including the sample, into a new user row. Optional body `{ "name": "..." }`.
Without a name, the copy is named `"<original> copy"`. `201`.

There is no "apply" route. The page posts the filled form to the existing
design endpoint.

### Profile

`GET /v1/favorites` returns the profile, newest first. Each item is the
favorite row plus the voice fields My voices already shows (`name`,
`language`, `seed`, `created_at` of the voice, `notes` of the voice). The
favorite's own note is `profile_note`, so the two notes are not mixed.

`PUT /v1/favorites/{voice_id}` adds the voice, or updates `note` if it is
already there. Body `{ "note": "..." }` or `{}`. Unknown voice is `404`.
`200` with the item.

`DELETE /v1/favorites/{voice_id}` removes it from the profile. `204` when it
was there, `404` when it was not. The voice row remains.

## What does not change

- Design, lock, and speak jobs, their statuses, and the quality checks.
- Candidate audio, the waveform, and the one-clip-at-a-time player. Template
  samples use that same player.
- `DELETE /v1/jobs/{id}` still cancels a queued job. `DELETE /v1/jobs/{id}/record`
  still removes a finished job. `DELETE /v1/voices/{id}` still removes a voice,
  and now also drops its profile row.
- MCP `data/out`, and the MCP tools. Templates and profile are studio
  features in this change. An agent can still design, lock, and speak.
- The browser token, `voice-generator.toml`, and model weights.

## Tests

The fake-backend API tests cover:

- A new database is version 2, has no `presets` table, and has the sixteen
  built-in rows.
- A version 1 database gains `templates`, `template_samples`, and
  `favorites`, loses `presets`, and keeps an existing voice row.
- Each built-in sample decompresses to a WAV that starts with `RIFF`. The
  test fixture uses a tiny packaged WAV, not a model.
- Startup with a built-in row deleted inserts that row and its sample again,
  and does not duplicate the ones still present.
- Create, update, duplicate, and delete a user template. Duplicate keeps
  `has_sample` when the source had one.
- Create with `from_job` and `candidate` stores that candidate's bytes as
  the sample. Deleting the job leaves the sample in place.
- Delete and patch of a builtin id return `409`, and replacing its sample
  returns `409`.
- Submit a design whose body matches a template. The job spec equals that
  body. Deleting a user template leaves the job.
- Add a locked voice to the profile, list it, remove it, and see the voice
  still in `GET /v1/voices`.
- Delete the voice and see the favorites row gone.
- Add a favorite for an unknown voice id and get `404`.
