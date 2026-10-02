"""Playgrounds, voice versions, styles, and narrations."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from voice_engine.storage.blobs import compress, decompress


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{secrets.token_hex(3)}"


def _row(row, json_keys=()) -> dict:
    data = dict(row)
    for key in json_keys:
        if key in data and isinstance(data[key], str):
            data[key] = json.loads(data[key])
    for key in ("favorite", "archived", "builtin"):
        if key in data and data[key] is not None:
            data[key] = bool(data[key])
    return data


class Playgrounds:
    JSON = ("config",)

    def __init__(self, storage) -> None:
        self.storage = storage

    def create(self, name: str, config: dict, notes: str | None = None, template_id: str | None = None, copied_from: str | None = None) -> dict:
        stamp = now()
        playground_id = new_id("pg")
        self.storage.execute(
            "INSERT INTO playgrounds (id, name, notes, template_id, config, copied_from, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (playground_id, name, notes, template_id, json.dumps(config), copied_from, stamp, stamp),
        )
        return self.get(playground_id)

    def get(self, playground_id: str) -> dict | None:
        rows = self.storage.query("SELECT * FROM playgrounds WHERE id = ?", (playground_id,))
        if not rows:
            return None
        data = _row(rows[0], self.JSON)
        data["runs"] = self.runs(playground_id)
        return data

    def list(self, limit: int = 100) -> list[dict]:
        rows = self.storage.query("SELECT * FROM playgrounds ORDER BY updated_at DESC LIMIT ?", (limit,))
        items = []
        for row in rows:
            data = _row(row, self.JSON)
            data["run_count"] = int(self.storage.query("SELECT COUNT(*) AS n FROM playground_runs WHERE playground_id = ?", (row["id"],))[0]["n"])
            items.append(data)
        return items

    def update(self, playground_id: str, **fields) -> dict:
        allowed = {"name", "notes", "template_id", "config"}
        changes = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not self.get(playground_id):
            raise LookupError(playground_id)
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            values = [json.dumps(v) if k == "config" else v for k, v in changes.items()]
            self.storage.execute(f"UPDATE playgrounds SET {sets}, updated_at = ? WHERE id = ?", (*values, now(), playground_id))
        return self.get(playground_id)

    def copy(self, playground_id: str, name: str | None = None) -> dict:
        source = self.get(playground_id)
        if source is None:
            raise LookupError(playground_id)
        return self.create(name or f"{source['name']} copy", source["config"], source["notes"], source["template_id"], copied_from=playground_id)

    def delete(self, playground_id: str) -> None:
        with self.storage.transaction() as conn:
            conn.execute("UPDATE voices SET playground_id = NULL WHERE playground_id = ?", (playground_id,))
            cursor = conn.execute("DELETE FROM playgrounds WHERE id = ?", (playground_id,))
            if cursor.rowcount == 0:
                raise LookupError(playground_id)

    def add_run(self, playground_id: str, job_id: str, config: dict) -> dict:
        with self.storage.transaction() as conn:
            row = conn.execute("SELECT COALESCE(MAX(run_no), 0) + 1 AS n FROM playground_runs WHERE playground_id = ?", (playground_id,)).fetchone()
            run_id = new_id("run")
            conn.execute(
                "INSERT INTO playground_runs (id, playground_id, run_no, job_id, config, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, playground_id, row["n"], job_id, json.dumps(config), now()),
            )
            conn.execute("UPDATE playgrounds SET updated_at = ? WHERE id = ?", (now(), playground_id))
        return self.run(run_id)

    def run(self, run_id: str) -> dict | None:
        rows = self.storage.query("SELECT * FROM playground_runs WHERE id = ?", (run_id,))
        return _row(rows[0], self.JSON) if rows else None

    def runs(self, playground_id: str) -> list[dict]:
        rows = self.storage.query("SELECT * FROM playground_runs WHERE playground_id = ? ORDER BY run_no", (playground_id,))
        return [_row(row, self.JSON) for row in rows]

    def run_for_job(self, job_id: str) -> dict | None:
        rows = self.storage.query("SELECT * FROM playground_runs WHERE job_id = ?", (job_id,))
        return _row(rows[0], self.JSON) if rows else None


class Versions:
    JSON = ("edits",)

    def __init__(self, storage) -> None:
        self.storage = storage

    def add(
        self,
        voice_id: str,
        *,
        kind: str,
        audio: bytes,
        sample_rate: int,
        ref_text: str,
        duration_s: float | None = None,
        parent_version_id: str | None = None,
        label: str | None = None,
        prompt: bytes | None = None,
        edits: dict | None = None,
        job_id: str | None = None,
        make_current: bool = True,
    ) -> dict:
        with self.storage.transaction() as conn:
            row = conn.execute("SELECT COALESCE(MAX(version_no), 0) + 1 AS n FROM voice_versions WHERE voice_id = ?", (voice_id,)).fetchone()
            version_no = int(row["n"])
            version_id = f"{voice_id}@{version_no}"
            conn.execute(
                """
                INSERT INTO voice_versions (
                    id, voice_id, version_no, parent_version_id, kind, label, sample_rate, duration_s,
                    audio, prompt, ref_text, edits, job_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id, voice_id, version_no, parent_version_id, kind,
                    label or ("Original" if version_no == 1 else f"Version {version_no}"),
                    sample_rate, duration_s, compress(audio), prompt, ref_text,
                    json.dumps(edits or {}), job_id, now(),
                ),
            )
            if make_current:
                conn.execute("UPDATE voices SET current_version_id = ? WHERE voice_id = ?", (version_id, voice_id))
        return self.get(version_id)

    def get(self, version_id: str) -> dict | None:
        rows = self.storage.query(
            "SELECT id, voice_id, version_no, parent_version_id, kind, label, sample_rate, duration_s, ref_text, edits, job_id, created_at FROM voice_versions WHERE id = ?",
            (version_id,),
        )
        return _row(rows[0], self.JSON) if rows else None

    def list(self, voice_id: str) -> list[dict]:
        rows = self.storage.query(
            "SELECT id, voice_id, version_no, parent_version_id, kind, label, sample_rate, duration_s, ref_text, edits, job_id, created_at FROM voice_versions WHERE voice_id = ? ORDER BY version_no",
            (voice_id,),
        )
        return [_row(row, self.JSON) for row in rows]

    def audio(self, version_id: str) -> bytes | None:
        rows = self.storage.query("SELECT audio FROM voice_versions WHERE id = ?", (version_id,))
        return decompress(rows[0]["audio"]) if rows else None

    def prompt(self, version_id: str) -> bytes | None:
        rows = self.storage.query("SELECT prompt FROM voice_versions WHERE id = ?", (version_id,))
        return rows[0]["prompt"] if rows and rows[0]["prompt"] is not None else None

    def set_prompt(self, version_id: str, prompt: bytes) -> None:
        self.storage.execute("UPDATE voice_versions SET prompt = ? WHERE id = ?", (prompt, version_id))

    def relabel(self, version_id: str, label: str) -> dict:
        if self.get(version_id) is None:
            raise LookupError(version_id)
        self.storage.execute("UPDATE voice_versions SET label = ? WHERE id = ?", (label, version_id))
        return self.get(version_id)


class Styles:
    FIELDS = ("name", "temperature", "pause_comma_s", "pause_period_s", "pause_paragraph_s", "loudness_dbfs", "crossfade_s", "emotion")

    def __init__(self, storage) -> None:
        self.storage = storage

    def get(self, style_id: str) -> dict | None:
        rows = self.storage.query("SELECT * FROM styles WHERE id = ?", (style_id,))
        return _row(rows[0]) if rows else None

    def list(self) -> list[dict]:
        return [_row(row) for row in self.storage.query("SELECT * FROM styles ORDER BY builtin DESC, created_at")]

    def create(self, style_id: str, copied_from: str | None = None, **fields) -> dict:
        if self.get(style_id):
            raise FileExistsError(f"style {style_id} already exists")
        base = self.get(copied_from) if copied_from else None
        if copied_from and base is None:
            raise LookupError(copied_from)
        values = {k: fields.get(k, base.get(k) if base else None) for k in self.FIELDS}
        if values["name"] is None:
            values["name"] = style_id
        missing = [k for k, v in values.items() if v is None and k != "emotion"]
        if missing:
            raise ValueError(f"style needs {', '.join(missing)}")
        stamp = now()
        self.storage.execute(
            """
            INSERT INTO styles (id, name, builtin, temperature, pause_comma_s, pause_period_s, pause_paragraph_s, loudness_dbfs, crossfade_s, emotion, copied_from, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (style_id, values["name"], values["temperature"], values["pause_comma_s"], values["pause_period_s"], values["pause_paragraph_s"], values["loudness_dbfs"], values["crossfade_s"], values["emotion"], copied_from, stamp, stamp),
        )
        return self.get(style_id)

    def update(self, style_id: str, **fields) -> dict:
        style = self.get(style_id)
        if style is None:
            raise LookupError(style_id)
        if style["builtin"]:
            raise PermissionError("built-in styles stay as shipped. Copy one first.")
        changes = {k: v for k, v in fields.items() if k in self.FIELDS and (v is not None or k == "emotion")}
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            self.storage.execute(f"UPDATE styles SET {sets}, updated_at = ? WHERE id = ?", (*changes.values(), now(), style_id))
        return self.get(style_id)

    def delete(self, style_id: str) -> None:
        style = self.get(style_id)
        if style is None:
            raise LookupError(style_id)
        if style["builtin"]:
            raise PermissionError("built-in styles stay as shipped")
        used = self.storage.query("SELECT 1 FROM narrations WHERE style_id = ? LIMIT 1", (style_id,))
        if used:
            raise PermissionError("a narration uses this style. Delete or re-style those narrations first.")
        self.storage.execute("DELETE FROM styles WHERE id = ?", (style_id,))


class Narrations:
    JSON = ("params",)
    EDITABLE = {"title", "notes", "voice_id", "version_id", "style_id", "script", "language", "params", "seed"}
    AFTER_RENDER = {"title", "notes"}

    def __init__(self, storage) -> None:
        self.storage = storage

    def create(self, **fields) -> dict:
        stamp = now()
        narration_id = new_id("nar")
        self.storage.execute(
            """
            INSERT INTO narrations (id, title, notes, voice_id, version_id, style_id, script, language, params, seed, status, job_id, copied_from, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', NULL, ?, ?, ?)
            """,
            (
                narration_id, fields["title"], fields.get("notes"), fields["voice_id"], fields["version_id"], fields.get("style_id", "narration"),
                fields["script"], fields.get("language", "English"), json.dumps(fields.get("params") or {}),
                int(fields.get("seed", 1)), fields.get("copied_from"), stamp, stamp,
            ),
        )
        return self.get(narration_id)

    def get(self, narration_id: str) -> dict | None:
        rows = self.storage.query("SELECT * FROM narrations WHERE id = ?", (narration_id,))
        return _row(rows[0], self.JSON) if rows else None

    def list(self, voice_id: str | None = None, status: str | None = None, limit: int = 100) -> list[dict]:
        sql, params = "SELECT * FROM narrations WHERE 1 = 1", []
        if voice_id:
            sql += " AND voice_id = ?"
            params.append(voice_id)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        return [_row(row, self.JSON) for row in self.storage.query(sql, tuple(params))]

    def update(self, narration_id: str, **fields) -> dict:
        narration = self.get(narration_id)
        if narration is None:
            raise LookupError(narration_id)
        allowed = self.EDITABLE if narration["status"] == "draft" else self.AFTER_RENDER
        changes = {k: v for k, v in fields.items() if v is not None}
        refused = set(changes) - allowed
        if refused:
            raise PermissionError(f"{narration['status']} narration: only {sorted(allowed)} can change. Copy it to start a new draft.")
        if changes:
            sets = ", ".join(f"{k} = ?" for k in changes)
            values = [json.dumps(v) if k == "params" else v for k, v in changes.items()]
            self.storage.execute(f"UPDATE narrations SET {sets}, updated_at = ? WHERE id = ?", (*values, now(), narration_id))
        return self.get(narration_id)

    def set_job(self, narration_id: str, job_id: str | None, status: str) -> dict:
        self.storage.execute("UPDATE narrations SET job_id = ?, status = ?, updated_at = ? WHERE id = ?", (job_id, status, now(), narration_id))
        return self.get(narration_id)

    def for_job(self, job_id: str) -> dict | None:
        rows = self.storage.query("SELECT * FROM narrations WHERE job_id = ?", (job_id,))
        return _row(rows[0], self.JSON) if rows else None

    def copy(self, narration_id: str, title: str | None = None) -> dict:
        source = self.get(narration_id)
        if source is None:
            raise LookupError(narration_id)
        return self.create(
            title=title or f"{source['title']} copy", notes=source["notes"], voice_id=source["voice_id"], version_id=source["version_id"],
            style_id=source["style_id"], script=source["script"], language=source["language"], params=source["params"],
            seed=source["seed"], copied_from=narration_id,
        )

    def delete(self, narration_id: str) -> str | None:
        narration = self.get(narration_id)
        if narration is None:
            raise LookupError(narration_id)
        if narration["status"] == "rendering":
            raise ValueError("a rendering narration cannot be deleted. Wait for it to finish.")
        self.storage.execute("DELETE FROM narrations WHERE id = ?", (narration_id,))
        return narration["job_id"]

    def uses_voice(self, voice_id: str) -> bool:
        return bool(self.storage.query("SELECT 1 FROM narrations WHERE voice_id = ? LIMIT 1", (voice_id,)))
