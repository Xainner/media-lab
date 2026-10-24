import pytest
from pydantic import ValidationError

from media_lab.contracts import SoundRequest
from media_lab.creative_workflows import SA3_CHECKPOINTS, SA3_ENCODER, SA3_REWRITER, sa3_workflow
from media_lab.upsamplers import SA3_SYSTEM


def test_music_follows_the_official_medium_template():
    graph = sa3_workflow("cumbia lenta con acordeón", "music", 90, 5)
    assert graph["ckpt"]["inputs"]["ckpt_name"] == SA3_CHECKPOINTS["medium"]
    assert graph["clip"]["inputs"] == {"clip_name": SA3_ENCODER, "type": "stable_audio", "device": "default"}
    assert graph["rw_clip"]["inputs"]["clip_name"] == SA3_REWRITER
    rewrite = graph["rewrite"]["inputs"]
    assert rewrite["prompt"].startswith(SA3_SYSTEM["Music"])
    assert rewrite["prompt"].endswith("Input: cumbia lenta con acordeón\nTarget audio length: 90 seconds.\nOutput:")
    assert graph["positive"]["inputs"]["text"] == ["rewrite", 0]
    assert graph["latent"]["inputs"]["seconds"] == 90
    sample = graph["sample"]["inputs"]
    assert (sample["steps"], sample["cfg"], sample["sampler_name"], sample["scheduler"]) == (8, 1.0, "lcm", "simple")
    assert graph["decode"]["inputs"]["vae"] == ["ckpt", 2]
    assert "format.quality" not in graph["save"]["inputs"]


def test_effects_use_small_sfx_and_plain_prompts_skip_the_rewrite():
    graph = sa3_workflow("Glass shatters on concrete", "one_shot", 2, 1, enhance=False, fmt="mp3")
    assert graph["ckpt"]["inputs"]["ckpt_name"] == SA3_CHECKPOINTS["small_sfx"]
    assert "rewrite" not in graph and "caption" not in graph
    assert graph["positive"]["inputs"]["text"] == "Glass shatters on concrete"
    assert graph["save"]["inputs"]["format.quality"] == "V0"
    assert sa3_workflow("rain", "sfx", 10, 1)["rewrite"]["inputs"]["prompt"].startswith(SA3_SYSTEM["SFX"])


def test_lengths_follow_each_kind():
    assert SoundRequest(prompt="x", kind="music", seconds=380).seconds == 380
    assert SoundRequest(prompt="x", kind="one_shot", seconds=0.5).kind == "one_shot"
    for kind, seconds in (("music", 4), ("sfx", 121), ("one_shot", 11), ("instrument", 1)):
        with pytest.raises(ValidationError):
            SoundRequest(prompt="x", kind=kind, seconds=seconds)
