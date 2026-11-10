import threading
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from media_lab import main
from media_lab.contracts import PRESETS_2K, PRESETS_4K, EditRequest, GenerateRequest, generation_size
from media_lab.jobs import JobManager
from media_lab.workflows import (H3_IMAGE_ENCODER, H3_IMAGE_EXPANDER, H3_IMAGE_PROMPTS, H3_IMAGE_UNET, H3_IMAGE_VAE,
                                 h3_image_edit_workflow, h3_image_ready, h3_image_request, h3_image_workflow)

REF = {"uri": "artifact://a", "sha256": "a" * 64}


def test_t2i_follows_the_official_template():
    graph = h3_image_workflow("The image is a red fox in fresh snow.", 2048, 2048, 7)
    assert graph["1"]["inputs"] == {"unet_name": H3_IMAGE_UNET, "weight_dtype": "default"}
    assert graph["2"]["inputs"] == {"clip_name": H3_IMAGE_ENCODER, "type": "minimax", "device": "default"}
    assert graph["3"]["inputs"] == {"vae_name": H3_IMAGE_VAE}
    cond = graph["4"]["inputs"]
    assert graph["4"]["class_type"] == "MiniMaxH3ImageConditioning"
    assert (cond["prompt"], cond["width"], cond["height"]) == ("The image is a red fox in fresh snow.", 2048, 2048)
    assert not any(key.startswith("images.") for key in cond)
    sample = graph["6"]["inputs"]
    assert (sample["steps"], sample["cfg"], sample["sampler_name"], sample["scheduler"]) == (6, 1.0, "euler", "simple")
    assert sample["latent_image"] == ["4", 1] and graph["neg"]["class_type"] == "ConditioningZeroOut"
    assert "expand" not in graph  # text to image uses the prompt as given, like the template default
    with pytest.raises(ValueError):
        h3_image_workflow("x", 2000, 2048, 1)


def test_edit_expands_the_instruction_and_keeps_picture_one_at_4_mp():
    graph = h3_image_edit_workflow("Pon a <image2> junto a <image1>", ["a.png", "b.png"], 3, "SYSTEM", "TASK\n")
    expand = graph["expand"]["inputs"]
    assert expand["prompt"] == "TASK\nUser input: Pon a <Picture 2> junto a <Picture 1>\noutput_text:\n"
    assert expand["system_prompt"] == "SYSTEM" and expand["thinking"] is True
    assert graph["up_clip"]["inputs"]["clip_name"] == H3_IMAGE_EXPANDER
    assert (expand["sampling_mode.temperature"], expand["sampling_mode.top_k"], expand["max_length"]) == (1.0, 20, 8196)
    assert expand["images.image1"] == ["canvas", 0] and expand["images.image2"] == ["ref1", 0]
    assert graph["scale"]["inputs"]["input"] == ["ref0", 0]
    assert graph["scale"]["inputs"]["resize_type.megapixels"] == 4.0
    assert graph["canvas"]["inputs"]["resize_type.multiple"] == 32
    assert graph["extract"]["inputs"] == {"json_string": ["expand", 0], "key": "expanded_caption"}
    cond = graph["4"]["inputs"]
    assert cond["prompt"] == ["extract", 0] and (cond["width"], cond["height"]) == (["size", 0], ["size", 1])
    assert cond["images.image_1"] == ["canvas", 0] and cond["images.image_2"] == ["ref1", 0]
    assert graph["caption"] == {"class_type": "PreviewAny", "inputs": {"source": ["extract", 0]}}
    with pytest.raises(ValueError):
        h3_image_edit_workflow("x", ["a"] * 11, 1, "S", "T")
    assert h3_image_request("<image12> stays") == "<Picture 12> stays"


def test_generate_contract_defaults_to_4_mp_and_offers_16_mp():
    body = GenerateRequest(prompt="x", model="h3image", aspect_ratio="16:9")
    assert body.resolution_tier == "2k" and generation_size(body, False) == PRESETS_2K["16:9"]
    big = GenerateRequest(prompt="x", model="h3image", resolution_tier="4k", aspect_ratio="4:5")
    assert generation_size(big, False) == PRESETS_4K["4:5"]
    for ratio, (w, h) in PRESETS_4K.items():
        assert w % 32 == 0 and h % 32 == 0 and 15_500_000 < w * h < 17_500_000, ratio
    for bad in ({"resolution_tier": "1mp"}, {"transparent": True}, {"model_variant": "turbo"},
                {"model_precision": "bf16"}, {"options": {"steps": 10}}, {"loras": [{"id": "lora_" + "0" * 16}]},
                {"control": {"reference": REF}}):
        with pytest.raises(ValidationError):
            GenerateRequest(prompt="x", model="h3image", **bad)
    for model in ("qwen", "moss", "flux3"):
        with pytest.raises(ValidationError):
            GenerateRequest(prompt="x", model=model, resolution_tier="4k")
    assert GenerateRequest(prompt="x").resolution_tier == "1mp"


def test_edit_contract_stays_on_its_path():
    assert EditRequest(prompt="x", references=[REF] * 10, model="h3image").model == "h3image"
    for bad in ({"references": [REF] * 11}, {"remove_background": True}, {"camera": {}}, {"resolution": 1024},
                {"model_variant": "turbo"}, {"transparent": True}):
        with pytest.raises(ValidationError):
            EditRequest(**{"prompt": "x", "references": [REF], "model": "h3image", **bad})


def test_ready_needs_weights_encoders_and_expander_prompts(tmp_path):
    models, shared = tmp_path / "models", tmp_path / "shared"
    files = [models / "diffusion_models" / H3_IMAGE_UNET, models / "vae" / H3_IMAGE_VAE,
             models / "text_encoders" / H3_IMAGE_EXPANDER, shared / "text_encoders" / H3_IMAGE_ENCODER,
             *(models / p for p in H3_IMAGE_PROMPTS)]
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    assert h3_image_ready(models, shared)
    files[-1].unlink()
    assert not h3_image_ready(models, shared)


def test_edit_job_reads_the_pe_prompts_and_keeps_the_caption(tmp_path):
    for path, text in zip(H3_IMAGE_PROMPTS, ("SYSTEM\n", "TASK\n")):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text(text)
    graphs, imported = [], []
    client = SimpleNamespace(upload_image=lambda source, name: f"{name}.png",
                             run=lambda graph, *a: graphs.append(graph) or (b"png", {"prompt_id": "p"}),
                             output_text=lambda pid, node: "The target image shows <Subject 1>.")
    manager = object.__new__(JobManager)
    manager.settings = SimpleNamespace(model_root=tmp_path)
    manager.clients = [client]
    manager.store = SimpleNamespace(cancel_requested=lambda job: False, update_job=lambda *a, **k: None)
    manager.artifacts = SimpleNamespace(resolve=lambda uri, sha: tmp_path / "ref.png",
                                        import_image=lambda session, raw, meta: imported.append(meta) or {"uri": "u"})
    manager._preview_lock = threading.Lock()
    body = EditRequest(prompt="Make it night", references=[REF], model="h3image", seed=5)
    result = manager._edit("job", {"session_id": "s", "request": body.model_dump()}, 0)
    assert graphs[0]["expand"]["inputs"]["system_prompt"] == "SYSTEM"
    assert graphs[0]["expand"]["inputs"]["prompt"].startswith("TASK\nUser input: Make it night")
    assert imported[0]["compiled_prompt"] == "The target image shows <Subject 1>."
    assert imported[0]["workflow"] == "h3_image_edit_v1" and result["data"]["steps"] == 6


def test_capabilities_and_routes(monkeypatch):
    caps = main.capabilities()["image_models"]["h3image"]
    assert caps["resolution_tiers"] == ["2k", "4k"] and caps["max_references"] == 10 and caps["steps"] == 6
    monkeypatch.setattr(main, "h3_image_ready", lambda *a: False)
    with pytest.raises(main.HTTPException) as refused:
        main.generate(GenerateRequest(prompt="x", model="h3image"), None)
    assert refused.value.status_code == 422 and "MiniMax-H3-Image" in refused.value.detail
