from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from voice_engine.app import create_app
from voice_engine.config import Settings, load_settings


def wait(client: TestClient, job_id: str, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"{job_id} did not finish")


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, backend="fake"))
    with TestClient(app) as c:
        yield c


DESIGN = {
    "type": "design",
    "instruct": "Warm adult narrator",
    "text": "Ordinary things get interesting.",
    "candidates": 2,
    "params": {"temperature": 0.7},
}


def test_design_lock_speak(client):
    assert client.get("/health").json()["backend"] == "fake"

    design = client.post("/v1/jobs", json=DESIGN)
    assert design.status_code == 202
    design = wait(client, design.json()["id"])
    assert design["status"] == "succeeded"
    assert [o["file"] for o in design["outputs"]] == ["candidate-01.wav", "candidate-02.wav"]
    assert [o["seed"] for o in design["outputs"]] == [1000, 1001]
    assert design["applied"] == ["temperature"]
    assert design["outputs"][0]["checks"]["ok"] is True
    assert design["outputs"][0]["url"] == f"/v1/jobs/{design['id']}/files/candidate-01.wav"

    wav = client.get(f"/v1/jobs/{design['id']}/files/candidate-02.wav")
    assert wav.status_code == 200 and wav.content[:4] == b"RIFF"

    lock = {"type": "lock", "voice_id": "narrator-v1", "from_job": design["id"], "candidate": 2}
    locked = wait(client, client.post("/v1/jobs", json=lock).json()["id"])
    assert locked["status"] == "succeeded"
    voice = client.get("/v1/voices/narrator-v1").json()
    assert voice["seed"] == 1001
    assert client.get("/v1/voices/narrator-v1/files/preview.txt").text.strip() == DESIGN["text"]

    assert client.post("/v1/jobs", json=lock).status_code == 409

    speak = {
        "type": "speak",
        "voice_id": "narrator-v1",
        "text": "First line.\nSecond line.",
        "params": {"speed": 1.1},
    }
    spoken = wait(client, client.post("/v1/jobs", json=speak).json()["id"])
    assert spoken["status"] == "succeeded"
    assert spoken["applied"] == ["speed"]
    assert spoken["outputs"][0]["checks"]["duration_s"] > 0.5
    assert client.get(f"/v1/jobs/{spoken['id']}/files/audio.wav").status_code == 200


def test_rejects_bad_requests(client):
    assert client.post("/v1/jobs", json={**DESIGN, "candidates": 99}).status_code == 422
    assert client.post("/v1/jobs", json={"type": "speak", "voice_id": "Bad Id", "text": "x"}).status_code == 422
    assert client.post("/v1/jobs", json={"type": "speak", "voice_id": "missing-v1", "text": "x"}).status_code == 404
    lock = {"type": "lock", "voice_id": "x-v1", "from_job": "job_nope", "candidate": 1}
    assert client.post("/v1/jobs", json=lock).status_code == 404
    assert client.get("/v1/jobs/job_nope/files/../job.json").status_code == 404


def test_token_required(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, backend="fake", token="secret"))
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/v1/jobs").status_code == 401
        assert c.get("/v1/jobs", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_off_loopback_needs_token(monkeypatch):
    monkeypatch.delenv("VOICE_ENGINE_TOKEN", raising=False)
    with pytest.raises(ValueError):
        load_settings(host="0.0.0.0")
    assert load_settings(host="0.0.0.0", token="t").token == "t"


def test_design_and_speech_sections(client):
    design = wait(client, client.post("/v1/designs", json={"instruct": "Warm narrator", "text": "Hello there.", "candidates": 1}).json()["id"])
    assert design["type"] == "design" and design["status"] == "succeeded"
    assert client.get(f"/v1/designs/{design['id']}/files/candidate-01.wav").content[:4] == b"RIFF"
    assert client.get(f"/v1/speech/{design['id']}").status_code == 404

    locked = wait(
        client,
        client.post("/v1/voices", json={"voice_id": "section-v1", "from_design": design["id"], "candidate": 1}).json()["id"],
    )
    assert locked["status"] == "succeeded"
    spoken = wait(client, client.post("/v1/speech", json={"voice_id": "section-v1", "text": "A new line."}).json()["id"])
    assert spoken["type"] == "speak"
    audio = client.get(f"/v1/speech/{spoken['id']}/audio")
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    assert client.get("/v1/speech").json()[0]["id"] == spoken["id"]
    assert client.get("/v1/designs").json()[0]["id"] == design["id"]

    rendered = wait(
        client,
        client.post(
            "/v1/renders",
            json={
                "voice_id": "section-v1",
                "style": "comedy",
                "text": "[whispers] Don't look now. [laughs] Then the room broke.",
            },
        ).json()["id"],
    )
    assert rendered["status"] == "succeeded"
    assert rendered["type"] == "render"
    names = [item["file"] for item in rendered["outputs"]]
    assert "audio.wav" in names and any(name.startswith("segment-") for name in names)
    assert "tag:whispers" in rendered["deferred"]
    assert rendered["progress"]["phase"] == "done"
    assert rendered["progress"]["completed"] == rendered["progress"]["total"] > 0
    missing = client.get(f"/v1/jobs/{rendered['id']}/files/not-a-real.wav")
    assert missing.status_code == 404
    assert "tag:laughs" in rendered["deferred"]
    wav = client.get(f"/v1/jobs/{rendered['id']}/files/audio.wav")
    assert wav.status_code == 200 and wav.content[:4] == b"RIFF"


def test_swagger_and_download(client):
    spec = client.get("/openapi.json").json()
    examples = spec["paths"]["/v1/jobs"]["post"]["requestBody"]["content"]["application/json"]["examples"]
    assert {"design", "lock", "speak", "render"} <= set(examples)
    download = spec["paths"]["/v1/jobs/{job_id}/files/{name}"]["get"]
    assert "audio/wav" in download["responses"]["200"]["content"]
    assert "swagger-ui" in client.get("/docs").text
    assert client.get("/", follow_redirects=False).headers["location"] == "/docs"

    job = wait(client, client.post("/v1/jobs", json=DESIGN).json()["id"])
    wav = client.get(job["outputs"][0]["url"])
    assert wav.status_code == 200
    assert wav.headers["content-type"].startswith("audio/wav")
    assert "attachment" in wav.headers["content-disposition"]
    assert wav.content[:4] == b"RIFF"

    cors = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert cors.headers["access-control-allow-origin"] == "*"
    assert cors.json()["docs"] == "/docs"


def test_restart_keeps_history(tmp_path):
    settings = Settings(data_dir=tmp_path, backend="fake")
    with TestClient(create_app(settings)) as c:
        job = wait(c, c.post("/v1/jobs", json=DESIGN).json()["id"])
    with TestClient(create_app(settings)) as c:
        assert c.get(f"/v1/jobs/{job['id']}").json()["status"] == "succeeded"


def test_database_replaces_folders(client, tmp_path):
    design = wait(client, client.post("/v1/jobs", json=DESIGN).json()["id"])
    assert (tmp_path / "studio.db").is_file()
    assert not (tmp_path / "jobs").exists()
    assert client.get(design["outputs"][0]["url"]).content[:4] == b"RIFF"

    locked = wait(client, client.post("/v1/jobs", json={"type": "lock", "voice_id": "keep-v1", "from_job": design["id"], "candidate": 1}).json()["id"])
    assert locked["status"] == "succeeded"
    spoken = wait(client, client.post("/v1/jobs", json={"type": "speak", "voice_id": "keep-v1", "text": "Still here."}).json()["id"])
    assert client.delete(f"/v1/jobs/{design['id']}/record").status_code == 204
    assert client.get(f"/v1/jobs/{design['id']}").status_code == 404
    voice = client.get("/v1/voices/keep-v1").json()
    assert voice["from_job"] == design["id"]
    assert client.delete("/v1/voices/keep-v1").status_code == 204
    assert client.get("/v1/voices/keep-v1").status_code == 404
    assert client.get(f"/v1/jobs/{spoken['id']}").json()["voice_id"] == "keep-v1"
    assert client.post("/v1/jobs", json={"type": "speak", "voice_id": "keep-v1", "text": "Gone."}).status_code == 404


def test_legacy_import_runs_once(tmp_path):
    from voice_engine.storage import open_storage
    from voice_engine.storage.blobs import decompress

    job_dir = tmp_path / "jobs" / "job_old"
    job_dir.mkdir(parents=True)
    payload = """
        {"id":"job_old","type":"speak","status":"succeeded","spec":{"type":"speak","voice_id":"old-v1","text":"Hi"},
         "backend":"fake","created_at":"2026-01-01T00:00:00+00:00","started_at":null,"finished_at":null,
         "applied":[],"deferred":[],"outputs":[{"file":"audio.wav","seed":1,"sample_rate":24000,
         "checks":{"duration_s":1,"peak":0.1,"rms_dbfs":-20,"clipped_ratio":0,"lead_silence_s":0,"tail_silence_s":0,"chars_per_s":2,"ok":true,"warnings":[]}}],
         "voice_id":"old-v1","error":null}
        """
    (job_dir / "job.json").write_text(payload)
    (job_dir / "audio.wav").write_bytes(b"RIFF" + b"\x00" * 32)
    voice_dir = tmp_path / "voices" / "old-v1"
    voice_dir.mkdir(parents=True)
    (voice_dir / "voice.json").write_text(
        '{"voice_id":"old-v1","name":"Old","notes":null,"created_at":"2026-01-01T00:00:00+00:00","language":"English","from_job":"job_old","candidate":1,"seed":1,"design_backend":"fake","sample_rate":24000}'
    )
    (voice_dir / "preview.txt").write_text("Hi\n")
    (voice_dir / "instruct.txt").write_text("Warm\n")
    (voice_dir / "master.wav").write_bytes(b"RIFF" + b"\x00" * 32)

    storage = open_storage(tmp_path)
    assert storage.metadata("legacy_import_v1") == "complete"
    assert storage.jobs.get("job_old") is not None
    assert decompress(storage.query("SELECT audio FROM outputs WHERE job_id = 'job_old'")[0]["audio"]).startswith(b"RIFF")
    assert storage.voices.get("old-v1")["from_job"] == "job_old"
    assert not (tmp_path / "jobs").exists()
    assert not (tmp_path / "voices").exists()

    (tmp_path / "jobs" / "job_new").mkdir(parents=True)
    (tmp_path / "jobs" / "job_new" / "job.json").write_text(payload.replace("job_old", "job_new"))
    again = open_storage(tmp_path)
    assert again.jobs.get("job_new") is None
    assert again.metadata("legacy_import_v1") == "complete"

