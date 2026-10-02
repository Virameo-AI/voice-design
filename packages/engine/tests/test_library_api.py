"""API: playgrounds → runs → keep → versions → narrations → downloads."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from voice_engine.app import create_app
from voice_engine.config import Settings

from test_api import wait


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, backend="fake"))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def plain(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, backend="fake"))
    with TestClient(app) as c:
        yield c


def keep_voice(client, voice_id="narrator"):
    pg = client.post("/v1/playgrounds", json={"name": "Doc", "config": {"instruct": "Warm narrator", "text": "Hello there, listener.", "candidates": 2}}).json()
    run = client.post(f"/v1/playgrounds/{pg['id']}/runs", json={"candidates": 1, "save": False})
    assert run.status_code == 202, run.text
    job = wait(client, run.json()["id"])
    assert job["status"] == "succeeded"
    locked = wait(client, client.post("/v1/voices", json={"voice_id": voice_id, "from_design": job["id"], "candidate": 1, "name": "Narrator"}).json()["id"])
    assert locked["status"] == "succeeded"
    return pg, job


def test_playground_runs_and_keep_links_voice(client):
    pg, job = keep_voice(client)
    loaded = client.get(f"/v1/playgrounds/{pg['id']}").json()
    assert len(loaded["runs"]) == 1 and loaded["runs"][0]["run_no"] == 1
    assert loaded["runs"][0]["job"]["id"] == job["id"]
    assert loaded["runs"][0]["config"]["candidates"] == 1
    assert loaded["config"]["candidates"] == 2, "save=false left the draft alone"
    assert [v["voice_id"] for v in loaded["voices"]] == ["narrator"]

    voice = client.get("/v1/voices/narrator").json()
    assert voice["playground_id"] == pg["id"]
    assert voice["current_version_id"] == "narrator@1"
    assert voice["versions"][0]["kind"] == "original"
    assert client.get("/v1/voices/narrator/versions/narrator@1/master.wav").content[:4] == b"RIFF"

    patched = client.patch(f"/v1/playgrounds/{pg['id']}", json={"name": "Documentary", "config": {"instruct": "Cooler", "text": "x", "unknown": True}}).json()
    assert patched["config"]["unknown"] is True
    copy = client.post(f"/v1/playgrounds/{pg['id']}/copy", json={"name": "Second"}).json()
    assert copy["copied_from"] == pg["id"] and copy["runs"] == []
    assert client.post("/v1/playgrounds/missing/runs").status_code == 404
    assert client.post("/v1/playgrounds", json={"name": "T", "template_id": "nope"}).status_code == 404

    assert client.delete(f"/v1/playgrounds/{pg['id']}").status_code == 204
    assert client.get("/v1/voices/narrator").json()["playground_id"] is None


def test_version_can_be_spoken_relabeled_and_copied(client):
    keep_voice(client)
    versions = client.get("/v1/voices/narrator/versions").json()
    assert [v["id"] for v in versions] == ["narrator@1"]
    assert versions[0]["kind"] == "original" and versions[0]["label"] == "Original"

    relabeled = client.patch("/v1/voices/narrator/versions/narrator@1", json={"label": "First take"}).json()
    assert relabeled["label"] == "First take"

    spoken = wait(client, client.post("/v1/speech", json={"voice_id": "narrator", "version_id": "narrator@1", "text": "Hi."}).json()["id"])
    assert spoken["status"] == "succeeded" and spoken["version_id"] == "narrator@1"
    assert client.post("/v1/speech", json={"voice_id": "narrator", "version_id": "narrator@9", "text": "Hi."}).status_code == 404

    client.patch("/v1/voices/narrator", json={"current_version_id": "narrator@1", "favorite": True, "notes": "keep"})
    voice = client.get("/v1/voices/narrator").json()
    assert voice["current_version_id"] == "narrator@1" and voice["favorite"] is True and voice["notes"] == "keep"
    assert client.patch("/v1/voices/narrator", json={"current_version_id": "other@1"}).status_code == 400

    copied = client.post("/v1/voices/narrator/copy", json={"voice_id": "narrator-b", "version_id": "narrator@1"})
    assert copied.status_code == 201, copied.text
    assert copied.json()["copied_from"] == "narrator@1"
    assert copied.json()["versions"][0]["kind"] == "original"


def test_styles(plain):
    styles = plain.get("/v1/styles").json()
    assert [s["id"] for s in styles][:4] == ["narration", "comedy", "commercial", "kids"]
    assert plain.patch("/v1/styles/comedy", json={"temperature": 0.5}).status_code == 409
    mine = plain.post("/v1/styles", json={"id": "my-comedy", "copy_of": "comedy", "temperature": 0.8, "name": "Mine"}).json()
    assert mine["temperature"] == 0.8 and mine["pause_comma_s"] == 0.1 and mine["builtin"] is False
    assert plain.patch("/v1/styles/my-comedy", json={"emotion": "happy"}).json()["emotion"] == "happy"
    assert plain.post("/v1/styles", json={"id": "my-comedy", "copy_of": "comedy"}).status_code == 409
    assert plain.post("/v1/styles", json={"id": "blank"}).status_code == 400
    assert plain.delete("/v1/styles/my-comedy").status_code == 204
    assert plain.delete("/v1/styles/narration").status_code == 409


def test_narration_draft_render_copy_download(plain):
    keep_voice(plain)
    plain.post("/v1/styles", json={"id": "my-narration", "copy_of": "narration", "temperature": 0.6})
    draft = plain.post("/v1/narrations", json={"title": "Intro", "voice_id": "narrator", "style_id": "my-narration", "script": "[calm] Hello. [laughs] Bye.", "params": {"top_p": 0.9}})
    assert draft.status_code == 201, draft.text
    draft = draft.json()
    assert draft["status"] == "draft" and draft["version_id"] == "narrator@1"
    assert plain.get(f"/v1/narrations/{draft['id']}/audio.wav").status_code == 409

    edited = plain.patch(f"/v1/narrations/{draft['id']}", json={"script": "Hello there.\n\nAnd goodbye.", "seed": 5}).json()
    assert edited["seed"] == 5

    render = plain.post(f"/v1/narrations/{draft['id']}/render")
    assert render.status_code == 202, render.text
    job = render.json()
    assert job["type"] == "render" and job["spec"]["style"] == "my-narration" and job["spec"]["narration_id"] == draft["id"]
    job = wait(plain, job["id"])
    assert job["status"] == "succeeded", job["error"]

    done = plain.get(f"/v1/narrations/{draft['id']}").json()
    assert done["status"] == "rendered" and done["job"]["id"] == job["id"]
    assert done["audio_url"] == f"/v1/narrations/{draft['id']}/audio.wav"
    assert plain.get(done["audio_url"]).content[:4] == b"RIFF"
    assert plain.patch(f"/v1/narrations/{draft['id']}", json={"script": "changed"}).status_code == 409
    assert plain.patch(f"/v1/narrations/{draft['id']}", json={"title": "Intro final"}).status_code == 200
    assert plain.post(f"/v1/narrations/{draft['id']}/render").status_code == 409
    assert plain.delete("/v1/styles/my-narration").status_code == 409, "style in use"
    assert plain.delete("/v1/voices/narrator").status_code == 409, "voice in use"

    copy = plain.post(f"/v1/narrations/{draft['id']}/copy").json()
    assert copy["status"] == "draft" and copy["script"] == "Hello there.\n\nAnd goodbye." and copy["job_id"] is None
    listed = plain.get("/v1/narrations", params={"voice_id": "narrator"}).json()
    assert {n["id"] for n in listed} == {draft["id"], copy["id"]}

    downloads = plain.get("/v1/downloads").json()
    kinds = {(d["kind"], d["id"]) for d in downloads}
    assert ("narration", draft["id"]) in kinds and ("voice", "narrator@1") in kinds

    assert plain.delete(f"/v1/narrations/{draft['id']}").status_code == 204
    assert plain.get(f"/v1/jobs/{job['id']}").status_code == 404, "rendered audio goes with the narration"
    assert plain.delete(f"/v1/narrations/{copy['id']}").status_code == 204
    assert plain.delete("/v1/voices/narrator").status_code == 204


def test_legacy_render_records_tags_and_speaks_the_words(plain):
    keep_voice(plain)
    job = wait(plain, plain.post("/v1/renders", json={"voice_id": "narrator", "text": "[laughs] Hi there.", "style": "comedy"}).json()["id"])
    assert job["status"] == "succeeded" and "tag:laughs" in job["deferred"]
    assert plain.post("/v1/renders", json={"voice_id": "narrator", "text": "Hi", "style": "nope"}).status_code == 400
