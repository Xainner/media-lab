import pytest

from media_lab.contracts import (
    EditRequest,
    ExportRequest,
    GenerateRequest,
    PRESETS_1MP,
    compile_prompt,
    generation_size,
    steps_for_quality,
    resolution_presets,
)


def test_default_generation_contract():
    body = GenerateRequest(prompt="a glass fox")
    assert generation_size(body, False) == (1024, 1024)
    assert steps_for_quality(body.quality) == 40


def test_2k_is_feature_gated():
    body = GenerateRequest(prompt="x", resolution_tier="2k")
    with pytest.raises(ValueError, match="2K"):
        generation_size(body, False)
    assert generation_size(body, True) == (2048, 2048)


def test_model_precision_is_explicit_and_limited():
    assert GenerateRequest(prompt="x").model_precision == "int8"
    assert GenerateRequest(prompt="x", model_precision="bf16").model_precision == "bf16"
    with pytest.raises(ValueError):
        GenerateRequest(prompt="x", model_precision="fp8")


def test_nine_one_megapixel_presets_are_valid():
    presets = resolution_presets()
    assert len(presets) == 9
    assert PRESETS_1MP["4:5"] == (896, 1120)
    assert PRESETS_1MP["5:4"] == (1120, 896)
    for preset in presets:
        assert preset["width"] % 32 == 0
        assert preset["height"] % 32 == 0
        assert 950_000 <= preset["width"] * preset["height"] <= 1_050_000


def test_rgba_prompt_is_explicit():
    result = compile_prompt("a red dragon sticker", True)
    assert result == ("This is an RGBA image with transparency. a red dragon sticker. "
                      "The image has alpha channel and the background is transparent.")
    assert compile_prompt("a red dragon sticker.", True) == result


def test_edit_reference_bounds_and_resolution():
    ref = {"uri": "artifact://s/references/x.png", "sha256": "a" * 64}
    assert len(EditRequest(prompt="edit", references=[ref]).references) == 1
    with pytest.raises(ValueError):
        EditRequest(prompt="edit", references=[ref], resolution=1000)
    with pytest.raises(ValueError):
        EditRequest(prompt="edit", references=[ref] * 17)


def test_ids_and_checksums_are_constrained():
    with pytest.raises(ValueError):
        GenerateRequest(prompt="x", session_id="../escape")
    with pytest.raises(ValueError):
        EditRequest(prompt="x", references=[{
            "uri": "artifact://s/references/x.png", "sha256": "not-a-digest",
        }])


def test_export_contract_rejects_invalid_options():
    base = {"uri": "artifact://s/images/x.png", "sha256": "a" * 64}
    assert ExportRequest(**base, format="webp", quality=90).format == "webp"
    with pytest.raises(ValueError):
        ExportRequest(**base, format="tiff")
    with pytest.raises(ValueError):
        ExportRequest(**base, quality=0)
    with pytest.raises(ValueError):
        ExportRequest(**base, background="white")
