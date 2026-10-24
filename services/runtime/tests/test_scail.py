from media_lab.contracts import SwapRequest
from media_lab.workflows import ENCODER
from media_lab.creative_workflows import (SAM_MODEL, SCAIL_DISTILL_LORA, SCAIL_DPO_LORA, SCAIL_MODEL, WAN_CLIP,
                                                  WAN_CLIP_VISION, WAN_VAE, scail_frames, scail_ready, scail_size,
                                                  scail_workflow)

REF = {"uri": "artifact://s/videos/a.mp4", "sha256": "a" * 64}
PICTURE = {"uri": "artifact://s/images/b.png", "sha256": "b" * 64}


def test_chunks_cover_the_clip_in_76_frame_steps():
    assert scail_frames(60) == (1, 81)
    assert scail_frames(81) == (1, 81)
    assert scail_frames(120) == (2, 157)
    assert scail_frames(360) == (5, 385)
    assert scail_size(864, 480) == (896, 512) and scail_size(480, 864) == (512, 896)


def test_one_chunk_follows_the_template_recipe():
    graph = scail_workflow("clip.mp4", "me.png", "prompt", "man in yellow hoodie", 896, 512, 60, 7)
    assert graph["unet"]["inputs"]["unet_name"] == SCAIL_MODEL
    assert graph["dpo"]["inputs"]["lora_name"] == SCAIL_DPO_LORA and graph["distill"]["inputs"]["strength_model"] == 0.8
    assert graph["shift"]["inputs"]["shift"] == 5.0 and graph["sigmas"]["inputs"]["steps"] == 6
    assert graph["sample_0"]["inputs"]["cfg"] == 1.0 and graph["sample_0"]["inputs"]["model"] == ["shift", 0]
    assert graph["who"]["inputs"]["text"] == "man in yellow hoodie"
    assert graph["scail_0"]["inputs"]["pose_video_mask"] == ["masks_0", 0]
    assert graph["scail_0"]["inputs"]["reference_image_mask"] == ["masks_0", 1]
    assert "previous_frames" not in graph["scail_0"]["inputs"]
    assert graph["video"]["inputs"]["images"] == ["decode_0", 0]
    assert graph["positive"]["inputs"]["text"] == "prompt" and "description" not in graph


def test_without_a_prompt_qwen_describes_the_new_character_not_the_target():
    graph = scail_workflow("clip.mp4", "me.png", "", "man in yellow hoodie", 896, 512, 60, 7)
    assert graph["description"]["inputs"]["image"] == ["character", 0]
    assert graph["describer"]["inputs"]["clip_name"] == ENCODER
    assert graph["positive"]["inputs"]["text"] == ["prompt", 0]
    assert "yellow" not in graph["prompt"]["inputs"]["string_b"]


def test_later_chunks_chain_on_the_previous_tail():
    graph = scail_workflow("clip.mp4", "me.png", "prompt", "", 896, 512, 200, 7)
    assert [graph[f"pose_{i}"]["inputs"]["batch_index"] for i in range(3)] == [0, 76, 152]
    assert graph["scail_1"]["inputs"]["previous_frames"] == ["decode_0", 0]
    assert graph["scail_2"]["inputs"]["previous_frames"] == ["graded_1", 0]
    assert graph["fresh_1"]["inputs"]["batch_index"] == 5
    assert graph["joined_2"]["inputs"] == {"image1": ["joined_1", 0], "image2": ["graded_2", 0]}
    assert graph["video"]["inputs"]["images"] == ["joined_2", 0]
    assert graph["who"]["inputs"]["text"] == "person"


def test_ready_and_mode(tmp_path):
    model_root, shared = tmp_path / "m", tmp_path / "s"
    assert not scail_ready(model_root, shared)
    for root, folder, name in ((model_root, "text_encoders", ENCODER), (model_root, "diffusion_models", SCAIL_MODEL),
                               (model_root, "loras", SCAIL_DPO_LORA),
                               (model_root, "loras", SCAIL_DISTILL_LORA), (model_root, "clip_vision", WAN_CLIP_VISION),
                               (model_root, "checkpoints", SAM_MODEL), (shared, "text_encoders", WAN_CLIP), (shared, "vae", WAN_VAE)):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / name).touch()
    assert scail_ready(model_root, shared)
    assert SwapRequest(mode="scail", video=REF, character=PICTURE).mode == "scail"
