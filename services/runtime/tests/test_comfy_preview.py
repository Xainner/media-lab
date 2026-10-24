from media_lab.comfy import parse_preview_frame


def frame(event: int, image_type: int, body: bytes) -> bytes:
    return event.to_bytes(4, "big") + image_type.to_bytes(4, "big") + body


def test_preview_frames_are_parsed_by_image_type():
    assert parse_preview_frame(frame(1, 1, b"jpeg")) == (b"jpeg", "image/jpeg")
    assert parse_preview_frame(frame(1, 2, b"png")) == (b"png", "image/png")


def test_unknown_or_empty_frames_are_ignored():
    assert parse_preview_frame(frame(2, 1, b"x")) is None
    assert parse_preview_frame(frame(1, 9, b"x")) is None
    assert parse_preview_frame(frame(1, 1, b"")) is None
