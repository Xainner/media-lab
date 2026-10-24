import io
import wave
import pytest
import threading
from pathlib import Path
from types import SimpleNamespace
from pydantic import ValidationError

from media_lab.artifacts import ArtifactStore
from media_lab.comfy import ComfyClient
from media_lab.creative_workflows import (h3_workflow, yue2_workflow, h3_profiles,
    H3_FUSED, H3_FUSED_VIDEO_VAE, H3_CLIP, H3_AUDIO_VAE)
from media_lab.contracts import VideoRequest, ProductionRequest
from media_lab.creative import CreativeJobs
from media_lab.store import Store, IdempotencyConflict


@pytest.mark.parametrize("operation", ["video", "production"])
def test_pre_upgrade_base_idempotency_returns_same_job_without_gpu_admission(tmp_path, operation):
    store = Store(tmp_path / "jobs.db")
    if operation == "video":
        request = VideoRequest(prompt="x", session_id="s").model_dump()
        legacy = {k: v for k, v in request.items() if k != "profile"}
    else:
        request = ProductionRequest(title="x", brief="x", song={"uri": "artifact://s/songs/x.flac", "sha256": "a" * 64},
                                    scenes=[{}], session_id="s").model_dump()
        legacy = {k: v for k, v in request.items() if k not in {"video_profile", "video_steps"}}
    store.create_job_once("old", "s", operation, legacy, key="pre-upgrade")
    def no_effect(*args):
        raise AssertionError("idempotent replay must not be dispatched")
    creative = CreativeJobs(SimpleNamespace(max_pending=4), store, None, SimpleNamespace(clients=[], submit=no_effect))
    assert creative.submit(operation, request, 0, key="pre-upgrade")["job_id"] == "old"
    changed = {**request, **({"profile": "fused_turbo", "steps": 4} if operation == "video"
                            else {"video_profile": "fused_turbo", "video_steps": 4})}
    with pytest.raises(IdempotencyConflict):
        creative.submit(operation, changed, 0, key="pre-upgrade")


@pytest.mark.parametrize("profile,steps", [("base", 20), ("fused_turbo", 4)])
def test_director_new_clip_inherits_profile_without_regenerating_its_reference(monkeypatch, profile, steps):
    monkeypatch.setattr("media_lab.creative.audio_analysis", lambda path: {"duration": 5})
    creative = object.__new__(CreativeJobs)
    creative.artifacts = SimpleNamespace(resolve=lambda *args: Path("test.png"))
    creative.store = SimpleNamespace(cancel_requested=lambda job: False)
    creative.h3_locks = [threading.Lock(), threading.Lock()]
    captured = []
    def video(job, session, gpu, body):
        captured.append(body)
        raise RuntimeError("stop before actual generation")
    creative._video_locked = video
    ref = {"uri": "artifact://s/images/ref.png", "sha256": "a" * 64}
    body = ProductionRequest(title="x", brief="x", song=ref, video_profile=profile,
                             scenes=[{"start": 0, "end": 5, "image": ref, "image_prompt": "x", "video_prompt": "x"}])
    with pytest.raises(RuntimeError, match="stop before actual generation"):
        creative._production("job", {"session_id": "s", "request": body.model_dump()}, 1)
    assert captured[0].profile == profile and captured[0].steps == steps
    assert captured[0].first_frame.uri == ref["uri"]


def test_h3_profile_defaults_and_step_boundaries():
    assert VideoRequest(prompt="x").steps == 20
    assert VideoRequest(prompt="x", profile="fused_turbo").steps == 4
    assert VideoRequest(prompt="x", profile="fused_turbo", steps=12).steps == 12
    for profile, steps in (("base", 4), ("fused_turbo", 13), ("fused_turbo", 3)):
        with pytest.raises(ValidationError):
            VideoRequest(prompt="x", profile=profile, steps=steps)
    with pytest.raises(ValidationError):
        VideoRequest(prompt="x", profile="invented")
    old = ProductionRequest(title="x", song={"uri": "artifact://s/songs/x.flac", "sha256": "a" * 64},
                            brief="x", scenes=[{}])
    assert (old.video_profile, old.video_steps) == ("base", 20)
    new = ProductionRequest.model_validate({**old.model_dump(), "video_profile": "fused_turbo", "video_steps": None})
    assert new.video_steps == 4


@pytest.mark.parametrize("mode", ["t2v", "i2v", "r2v"])
def test_fused_graph_uses_same_bake_native_shift_simple_and_no_extra_lora(mode):
    graph = h3_workflow("cup", mode, 640, 352, 5, 4, 7,
                        first="first.png", references=["ref.png"], profile="fused_turbo")
    assert graph["unet"]["inputs"]["unet_name"] == H3_FUSED
    assert graph["video_vae"]["inputs"]["vae_name"] == H3_FUSED_VIDEO_VAE
    assert graph["scheduler"]["inputs"] == {"model": ["shift", 0], "scheduler": "simple", "steps": 4, "denoise": 1.0}
    assert graph["shift"]["inputs"] == {"model": ["unet", 0], "shift_video": 12.0, "shift_audio": 3.0}
    assert graph["guider"]["inputs"]["model"] == ["shift", 0]
    assert not any("lora" in n["class_type"].lower() or "sla" in n["class_type"].lower() for n in graph.values())
    assert graph["condition"]["inputs"]["length"] % 17 == 5


def test_fused_readiness_checks_shared_encoder_audio_and_dedicated_assets(tmp_path):
    shared, fused = tmp_path / "shared", tmp_path / "fused"
    for root, folder, name in ((shared, "text_encoders", H3_CLIP), (shared, "vae", H3_AUDIO_VAE),
                              (fused, "diffusion_models", H3_FUSED), (fused, "vae", H3_FUSED_VIDEO_VAE)):
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / name).touch()
    profiles = h3_profiles(shared, fused, tmp_path)
    assert profiles["fused_turbo"]["ready"] and not profiles["base"]["ready"]
    (shared / "vae" / H3_AUDIO_VAE).unlink()
    assert not h3_profiles(shared, fused, tmp_path)["fused_turbo"]["ready"]


def test_h3_reference_graph_uses_native_autogrow_and_mp4():
    graph = h3_workflow("actor <Picture 1>", "r2v", 864, 480, 5, 20, 7,
                        references=["reference.png"])
    assert graph["condition"]["class_type"] == "MiniMaxH3ReferenceToVideo"
    assert graph["condition"]["inputs"]["ref_images.ref_image_0"] == ["ref_0", 0]
    assert graph["save"]["inputs"]["format"] == "mp4"
    assert graph["save"]["inputs"]["format.codec"] == "h264"


def test_yue2_direct_and_cover_graphs():
    direct = yue2_workflow("rock", "hello", "direct", "", 120, 32, 7)
    assert direct["music"]["inputs"]["abc"] == ""
    assert direct["save"]["inputs"]["format"] == "flac"
    cover = yue2_workflow("rock", "hello", "melody", "", 120, 32, 7, "source.wav")
    assert cover["abc"]["class_type"] == "SheetSage2AudioToABC"
    assert cover["music"]["inputs"]["abc"] == ["abc", 0]


def test_comfy_save_video_history_uses_images_key():
    history = {"prompt": {"outputs": {"save": {"images": [{
        "filename": "h3_00001_.mp4", "subfolder": "media_lab", "type": "output"}]}}}}
    assert ComfyClient._first_output(history, "prompt", "videos")["filename"].endswith(".mp4")


def test_media_store_preserves_original_bytes_and_kind(tmp_path):
    sink = io.BytesIO()
    with wave.open(sink, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 8000)
    store = ArtifactStore(tmp_path, 20_000_000, 100_000_000)
    ref = store.put_media("sess_a", sink.getvalue(), "audio/wav", "songs", {"model": "YuE2"})
    assert store.resolve(ref["uri"], ref["sha256"]).read_bytes() == sink.getvalue()
    assert store.library()[0]["model"] == "YuE2"
    source = tmp_path / "movie.mkv"
    source.write_bytes(b"matroska-smoke")
    master = store.put_media("sess_a", source, "video/x-matroska", "productions")
    assert store.resolve(master["uri"], master["sha256"]).read_bytes() == b"matroska-smoke"


def test_director_lip_sync_scene_uses_r2v_with_song_excerpt(monkeypatch, tmp_path):
    monkeypatch.setattr("media_lab.creative.audio_analysis", lambda path: {"duration": 6})
    calls = []
    monkeypatch.setattr("media_lab.creative.subprocess.run", lambda cmd, **kw: (calls.append(cmd), Path(cmd[-1]).write_bytes(b"fLaC"))[0])
    stored = []
    def put_media(session, path, mime, kind, provenance):
        stored.append((mime, kind, provenance))
        return {"uri": "artifact://s/sources/seg.flac", "sha256": "b" * 64}
    creative = object.__new__(CreativeJobs)
    creative.artifacts = SimpleNamespace(resolve=lambda *args: Path("test.png"), put_media=put_media)
    creative.store = SimpleNamespace(cancel_requested=lambda job: False)
    creative.h3_locks = [threading.Lock(), threading.Lock()]
    captured = []
    def video(job, session, gpu, body):
        captured.append(body)
        raise RuntimeError("stop")
    creative._video_locked = video
    ref = {"uri": "artifact://s/images/ref.png", "sha256": "a" * 64}
    song = {"uri": "artifact://s/songs/x.flac", "sha256": "c" * 64}
    ref2va = "subject_definitions:\n<Subject 1> is the singer in <Picture 1>."
    body = ProductionRequest(title="x", brief="x", song=song, scenes=[
        {"start": 0, "end": 6, "image": ref, "image_prompt": "x", "video_prompt": ref2va, "lip_sync": True}])
    with pytest.raises(RuntimeError, match="stop"):
        creative._production("job", {"session_id": "s", "request": body.model_dump()}, 0)
    request = captured[0]
    assert request.mode == "r2v" and request.first_frame is None
    assert request.references[0].uri == ref["uri"]
    assert request.reference_audios[0].uri == "artifact://s/sources/seg.flac"
    assert calls[0][calls[0].index("-ss") + 1] == "0.000" and calls[0][calls[0].index("-t") + 1] == "6.000"
    assert stored[0][:2] == ("audio/flac", "sources") and stored[0][2]["operation"] == "production_lip_sync_audio"


@pytest.mark.parametrize("scene,error", [
    ({"start": 0, "end": 6, "video_prompt": "integrated_multimodal_description: [Shot 1] x"}, "Ref2VA"),
    ({"start": 0, "end": 1.5, "video_prompt": "subject_definitions: x"}, "2 seconds"),
])
def test_director_lip_sync_validates_before_gpu_work(monkeypatch, scene, error):
    monkeypatch.setattr("media_lab.creative.audio_analysis", lambda path: {"duration": scene["end"]})
    creative = object.__new__(CreativeJobs)
    creative.artifacts = SimpleNamespace(resolve=lambda *args: Path("x"))
    song = {"uri": "artifact://s/songs/x.flac", "sha256": "c" * 64}
    body = ProductionRequest(title="x", brief="x", song=song, scenes=[{**scene, "image_prompt": "x", "lip_sync": True}])
    with pytest.raises(ValueError, match=error):
        creative._production("job", {"session_id": "s", "request": body.model_dump()}, 0)


def test_edit_accepts_at_most_ten_references():
    from media_lab.contracts import EditRequest
    ref = {"uri": "artifact://s/images/r.png", "sha256": "a" * 64}
    assert len(EditRequest(prompt="x", references=[ref] * 10).references) == 10
    with pytest.raises(ValidationError):
        EditRequest(prompt="x", references=[ref] * 11)


def test_turbo_profile_adds_the_lightx2v_lora_on_the_official_weights(tmp_path):
    from media_lab.creative_workflows import H3_FL, H3_REF, H3_TURBO_FL_LORA, H3_TURBO_REF_LORA
    graph = h3_workflow("[Shot 1] A market.", "t2v", 864, 480, 5, 8, 1, profile="turbo")
    assert graph["unet"]["inputs"]["unet_name"] == H3_FL
    assert graph["turbo_lora"]["inputs"] == {"model": ["unet", 0], "lora_name": H3_TURBO_FL_LORA, "strength_model": 1.0}
    assert graph["shift"]["inputs"] == {"model": ["turbo_lora", 0], "shift_video": 6.0, "shift_audio": 3.0}
    assert graph["guider"]["inputs"]["model"] == graph["scheduler"]["inputs"]["model"] == ["shift", 0]
    assert (graph["sampler"]["inputs"]["sampler_name"], graph["scheduler"]["inputs"]["scheduler"]) == ("euler", "simple")
    assert graph["video_vae"]["inputs"]["vae_name"] == H3_FUSED_VIDEO_VAE
    ref = h3_workflow("x", "r2v", 864, 480, 5, 8, 1, references=["a.png"], profile="turbo")
    assert ref["unet"]["inputs"]["unet_name"] == H3_REF and ref["turbo_lora"]["inputs"]["lora_name"] == H3_TURBO_REF_LORA
    with pytest.raises(ValueError):
        h3_workflow("x", "t2v", 864, 480, 5, 20, 1, profile="turbo")
    shared, fused = tmp_path / "shared", tmp_path / "fused"
    files = [(shared, "text_encoders", H3_CLIP), (shared, "vae", H3_AUDIO_VAE), (shared, "diffusion_models", H3_FL),
             (shared, "diffusion_models", H3_REF), (fused, "vae", H3_FUSED_VIDEO_VAE),
             (tmp_path, "loras", H3_TURBO_FL_LORA), (tmp_path, "loras", H3_TURBO_REF_LORA)]
    for root, folder, name in files:
        (root / folder).mkdir(parents=True, exist_ok=True)
        (root / folder / name).touch()
    profiles = h3_profiles(shared, fused, tmp_path)
    assert profiles["turbo"]["ready"] and not profiles["base"]["ready"]
    assert profiles["turbo"]["steps"]["default"] == 8
