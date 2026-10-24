import hashlib
import json
import math
import struct
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from test_web_security import lab, sign_in, image, ORIGIN
from media_lab.characters import CharacterBody
from media_lab.contracts import EditRequest, GenerateRequest, LoraUse, VideoRequest
from media_lab.creative_workflows import h3_workflow
from media_lab.loras import LoraLibrary, inspect_lora, lora_base, lora_file, parse_source, resolve_loras
from media_lab.security import as_owner
from media_lab.tenancy import NotOwned, ResourceLimit
from media_lab.workflows import chain_loras, edit_workflow, t2i_workflow

QWEN21 = {"diffusion_model.transformer_blocks.0.attn.to_q.lora_A.weight": [4, 4096],
          "diffusion_model.transformer_blocks.0.attn.to_q.lora_B.weight": [4096, 4]}
QWEN1 = {"transformer.transformer_blocks.0.attn.to_q.lora_A.weight": [4, 3072],
         "transformer.transformer_blocks.0.attn.to_q.lora_B.weight": [3072, 4]}
H3 = {"diffusion_model.blocks.0.attn.qkv_proj.lora_A.weight": [4, 5376],
      "diffusion_model.blocks.0.attn.qkv_proj.lora_B.weight": [16128, 4]}
WAN = {"diffusion_model.blocks.0.cross_attn.k.lora_down.weight": [4, 5120],
       "diffusion_model.blocks.0.cross_attn.k.lora_up.weight": [5120, 4]}


def safetensors(tensors: dict) -> bytes:
    header, offset = {"__metadata__": {"format": "pt"}}, 0
    for name, shape in tensors.items():
        size = 2 * math.prod(shape)
        header[name] = {"dtype": "BF16", "shape": shape, "data_offsets": [offset, offset + size]}
        offset += size
    raw = json.dumps(header).encode()
    return struct.pack("<Q", len(raw)) + raw + b"\0" * offset


def header(tensors):
    return {name: {"shape": shape} for name, shape in tensors.items()}


def test_links_from_hugging_face_and_civitai():
    assert parse_source("https://huggingface.co/me/qwen-style") == {"site": "hf", "repo": "me/qwen-style", "revision": "main", "path": ""}
    assert parse_source("https://huggingface.co/me/qwen-style/blob/v2/loras/a.safetensors")["path"] == "loras/a.safetensors"
    assert parse_source("https://civitai.com/models/123/some-style?modelVersionId=456") == {"site": "civitai", "model": "123", "version": "456"}
    assert parse_source("https://civitai.com/api/download/models/456")["version"] == "456"
    for bad in ("http://huggingface.co/me/x", "https://example.com/me/x", "https://huggingface.co/datasets/me/x",
                "https://civitai.com/images/9", "https://huggingface.co/me/x/blob/main/../../etc"):
        with pytest.raises(ValueError):
            parse_source(bad)


def test_base_comes_from_tensor_names_and_shapes(tmp_path):
    assert lora_base(header(QWEN21)) == "qwen" and lora_base(header(H3)) == "h3"
    with pytest.raises(ValueError, match="Qwen-Image 1"):
        lora_base(header(QWEN1))
    with pytest.raises(ValueError, match="no compatible"):
        lora_base(header(WAN))
    with pytest.raises(ValueError, match="no es un LoRA"):
        lora_base(header({"model.diffusion_model.input_blocks.0.weight": [320, 4]}))
    good, cut = tmp_path / "good.safetensors", tmp_path / "cut.safetensors"
    good.write_bytes(safetensors(H3))
    cut.write_bytes(safetensors(H3)[:-10])
    assert inspect_lora(good) == "h3"
    with pytest.raises(ValueError, match="incompleto"):
        inspect_lora(cut)


def site(files: dict, civitai: dict | None = None):
    """Hugging Face repo me/style at commit c0ffee and an optional Civitai version 456."""
    def handler(request: httpx.Request):
        url = str(request.url)
        if "/api/models/me/style/revision/" in url:
            return httpx.Response(200, json={"sha": "c0ffee", "siblings": [
                {"rfilename": n, "lfs": {"sha256": hashlib.sha256(d).hexdigest(), "size": len(d)}} for n, d in files.items()]})
        if "/me/style/resolve/c0ffee/" in url:
            return httpx.Response(200, content=files[url.rsplit("/", 1)[1]])
        if civitai and url.endswith("/api/v1/model-versions/456"):
            return httpx.Response(200, json={k: v for k, v in civitai.items() if k != "_data"})
        if civitai and url == "https://civitai.com/api/download/models/456":
            return httpx.Response(200, content=civitai["_data"])
        return httpx.Response(404)
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def settle(library, lid):
    for _ in range(200):
        item = library.get(lid)
        if item["status"] != "downloading":
            return item
        time.sleep(0.02)
    raise AssertionError("download did not finish")


def test_hugging_face_lora_is_private_shared_on_disk_and_resolved(lab, tmp_path, monkeypatch):
    app, _, store, _, _, alice, bob = lab
    monkeypatch.setenv("LORA_ROOT", str(tmp_path / "loras"))
    data = safetensors(QWEN21)
    library = LoraLibrary(store, tmp_path / "loras", site({"style.safetensors": data}))
    with as_owner(alice):
        item = settle(library, library.add("https://huggingface.co/me/style", "")["id"])
        assert (item["status"], item["base"], item["name"], item["bytes"]) == ("ready", "qwen", "style", len(data))
        file = tmp_path / "loras" / "loras" / lora_file(hashlib.sha256(data).hexdigest())
        assert file.read_bytes() == data
        with pytest.raises(ValueError, match="Ya añadiste"):
            library.add("https://huggingface.co/me/style")
        library.update(item["id"], {"strength": 0.7, "trigger": "zxc style"})
        assert resolve_loras(store, [LoraUse(id=item["id"])], "qwen") == [(file.name, 0.7)]
        assert resolve_loras(store, [LoraUse(id=item["id"], strength=1.2)], "qwen") == [(file.name, 1.2)]
        with pytest.raises(ValueError, match="hace falta"):
            resolve_loras(store, [LoraUse(id=item["id"])], "h3")
    with as_owner(bob):
        assert library.items() == []
        with pytest.raises(ValueError):
            resolve_loras(store, [LoraUse(id=item["id"])], "qwen")
        with pytest.raises(NotOwned):
            library.delete(item["id"])
        twin = settle(library, library.add("https://huggingface.co/me/style")["id"])
    with as_owner(alice):
        library.delete(item["id"])
    assert file.is_file()  # Bob still has it.
    with as_owner(bob):
        library.delete(twin["id"])
    assert not file.exists()


def test_repository_with_several_files_needs_the_file_link(lab, tmp_path):
    _, _, store, _, _, alice, _ = lab
    files = {"a.safetensors": safetensors(QWEN21), "b.safetensors": safetensors(H3)}
    library = LoraLibrary(store, tmp_path / "loras", site(files))
    with as_owner(alice):
        failed = settle(library, library.add("https://huggingface.co/me/style")["id"])
        assert failed["status"] == "error" and "2 archivos" in failed["error"]
        video = settle(library, library.add("https://huggingface.co/me/style/blob/main/b.safetensors")["id"])
        assert video["base"] == "h3"
        wan = LoraLibrary(store, tmp_path / "loras", site({"w.safetensors": safetensors(WAN)}))
        rejected = settle(wan, wan.add("https://huggingface.co/me/style/resolve/main/w.safetensors")["id"])
        assert rejected["status"] == "error" and "no compatible" in rejected["error"]
        assert not list((tmp_path / "loras" / "loras").glob(".*.part"))


def test_civitai_checks_type_hash_and_real_person_flag(lab, tmp_path):
    _, _, store, _, _, alice, _ = lab
    data = safetensors(H3)
    version = {"id": 456, "modelId": 123, "name": "v1", "baseModel": "Other", "trainedWords": ["zxc dance", "neon"],
               "model": {"name": "Neon Dance", "type": "LORA", "poi": False}, "_data": data,
               "files": [{"type": "Model", "primary": True, "metadata": {"format": "SafeTensor"}, "sizeKB": len(data) / 1024,
                          "hashes": {"SHA256": hashlib.sha256(data).hexdigest().upper()},
                          "downloadUrl": "https://civitai.com/api/download/models/456"}]}
    with as_owner(alice):
        library = LoraLibrary(store, tmp_path / "loras", site({}, version))
        item = settle(library, library.add("https://civitai.com/models/123?modelVersionId=456")["id"])
        assert (item["status"], item["base"], item["name"], item["trigger"]) == ("ready", "h3", "Neon Dance · v1", "zxc dance, neon")
        library.delete(item["id"])
        for change, message in (({"model": {**version["model"], "poi": True}}, "persona real"),
                                ({"model": {**version["model"], "type": "Checkpoint"}}, "no un LoRA"),
                                ({"baseModel": "Pony"}, "para Pony"),
                                ({"files": [{**version["files"][0], "hashes": {"SHA256": "0" * 64}}]}, "hash")):
            library = LoraLibrary(store, tmp_path / "loras", site({}, {**version, **change}))
            failed = settle(library, library.add("https://civitai.com/models/123?modelVersionId=456")["id"])
            assert failed["status"] == "error" and message in failed["error"], failed
            library.delete(failed["id"])


def test_library_needs_a_root_and_has_a_limit(lab, tmp_path, monkeypatch):
    _, _, store, _, _, alice, _ = lab
    with as_owner(alice):
        with pytest.raises(ValueError, match="no está configurada"):
            LoraLibrary(store, None).add("https://huggingface.co/me/style")
        monkeypatch.setattr("media_lab.loras.LORA_LIMIT", 1)
        library = LoraLibrary(store, tmp_path / "loras", site({"style.safetensors": safetensors(QWEN21)}))
        settle(library, library.add("https://huggingface.co/me/style")["id"])
        with pytest.raises(ResourceLimit):
            library.add("https://huggingface.co/me/other")


def test_loras_chain_after_the_diffusion_model():
    loras = [("ml_a.safetensors", 0.8), ("ml_b.safetensors", 1.0)]
    graph = t2i_workflow("p", 1024, 1024, 1, 25)
    chain_loras(graph, "1", loras)
    assert graph["user_lora_0"]["inputs"] == {"model": ["1", 0], "lora_name": "ml_a.safetensors", "strength_model": 0.8}
    assert graph["user_lora_1"]["inputs"]["model"] == ["user_lora_0", 0]
    assert graph["6"]["inputs"]["model"] == ["user_lora_1", 0]
    edit = edit_workflow("p", ["a.png"], 1, 25)
    chain_loras(edit, "1", loras[:1])
    assert edit["2"]["inputs"]["model"] == ["user_lora_0", 0]
    video = h3_workflow("p", "t2v", 832, 480, 5, 8, 1, profile="turbo")
    chain_loras(video, "unet", loras[:1])
    assert video["turbo_lora"]["inputs"]["model"] == ["user_lora_0", 0]
    assert video["user_lora_0"]["inputs"]["model"] == ["unet", 0]
    untouched = t2i_workflow("p", 1024, 1024, 1, 25)
    chain_loras(untouched, "1", [])
    assert untouched == t2i_workflow("p", 1024, 1024, 1, 25)


def test_requests_accept_library_loras():
    use = {"id": "lora_" + "a" * 16}
    assert GenerateRequest(prompt="p", loras=[use]).loras[0].strength is None
    assert "loras" not in GenerateRequest(prompt="p").model_dump()
    assert VideoRequest(prompt="p", loras=[use]).loras[0].id == use["id"]
    ref = {"uri": "artifact://s/images/a.png", "sha256": "a" * 64}
    for bad in (lambda: GenerateRequest(prompt="p", loras=[use, use]),
                lambda: GenerateRequest(prompt="p", model="moss", loras=[use]),
                lambda: EditRequest(references=[ref], remove_background=True, loras=[use]),
                lambda: GenerateRequest(prompt="p", loras=[{"id": "../x"}])):
        with pytest.raises(ValueError):
            bad()


def test_characters_are_private_and_hold_images_and_a_lora(lab, tmp_path):
    app, _, store, artifacts, _, alice, bob = lab
    characters = app.state.characters
    library = LoraLibrary(store, tmp_path / "loras", site({"style.safetensors": safetensors(QWEN21)}))
    with as_owner(alice):
        face = artifacts.import_image("direct", image(), {"operation": "upload"})
        lora = settle(library, library.add("https://huggingface.co/me/style")["id"])
        ref = {"uri": face["uri"], "sha256": face["sha256"]}
        made = characters.save(CharacterBody(handle="Ana", name="Ana", description="woman with curly hair",
                                             references=[ref], lora_id=lora["id"]))
        assert made["handle"] == "ana" and made["references"] == [ref] and made["lora"]["base"] == "qwen"
        with pytest.raises(ValueError, match="@ana"):
            characters.save(CharacterBody(handle="ana", name="Other", references=[ref]))
        library.delete(lora["id"])
        assert characters.get(made["id"])["lora"] is None
    with as_owner(bob):
        assert characters.items() == []
        with pytest.raises(NotOwned):
            characters.save(CharacterBody(handle="ana", name="Ana", references=[ref]))
        with pytest.raises(NotOwned):
            characters.delete(made["id"])
    with as_owner(alice):
        artifacts.delete_media(face["uri"], face["sha256"])
        assert characters.get(made["id"])["references"] == []
        characters.delete(made["id"])
        assert characters.items() == []


def test_routes_are_behind_the_browser_boundary(lab):
    app, *_ = lab
    client = TestClient(app, base_url=ORIGIN)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": sign_in(client, "alice").json()["csrf"]}
    assert client.get("/v1/loras").json()["ready"] is False
    assert client.post("/v1/loras", json={"url": "https://huggingface.co/me/style"}).status_code == 403
    response = client.post("/v1/loras", json={"url": "https://huggingface.co/me/style"}, headers=headers)
    assert response.status_code == 422 and "no está configurada" in response.json()["detail"]
    assert client.get("/v1/characters").json() == {"items": []}
    bad = client.post("/v1/characters", json={"handle": "a b", "name": "x", "references": []}, headers=headers)
    assert bad.status_code in {400, 422}
    assert client.delete("/v1/characters/char_0000000000000000", headers=headers).status_code == 404
