from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from voice_engine.storage.blobs import compress, decompress


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _public(row, has_sample: bool) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "role": row["role"],
        "origin": row["origin"],
        "notes": row["notes"],
        "instruct": row["instruct"],
        "text": row["text"],
        "language": row["language"],
        "candidates": row["candidates"],
        "seed_start": row["seed_start"],
        "params": json.loads(row["params"]),
        "has_sample": has_sample,
        "sample_url": f"/v1/templates/{row['id']}/sample" if has_sample else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class Templates:
    def __init__(self, storage) -> None:
        self.storage = storage

    def list(self) -> list[dict]:
        rows = self.storage.query(
            """
            SELECT t.*, s.template_id IS NOT NULL AS has_sample
            FROM templates t
            LEFT JOIN template_samples s ON s.template_id = t.id
            ORDER BY CASE t.origin WHEN 'builtin' THEN 0 ELSE 1 END, t.sort_order, t.name
            """
        )
        return [_public(row, bool(row["has_sample"])) for row in rows]

    def get(self, template_id: str) -> dict | None:
        rows = self.storage.query(
            """
            SELECT t.*, s.template_id IS NOT NULL AS has_sample
            FROM templates t
            LEFT JOIN template_samples s ON s.template_id = t.id
            WHERE t.id = ?
            """,
            (template_id,),
        )
        return _public(rows[0], bool(rows[0]["has_sample"])) if rows else None

    def wav(self, template_id: str) -> bytes | None:
        rows = self.storage.query("SELECT audio FROM template_samples WHERE template_id = ?", (template_id,))
        return decompress(rows[0]["audio"]) if rows else None

    def insert_user(self, fields: dict, sample: tuple[bytes, int] | None) -> dict:
        template_id = self._new_id()
        now = _now()
        params = json.dumps(fields["params"])
        with self.storage.transaction() as conn:
            conn.execute(
                """
                INSERT INTO templates (
                    id, origin, name, role, notes, instruct, text, language,
                    candidates, seed_start, params, sort_order, created_at, updated_at
                ) VALUES (?, 'user', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    template_id,
                    fields["name"],
                    fields["role"],
                    fields.get("notes"),
                    fields["instruct"],
                    fields["text"],
                    fields["language"],
                    fields["candidates"],
                    fields["seed_start"],
                    params,
                    now,
                    now,
                ),
            )
            if sample is not None:
                wav, seed = sample
                packed = compress(wav)
                conn.execute(
                    """
                    INSERT INTO template_samples (template_id, seed, sample_rate, audio, nbytes)
                    VALUES (?, ?, 24000, ?, ?)
                    """,
                    (template_id, seed, packed, len(packed)),
                )
        found = self.get(template_id)
        if found is None:
            raise RuntimeError("template insert failed")
        return found

    def update_user(self, template_id: str, fields: dict) -> dict:
        current = self._user(template_id)
        merged = {**current, **fields}
        if "params" in fields:
            merged["params"] = fields["params"]
        else:
            merged["params"] = current["params"]
        now = _now()
        self.storage.execute(
            """
            UPDATE templates
            SET name = ?, role = ?, notes = ?, instruct = ?, text = ?, language = ?,
                candidates = ?, seed_start = ?, params = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                merged["name"].strip(),
                merged["role"].strip(),
                merged.get("notes"),
                merged["instruct"].strip(),
                merged["text"].strip(),
                merged["language"],
                merged["candidates"],
                merged["seed_start"],
                json.dumps(merged["params"]),
                now,
                template_id,
            ),
        )
        found = self.get(template_id)
        if found is None:
            raise LookupError(template_id)
        return found

    def set_sample(self, template_id: str, wav: bytes, seed: int) -> dict:
        self._user(template_id)
        packed = compress(wav)
        self.storage.execute(
            """
            INSERT INTO template_samples (template_id, seed, sample_rate, audio, nbytes)
            VALUES (?, ?, 24000, ?, ?)
            ON CONFLICT(template_id) DO UPDATE SET
                seed = excluded.seed,
                sample_rate = excluded.sample_rate,
                audio = excluded.audio,
                nbytes = excluded.nbytes
            """,
            (template_id, seed, packed, len(packed)),
        )
        found = self.get(template_id)
        if found is None:
            raise LookupError(template_id)
        return found

    def delete_user(self, template_id: str) -> None:
        self._user(template_id)
        self.storage.execute("DELETE FROM templates WHERE id = ?", (template_id,))

    def duplicate(self, template_id: str, name: str | None) -> dict:
        source = self.get(template_id)
        if source is None:
            raise LookupError(template_id)
        wav = self.wav(template_id)
        sample = (wav, source["seed_start"]) if wav is not None else None
        fields = {
            "name": name.strip() if name and name.strip() else f"{source['name']} copy",
            "role": source["role"],
            "notes": source["notes"],
            "instruct": source["instruct"],
            "text": source["text"],
            "language": source["language"],
            "candidates": source["candidates"],
            "seed_start": source["seed_start"],
            "params": source["params"],
        }
        if len(fields["name"]) > 80:
            fields["name"] = fields["name"][:80].rstrip()
        return self.insert_user(fields, sample)

    def _user(self, template_id: str) -> dict:
        row = self.get(template_id)
        if row is None:
            raise LookupError(template_id)
        if row["origin"] == "builtin":
            raise PermissionError(template_id)
        return row

    def _new_id(self) -> str:
        for _ in range(5):
            template_id = "tpl_" + secrets.token_hex(4)
            if not self.storage.query("SELECT 1 FROM templates WHERE id = ?", (template_id,)):
                return template_id
        raise RuntimeError("could not allocate a template id")
