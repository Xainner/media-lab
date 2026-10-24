import pytest
from pydantic import ValidationError

from media_lab.contracts import SwapRequest
from media_lab.creative import check_swap_input
from media_lab.creative_workflows import (H3_REF, HEAD_LORA, HEAD_TURBO, SWAP_LORA, SWAP_STEPS, SWAP_TURBO,
                                                  head_swap_workflow, swap_prompt, swap_size, swap_workflow)
from media_lab.mcp_server import GUIDES, OPERATIONS

VIDEO = {"uri": "artifact://s/videos/a.mp4", "sha256": "a" * 64}
IMAGE = {"uri": "artifact://s/images/b.png", "sha256": "b" * 64}


def test_swap_graph_follows_the_tested_recipe():
    graph = swap_workflow(swap_prompt("the dancer"), 1344, 768, 5.0, 7, "clip.mp4", "hero.png", True)
    assert graph["unet"]["inputs"]["unet_name"] == H3_REF
    assert graph["turbo"]["inputs"] == {"model": ["unet", 0], "lora_name": SWAP_TURBO, "strength_model": 1.0}
    assert graph["swap"]["inputs"] == {"model": ["turbo", 0], "lora_name": SWAP_LORA, "strength_model": 1.0}
    assert graph["shift"]["inputs"]["model"] == ["swap", 0]
    assert graph["guider"]["inputs"]["model"] == ["shift", 0] and graph["scheduler"]["inputs"]["model"] == ["shift", 0]
    assert graph["scheduler"]["inputs"]["steps"] == SWAP_STEPS == 8
    assert graph["scheduler"]["inputs"]["scheduler"] == "normal" and graph["sampler"]["inputs"]["sampler_name"] == "er_sde"
    condition = graph["condition"]["inputs"]
    assert graph["condition"]["class_type"] == "MiniMaxH3ReferenceToVideo"
    assert condition["ref_videos.ref_video_0"] == ["ref_video_parts_0", 0]
    assert condition["ref_video_audios.ref_video_audio_0"] == ["ref_video_parts_0", 1]
    assert condition["ref_images.ref_image_0"] == ["ref_0", 0]
    assert "the dancer in <Video 1>" in condition["prompt"] and "<Picture 1>" in condition["prompt"]
    silent = swap_workflow(swap_prompt(), 768, 1344, 5.0, 7, "clip.mp4", "hero.png", False)
    assert "ref_video_audios.ref_video_audio_0" not in silent["condition"]["inputs"]
    assert "the main person" in silent["condition"]["inputs"]["prompt"]


def test_swap_keeps_the_source_aspect_on_the_32_px_grid():
    for source in ((1920, 1080), (1080, 1920), (1080, 1350), (720, 720)):
        width, height = swap_size(*source)
        assert width % 32 == 0 and height % 32 == 0
        assert width * height <= 1_100_000
        assert abs(width / height - source[0] / source[1]) < 0.05


def test_swap_request_and_input_limits():
    body = SwapRequest(video=VIDEO, character=IMAGE, target="the man on the left")
    assert body.prompt is None and body.target == "the man on the left"
    with pytest.raises(ValidationError):
        SwapRequest(video=VIDEO)
    check_swap_input({"duration": 3.2})
    for duration in (1.5, 15.5):
        with pytest.raises(ValueError):
            check_swap_input({"duration": duration})


def test_head_swap_guides_the_clip_and_references_the_face():
    graph = head_swap_workflow(1376, 768, 5.0, 7, "clip.mp4", "face.png", True, "the dancer")
    assert graph["unet"]["inputs"]["unet_name"] == H3_REF
    assert graph["shift"]["inputs"]["model"] == ["unet", 0]
    assert graph["turbo"]["inputs"] == {"model": ["shift", 0], "lora_name": HEAD_TURBO, "strength_model": 1.0}
    assert graph["head"]["inputs"] == {"model": ["turbo", 0], "lora_name": HEAD_LORA, "strength_model": 1.0}
    assert graph["scheduler"]["inputs"]["model"] == graph["guider"]["inputs"]["model"] == ["head", 0]
    assert graph["scheduler"]["inputs"]["scheduler"] == "beta" and graph["sampler"]["inputs"]["sampler_name"] == "euler"
    condition = graph["condition"]["inputs"]
    assert condition["ref_images.ref_image_0"] == ["ref_0", 0]
    assert not any(key.startswith("ref_videos") for key in condition)
    guide = graph["guide"]
    assert guide["class_type"] == "MiniMaxH3AddGuide" and guide["inputs"]["frame_idx"] == 0
    assert guide["inputs"]["image"] == ["source_parts", 0] and guide["inputs"]["audio"] == ["source_parts", 1]
    assert graph["guider"]["inputs"]["conditioning"] == ["guide", 0]
    # Face details come from the H3 vision encoder unless given.
    assert graph["details"]["inputs"]["image"] == ["ref_0", 0] and condition["prompt"] == ["prompt", 0]
    assert graph["prompt_head"]["inputs"]["string_a"].startswith("head_swap:")
    assert "<Subject 2> is the dancer in <Video 1>" in graph["prompt"]["inputs"]["string_b"]
    given = head_swap_workflow(1376, 768, 5.0, 7, "clip.mp4", "face.png", False, details="Male, red beard")
    assert "details" not in given and "audio" not in given["guide"]["inputs"]
    assert "Facial details of <Subject 1>:\nMale, red beard\n" in given["condition"]["inputs"]["prompt"]


def test_swap_modes():
    assert SwapRequest(video=VIDEO, character=IMAGE).mode == "character"
    assert SwapRequest(video=VIDEO, character=IMAGE, mode="head", details="Female, short silver hair").mode == "head"
    with pytest.raises(ValidationError):
        SwapRequest(video=VIDEO, character=IMAGE, mode="body")


def test_swap_is_an_mcp_tool_with_a_guide():
    assert any(op[0] == "swap_character" and op[2] == "/v1/jobs/swap" for op in OPERATIONS)
    guides = "".join(str(v) for v in GUIDES.values())
    assert "swap_character(body={mode, video, character, target, details, prompt, seed})" in guides
    assert "`mode=head`" in guides
