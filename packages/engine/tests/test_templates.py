from __future__ import annotations

import sqlite3
import time

from fastapi.testclient import TestClient

from voice_engine.app import create_app
from voice_engine.catalog import CATALOG
from voice_engine.config import Settings
from voice_engine.storage import open_storage
from voice_engine.storage.migrations import V1_SQL

DESIGN = {
    "type": "design",
    "instruct": "Warm adult narrator",
    "text": "Ordinary things get interesting.",
    "candidates": 2,
    "params": {"temperature": 0.7},
}


def wait(client: TestClient, job_id: str, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"{job_id} did not finish")


def test_catalog_samples_and_profile(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, backend="fake"))
    with TestClient(app) as client:
        listed = client.get("/v1/templates").json()
        builtins = [item for item in listed if item["origin"] == "builtin"]
        assert [item["id"] for item in builtins] == [item.id for item in CATALOG]
        assert all(item["has_sample"] for item in builtins)
        sample = client.get(builtins[0]["sample_url"])
        assert sample.status_code == 200 and sample.content[:4] == b"RIFF"
        assert client.delete(f"/v1/templates/{builtins[0]['id']}").status_code == 409
        assert client.patch(f"/v1/templates/{builtins[0]['id']}", json={"name": "Nope"}).status_code == 409
        assert client.put(
            f"/v1/templates/{builtins[0]['id']}/sample",
            json={"from_job": "job_x", "candidate": 1},
        ).status_code == 409

        design = wait(client, client.post("/v1/jobs", json=DESIGN).json()["id"])
        created = client.post(
            "/v1/templates",
            json={
                "name": "My narrator",
                "role": "A test recipe",
                "instruct": DESIGN["instruct"],
                "text": DESIGN["text"],
                "candidates": 2,
                "seed_start": 1000,
                "params": {"temperature": 0.7},
                "from_job": design["id"],
                "candidate": 1,
            },
        )
        assert created.status_code == 201
        saved = created.json()
        assert saved["origin"] == "user" and saved["has_sample"] is True
        assert client.get(saved["sample_url"]).content == client.get(design["outputs"][0]["url"]).content

        assert client.delete(f"/v1/jobs/{design['id']}/record").status_code == 204
        assert client.get(saved["sample_url"]).content[:4] == b"RIFF"

        copied = client.post(f"/v1/templates/{saved['id']}/duplicate", json={}).json()
        assert copied["has_sample"] is True and copied["name"] == "My narrator copy"

        assert client.patch(f"/v1/templates/{saved['id']}", json={"name": "Renamed"}).json()["name"] == "Renamed"
        job = wait(
            client,
            client.post(
                "/v1/jobs",
                json={
                    "type": "design",
                    "instruct": saved["instruct"],
                    "text": saved["text"],
                    "language": saved["language"],
                    "candidates": saved["candidates"],
                    "seed_start": saved["seed_start"],
                    "params": saved["params"],
                },
            ).json()["id"],
        )
        assert job["spec"]["instruct"] == saved["instruct"]
        assert job["spec"]["seed_start"] == saved["seed_start"]
        assert client.delete(f"/v1/templates/{saved['id']}").status_code == 204
        assert client.get(f"/v1/jobs/{job['id']}").status_code == 200
        assert client.get(f"/v1/templates/{saved['id']}").status_code == 404

        locked = wait(
            client,
            client.post(
                "/v1/jobs",
                json={"type": "lock", "voice_id": "keeper-v1", "from_job": job["id"], "candidate": 1},
            ).json()["id"],
        )
        assert locked["status"] == "succeeded"
        assert client.put("/v1/favorites/missing-v1", json={}).status_code == 404
        kept = client.put("/v1/favorites/keeper-v1", json={"note": "the one"})
        assert kept.status_code == 200 and kept.json()["profile_note"] == "the one"
        assert client.delete("/v1/favorites/keeper-v1").status_code == 204
        assert client.get("/v1/voices/keeper-v1").status_code == 200
        assert client.get("/v1/favorites").json() == []
        assert client.put("/v1/favorites/keeper-v1", json={}).status_code == 200
        assert client.delete("/v1/voices/keeper-v1").status_code == 204
        assert client.get("/v1/favorites").json() == []


def test_version_1_upgrades_and_restores_builtins(tmp_path):
    db = sqlite3.connect(tmp_path / "studio.db")
    db.executescript(V1_SQL)
    db.execute("INSERT INTO schema_version (version) VALUES (1)")
    db.execute(
        """
        INSERT INTO voices (
            voice_id, name, notes, created_at, language, from_job, candidate, seed,
            design_backend, sample_rate, preview, instruct, master, prompt
        ) VALUES ('keep-v1', 'Keep', NULL, '2026-01-01T00:00:00+00:00', 'English', 'job_old', 1, 1, 'fake', 24000, 'Hi', 'Warm', ?, NULL)
        """,
        (b"RIFF",),
    )
    db.commit()
    db.close()

    storage = open_storage(tmp_path)
    assert storage.query("SELECT version FROM schema_version")[0]["version"] == 2
    assert storage.query("SELECT name FROM sqlite_master WHERE name = 'presets'") == []
    assert storage.voices.get("keep-v1")["name"] == "Keep"
    assert len(storage.templates.list()) == len(CATALOG)
    assert storage.templates.wav("builtin-animated")[:4] == b"RIFF"

    storage.execute("DELETE FROM templates WHERE id = 'builtin-villain'")
    again = open_storage(tmp_path)
    restored = again.templates.get("builtin-villain")
    assert restored is not None and restored["has_sample"] is True
    assert again.templates.get("builtin-warm-narrator")["has_sample"] is True


def test_fresh_database_is_version_2(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, backend="fake"))
    with TestClient(app):
        pass
    db = sqlite3.connect(tmp_path / "studio.db")
    version = db.execute("SELECT version FROM schema_version").fetchone()[0]
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    db.close()
    assert version == 2
    assert "presets" not in tables
    assert {"templates", "template_samples", "favorites"} <= tables
