import pytest
from pydantic import ValidationError

from media_lab.contracts import ProductionRequest, VideoRequest
from media_lab.creative_workflows import (H3_AUDIO_VAE, H3_CLIP, H3_FL, H3_FLEX_FL_LORA, H3_FLEX_REF_LORA, H3_FLEX_SIGMAS,
                                          H3_FUSED_VIDEO_VAE, H3_REF, h3_profiles, h3_workflow)
from media_lab.workflows import chain_loras


def test_flex_profile_runs_the_pika_template_on_the_official_weights():
    graph = h3_workflow("[Shot 1] A market.", "t2v", 1344, 768, 5, 6, 1, profile="flex")
    assert graph["unet"]["inputs"]["unet_name"] == H3_FL
    assert graph["flex_lora"]["inputs"] == {"model": ["unet", 0], "lora_name": H3_FLEX_FL_LORA, "strength_model": 1.0}
    assert graph["scheduler"] == {"class_type": "ManualSigmas", "inputs": {"sigmas": H3_FLEX_SIGMAS}}
    assert graph["sampler"]["inputs"]["sampler_name"] == "lcm"
    assert graph["guider"]["inputs"]["model"] == ["flex_lora", 0]
    assert "shift" not in graph and "turbo_lora" not in graph
    assert graph["video_vae"]["inputs"]["vae_name"] == H3_FUSED_VIDEO_VAE
    ref = h3_workflow("x", "r2v", 1344, 768, 5, 6, 1, references=["a.png"], profile="flex")
    assert ref["unet"]["inputs"]["unet_name"] == H3_REF and ref["flex_lora"]["inputs"]["lora_name"] == H3_FLEX_REF_LORA
    with pytest.raises(ValueError):
        h3_workflow("x", "t2v", 1344, 768, 5, 8, 1, profile="flex")


def test_library_loras_load_before_the_flex_adapter():
    graph = h3_workflow("x", "i2v", 1344, 768, 5, 6, 1, first="f.png", profile="flex")
    chain_loras(graph, "unet", [("style.safetensors", 0.8)])
    assert graph["flex_lora"]["inputs"]["model"] == ["user_lora_0", 0]
    assert graph["guider"]["inputs"]["model"] == ["flex_lora", 0]


def test_flex_keeps_six_steps_and_refuses_schedule_options():
    assert VideoRequest(prompt="x", profile="flex").steps == 6
    with pytest.raises(ValidationError):
        VideoRequest(prompt="x", profile="flex", steps=8)
    for options in ({"sampler": "euler"}, {"scheduler": "beta"}, {"denoise": 0.9}, {"shift_video": 6}, {"shift_audio": 2}):
        with pytest.raises(ValidationError):
            VideoRequest(prompt="x", profile="flex", options=options)
    assert VideoRequest(prompt="x", profile="flex", options={"resolution": "native", "crf": 20}).options.resolution == "native"
    with pytest.raises(ValidationError):
        VideoRequest(prompt="x", profile="flex", mode="r2v", control={"video": {"uri": "artifact://s/videos/a.mp4", "sha256": "a" * 64}})
    song = {"uri": "artifact://s/songs/a.flac", "sha256": "b" * 64}
    production = ProductionRequest(title="t", song=song, brief="b", video_profile="flex",
                                   scenes=[{"start": 0, "end": 5, "image_prompt": "x", "video_prompt": "y"}])
    assert production.video_steps == 6


def test_flex_is_ready_only_with_both_adapters(tmp_path):
    shared, fused = tmp_path / "shared", tmp_path / "fused"
    files = [(shared, "text_encoders", H3_CLIP), (shared, "vae", H3_AUDIO_VAE), (shared, "diffusion_models", H3_FL),
             (shared, "diffusion_models", H3_REF), (fused, "vae", H3_FUSED_VIDEO_VAE),
             (tmp_path, "loras", H3_FLEX_FL_LORA), (tmp_path, "loras", H3_FLEX_REF_LORA)]
    for root, folder, name in files:
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / name).touch()
    profile = h3_profiles(shared, fused, tmp_path)["flex"]
    assert profile["ready"] and profile["steps"] == {"min": 6, "max": 6, "default": 6}
    (tmp_path / "loras" / H3_FLEX_REF_LORA).unlink()
    assert not h3_profiles(shared, fused, tmp_path)["flex"]["ready"]
