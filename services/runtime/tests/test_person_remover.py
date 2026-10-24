import pytest
from pydantic import ValidationError

from media_lab.contracts import RemoveRequest
from media_lab.creative import check_remove_input
from media_lab.creative_workflows import (REMOVER_LORA, REMOVER_PROMPT, SAM_MODEL, H3_REF, remover_mask_workflow,
                                                  remover_ready, remover_workflow)

REF = {"uri": "artifact://s/videos/a.mp4", "sha256": "a" * 64}


def test_mask_graph_tracks_one_person_and_paints_them_green():
    graph = remover_mask_workflow("clip.mp4", " man in yellow hoodie ")
    assert graph["sam"]["inputs"] == {"ckpt_name": SAM_MODEL}
    assert graph["subject"]["inputs"]["text"] == "man in yellow hoodie"
    assert graph["track"]["inputs"]["max_objects"] == 1 and graph["track"]["inputs"]["initial_mask"] == ["detect", 0]
    assert graph["grow"]["inputs"]["expand"] == 5 and graph["green"]["inputs"]["color"] == 0x00FF00
    assert graph["video"]["inputs"]["audio"] == ["parts", 1]
    assert remover_mask_workflow("clip.mp4", "")["subject"]["inputs"]["text"] == "person"


def test_removal_graph_follows_the_author_recipe_in_one_pass():
    graph = remover_workflow(864, 480, 124, 9, "green.mp4", "clean.png", soundtrack=True)
    assert graph["unet"]["inputs"]["unet_name"] == H3_REF
    assert graph["condition"]["inputs"]["length"] == 124 and graph["condition"]["inputs"]["prompt"] == REMOVER_PROMPT
    assert graph["condition"]["inputs"]["ref_videos.ref_video_0"] == ["green_parts", 0]
    assert graph["condition"]["inputs"]["ref_images.ref_image_0"] == ["ref_0", 0]
    assert graph["remover"]["inputs"] == {"model": ["shift", 0], "lora_name": REMOVER_LORA, "strength_model": 1.0}
    assert graph["shift"]["inputs"]["shift_video"] == 12.0
    assert (graph["scheduler"]["inputs"]["steps"], graph["scheduler"]["inputs"]["scheduler"],
            graph["sampler"]["inputs"]["sampler_name"]) == (12, "simple", "er_sde")
    assert graph["guide"]["inputs"]["image"] == ["ref_0", 0] and graph["guide"]["inputs"]["frame_idx"] == 0
    assert graph["guider"]["inputs"] == {"model": ["remover", 0], "conditioning": ["guide", 0]}
    assert graph["video"]["inputs"]["audio"] == ["green_parts", 1]
    silent = remover_workflow(864, 480, 124, 9, "green.mp4", "clean.png", soundtrack=False)
    assert silent["video"]["inputs"]["audio"] == ["decode_audio", 0]


def test_ready_and_input_limits(tmp_path):
    model_root, h3_root = tmp_path / "m", tmp_path / "h"
    assert not remover_ready(model_root, h3_root)
    for root, folder, name in ((model_root, "loras", REMOVER_LORA), (model_root, "checkpoints", SAM_MODEL),
                               (h3_root, "diffusion_models", H3_REF),
                               (h3_root, "text_encoders", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors")):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / name).touch()
    assert remover_ready(model_root, h3_root)
    check_remove_input({"duration": 5.2})
    for seconds in (0.5, 12):
        with pytest.raises(ValueError):
            check_remove_input({"duration": seconds})
    assert RemoveRequest(video=REF).clean_frame is None
    with pytest.raises(ValidationError):
        RemoveRequest(video=REF, target="x" * 301)
