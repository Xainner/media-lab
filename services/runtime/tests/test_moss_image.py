import pytest
from pydantic import ValidationError

from media_lab.contracts import GenerateRequest
from media_lab.workflows import MOSS_ENCODER, MOSS_STEPS, MOSS_UNET, MOSS_VAE, moss_workflow


def test_graph_follows_the_official_sft_template():
    graph = moss_workflow("A poster that says \"HOLA\"", 1152, 864, 9, MOSS_STEPS["quality"])
    assert graph["1"]["inputs"]["unet_name"] == MOSS_UNET
    assert graph["2"]["inputs"] == {"clip_name": MOSS_ENCODER, "type": "moss_image", "device": "default"}
    assert graph["3"]["inputs"]["vae_name"] == MOSS_VAE
    assert graph["slg"]["inputs"] == {"model": ["1", 0], "double_layers": "", "single_layers": "22",
                                      "start_percent": 0.0, "end_percent": 0.5}
    sample = graph["6"]["inputs"]
    assert sample["model"] == ["slg", 0] and sample["negative"] == ["neg", 0]
    assert (sample["steps"], sample["cfg"], sample["sampler_name"], sample["scheduler"]) == (25, 2.5, "er_sde", "simple")
    assert graph["5"]["class_type"] == "EmptyFlux2LatentImage" and graph["5"]["inputs"]["width"] == 1152
    with pytest.raises(ValueError):
        moss_workflow("x", 1000, 1000, 1, 25)


def test_moss_requests_stay_on_the_plain_1mp_path():
    assert GenerateRequest(prompt="cartel", model="moss", aspect_ratio="16:9").model == "moss"
    assert GenerateRequest(prompt="x").model == "qwen"
    for bad in ({"transparent": True}, {"model_variant": "turbo"}, {"model_precision": "bf16"}, {"resolution_tier": "2k"}):
        with pytest.raises(ValidationError):
            GenerateRequest(prompt="x", model="moss", **bad)
