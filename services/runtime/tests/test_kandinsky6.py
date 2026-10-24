import pytest
from pydantic import ValidationError

from media_lab.contracts import VideoRequest
from media_lab.creative_workflows import K6_AUDIO_SCALING, K6_DIT, K6_STEPS, kandinsky6_workflow

REF = {"uri": "artifact://a", "sha256": "a" * 64}


def test_text_to_video_audio_follows_the_extension_template():
    graph = kandinsky6_workflow("A man says <S>Hola<E>", "deep calm voice, rain", "9:16", 4)
    assert graph["unet"]["inputs"]["unet_name"] == K6_DIT
    assert graph["clip"]["inputs"]["type"] == "kandinsky5"
    assert graph["audio_vae"]["inputs"]["scaling_factor"] == K6_AUDIO_SCALING
    assert (graph["latent"]["inputs"]["width"], graph["latent"]["inputs"]["height"]) == (480, 864)
    assert graph["latent"]["inputs"]["length"] == 121
    beautify = graph["beautify"]["inputs"]
    assert beautify["enabled"] is True and beautify["audio_caption"] == "deep calm voice, rain" and "image" not in beautify
    assert graph["positive"]["inputs"]["video_caption"] == ["beautify", 0]
    sample = graph["sample"]["inputs"]
    assert (sample["steps"], sample["cfg"]) == (K6_STEPS, 1.0) and sample["latent_image"] == ["latent", 0]
    assert graph["decode"]["inputs"]["samples"] == ["sample", 0]
    assert graph["video"]["inputs"]["audio"] == ["audio", 0]


def test_first_frame_goes_through_i2va_and_is_dropped_before_decoding():
    graph = kandinsky6_workflow("x", "", "16:9", 1, "first.png", enhance=False)
    assert graph["beautify"]["inputs"]["enabled"] is False and graph["beautify"]["inputs"]["image"] == ["first", 0]
    assert graph["sample"]["inputs"]["positive"] == ["i2va", 0] and graph["sample"]["inputs"]["latent_image"] == ["i2va", 2]
    assert graph["decode"]["inputs"]["samples"] == ["drop_ref", 0]
    assert graph["audio"]["inputs"]["joint_latent"] == ["drop_ref", 0]


def test_kandinsky_requests_stay_in_scope():
    body = VideoRequest(prompt="x", model="kandinsky6", audio_prompt="birds")
    assert body.steps is None and body.model_dump()["model"] == "kandinsky6"
    assert VideoRequest(prompt="x", model="kandinsky6", mode="i2v", first_frame=REF).mode == "i2v"
    for bad in ({"mode": "r2v", "references": [REF]}, {"seconds": 10}, {"aspect_ratio": "1:1"},
                {"profile": "turbo"}, {"steps": 8}, {"mode": "i2v"}, {"mode": "i2v", "first_frame": REF, "last_frame": REF}):
        with pytest.raises(ValidationError):
            VideoRequest(**{"prompt": "x", "model": "kandinsky6", **bad})
    with pytest.raises(ValidationError):
        VideoRequest(prompt="x", audio_prompt="birds")


def test_h3_fingerprints_are_unchanged():
    dumped = VideoRequest(prompt="x").model_dump()
    assert not {"model", "audio_prompt", "literal_prompt"} & set(dumped)
