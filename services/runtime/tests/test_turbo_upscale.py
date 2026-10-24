import pytest
from pydantic import ValidationError

from media_lab.comfy import ComfyClient
from media_lab.contracts import (EditRequest, GenerateRequest, ProductionRequest, UpscaleRequest,
                                         steps_for, upscale_estimate)
from media_lab.creative import check_upscale_input, upscale_chunk_frames, upscale_chunks
from media_lab.creative_workflows import flashvsr_tile, flashvsr_workflow
from media_lab.mcp_guides import build_guides
from media_lab.mcp_server import GUIDES, OPERATIONS
from media_lab.model_options import CanvasOptions, ImageOptions
from media_lab.workflows import (TURBO_SIGMAS, UNET, UNET_BF16, UNET_TURBO, UNET_TURBO_BF16,
                                         diffusion_model, edit_workflow, t2i_workflow)

REF = {"uri": "artifact://s/videos/a.mp4", "sha256": "a" * 64}


def test_turbo_text_to_image_uses_the_fixed_eight_step_schedule():
    graph = t2i_workflow("a cat", 1024, 1024, 7, 8, unet=UNET_TURBO, turbo=True,
                         options=CanvasOptions(sampler="euler_ancestral", cfg=1.5, negative_prompt="blurry"))
    assert graph["1"]["inputs"]["unet_name"] == UNET_TURBO
    assert graph["6"]["class_type"] == "SamplerCustomAdvanced"
    sigmas = [float(v) for v in graph["22"]["inputs"]["sigmas"].split(",")]
    assert sigmas == list(TURBO_SIGMAS) and len(sigmas) == 9 and sigmas[-1] == 0.0
    assert graph["20"]["inputs"]["noise_seed"] == 7
    assert graph["21"]["inputs"]["sampler_name"] == "euler_ancestral"
    assert graph["23"]["inputs"]["cfg"] == 1.5 and graph["23"]["inputs"]["model"] == ["1", 0]
    assert graph["4"]["inputs"]["negative_prompt"] == "blurry"
    assert graph["6"]["inputs"]["latent_image"] == ["5", 0] and graph["7"]["inputs"]["samples"] == ["6", 0]
    base = t2i_workflow("a cat", 1024, 1024, 7, 40)
    assert base["6"]["class_type"] == "KSampler" and "22" not in base


def test_turbo_edit_keeps_the_prefix_cache_and_reference_latent():
    graph = edit_workflow("make it night", ["a.png", "b.png"], 3, 8, unet=UNET_TURBO, turbo=True)
    assert graph["23"]["inputs"]["model"] == ["2", 0]
    assert graph["2"]["class_type"] == "QwenImage21Cache"
    assert graph["6"]["inputs"]["latent_image"] == ["5", 2]
    assert graph["5"]["inputs"]["images.image_2"] == ["12", 0]


def test_variant_and_precision_select_the_checkpoint():
    assert diffusion_model() == UNET and diffusion_model("base", "bf16") == UNET_BF16
    assert diffusion_model("turbo") == UNET_TURBO and diffusion_model("turbo", "bf16") == UNET_TURBO_BF16
    assert steps_for("turbo", "draft", ImageOptions()) == 8
    assert steps_for("base", "draft", None) == 25 and steps_for("base", "quality", ImageOptions(steps=12)) == 12


def test_turbo_rejects_schedule_options_and_base_keeps_old_fingerprints():
    with pytest.raises(ValidationError, match="8 pasos"):
        GenerateRequest(prompt="x", model_variant="turbo", options=CanvasOptions(steps=20))
    with pytest.raises(ValidationError, match="scheduler"):
        EditRequest(prompt="x", references=[{"uri": "artifact://s/images/a.png", "sha256": "b" * 64}],
                    model_variant="turbo", options=ImageOptions(scheduler="karras"))
    with pytest.raises(ValidationError):
        ProductionRequest(title="t", song=REF, brief="b", scenes=[{}], keyframe_variant="turbo",
                          keyframe_options=CanvasOptions(denoise=.5))
    assert "model_variant" not in GenerateRequest(prompt="x").model_dump()
    assert GenerateRequest(prompt="x", model_variant="turbo").model_dump()["model_variant"] == "turbo"
    assert "keyframe_variant" not in ProductionRequest(title="t", song=REF, brief="b", scenes=[{}]).model_dump()


def test_upscale_request_defaults_and_bounds():
    body = UpscaleRequest(video=REF)
    assert (body.scale, body.quality) == (2, "fast")
    with pytest.raises(ValidationError):
        UpscaleRequest(video=REF, scale=3)
    with pytest.raises(ValidationError):
        UpscaleRequest(video=REF, quality="ultra")


@pytest.mark.parametrize("frames,size", [(1, 121), (10, 121), (141, 41), (141, 108), (124, 54), (5760, 121)])
def test_upscale_chunks_cover_every_frame_once_with_overlap(frames, size):
    plan = upscale_chunks(frames, size)
    assert plan[0] == (0, plan[0][1], 0)
    covered = 0
    for first, count, shared in plan:
        assert first == covered - shared and shared <= 8 and count - shared > 0
        covered += count - shared
    assert covered == frames
    lengths = [count - shared for _, count, shared in plan]
    assert max(lengths) - min(lengths) < len(plan)  # balanced: no short trailing chunk


def test_chunk_size_follows_output_pixels():
    assert upscale_chunk_frames(896 * 512 * 4) == 121
    assert upscale_chunk_frames(1280 * 704 * 4) == 110
    assert upscale_chunk_frames(896 * 512 * 16) == 54
    assert upscale_chunk_frames(10 ** 10) == 41


def test_flashvsr_graph_is_tile_aligned_and_silent():
    for scale in (2, 4):
        tile = flashvsr_tile(scale, 896, 512)
        assert tile * scale % 128 == 0
        graph = flashvsr_workflow("chunk.mp4", scale, "quality", 5, tile)
        assert graph["pipe"]["class_type"] == "FlashVSRInitPipe" and graph["pipe"]["inputs"]["mode"] == "full"
        assert graph["upscale"]["inputs"]["scale"] == scale and graph["upscale"]["inputs"]["tiled_dit"] is True
        assert "audio" not in graph["video"]["inputs"]
        assert graph["video"]["inputs"]["fps"] == ["parts", 2]
    assert flashvsr_workflow("c.mp4", 2, "fast", 1, 512)["pipe"]["inputs"]["mode"] == "tiny"


def test_upscale_input_limits():
    small = {"width": 864, "height": 480, "fps": 24.0, "frames": 141, "duration": 5.875, "audio_codec": "aac"}
    check_upscale_input(small, 2)
    check_upscale_input(small, 4)
    with pytest.raises(ValueError, match="x4"):
        check_upscale_input({**small, "width": 1280, "height": 704}, 4)
    with pytest.raises(ValueError, match="minutos"):
        check_upscale_input({**small, "duration": 601}, 2)
    with pytest.raises(ValueError, match="tardaría"):
        check_upscale_input({**small, "duration": 240}, 4)
    with pytest.raises(ValueError, match="fotogramas"):
        check_upscale_input({**small, "fps": 120}, 2)
    assert upscale_estimate(10, 640, 352, 2, "fast") < upscale_estimate(10, 640, 352, 2, "quality")


def test_comfy_output_ignores_input_previews():
    history = {"p": {"outputs": {
        "load": {"images": [{"filename": "chunk.mp4", "subfolder": "", "type": "input"}], "animated": [True]},
        "save": {"images": [{"filename": "flashvsr_00001_.mp4", "subfolder": "media_lab", "type": "output"}]},
    }}}
    assert ComfyClient._first_output(history, "p", "videos")["filename"] == "flashvsr_00001_.mp4"


def test_mcp_exposes_upscaling_and_turbo_guidance():
    assert any(op[0] == "upscale_video" and op[2] == "/v1/jobs/upscale" and op[3] == "create" for op in OPERATIONS)
    guides = build_guides(OPERATIONS)
    assert "upscale_video" in guides["overview"] and "FlashVSR" in guides["overview"]
    assert "model_variant" in GUIDES["controls"] and "keyframe_variant" in GUIDES["controls"]
    assert "Turbo" in GUIDES["image"] and "8-step" in GUIDES["image"]
