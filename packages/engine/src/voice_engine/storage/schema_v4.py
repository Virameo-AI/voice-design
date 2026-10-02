"""Version 4: playgrounds, voice versions, styles, narrations.

Drafts are editable rows. Snapshots are frozen when a job is queued. Audio for
takes and narration beats stays in outputs; a voice version holds its own master.
"""

V4_SQL = """
CREATE TABLE IF NOT EXISTS playgrounds (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    notes       TEXT,
    template_id TEXT,
    config      TEXT NOT NULL,
    copied_from TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS playground_runs (
    id            TEXT PRIMARY KEY,
    playground_id TEXT NOT NULL REFERENCES playgrounds(id) ON DELETE CASCADE,
    run_no        INTEGER NOT NULL,
    job_id        TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    config        TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE (playground_id, run_no)
);

CREATE TABLE IF NOT EXISTS voice_versions (
    id                TEXT PRIMARY KEY,
    voice_id          TEXT NOT NULL REFERENCES voices(voice_id) ON DELETE CASCADE,
    version_no        INTEGER NOT NULL,
    parent_version_id TEXT REFERENCES voice_versions(id) ON DELETE SET NULL,
    kind              TEXT NOT NULL,
    label             TEXT,
    sample_rate       INTEGER NOT NULL,
    duration_s        REAL,
    audio             BLOB NOT NULL,
    prompt            BLOB,
    ref_text          TEXT NOT NULL,
    edits             TEXT NOT NULL DEFAULT '{}',
    job_id            TEXT,
    created_at        TEXT NOT NULL,
    UNIQUE (voice_id, version_no)
);

CREATE TABLE IF NOT EXISTS styles (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    builtin           INTEGER NOT NULL DEFAULT 0,
    temperature       REAL NOT NULL,
    pause_comma_s     REAL NOT NULL,
    pause_period_s    REAL NOT NULL,
    pause_paragraph_s REAL NOT NULL,
    loudness_dbfs     REAL NOT NULL,
    crossfade_s       REAL NOT NULL,
    emotion           TEXT,
    copied_from       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS narrations (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    notes        TEXT,
    voice_id     TEXT NOT NULL REFERENCES voices(voice_id) ON DELETE RESTRICT,
    version_id   TEXT NOT NULL REFERENCES voice_versions(id) ON DELETE RESTRICT,
    style_id     TEXT NOT NULL REFERENCES styles(id) ON DELETE RESTRICT,
    script       TEXT NOT NULL,
    language     TEXT NOT NULL,
    params       TEXT NOT NULL DEFAULT '{}',
    seed         INTEGER NOT NULL DEFAULT 1,
    status       TEXT NOT NULL DEFAULT 'draft',
    job_id       TEXT REFERENCES jobs(id) ON DELETE SET NULL,
    copied_from  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS narrations_voice ON narrations (voice_id, created_at);
CREATE INDEX IF NOT EXISTS runs_playground ON playground_runs (playground_id, run_no);
"""

VOICE_COLUMNS = {
    "playground_id": "TEXT",
    "origin_job_id": "TEXT",
    "origin_candidate": "INTEGER",
    "current_version_id": "TEXT",
    "favorite": "INTEGER NOT NULL DEFAULT 0",
    "archived": "INTEGER NOT NULL DEFAULT 0",
    "copied_from": "TEXT",
}

BUILTIN_STYLES = [
    ("narration", "Narration", 0.7, 0.15, 0.35, 0.7, -20.0, 0.02, None),
    ("comedy", "Comedy", 0.95, 0.1, 0.28, 0.45, -18.0, 0.015, "excited"),
    ("commercial", "Commercial", 0.65, 0.12, 0.3, 0.4, -16.0, 0.02, "calm"),
    ("kids", "Kids", 0.85, 0.18, 0.4, 0.6, -18.0, 0.02, "happy"),
]


def upgrade_v4(conn, now: str) -> None:
    conn.executescript(V4_SQL)
    names = {row[1] for row in conn.execute("PRAGMA table_info(voices)")}
    for column, ddl in VOICE_COLUMNS.items():
        if column not in names:
            conn.execute(f"ALTER TABLE voices ADD COLUMN {column} {ddl}")
    job_names = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
    if "version_id" not in job_names:
        conn.execute("ALTER TABLE jobs ADD COLUMN version_id TEXT")
    for style in BUILTIN_STYLES:
        conn.execute(
            """
            INSERT OR IGNORE INTO styles (
                id, name, builtin, temperature, pause_comma_s, pause_period_s, pause_paragraph_s,
                loudness_dbfs, crossfade_s, emotion, created_at, updated_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*style, now, now),
        )
    backfill(conn)


def backfill(conn) -> None:
    """Idempotent: give every voice a version 1 and every design job a playground."""
    rows = list(conn.execute("SELECT voice_id, from_job, candidate, created_at, sample_rate, master, prompt, preview FROM voices"))
    for row in rows:
        version_id = f"{row['voice_id']}@1"
        exists = conn.execute("SELECT 1 FROM voice_versions WHERE id = ?", (version_id,)).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO voice_versions (
                id, voice_id, version_no, parent_version_id, kind, label, sample_rate, duration_s,
                audio, prompt, ref_text, edits, job_id, created_at
            ) VALUES (?, ?, 1, NULL, 'original', 'Original', ?, NULL, ?, ?, ?, '{}', ?, ?)
            """,
            (version_id, row["voice_id"], row["sample_rate"], row["master"], row["prompt"], row["preview"], row["from_job"], row["created_at"]),
        )
        conn.execute(
            "UPDATE voices SET current_version_id = ?, origin_job_id = ?, origin_candidate = ? WHERE voice_id = ?",
            (version_id, row["from_job"], row["candidate"], row["voice_id"]),
        )
    # Favorites fold into the voice row.
    conn.execute("UPDATE voices SET favorite = 1 WHERE voice_id IN (SELECT voice_id FROM favorites)")
    # Each earlier design job becomes a playground with one run.
    designs = list(conn.execute("SELECT id, spec, created_at FROM jobs WHERE type = 'design'"))
    for design in designs:
        linked = conn.execute("SELECT 1 FROM playground_runs WHERE job_id = ?", (design["id"],)).fetchone()
        if linked:
            continue
        playground_id = f"pg_{design['id']}"
        conn.execute(
            "INSERT OR IGNORE INTO playgrounds (id, name, notes, template_id, config, copied_from, created_at, updated_at) VALUES (?, ?, NULL, NULL, ?, NULL, ?, ?)",
            (playground_id, f"Design {design['id'][-6:]}", design["spec"], design["created_at"], design["created_at"]),
        )
        conn.execute(
            "INSERT INTO playground_runs (id, playground_id, run_no, job_id, config, created_at) VALUES (?, ?, 1, ?, ?, ?)",
            (f"run_{design['id']}", playground_id, design["id"], design["spec"], design["created_at"]),
        )
        conn.execute("UPDATE voices SET playground_id = ? WHERE from_job = ? AND playground_id IS NULL", (playground_id, design["id"]))
