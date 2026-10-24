import pytest
from pydantic import ValidationError

from media_lab.contracts import EditRequest, GenerateRequest
from media_lab.upsamplers import FLUX3_EDIT_SYSTEM, FLUX3_T2I_SYSTEM
from media_lab.workflows import (FLUX3_ENCODER, FLUX3_UNETS, FLUX3_UPSAMPLER, FLUX3_VAE, flux3_edit_workflow,
                                         flux3_request, flux3_workflow)

REF = {"uri": "artifact://a", "sha256": "a" * 64}


def test_t2i_follows_the_official_templates():
    draft = flux3_workflow("un zorro rojo en la nieve", 1344, 768, 7, "draft", "16:9")
    assert draft["1"]["inputs"]["unet_name"] == FLUX3_UNETS["draft"]
    assert draft["2"]["inputs"] == {"clip_name": FLUX3_ENCODER, "type": "flux3", "device": "default"}
    assert draft["3"]["inputs"]["vae_name"] == FLUX3_VAE
    sample = draft["6"]["inputs"]
    assert (sample["steps"], sample["cfg"], sample["sampler_name"], sample["scheduler"]) == (16, 1.0, "euler", "simple")
    # The caption the upsampler writes is what the DiT encodes; the request carries the canvas line.
    assert draft["4"]["inputs"]["text"] == ["upsample", 0]
    up = draft["upsample"]["inputs"]
    assert up["prompt"] == "TARGET CANVAS: 16:9\nun zorro rojo en la nieve"
    assert up["system_prompt"] == FLUX3_T2I_SYSTEM and up["sampling_mode.top_k"] == 1
    assert draft["up_clip"]["inputs"]["clip_name"] == FLUX3_UPSAMPLER
    assert draft["caption"] == {"class_type": "PreviewAny", "inputs": {"source": ["upsample", 0]}}
    quality = flux3_workflow("x", 1024, 1024, 7, "quality", "1:1")
    assert quality["1"]["inputs"]["unet_name"] == FLUX3_UNETS["quality"]
    assert (quality["6"]["inputs"]["steps"], quality["6"]["inputs"]["cfg"]) == (50, 3.5)
    with pytest.raises(ValueError):
        flux3_workflow("x", 1000, 1000, 1, "draft", "1:1")


def test_edit_sends_every_reference_to_the_upsampler_and_the_reference_latents():
    graph = flux3_edit_workflow("Pon a <image2> junto a <image1>", ["a.png", "b.png"], 3)
    assert graph["upsample"]["inputs"]["prompt"] == "Pon a the second image junto a the first image"
    assert graph["upsample"]["inputs"]["system_prompt"] == FLUX3_EDIT_SYSTEM
    assert graph["up_images"]["inputs"] == {"images.image0": ["ref0", 0], "images.image1": ["ref1", 0]}
    refs = graph["refs"]["inputs"]
    assert refs["images.image0"] == ["ref0", 0] and refs["images.image1"] == ["ref1", 0]
    assert refs["negative"] == ["neg", 0] and graph["neg"]["class_type"] == "ConditioningZeroOut"
    assert graph["6"]["inputs"]["latent_image"] == ["refs", 2] and graph["6"]["inputs"]["steps"] == 16
    with pytest.raises(ValueError):
        flux3_edit_workflow("x", ["a"] * 5, 1)
    assert flux3_request("<image12> stays") == "<image12> stays"


def test_flux3_requests_stay_on_their_path():
    assert GenerateRequest(prompt="x", model="flux3", quality="draft").model == "flux3"
    for bad in ({"transparent": True}, {"model_variant": "turbo"}, {"resolution_tier": "2k"},
                {"loras": [{"id": "lora_" + "0" * 16}]}, {"control": {"reference": REF}}):
        with pytest.raises(ValidationError):
            GenerateRequest(prompt="x", model="flux3", **bad)
    assert EditRequest(prompt="x", references=[REF] * 4, model="flux3").model == "flux3"
    for bad in ({"references": [REF] * 5}, {"remove_background": True}, {"camera": {}}, {"resolution": 1024},
                {"model_variant": "turbo"}):
        with pytest.raises(ValidationError):
            EditRequest(**{"prompt": "x", "references": [REF], "model": "flux3", **bad})


def test_default_edit_engine_keeps_old_fingerprints():
    assert "model" not in EditRequest(prompt="x", references=[REF]).model_dump()
    assert EditRequest(prompt="x", references=[REF], model="flux3").model_dump()["model"] == "flux3"


def test_output_text_reads_the_preview_node_of_the_finished_run(monkeypatch):
    from media_lab.comfy import ComfyClient

    class Response:
        def raise_for_status(self): pass
        def json(self): return {"p": {"outputs": {"caption": {"text": ["A rewritten prompt."]}, "save": {"images": []}}}}

    class Http:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def get(self, url): return Response()

    monkeypatch.setattr("media_lab.comfy.httpx.Client", Http)
    client = ComfyClient("http://comfy", 5)
    assert client.output_text("p", "caption") == "A rewritten prompt."
    assert client.output_text("p", "missing") == ""
