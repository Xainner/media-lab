import pytest
from pydantic import ValidationError

from media_lab.contracts import VideoRequest
from media_lab.creative import check_control_input, nearest_video_aspect
from media_lab.creative_workflows import H3_CONTROL_PATCH, H3_DETECTOR, H3_REF, h3_control_ready, h3_workflow

CLIP = {"uri": "artifact://s/videos/dance.mp4", "sha256": "d" * 64}
PICTURE = {"uri": "artifact://s/images/me.png", "sha256": "e" * 64}


def test_pose_control_patches_the_ref2va_model_from_skeletons():
    graph = h3_workflow("dance", "r2v", 864, 480, 5, 20, 1, profile="base", control=("clip.mp4", "pose", 1.0))
    assert graph["unet"]["inputs"]["unet_name"] == H3_REF
    assert graph["control_patch"]["inputs"]["name"] == H3_CONTROL_PATCH
    control = graph["control"]["inputs"]
    assert control["model"] == ["unet", 0] and control["control_video"] == ["control_map", 0] and control["strength"] == 1.0
    assert graph["guider"]["inputs"]["model"] == graph["scheduler"]["inputs"]["model"] == ["control", 0]
    assert graph["scheduler"]["inputs"]["scheduler"] == "simple"
    assert graph["control_detector"]["inputs"]["unet_name"] == H3_DETECTOR
    assert graph["control_keypoints"]["inputs"]["bboxes"] == ["control_people", 0]
    assert not any(k.startswith("ref_") for k in graph)


def test_turbo_control_sits_after_the_lora_and_shift():
    graph = h3_workflow("dance", "r2v", 864, 480, 5, 8, 1, references=["me.png"], profile="turbo",
                        control=("clip.mp4", "canny", 0.7))
    assert graph["control"]["inputs"]["model"] == ["shift", 0]
    assert graph["control_map"]["class_type"] == "Canny"
    assert graph["condition"]["inputs"]["ref_images.ref_image_0"] == ["ref_0", 0]


def test_control_rules():
    with pytest.raises(ValueError):
        h3_workflow("x", "t2v", 864, 480, 5, 20, 1, control=("clip.mp4", "pose", 1.0))
    with pytest.raises(ValueError):
        h3_workflow("x", "r2v", 864, 480, 5, 8, 1, profile="omni", control=("clip.mp4", "pose", 1.0))
    body = VideoRequest(prompt="dance", mode="r2v", control={"video": CLIP}, references=[PICTURE])
    assert body.control.mode == "pose" and body.control.keep_audio
    with pytest.raises(ValidationError):
        VideoRequest(prompt="dance", mode="t2v", control={"video": CLIP})
    with pytest.raises(ValidationError):
        VideoRequest(prompt="dance", mode="r2v", profile="fused_turbo", control={"video": CLIP})
    assert "control" not in VideoRequest(prompt="x").model_dump()
    check_control_input({"duration": 6.0})
    with pytest.raises(ValueError):
        check_control_input({"duration": 16.0})
    assert [nearest_video_aspect(*s) for s in ((1920, 1080), (720, 1280), (1000, 1100))] == ["16:9", "9:16", "1:1"]


def test_ready_per_mode(tmp_path):
    (tmp_path / "model_patches").mkdir()
    (tmp_path / "model_patches" / H3_CONTROL_PATCH).touch()
    assert h3_control_ready(tmp_path, "canny") and not h3_control_ready(tmp_path, "pose")
