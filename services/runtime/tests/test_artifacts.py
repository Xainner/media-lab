from io import BytesIO

import pytest
from PIL import Image

from media_lab.artifacts import ArtifactStore


def png(mode: str, color) -> bytes:
    stream = BytesIO()
    Image.new(mode, (32, 16), color).save(stream, "PNG")
    return stream.getvalue()


def test_fully_opaque_rgba_is_treated_as_rgb(tmp_path):
    store = ArtifactStore(tmp_path, 1024 * 1024, 1_000_000)
    media = store.import_image("s1", png("RGBA", (1, 2, 3, 255)), {})
    assert media["has_alpha"] is False
    _preview, content_type, stats = store.review_preview(media["uri"], media["sha256"])
    assert content_type == "image/jpeg"
    assert stats == {"has_alpha": False}


def test_transparency_and_checksum_are_preserved(tmp_path):
    store = ArtifactStore(tmp_path, 1024 * 1024, 1_000_000)
    media = store.put_upload("s1", png("RGBA", (1, 2, 3, 0)), "image/png")
    assert media["has_alpha"] is True
    _preview, content_type, stats = store.review_preview(media["uri"], media["sha256"])
    assert content_type == "image/png"
    assert stats["alpha_min"] == 0
    with pytest.raises(ValueError, match="checksum"):
        store.resolve(media["uri"], "0" * 64)


def test_png_export_is_byte_identical(tmp_path):
    store = ArtifactStore(tmp_path, 1024 * 1024, 1_000_000)
    media = store.import_image("s1", png("RGB", (12, 34, 56)), {})
    original = store.resolve(media["uri"], media["sha256"]).read_bytes()
    exported, content_type = store.export_image(media["uri"], media["sha256"], "png")
    assert exported == original
    assert content_type == "image/png"


@pytest.mark.parametrize("background,expected", [
    ("#ffffff", (255, 255, 255)),
    ("#000000", (0, 0, 0)),
    ("#336699", (51, 102, 153)),
])
def test_jpeg_export_flattens_transparency(tmp_path, background, expected):
    store = ArtifactStore(tmp_path, 1024 * 1024, 1_000_000)
    media = store.import_image("s1", png("RGBA", (255, 0, 0, 0)), {})
    exported, content_type = store.export_image(
        media["uri"], media["sha256"], "jpeg", 100, background,
    )
    image = Image.open(BytesIO(exported))
    assert content_type == "image/jpeg"
    assert image.mode == "RGB"
    actual = image.getpixel((8, 8))
    assert all(abs(a - b) <= 3 for a, b in zip(actual, expected))


def test_webp_export_preserves_alpha(tmp_path):
    store = ArtifactStore(tmp_path, 1024 * 1024, 1_000_000)
    media = store.import_image("s1", png("RGBA", (12, 34, 56, 0)), {})
    exported, content_type = store.export_image(media["uri"], media["sha256"], "webp", 90)
    image = Image.open(BytesIO(exported)).convert("RGBA")
    assert content_type == "image/webp"
    assert image.getchannel("A").getextrema()[0] == 0


def test_export_requires_matching_checksum(tmp_path):
    store = ArtifactStore(tmp_path, 1024 * 1024, 1_000_000)
    media = store.import_image("s1", png("RGB", (12, 34, 56)), {})
    with pytest.raises(ValueError, match="checksum"):
        store.export_image(media["uri"], "0" * 64, "jpeg")


def test_delete_image_removes_file_and_sidecar(tmp_path):
    store = ArtifactStore(tmp_path, 1024 * 1024, 1_000_000)
    media = store.import_image("s1", png("RGB", (1, 2, 3)), {"input_prompt": "x"})
    ref = store.put_upload("s1", png("RGB", (1, 2, 3)), "image/png")
    with pytest.raises(ValueError, match="checksum"):
        store.delete_image(media["uri"], "0" * 64)
    with pytest.raises(ValueError, match="checksum"):
        store.delete_image(media["uri"], "")
    with pytest.raises(ValueError, match="gallery"):
        store.delete_image(ref["uri"], ref["sha256"])
    store.delete_image(media["uri"], media["sha256"])
    assert store.gallery() == []
    assert not list(tmp_path.glob("s1/images/*"))
    trash = list((tmp_path / ".trash").glob("*"))
    assert len(trash) == 1
    assert sorted(path.name for path in trash[0].iterdir()) == sorted([
        media["uri"].rsplit("/", 1)[-1],
        media["uri"].rsplit("/", 1)[-1] + ".json",
    ])
