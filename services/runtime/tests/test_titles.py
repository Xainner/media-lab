import json
import shutil
import subprocess
import threading
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from media_lab import main
from media_lab.contracts import AnimatedTitleRequest
from media_lab.creative import CreativeJobs, title_fade, video_info
from media_lab.creative_workflows import TITLE_FADE, TITLE_STYLES, TITLE_TAIL, title_duration, title_ink, title_prompt, title_slots
from media_lab.model_options import VideoOptions, video_size
from media_lab.store import IdempotencyConflict, Store


def test_contract_defaults_and_text_limits():
    body = AnimatedTitleRequest(phrases=["  MEDIA LAB  "], background="#ffffff")
    assert body.phrases == ["MEDIA LAB"] and body.background == "#FFFFFF"
    assert (body.seconds, body.aspect_ratio, body.resolution, body.style) == (5, "16:9", "720p", None)
    AnimatedTitleRequest(phrases=["x" * 160])
    AnimatedTitleRequest(phrases=["x" * 80, "y" * 80], seconds=5)
    for bad in ({"phrases": []}, {"phrases": ["x"] * 7}, {"phrases": [" "]}, {"phrases": ["a\nb"]},
                {"phrases": ["x" * 161]}, {"phrases": ["x" * 81, "y"]}, {"phrases": ["x" * 80, "y" * 80, "z"]},
                {"phrases": ["x"], "background": "black"}, {"phrases": ["x"], "background": "#12345"},
                {"phrases": ["x"], "background": "#1E3A8A"}, {"phrases": ["x"], "background": "#00FF00"},
                {"phrases": ["x"], "style": "chroma"}, {"phrases": ["x"], "seconds": 4},
                {"phrases": ["x"], "seconds": 16}, {"phrases": ["x"], "resolution": "native"},
                {"phrases": ["x"], "motion": "m" * 801}, {"phrases": ["x"], "look": "l" * 401}):
        with pytest.raises(ValidationError):
            AnimatedTitleRequest(**bad)


def test_sequence_needs_a_second_per_phrase_plus_the_tail():
    # 5 s is 124 frames (5.17 s): four phrases fit, five need 6 s.
    AnimatedTitleRequest(phrases=list("ABCD"), seconds=5)
    with pytest.raises(ValidationError, match="5 frases necesitan al menos 6 s"):
        AnimatedTitleRequest(phrases=list("ABCDE"), seconds=5)
    AnimatedTitleRequest(phrases=list("ABCDEF"), seconds=7)


@pytest.mark.parametrize("phrases,seconds", [(["CREA", "EXPLORA", "INSPIRA"], 6), (list("ABCD"), 5),
                                             (["Una frase bastante más larga", "corta"], 10)])
def test_slots_are_contiguous_and_end_before_the_tail(phrases, seconds):
    slots = title_slots(phrases, seconds)
    assert slots[0][0] == 0 and len(slots) == len(phrases)
    assert all(b[0] == a[1] for a, b in zip(slots, slots[1:]))
    assert all(end - start >= 0.99 for start, end in slots)
    assert slots[-1][1] == pytest.approx(title_duration(seconds) - TITLE_TAIL, abs=0.01)


def test_ink_contrasts_with_the_background():
    assert title_ink("#000000") == "white" and title_ink("#1E3A8A") == "white"
    assert title_ink("#FFFFFF") == "black" and title_ink("#FFD700") == "black"


def test_single_title_prompt_keeps_the_text_exact_and_ends_on_the_background():
    prompt = title_prompt(["¡Bienvenidos a Media Lab!"], 5, "#ffffff", "typewriter")
    assert '"¡Bienvenidos a Media Lab!"' in prompt
    assert TITLE_STYLES["typewriter"] in prompt and "black lettering" in prompt
    stop = f"{title_duration(5) - TITLE_TAIL:.2f}"
    assert f"left the frame by {stop} s" in prompt
    assert "pure white background (#FFFFFF)" in prompt and "no speech, singing or music" in prompt
    assert "Picture" not in prompt  # the runtime adds the FL2VA alignment line
    # Naming people or faces, even to forbid them, made H3 draw a face on light backgrounds.
    assert not any(word in prompt.lower() for word in ("people", "face", "person", "hands"))


def test_sequence_prompt_schedules_every_phrase_in_order():
    phrases = ["CREA", "EXPLORA", "INSPIRA"]
    prompt = title_prompt(phrases, 6, "#000000", motion="Each word rises out of light.", look="Thin gold serif.")
    lines = [line for line in prompt.splitlines() if line[:2] in {"1.", "2.", "3."}]
    assert [f'only "{p}" is visible' in line for p, line in zip(phrases, lines)] == [True] * 3
    assert "Each word rises out of light." in prompt and "Thin gold serif." in prompt
    assert not any(text in prompt for text in TITLE_STYLES.values())
    assert "pure black background (#000000)" in prompt and "Never show two phrases together" in prompt
    assert lines[-1].endswith("It does not stay on screen until the end.") and "until the end" not in lines[0]


def test_title_job_renders_the_background_once_as_first_and_last_frame(monkeypatch):
    monkeypatch.setattr("media_lab.creative.resolve_loras", lambda *_: [])
    creative = object.__new__(CreativeJobs)
    creative.store = SimpleNamespace()
    creative.h3_locks = [threading.Lock(), threading.Lock()]
    uploads, graphs = [], []

    def upload_image(path, job):
        with Image.open(path) as image:
            uploads.append((image.size, image.getpixel((0, 0)), image.getpixel((image.width - 1, image.height - 1))))
        return "background_job.png"
    creative.clients = [None, SimpleNamespace(upload_image=upload_image)]

    def run(job, gpu, graph, kind):
        graphs.append(graph)
        raise RuntimeError("stop before ComfyUI")
    creative._run = run
    request = AnimatedTitleRequest(phrases=["MEDIA LAB"], style="dust", background="#FFFFFF",
                                   aspect_ratio="9:16", seed=7).model_dump()
    with pytest.raises(RuntimeError, match="stop before ComfyUI"):
        creative._title("job", {"session_id": "s", "request": request}, 1)
    size = video_size("9:16", VideoOptions(resolution="720p"))
    assert uploads == [(size, (255, 255, 255), (255, 255, 255))]
    text = json.dumps(graphs[0])
    assert text.count("background_job.png") == 2 and "MEDIA LAB" in text
    assert "Picture 1" in text  # FL2VA alignment line


def test_title_job_reports_title_provenance(monkeypatch):
    creative = object.__new__(CreativeJobs)
    creative.h3_locks = [threading.Lock(), threading.Lock()]
    captured = {}

    def video(job, session, gpu, body, frame=None, provenance=None, finish=None):
        captured.update(body=body, frame=frame, provenance=provenance, exists=frame.exists(), finish=finish)
        return {"media": []}
    creative._video_locked = video
    request = AnimatedTitleRequest(phrases=["A", "B"], seconds=6, resolution="480p").model_dump()
    creative._title("job", {"session_id": "s", "request": request}, 0)
    body = captured["body"]
    assert (body.mode, body.profile, body.steps, body.seconds) == ("i2v", "fused_turbo", 4, 6)
    assert body.options.resolution == "480p" and body.first_frame is None and captured["exists"]
    assert not captured["frame"].exists()  # the background is never kept
    assert captured["provenance"] == {"workflow": "h3_title_v1", "title": {
        "phrases": ["A", "B"], "style": None, "motion": None, "look": None, "background": "#000000"}, "fade_out": TITLE_FADE}
    assert callable(captured["finish"])


def test_route_refuses_without_fused_turbo_and_submits_on_gpu_zero(monkeypatch):
    submitted = []
    monkeypatch.setattr(main, "creative", SimpleNamespace(
        submit=lambda op, request, gpu, key=None: submitted.append((op, gpu, key)) or {"job_id": "j", "status": "queued"}))
    body = AnimatedTitleRequest(phrases=["MEDIA LAB"])

    def missing(profile):
        raise ValueError(f"H3 {profile} is unavailable; no automatic model substitution")
    monkeypatch.setattr(main, "require_h3_profile", missing)
    with pytest.raises(HTTPException) as refused:
        main.title_job(body, None)
    assert refused.value.status_code == 422 and "fused_turbo" in refused.value.detail and not submitted
    monkeypatch.setattr(main, "require_h3_profile", lambda profile: None)
    assert main.title_job(body, "key-1")["job_id"] == "j"
    assert submitted == [("title", 0, "key-1")]


def test_title_is_a_resumable_creative_operation_with_idempotency(tmp_path):
    assert "title" in main.CREATIVE_OPERATIONS
    store = Store(tmp_path / "jobs.db")
    dispatched = []
    creative = CreativeJobs(SimpleNamespace(max_pending=4), store, None,
                            SimpleNamespace(clients=[], submit=lambda *args: dispatched.append(args) or 0))
    request = AnimatedTitleRequest(phrases=["MEDIA LAB"], session_id="s").model_dump()
    first = creative.submit("title", request, 0, key="title-1")
    assert creative.submit("title", request, 0, key="title-1")["job_id"] == first["job_id"]
    with pytest.raises(IdempotencyConflict):
        creative.submit("title", {**request, "background": "#FFFFFF"}, 0, key="title-1")
    assert len(dispatched) == 1


def test_capabilities_describe_titles():
    titles = main.capabilities()["video"]["titles"]
    assert titles["profile"] == "fused_turbo" and titles["styles"] == list(TITLE_STYLES)
    assert titles["max_phrases"] == 6 and titles["seconds"] == [5, 15]
    assert titles["resolutions"] == ["preview", "480p", "720p"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_title_fade_ends_picture_and_sound_on_the_background(tmp_path):
    clip = tmp_path / "red.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=128x72:r=24:d=2", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=2", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(clip)], check=True)
    faded = tmp_path / "faded.mp4"
    faded.write_bytes(title_fade(clip.read_bytes(), tmp_path, "#FFFFFF"))
    info = video_info(faded)
    assert info["audio_codec"] == "aac" and abs(info["duration"] - video_info(clip)["duration"]) < 0.1

    def pixel(seek):
        frame = tmp_path / "frame.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *seek, "-i", str(faded), "-update", "1", str(frame)], check=True)
        return Image.open(frame).convert("RGB").getpixel((64, 36))
    start = pixel(["-ss", "0.5", "-t", "0.04"])
    assert start[0] > 200 and start[1] < 60             # still red before the fade
    assert min(pixel(["-sseof", "-0.3"])) > 250         # the last frame is the background
