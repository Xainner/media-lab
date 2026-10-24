from media_lab.workflows import UNET_BF16, edit_workflow, t2i_workflow


def test_t2i_uses_only_native_qwen21_nodes():
    graph = t2i_workflow("test", 1024, 1024, 7, 25)
    classes = {node["class_type"] for node in graph.values()}
    assert "TextEncodeQwenImage21" in classes
    assert "KSampler" in classes
    assert graph["6"]["inputs"]["cfg"] == 1.0


def test_edit_autogrow_input_paths_are_v3_compatible():
    graph = edit_workflow("use <image2>", ["a.png", "b.png"], 7, 25)
    text = graph["5"]["inputs"]
    assert text["images.image_1"] == ["11", 0]
    assert text["images.image_2"] == ["12", 0]
    assert graph["6"]["inputs"]["latent_image"] == ["5", 2]


def test_bf16_changes_only_diffusion_weights():
    original = t2i_workflow("x", 1024, 1024, 123, 40)
    alternate = t2i_workflow("x", 1024, 1024, 123, 40, unet=UNET_BF16)
    assert alternate["1"]["inputs"]["unet_name"] == UNET_BF16
    alternate["1"] = original["1"]
    assert alternate == original
