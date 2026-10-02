from voice_engine.pipeline.plan import plan_script
from voice_engine.pipeline.stitch import match_level, stitch, trim_silence
from voice_engine.pipeline.styles import get_style

import numpy as np


def test_plan_keeps_tags_on_the_following_line():
    style = get_style("narration")
    segments = plan_script("[whispers] Don't look now. [laughs] Then the room broke.", style)
    assert segments[0].tags == ["whispers"]
    assert "Don't look" in segments[0].spoken
    assert "laughs" in segments[1].tags
    assert "[" not in segments[0].spoken


def test_plan_pause_tag_sets_the_gap():
    segments = plan_script("First sentence. [pause 0.8s] Second sentence.", get_style("comedy"))
    assert segments[0].pause_after_s == 0.8
    assert len(segments) == 2


def test_plan_rejects_an_unknown_tag():
    try:
        plan_script("[dance] Hello.", get_style("narration"))
    except ValueError as exc:
        assert "unknown tag" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_long_script_is_split_under_the_cap():
    sentence = "This is one steady sentence about the engine. "
    segments = plan_script(sentence * 40, get_style("narration"))
    assert len(segments) > 1
    assert all(len(segment.spoken) <= 13 * 20 for segment in segments)


def test_stitch_inserts_a_pause_and_levels():
    tone = (0.02 * np.ones(2400)).astype("float32")
    quiet = match_level(tone, -20.0)
    assert abs(quiet).max() > abs(tone).max()
    joined = stitch([(tone, 0.1), (tone, 0.0)], 24000, 0.0)
    assert len(joined) == 2400 * 2 + int(24000 * 0.1)
    assert len(trim_silence(np.concatenate([np.zeros(1000), tone, np.zeros(1000)]), 24000)) < len(tone) + 2000


def test_setup_chooses_mlx_repos_on_apple(monkeypatch):
    import voice_engine.setup_models as setup

    monkeypatch.setattr(setup.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(setup.platform, "machine", lambda: "arm64")
    assert setup.choose_backend("auto") == "mlx"
    assert setup.repos_for("mlx")[0].startswith("mlx-community/")
    assert setup.repos_for("cuda")[0].startswith("Qwen/")
