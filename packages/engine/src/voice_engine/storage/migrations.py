from __future__ import annotations

# Version 1, kept so an existing studio.db can be upgraded in place.
V1_SQL = """
CREATE TABLE schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE jobs (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    status      TEXT NOT NULL,
    spec        TEXT NOT NULL,
    backend     TEXT,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT,
    applied     TEXT NOT NULL,
    deferred    TEXT NOT NULL,
    voice_id    TEXT,
    error       TEXT,
    progress    TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX jobs_status_created ON jobs (status, created_at);

CREATE TABLE outputs (
    job_id      TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    seed        INTEGER,
    sample_rate INTEGER NOT NULL,
    checks      TEXT NOT NULL,
    audio       BLOB NOT NULL,
    nbytes      INTEGER NOT NULL,
    PRIMARY KEY (job_id, name)
);

CREATE TABLE voices (
    voice_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    notes           TEXT,
    created_at      TEXT NOT NULL,
    language        TEXT NOT NULL,
    from_job        TEXT NOT NULL,
    candidate       INTEGER NOT NULL,
    seed            INTEGER,
    design_backend  TEXT,
    sample_rate     INTEGER NOT NULL,
    preview         TEXT NOT NULL,
    instruct        TEXT NOT NULL,
    master          BLOB NOT NULL,
    prompt          BLOB
);

CREATE TABLE presets (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    params      TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

TEMPLATES_SQL = """
CREATE TABLE templates (
    id          TEXT PRIMARY KEY,
    origin      TEXT NOT NULL,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL,
    notes       TEXT,
    instruct    TEXT NOT NULL,
    text        TEXT NOT NULL,
    language    TEXT NOT NULL,
    candidates  INTEGER NOT NULL,
    seed_start  INTEGER NOT NULL,
    params      TEXT NOT NULL,
    sort_order  INTEGER NOT NULL,
    created_at  TEXT,
    updated_at  TEXT
);

CREATE TABLE template_samples (
    template_id TEXT PRIMARY KEY REFERENCES templates(id) ON DELETE CASCADE,
    seed        INTEGER NOT NULL,
    sample_rate INTEGER NOT NULL,
    audio       BLOB NOT NULL,
    nbytes      INTEGER NOT NULL
);

CREATE TABLE favorites (
    voice_id   TEXT PRIMARY KEY REFERENCES voices(voice_id) ON DELETE CASCADE,
    note       TEXT,
    created_at TEXT NOT NULL
);
"""

V2_SQL = V1_SQL.replace(
    """
CREATE TABLE presets (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    params      TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
""",
    TEMPLATES_SQL,
)

UPGRADE_V2 = "DROP TABLE IF EXISTS presets;\n" + TEMPLATES_SQL


def _version(storage) -> int:
    exists = storage.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if not exists:
        return 0
    row = storage.conn.execute("SELECT version FROM schema_version").fetchone()
    return int(row[0]) if row else 0


def migrate(storage) -> None:
    with storage._lock:
        version = _version(storage)
        if version == 0:
            storage.conn.executescript(V2_SQL)
            storage.conn.execute("INSERT INTO schema_version (version) VALUES (3)")
            storage.conn.commit()
            version = 3
            # Columns from version 3 are already in V1_SQL; fall through to version 4.
        elif version < 2:
            storage.conn.executescript(UPGRADE_V2)
            storage.conn.execute("UPDATE schema_version SET version = 2")
            storage.conn.commit()
            version = 2
        if version < 3:
            names = {row[1] for row in storage.conn.execute("PRAGMA table_info(jobs)")}
            if "progress" not in names:
                storage.conn.execute("ALTER TABLE jobs ADD COLUMN progress TEXT NOT NULL DEFAULT '{}'")
            storage.conn.execute("UPDATE schema_version SET version = 3")
            storage.conn.commit()
            version = 3
        if version < 4:
            from datetime import datetime, timezone

            from voice_engine.storage.schema_v4 import upgrade_v4

            upgrade_v4(storage.conn, datetime.now(timezone.utc).isoformat(timespec="seconds"))
            storage.conn.execute("UPDATE schema_version SET version = 4")
            storage.conn.commit()
        storage.conn.execute("PRAGMA foreign_keys=ON")
