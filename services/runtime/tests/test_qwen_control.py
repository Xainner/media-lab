import pytest
from pydantic import ValidationError

from media_lab.contracts import EditRequest, GenerateRequest
from media_lab.workflows import (CAMERA_LORA, CONTROL_PATCH, DEPTH_MODEL, POSE_MODEL, apply_camera,
                                         apply_control, camera_prompt, control_ready, edit_workflow, t2i_workflow)

REF = {"uri": "artifact://upload/a.png", "sha256": "a" * 64}


def test_control_routes_the_model_through_the_union_patch():
    graph = t2i_workflow("a pier at dawn", 864, 1152, 7, 40)
    apply_control(graph, "pose.png", "canny", 0.8, 864, 1152)
    assert graph["cp"]["inputs"] == {"name": CONTROL_PATCH}
    assert graph["cn"]["class_type"] == "ZImageFunControlnet"
    assert graph["cn"]["inputs"]["model"] == ["1", 0] and graph["cn"]["inputs"]["strength"] == 0.8
    assert graph["6"]["inputs"]["model"] == ["cn", 0]
    assert graph["c2"]["inputs"] | {"image": None} == {"image": None, "upscale_method": "lanczos",
                                                       "width": 864, "height": 1152, "crop": "center"}
    assert graph["cn"]["inputs"]["image"] == ["c3", 0] and graph["c3"]["class_type"] == "Canny"


def test_control_maps_per_mode_and_turbo_guider():
    for mode, node in (("depth", "DA3Render"), ("pose", "SDPoseDrawKeypoints")):
        graph = t2i_workflow("x", 1024, 1024, 1, 40)
        apply_control(graph, "in.png", mode, 1.0, 1024, 1024)
        assert graph["c3"]["class_type"] == node
    graph = t2i_workflow("x", 1024, 1024, 1, 40)
    apply_control(graph, "in.png", "map", 1.0, 1024, 1024)
    assert graph["cn"]["inputs"]["image"] == ["c2", 0] and "c3" not in graph
    turbo = t2i_workflow("x", 1024, 1024, 1, 8, turbo=True)
    apply_control(turbo, "in.png", "map", 1.0, 1024, 1024)
    assert turbo["23"]["inputs"]["model"] == ["cn", 0]


def test_control_ready_checks_each_mode(tmp_path):
    (tmp_path / "model_patches").mkdir()
    (tmp_path / "model_patches" / CONTROL_PATCH).write_bytes(b"x")
    assert control_ready(tmp_path, "canny") and control_ready(tmp_path, "map")
    assert not control_ready(tmp_path, "depth") and not control_ready(tmp_path, "pose")
    for folder, name in (("geometry_estimation", DEPTH_MODEL), ("checkpoints", POSE_MODEL)):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / name).write_bytes(b"x")
    assert control_ready(tmp_path, "depth") and control_ready(tmp_path, "pose")


def test_control_requests_stay_on_qwen_1mp():
    body = GenerateRequest(prompt="x", control={"reference": REF, "mode": "pose"})
    assert body.control.strength is None
    assert "control" not in GenerateRequest(prompt="x").model_dump()
    for bad in ({"model": "moss"}, {"resolution_tier": "2k"}):
        with pytest.raises(ValidationError):
            GenerateRequest(prompt="x", control={"reference": REF}, **bad)
    with pytest.raises(ValidationError):
        GenerateRequest(prompt="x", control={"reference": REF, "mode": "hed"})


def test_camera_edit_follows_the_qma_card():
    prompt = camera_prompt("right side view", "eye-level shot", "medium shot")
    assert prompt == "<qma> right side view eye-level shot medium shot"
    assert camera_prompt("back view", "high-angle shot", "wide shot", " keep the red scarf ").endswith(". keep the red scarf")
    graph = edit_workflow(prompt, ["in.png"], 3, 30)
    apply_camera(graph)
    assert graph["lora"]["inputs"] == {"model": ["1", 0], "lora_name": CAMERA_LORA, "strength_model": 1.0}
    assert graph["2"]["inputs"]["model"] == ["lora", 0]
    sample = graph["6"]["inputs"]
    assert (sample["steps"], sample["cfg"], sample["sampler_name"], sample["scheduler"]) == (30, 3.0, "euler", "simple")


def test_camera_requests_need_one_base_reference():
    body = EditRequest(references=[REF], camera={"azimuth": "back view"})
    assert body.camera.elevation == "eye-level shot" and body.prompt == ""
    with pytest.raises(ValidationError):
        EditRequest(references=[REF])
    for bad in ({"references": [REF, REF]}, {"model_variant": "turbo"}, {"transparent": True},
                {"options": {"steps": 10}}):
        with pytest.raises(ValidationError):
            EditRequest(**{"references": [REF], "camera": {}, **bad})
    assert "camera" not in EditRequest(prompt="x", references=[REF]).model_dump()
