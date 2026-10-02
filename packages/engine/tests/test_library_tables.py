"""Database layer: playgrounds, versions, styles, narrations."""

import pytest

from voice_engine.audio import wav_bytes
from voice_engine.storage import open_storage

import numpy as np


def tone(seconds=0.5, rate=24000):
    t = np.arange(int(rate * seconds)) / rate
    return wav_bytes((0.05 * np.sin(2 * np.pi * 220 * t)).astype("float32"), rate)


def make_voice(storage, voice_id="narrator"):
    storage.voices.insert(
        {
            "voice_id": voice_id,
            "name": "Narrator",
            "created_at": "2026-01-01T00:00:00+00:00",
            "language": "English",
            "from_job": "job_x",
            "candidate": 1,
            "sample_rate": 24000,
        },
        "Hello there.",
        "Warm voice",
        tone(),
        None,
    )
    return storage.versions.add(voice_id, kind="original", audio=tone(), sample_rate=24000, ref_text="Hello there.")


def test_playground_draft_run_and_copy(tmp_path):
    storage = open_storage(tmp_path)
    pg = storage.playgrounds.create("Doc narrator", {"instruct": "warm", "text": "hi", "extra_key": 1})
    assert pg["config"]["extra_key"] == 1
    assert pg["runs"] == []
    updated = storage.playgrounds.update(pg["id"], name="Documentary", config={"instruct": "cooler"})
    assert updated["name"] == "Documentary" and updated["config"] == {"instruct": "cooler"}
    copy = storage.playgrounds.copy(pg["id"])
    assert copy["copied_from"] == pg["id"] and copy["config"] == {"instruct": "cooler"}
    assert copy["name"] == "Documentary copy"
    with pytest.raises(LookupError):
        storage.playgrounds.update("missing", name="x")


def test_versions_form_a_tree_and_current_pointer(tmp_path):
    storage = open_storage(tmp_path)
    v1 = make_voice(storage)
    assert v1["id"] == "narrator@1" and v1["label"] == "Original"
    v2 = storage.versions.add("narrator", kind="copy", audio=tone(), sample_rate=24000, ref_text="Hello there.", parent_version_id=v1["id"], edits={"note": "second take"})
    assert v2["id"] == "narrator@2" and v2["parent_version_id"] == "narrator@1"
    assert storage.voices.get("narrator")["current_version_id"] == "narrator@2"
    v3 = storage.versions.add("narrator", kind="copy", audio=tone(), sample_rate=24000, ref_text="Hello there.", parent_version_id=v1["id"], make_current=False)
    assert storage.voices.get("narrator")["current_version_id"] == "narrator@2"
    storage.voices.update("narrator", current_version_id=v3["id"], favorite=True)
    voice = storage.voices.get("narrator")
    assert voice["current_version_id"] == "narrator@3" and voice["favorite"] is True
    with pytest.raises(ValueError):
        storage.voices.update("narrator", current_version_id="other@1")
    assert storage.versions.audio("narrator@2")[:4] == b"RIFF"
    assert [v["version_no"] for v in storage.versions.list("narrator")] == [1, 2, 3]


def test_builtin_styles_are_frozen_and_copies_are_editable(tmp_path):
    storage = open_storage(tmp_path)
    with pytest.raises(PermissionError):
        storage.styles.update("comedy", temperature=0.5)
    mine = storage.styles.create("my-comedy", copied_from="comedy", temperature=0.8)
    assert mine["temperature"] == 0.8 and mine["emotion"] == "excited" and mine["builtin"] is False
    storage.styles.update("my-comedy", emotion=None)
    assert storage.styles.get("my-comedy")["emotion"] is None
    with pytest.raises(FileExistsError):
        storage.styles.create("my-comedy", copied_from="comedy")
    with pytest.raises(ValueError):
        storage.styles.create("empty")


def test_narration_draft_locks_after_render(tmp_path):
    storage = open_storage(tmp_path)
    v1 = make_voice(storage)
    storage.styles.create("mine", copied_from="narration")
    nar = storage.narrations.create(title="Intro", voice_id="narrator", version_id=v1["id"], style_id="mine", script="Hello world.", params={"top_p": 0.9})
    assert nar["status"] == "draft" and nar["params"] == {"top_p": 0.9}
    storage.narrations.update(nar["id"], script="Hello again.", seed=7)
    storage.narrations.set_job(nar["id"], None, "rendered")
    with pytest.raises(PermissionError):
        storage.narrations.update(nar["id"], script="changed")
    storage.narrations.update(nar["id"], title="Intro v1")
    copy = storage.narrations.copy(nar["id"])
    assert copy["status"] == "draft" and copy["script"] == "Hello again." and copy["copied_from"] == nar["id"]
    assert storage.narrations.uses_voice("narrator")
    with pytest.raises(PermissionError):
        storage.styles.delete("mine")
    storage.narrations.delete(nar["id"])
    storage.narrations.delete(copy["id"])
    assert not storage.narrations.uses_voice("narrator")
    storage.styles.delete("mine")
    assert storage.styles.get("mine") is None


def test_delete_playground_keeps_voices(tmp_path):
    storage = open_storage(tmp_path)
    pg = storage.playgrounds.create("P", {})
    make_voice(storage)
    storage.execute("UPDATE voices SET playground_id = ? WHERE voice_id = 'narrator'", (pg["id"],))
    storage.playgrounds.delete(pg["id"])
    voice = storage.voices.get("narrator")
    assert voice is not None and voice["playground_id"] is None
