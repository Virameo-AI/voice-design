from __future__ import annotations

import shutil
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from voice_engine.catalog import ensure_catalog
from voice_engine.storage.favorites import Favorites
from voice_engine.storage.jobs import Jobs
from voice_engine.storage.legacy import import_legacy
from voice_engine.storage.migrations import migrate
from voice_engine.storage.outputs import Outputs
from voice_engine.storage.templates import Templates
from voice_engine.storage.voices import Voices


class Storage:
    """One SQLite file. JobStore and Library are the only callers."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "studio.db"
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        migrate(self)
        imported = import_legacy(self)
        self.jobs = Jobs(self)
        self.outputs = Outputs(self)
        self.voices = Voices(self)
        self.templates = Templates(self)
        self.favorites = Favorites(self)
        ensure_catalog(self)
        if imported:
            for name in ("jobs", "voices"):
                shutil.rmtree(data_dir / name, ignore_errors=True)

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                yield self.conn
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self.conn.execute(sql, params))

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.transaction() as conn:
            conn.execute(sql, params)

    def metadata(self, key: str) -> str | None:
        rows = self.query("SELECT value FROM metadata WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    def set_metadata(self, key: str, value: str, conn: sqlite3.Connection | None = None) -> None:
        sql = "INSERT INTO metadata (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        if conn is None:
            self.execute(sql, (key, value))
        else:
            conn.execute(sql, (key, value))


def open_storage(data_dir: Path) -> Storage:
    return Storage(data_dir)
