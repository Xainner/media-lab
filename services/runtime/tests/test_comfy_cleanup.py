import importlib.util
import json
import os
import time
from pathlib import Path

import httpx
import pytest

from media_lab import comfy
from media_lab.comfy import ComfyClient

RULES = Path(__file__).resolve().parents[2] / "comfyui-nodes" / "media_lab_cleanup" / "rules.py"
spec = importlib.util.spec_from_file_location("media_lab_cleanup_rules", RULES)
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)


def test_partially_valid_workflow_is_rejected_and_dequeued(monkeypatch):
    calls = []
    errors = {"latent": {"class_type": "EmptyLatentAudio", "dependent_outputs": ["save"], "errors": [
        {"type": "value_smaller_than_min", "message": "Value 0.6 smaller than min of 1.0", "details": "seconds"}]}}

    def handler(request):
        is_json = request.headers.get("content-type", "").startswith("application/json")
        calls.append((request.url.path, json.loads(request.content) if is_json else None))
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "p9", "number": 1, "node_errors": errors})
        return httpx.Response(200, json={})

    real = httpx.Client
    monkeypatch.setattr(comfy.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(comfy.websocket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    client = ComfyClient("http://comfy", 60)
    with pytest.raises(comfy.ComfyError, match=r"latent \(EmptyLatentAudio\): Value 0.6 smaller than min of 1.0: seconds"):
        client.run_output({"latent": {}}, "audio", lambda _: None, lambda: False)
    assert ("/queue", {"delete": ["p9"]}) in calls and ("/interrupt", {"prompt_id": "p9"}) in calls
    assert client.job_prompts == ["p9"]
    assert not any(path.startswith("/history") for path, _ in calls)


def test_end_job_deletes_uploads_outputs_and_history(monkeypatch):
    calls = []
    history = {"p1": {"outputs": {
        "9": {"gifs": [{"filename": "h3_00001_.mp4", "subfolder": "media_lab", "type": "output"}]},
        "4": {"images": [{"filename": "job_abc12345_1_x.png", "subfolder": "", "type": "input"},
                         {"filename": "ComfyUI_temp_1.png", "subfolder": "", "type": "temp"}]},
        "7": {"text": ["caption"]}}}}

    def handler(request):
        is_json = request.headers.get("content-type", "").startswith("application/json")
        calls.append((request.method, request.url.path, json.loads(request.content) if is_json else None))
        if request.url.path == "/upload/image":
            return httpx.Response(200, json={"name": "job_abc12345_voice_reference.wav", "subfolder": ""})
        if request.url.path == "/history/p1":
            return httpx.Response(200, json=history)
        return httpx.Response(200, json={})

    real = httpx.Client
    monkeypatch.setattr(comfy.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    # The scheduler and the job code hold different clients for the same worker.
    scheduler = ComfyClient("http://comfy", 3600)
    client = ComfyClient("http://comfy", 60)
    scheduler.begin_job()
    name = client.upload_audio(Path(__file__), "job_abc12345_voice")
    client.job_prompts.append("p1")
    scheduler.end_job()
    cleanup = next(body for method, path, body in calls if path == "/media_lab/cleanup")
    assert cleanup["files"] == [{"type": "input", "path": name},
                                {"type": "output", "path": "media_lab/h3_00001_.mp4"},
                                {"type": "temp", "path": "ComfyUI_temp_1.png"}]
    assert ("POST", "/history", {"delete": ["p1"]}) in calls
    # State is reset: a second end_job sends nothing.
    calls.clear()
    client.end_job()
    scheduler.end_job()
    assert calls == []


def roots(tmp_path):
    out = {name: tmp_path / name for name in ("input", "output", "temp")}
    for folder in out.values():
        folder.mkdir()
    (out["output"] / "media_lab").mkdir()
    return {k: str(v) for k, v in out.items()}


def test_cleanup_rules_only_touch_job_files(tmp_path):
    r = roots(tmp_path)
    inp, media = Path(r["input"]), Path(r["output"]) / "media_lab"
    for path in (inp / "job_abc12345_1_x.png", inp / "example.png", media / "h3_00001_.mp4",
                 media / "h3_00001_.png", media / "h3_00010_.mp4", Path(r["output"]) / "other.png"):
        path.write_bytes(b"x")
    assert rules.removable(r, "input", "job_abc12345_1_x.png") == [str(inp / "job_abc12345_1_x.png")]
    assert rules.removable(r, "input", "example.png") == []
    assert sorted(rules.removable(r, "output", "media_lab/h3_00001_.mp4")) == \
        [str(media / "h3_00001_.mp4"), str(media / "h3_00001_.png")]
    for bad in ("other.png", "../input/job_abc12345_1_x.png", str(media / "h3_00010_.mp4"), "media_lab/../other.png"):
        assert rules.removable(r, "output", bad) == []
    assert rules.removable(r, "secrets", "x") == []


def test_cleanup_rules_refuse_symlinks_and_sweep_only_old_job_files(tmp_path):
    r = roots(tmp_path)
    inp, media = Path(r["input"]), Path(r["output"]) / "media_lab"
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    try:
        os.symlink(outside, media / "link.mp4")
        assert rules.removable(r, "output", "media_lab/link.mp4") == []
    except (OSError, NotImplementedError):
        pass  # no symlink privilege on this host
    old, new, foreign = inp / "job_abc12345_old.png", media / "h3_00002_.mp4", inp / "example.png"
    for path in (old, new, foreign):
        path.write_bytes(b"x")
    past = time.time() - 2 * 86400
    os.utime(old, (past, past))
    os.utime(foreign, (past, past))
    assert rules.sweep(r, 86400, time.time()) == [str(old)]
    assert outside.read_text() == "keep"
