import json

import pytest
from PIL import Image

from media_lab.creative_workflows import FACE_STRENGTHS, HEAD_TURBO, face_detect_workflow, face_refine_workflow
from media_lab.face_refine import crop_frames, drop_outliers, face_windows, parse_boxes, paste_frames


def box(x, y, side):
    return {"x": x, "y": y, "width": side, "height": side, "label": "face", "score": 0.9}


def test_boxes_keep_the_largest_face_and_mark_empty_frames():
    text = json.dumps([[box(10, 10, 20), box(100, 50, 40)], [], [box(0, 0, 0)]])
    assert parse_boxes(text) == [box(100, 50, 40), None, None]


def test_misfires_on_head_turns_are_dropped():
    boxes = [box(400, 90, 50)] * 20 + [box(300, 0, 200)] * 3 + [box(400, 90, 52)] * 20
    kept = drop_outliers(boxes)
    assert kept[20:23] == [None, None, None] and kept[0] and kept[-1]


def test_windows_follow_the_face_smoothly_and_stay_inside_the_frame():
    boxes = [box(400 + i, 90, 50) for i in range(60)] + [None] * 5 + [box(820, 440, 60)]
    windows = face_windows(boxes, 864, 480)
    assert len(windows) == len(boxes)
    for left, top, side in windows:
        assert side % 2 == 0 and 64 <= side <= 480
        assert 0 <= left <= 864 - side and 0 <= top <= 480 - side
    assert all(abs(a[0] - b[0]) <= 4 for a, b in zip(windows[:50], windows[1:50]))
    assert windows[0][2] == 120  # 50 px face × 2.4


def test_no_face_or_tiny_faces_are_rejected():
    with pytest.raises(ValueError, match="ninguna cara"):
        face_windows([None, None], 640, 360)
    with pytest.raises(ValueError, match="pequeña"):
        face_windows([box(10, 10, 12)], 640, 360)


def test_crop_and_paste_round_trip_only_touches_the_face(tmp_path):
    frame = tmp_path / "f.png"
    Image.new("RGB", (320, 180), (40, 40, 40)).save(frame)
    windows = [(100, 20, 120)]
    crops = crop_frames([frame], windows, tmp_path / "crops", size=256)
    assert Image.open(crops[0]).size == (256, 256)
    Image.new("RGB", (256, 256), (250, 0, 0)).save(crops[0])
    pasted = Image.open(paste_frames([frame], crops, windows, tmp_path / "out")[0])
    assert pasted.getpixel((160, 80))[0] > 200          # window centre is the refined face
    assert pasted.getpixel((5, 5)) == (40, 40, 40)       # outside the window is untouched
    assert pasted.getpixel((102, 22))[0] < 60            # window corner stays feathered out


def test_refine_graph_starts_from_the_window_at_partial_noise_without_a_guide():
    graph = face_refine_workflow("win.mp4", "who.png", 512, 124, 3, "medium")
    assert graph["turbo"]["inputs"]["lora_name"] == HEAD_TURBO
    assert graph["sigmas"]["inputs"]["sigmas"] == FACE_STRENGTHS["medium"]
    assert graph["sample"]["inputs"]["latent_image"] == ["start", 0] and graph["sample"]["inputs"]["sigmas"] == ["sigmas", 0]
    assert graph["encode"]["inputs"]["pixels"] == ["source_parts", 0]
    assert "guide" not in graph and graph["guider"]["inputs"] == {"model": ["turbo", 0], "conditioning": ["condition", 0]}
    assert graph["condition"]["inputs"]["length"] == 124 and graph["condition"]["inputs"]["ref_images.ref_image_0"] == ["ref_0", 0]
    assert "scheduler" not in graph and "decode_audio" not in graph and "audio" not in graph["video"]["inputs"]
    assert face_detect_workflow("clip.mp4")["boxes"]["inputs"]["source"] == ["faces", 1]


def test_refine_is_an_mcp_tool_with_a_guide():
    from media_lab.contracts import FaceRefineRequest
    from media_lab.mcp_server import GUIDES, OPERATIONS
    assert any(op[0] == "refine_faces" and op[2] == "/v1/jobs/face_refine" for op in OPERATIONS)
    assert "refine_faces(body={video, identity, strength, seed})" in "".join(str(v) for v in GUIDES.values())
    body = FaceRefineRequest(video={"uri": "artifact://s/videos/a.mp4", "sha256": "a" * 64})
    assert body.strength == "medium" and body.identity is None
