from io import BytesIO

import pytest
from PIL import Image
from pydantic import ValidationError

from media_lab.contracts import EditRequest
from media_lab.jobs import clean_cutout

REF = {"uri": "artifact://s/images/a.png", "sha256": "a" * 64}


def test_remove_background_needs_no_prompt_and_one_base_image():
    body = EditRequest(references=[REF], remove_background=True)
    assert body.model_dump()["remove_background"] is True
    for bad in ({"references": [REF, REF]}, {"model_variant": "turbo"},
                {"camera": {"azimuth": "back view"}}):
        with pytest.raises(ValidationError):
            EditRequest(**{"references": [REF], "remove_background": True, **bad})


def test_plain_edits_keep_their_fingerprint():
    assert "remove_background" not in EditRequest(references=[REF], prompt="make it blue").model_dump()


def test_clean_cutout_clears_the_background_haze_and_keeps_soft_edges():
    image = Image.new("RGBA", (4, 1))
    for x, alpha in enumerate((3, 120, 250, 255)):
        image.putpixel((x, 0), (10, 20, 30, alpha))
    raw = BytesIO()
    image.save(raw, "PNG")
    cleaned = Image.open(BytesIO(clean_cutout(raw.getvalue())))
    assert [cleaned.getpixel((x, 0))[3] for x in range(4)] == [0, 120, 255, 255]
