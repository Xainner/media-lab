from __future__ import annotations

import json
import uuid
import tempfile
import subprocess
from pathlib import Path

from PIL import Image

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

from .artifacts import ArtifactStore
from .comfy import ComfyClient
from .config import SETTINGS
from .contracts import (ExportRequest, EditRequest, GenerateRequest, SessionMessage, VideoRequest, SongRequest,
                        FaceRefineRequest, ProductionRequest, RemoveRequest, SoundRequest, SpeechRequest, StemsRequest, SwapRequest, UpscaleRequest, UPSCALE_MAX_INPUT_PIXELS, UPSCALE_MAX_SECONDS,
                        UPSCALE_MAX_WORK_SECONDS, UPSCALE_RATE, resolution_presets)
from .creative import CreativeJobs, FACE_SECONDS, REMOVE_SECONDS, STEMS_SECONDS, SWAP_SECONDS, audio_analysis, check_face_input, check_remove_input, check_stems_input, check_control_input, check_swap_input, check_upscale_input, media_probe, video_info
from .model_options import option_catalog, image_canvas
from .contracts import generation_size
from .creative_workflows import (H3_FL, H3_REF, H3_CLIP, H3_VIDEO_VAE, H3_AUDIO_VAE, YUE2, SHEETSAGE, h3_profiles,
                                 FLASHVSR_FILES, FLASHVSR_MODEL, flashvsr_ready, swap_ready, SWAP_LORA,
                                 head_swap_ready, HEAD_LORA, face_refine_ready, FACE_STRENGTHS, ace_ready, ACE_SECONDS,
                                 remover_ready, REMOVER_LORA, stems_ready, STEMS, h3_control_ready, VIDEO_CONTROL_MODES,
                                 VIDEO_CONTROL_SECONDS, scail_ready, sa3_ready, SA3_KINDS, SA3_STEPS,
                                 kandinsky6_ready, K6_SIZES, K6_STEPS, tts_ready, TTS_CHECKPOINTS, TTS_LANGUAGES,
                                 TTS_REFERENCE_SECONDS, TTS_SPEAKERS)
from .gpu_guard import GpuGuard
from .jobs import JobManager, QueueFull
from .gpu_workers import GpuWorkers
from .store import Store, IdempotencyConflict
from .inspection import inspect_media
from .prompt_check import PromptCheck, check_prompt
from .loras import LORA_BASES, LORA_USE_MAX, lora_root, resolve_loras
from .workflows import (ENCODER, UNET, UNET_BF16, UNET_TURBO, UNET_TURBO_BF16, TURBO_STEPS, VAE, MOSS_STEPS, CAMERA_AZIMUTHS,
                        CAMERA_DISTANCES, CAMERA_ELEVATIONS, CONTROL_MODES, camera_ready, control_ready, diffusion_model,
                        moss_ready, FLUX3_STEPS, FLUX3_MAX_REFERENCES, flux3_ready)


# Jobs run by CreativeJobs (everything except Qwen generate/edit, which JobManager runs).
CREATIVE_OPERATIONS = {"video", "song", "production", "upscale", "swap", "face_refine", "remove", "stems", "sound", "speech"}

app = FastAPI(title="Media Lab Runtime", version="0.6.0")
store = Store(SETTINGS.db_path)
store.mark_interrupted_on_boot()
artifacts = ArtifactStore(SETTINGS.artifacts_root, SETTINGS.upload_max_bytes, SETTINGS.upload_max_pixels)
comfy = ComfyClient(SETTINGS.comfy_url, SETTINGS.generation_timeout)
guard = GpuGuard(SETTINGS)
workers = GpuWorkers(SETTINGS, store)
jobs = JobManager(SETTINGS, store, artifacts, workers)
creative = CreativeJobs(SETTINGS, store, artifacts, workers)


def model_status() -> dict:
    encoder = __import__("os").environ.get("QWEN21_ENCODER", ENCODER)
    required = {
        "diffusion_model": SETTINGS.model_root / "diffusion_models" / UNET,
        "text_encoder": SETTINGS.model_root / "text_encoders" / encoder,
        "vae": SETTINGS.model_root / "vae" / VAE,
    }
    files = {name: {"name": path.name, "present": path.is_file()} for name, path in required.items()}
    bf16_path = SETTINGS.model_root / "diffusion_models" / UNET_BF16
    turbo = {precision: {"name": name, "present": (SETTINGS.model_root / "diffusion_models" / name).is_file()}
             for precision, name in (("int8", UNET_TURBO), ("bf16", UNET_TURBO_BF16))}
    return {"ok": all(item["present"] for item in files.values()), "files": files,
            "bf16": {"name": bf16_path.name, "present": bf16_path.is_file(),
                     "enabled": SETTINGS.enable_bf16},
            "turbo": turbo,
            "flashvsr": {"name": FLASHVSR_MODEL, "present": flashvsr_ready(SETTINGS.model_root)}}


def image_model_ready(variant: str, precision: str) -> bool:
    if precision == "bf16" and not SETTINGS.enable_bf16:
        return False
    return (SETTINGS.model_root / "diffusion_models" / diffusion_model(variant, precision)).is_file()


def require_image_model(variant: str, precision: str) -> None:
    # The base INT8 model is the installation baseline; health/doctor report it if missing.
    if (variant, precision) != ("base", "int8") and not image_model_ready(variant, precision):
        label = "Qwen-Image 2.1 Turbo" if variant == "turbo" else "Qwen-Image 2.1"
        raise ValueError(f"{label} {precision.upper()} is not validated or its model is missing")


@app.get("/v1/health")
def health():
    comfy_state = comfy.health()
    models = model_status()
    worker_states = workers.status()
    guard_state = dict(worker_states[0]["gpu_guard"])
    guard_state["available"] = any(w["health"]["ok"] and w["gpu_guard"]["available"] for w in worker_states)
    guard_state["reason"] = "" if guard_state["available"] else "; ".join(
        f"GPU {w['gpu']}: {w['gpu_guard'].get('reason') or 'ComfyUI unavailable'}" for w in worker_states)
    return {
        "status": "ok" if all(w["health"]["ok"] for w in worker_states) and models["ok"] else "degraded",
        "runtime": {"ok": True, "version": app.version},
        "comfy": comfy_state,
        "models": models,
        "queue": store.queue_counts(),
        "gpu_guard": guard_state,
        "workers": worker_states,
    }


@app.get("/v1/capabilities")
def capabilities():
    profiles = h3_profiles(SETTINGS.h3_model_root, SETTINGS.h3_fused_root, SETTINGS.model_root)
    return {
        "backend": "comfyui",
        "model": "Qwen-Image-2.1",
        "text_to_image": True,
        "image_edit": True,
        "image_workers": {"gpus": list(range(len(workers.clients))), "automatic_selection": True,
                          "max_parallel": len(workers.clients),
                          "shared_with": ["video", "music", "production"]},
        "rgba": True,
        "max_references": 16,
        "generation_options": option_catalog(),
        "quality_modes": {"draft": 25, "quality": 40},
        "aspect_ratios": [preset["id"] for preset in resolution_presets()],
        "resolution_presets": resolution_presets(),
        "export_formats": {
            "png": {"alpha": True, "lossless": True, "quality": False},
            "jpeg": {"alpha": False, "lossless": False, "quality": True},
            "webp": {"alpha": True, "lossless": False, "quality": True},
        },
        "two_k_enabled": SETTINGS.enable_2k,
        "two_k_create_only": True,
        "model_precisions": {"int8": True, "bf16": image_model_ready("base", "bf16")},
        "model_variants": {
            "base": {"label": "Qwen-Image 2.1", "steps": {"draft": 25, "quality": 40},
                     "precisions": {"int8": image_model_ready("base", "int8"), "bf16": image_model_ready("base", "bf16")}},
            "turbo": {"label": "Qwen-Image 2.1 Turbo", "steps": TURBO_STEPS, "fixed_schedule": True,
                      "precisions": {"int8": image_model_ready("turbo", "int8"), "bf16": image_model_ready("turbo", "bf16")},
                      "ignored_options": ["steps", "scheduler", "denoise"]},
        },
        "image_models": {"qwen": {"label": "Qwen-Image 2.1", "ready": image_model_ready("base", "int8")},
                         "moss": {"label": "MOSS-Image SFT", "ready": moss_ready(SETTINGS.model_root),
                                  "steps": MOSS_STEPS, "text_rendering": True, "edit": False, "transparent": False},
                         "flux3": {"label": "FLUX 3 Image Klein", "ready": flux3_ready(SETTINGS.model_root, "draft"),
                                   "quality_ready": flux3_ready(SETTINGS.model_root, "quality"), "steps": FLUX3_STEPS,
                                   "prompt_upsampler": True, "edit": True, "max_references": FLUX3_MAX_REFERENCES,
                                   "transparent": False}},
        "image_control": {"label": "Qwen 2.1 Fun ControlNet Union",
                          "modes": {mode: control_ready(SETTINGS.model_root, mode) for mode in CONTROL_MODES}},
        "image_camera": {"label": "QMA camera angles", "ready": camera_ready(SETTINGS.model_root),
                         "azimuths": list(CAMERA_AZIMUTHS), "elevations": list(CAMERA_ELEVATIONS),
                         "distances": list(CAMERA_DISTANCES)},
        "image_remove_background": {"label": "Qwen-Image 2.1 background removal", "ready": image_model_ready("base", "int8"),
                                    "steps": 40, "output": "RGBA PNG"},
        "bf16_2k_enabled": False,
        "non_commercial_only": True,
        "video": {"model": "MiniMax-H3", "modes": ["t2v", "i2v", "r2v"],
                  "ready": any(p["ready"] for p in profiles.values()),
                  "models": {"h3": {"label": "MiniMax H3", "ready": any(p["ready"] for p in profiles.values())},
                             "kandinsky6": {"label": "Kandinsky 6.0 Lite", "ready": kandinsky6_ready(SETTINGS.model_root, SETTINGS.h3_model_root),
                                            "modes": ["t2v", "i2v"], "seconds": 5, "steps": K6_STEPS, "audio": True,
                                            "lip_sync": True, "sizes": {k: list(v) for k, v in K6_SIZES.items()}}},
                  "control": {"model": "MiniMax-H3 Fun ControlNet-Union 2.0", "profiles": ["base", "turbo"],
                              "modes": {mode: h3_control_ready(SETTINGS.model_root, mode) for mode in VIDEO_CONTROL_MODES},
                              "seconds": list(VIDEO_CONTROL_SECONDS), "keeps_audio": True},
                  "default_profile": "base", "profiles": profiles},
        "music": {"model": "YuE2-3B", "modes": ["direct", "full", "melody", "cover"],
                  "ready": (SETTINGS.model_root / "checkpoints" / YUE2).is_file(),
                  "cover_ready": (SETTINGS.model_root / "audio_encoders" / SHEETSAGE).is_file(),
                  "models": {"yue2": {"label": "YuE2 3B", "ready": (SETTINGS.model_root / "checkpoints" / YUE2).is_file(),
                                      "covers": True, "seconds": [10, 900]},
                             "ace_step": {"label": "ACE-Step 1.5 XL Turbo", "ready": ace_ready(SETTINGS.model_root),
                                          "covers": False, "seconds": list(ACE_SECONDS), "exact_length": True}}},
        "upscale": {"model": "FlashVSR v1.1", "ready": flashvsr_ready(SETTINGS.model_root),
                    "scales": [2, 4], "qualities": {"fast": "tiny", "quality": "full"}, "default_quality": "fast",
                    "max_seconds": UPSCALE_MAX_SECONDS, "max_work_seconds": UPSCALE_MAX_WORK_SECONDS,
                    "seconds_per_output_megapixel_second": UPSCALE_RATE,
                    "max_input_pixels": {str(k): v for k, v in UPSCALE_MAX_INPUT_PIXELS.items()},
                    "keeps_audio": True, "sources": ["videos", "productions", "sources"]},
        "swap": {"model": "MiniMax-H3 Character Swap v1.5", "lora": SWAP_LORA,
                 "ready": swap_ready(SETTINGS.model_root, SETTINGS.h3_model_root),
                 "modes": {"character": {"model": "MiniMax-H3 Character Swap v1.5", "lora": SWAP_LORA,
                                         "ready": swap_ready(SETTINGS.model_root, SETTINGS.h3_model_root)},
                           "head": {"model": "MiniMax-H3 Head Swap v1.0", "lora": HEAD_LORA, "experimental": True,
                                    "ready": head_swap_ready(SETTINGS.model_root, SETTINGS.h3_model_root)},
                           "scail": {"model": "SCAIL-2", "steps": 6,
                                     "ready": scail_ready(SETTINGS.model_root, SETTINGS.h3_model_root)}},
                 "seconds": list(SWAP_SECONDS), "best_seconds": 5, "keeps_audio": True,
                 "sources": ["videos", "productions", "sources"]},
        "face_refine": {"model": "MiniMax-H3 Face Refine", "detector": "MediaPipe Face Landmarker",
                        "ready": face_refine_ready(SETTINGS.model_root, SETTINGS.h3_model_root),
                        "seconds": list(FACE_SECONDS), "strengths": list(FACE_STRENGTHS), "faces": 1,
                        "keeps_audio": True, "sources": ["videos", "productions", "sources"]},
        "remove": {"model": "MiniMax-H3 Person Remover V1", "lora": REMOVER_LORA, "segmenter": "SAM 3.1",
                   "ready": remover_ready(SETTINGS.model_root, SETTINGS.h3_model_root),
                   "auto_clean_frame": image_model_ready("base", "int8"), "experimental": True,
                   "seconds": list(REMOVE_SECONDS), "best_seconds": 5, "people": 1, "keeps_audio": True,
                   "sources": ["videos", "productions", "sources"]},
        "stems": {"model": "Hybrid Demucs", "ready": stems_ready(SETTINGS.model_root), "modes": {k: list(v) for k, v in STEMS.items()},
                  "formats": ["flac", "mp3"], "seconds": list(STEMS_SECONDS), "sources": ["songs", "sources", "productions"]},
        "sound": {"model": "Stable Audio 3", "steps": SA3_STEPS, "formats": ["flac", "mp3"], "vocals": False,
                  "kinds": {kind: {"ready": sa3_ready(SETTINGS.model_root, kind), "seconds": list(limits),
                                   "model": {"medium": "Medium", "small_sfx": "Small SFX"}[checkpoint]}
                            for kind, (checkpoint, _, limits) in SA3_KINDS.items()}},
        "speech": {"model": "Qwen3-TTS 1.7B", "formats": ["flac", "mp3"], "languages": list(TTS_LANGUAGES),
                   "speakers": list(TTS_SPEAKERS), "max_chars": 5000, "reference_seconds": list(TTS_REFERENCE_SECONDS),
                   "clone_requires_consent": True,
                   "voices": {voice: tts_ready(SETTINGS.model_root, voice) for voice in TTS_CHECKPOINTS}},
        "loras": {"ready": lora_root() is not None, "bases": LORA_BASES, "max_per_job": LORA_USE_MAX,
                  "applies_to": {"qwen": ["generate_image", "edit_image"], "h3": ["generate_video"]}},
        "production": {"director": True, "resume": True, "keyframe_profiles": ["legacy", "1mp", "2k"],
                       "video_profiles": list(profiles)},
        "limits": {"max_pending": 4, "video_seconds": [5, 15], "video_steps": [4, 40],
                   "song_seconds": [10, 900], "song_steps": [4, 80], "max_scenes": 100},
        "inputs": input_limits(),
    }


def input_limits() -> dict:
    """What can be uploaded and how many owned references each creation accepts."""
    return {
        "image": {"accepted": ["image/png", "image/jpeg", "image/webp"], "stored_as": "image/png",
                  "max_bytes": SETTINGS.upload_max_bytes, "max_pixels": SETTINGS.upload_max_pixels},
        "audio": {"accepted": ["audio/wav", "audio/flac", "audio/mpeg", "audio/ogg", "audio/opus"],
                  "seconds": [1, 900], "max_bytes": MEDIA_UPLOAD_MAX_BYTES},
        "video": {"accepted": ["video/mp4", "video/x-matroska", "video/webm"],
                  "seconds": list(VIDEO_UPLOAD_SECONDS), "max_bytes": MEDIA_UPLOAD_MAX_BYTES},
        "references": {
            "edit_image": {"references": {"images": [1, 10]}},
            "generate_video": {"first_frame": {"images": [0, 1]}, "last_frame": {"images": [0, 1]},
                               "references": {"images": [0, 9], "mode": "r2v"},
                               "reference_videos": {"videos": [0, 3], "seconds": [2, 15], "mode": "r2v"},
                               "reference_audios": {"audios": [0, 3], "seconds": [1, 15], "mode": "r2v"}},
            "generate_music": {"source_audio": {"audios": [0, 1], "seconds": [1, 900]}},
            "upscale_video": {"video": {"videos": [1, 1], "seconds": [0, UPSCALE_MAX_SECONDS]}},
            "swap_character": {"video": {"videos": [1, 1], "seconds": list(SWAP_SECONDS)}, "character": {"images": [1, 1]}},
            "refine_faces": {"video": {"videos": [1, 1], "seconds": list(FACE_SECONDS)}, "identity": {"images": [0, 1]}},
            "separate_stems": {"audio": {"audios": [1, 1], "seconds": list(STEMS_SECONDS)}},
            "remove_person": {"video": {"videos": [1, 1], "seconds": list(REMOVE_SECONDS)}, "clean_frame": {"images": [0, 1]}},
            "create_production": {"song": {"audios": [1, 1], "seconds": [5, 900]},
                                  "scenes": [1, 100], "per_scene": {"image": [0, 1], "video": [0, 1]}},
            "improve_prompt": {"references": {"images": [0, 16]}},
            "start_agent": {"references": {"any": [0, 16]}},
            "add_message": {"media": {"any": [0, 100]}},
        },
    }


@app.get("/v1/nodes/status")
def node_status():
    packages = {
        "H3 storyboard": "custom_nodes.ComfyUI-MiniMaxH3",
        "H3 Audio T8": "custom_nodes.minimax-h3-audio-T8",
        "YuE2 ABC": "custom_nodes.ComfyUI-YuE2",
        "YuE2 piano roll": "custom_nodes.YuE2-ComfyUI",
        "FlashVSR": "custom_nodes.ComfyUI-FlashVSR_Ultra_Fast",
        "Media Lab stems": "custom_nodes.media_lab_stems",
    }
    workers = []
    for index, client in enumerate(creative.clients):
        try:
            info = client.object_info()
            counts = {name: sum(node.get("python_module") == module for node in info.values())
                      for name, module in packages.items()}
            workers.append({"gpu": index, "ok": True, "packages": counts,
                            "native_h3": "MiniMaxH3ImageToVideo" in info,
                            "native_yue2": "YuE2GenerateMusic" in info,
                            "flashvsr": "FlashVSRNodeAdv" in info})
        except Exception as exc:
            workers.append({"gpu": index, "ok": False, "error": str(exc), "packages": {}})
    return {"ok": all(worker["ok"] for worker in workers), "workers": workers}


MEDIA_UPLOAD_MAX_BYTES = 500 * 1024 * 1024
# Uploaded videos serve H3 references (2–15 s, checked per job) and upscaling (up to its limit).
VIDEO_UPLOAD_SECONDS = (1, UPSCALE_MAX_SECONDS)


def store_media_source(candidate: Path, content_type: str, session_id: str) -> dict:
    if content_type.startswith('video/'):
        probe = media_probe(candidate)
        low, high = VIDEO_UPLOAD_SECONDS
        if not any(stream.get('codec_type') == 'video' for stream in probe['streams']) or not low <= probe['duration'] <= high:
            raise ValueError(f'El vídeo debe durar entre {low} y {high} segundos')
    else:
        audio_analysis(candidate)
    return artifacts.put_media(session_id, candidate, content_type, "sources")


@app.post("/v1/media/uploads")
async def upload_media(file: UploadFile = File(...), session_id: str = Form(default="direct")):
    try:
        with tempfile.TemporaryDirectory() as directory:
            candidate, size = Path(directory) / "source", 0
            with candidate.open("wb") as target:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MEDIA_UPLOAD_MAX_BYTES:
                        raise ValueError("El archivo supera 500 MiB")
                    target.write(chunk)
            if not size:
                raise ValueError("El archivo está vacío")
            # Probing and the audio envelope are CPU/subprocess work; keep the event loop free.
            media = await run_in_threadpool(store_media_source, candidate, file.content_type or "", session_id)
        return {"ok": True, "data": media}
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/media/analyze")
def analyze_media(uri: str, sha256: str):
    try:
        return {"ok": True, **audio_analysis(artifacts.resolve(uri, sha256))}
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/library")
def library(limit: int = Query(default=100, ge=1, le=500), q: str = Query(default="", max_length=1000),
            kind: str = Query(default="", pattern="^(|images|songs|videos|productions|sources|references)$"),
            offset: int = Query(default=0, ge=0)):
    items = artifacts.search_library(q, kind)
    return {"ok": True, "items": items[offset:offset + limit], "total": len(items),
            "next_offset": offset + limit if offset + limit < len(items) else None}


@app.get("/v1/media/inspect")
def inspect_artifact(uri: str, sha256: str):
    try:
        return {"ok": True, **inspect_media(artifacts, uri, sha256)}
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/video", status_code=202)
def video_job(body: VideoRequest, idempotency_key: str | None = Header(default=None)):
    try:
        for ref in [body.first_frame, body.last_frame, *body.references, *body.reference_videos, *body.reference_audios]:
            if ref:
                artifacts.resolve(ref.uri, ref.sha256)
        if body.mode == "i2v" and not body.first_frame:
            raise ValueError("i2v requires first_frame")
        if body.control:
            if not h3_control_ready(SETTINGS.model_root, body.control.mode):
                raise ValueError("H3 video control is not installed for this mode; no automatic substitution")
            check_control_input(video_info(artifacts.resolve(body.control.video.uri, body.control.video.sha256)))
        # Official H3 Ref2VA input limits: an image or video is required, at most 12 files, each audio
        # 2–15 s, and at most 15 s of reference video and 15 s of reference audio in total.
        if body.mode == "r2v" and not (body.references or body.reference_videos or body.control):
            raise ValueError("r2v necesita al menos una imagen o un vídeo de referencia")
        if len(body.references) + len(body.reference_videos) + len(body.reference_audios) > 12:
            raise ValueError("H3 admite hasta 12 referencias en total")
        video_seconds = audio_seconds = 0.0
        for ref in body.reference_videos:
            probe = media_probe(artifacts.resolve(ref.uri, ref.sha256))
            if not any(stream.get('codec_type') == 'video' for stream in probe['streams']) or not 2 <= probe['duration'] <= 15:
                raise ValueError('Las referencias de vídeo deben durar entre 2 y 15 segundos')
            video_seconds += probe['duration']
            # A reference video's soundtrack becomes an <Audio> label and counts toward the audio total.
            if any(stream.get('codec_type') == 'audio' for stream in probe['streams']):
                audio_seconds += probe['duration']
        for ref in body.reference_audios:
            probe = media_probe(artifacts.resolve(ref.uri, ref.sha256))
            if not any(stream.get('codec_type') == 'audio' for stream in probe['streams']) or not 2 <= probe['duration'] <= 15:
                raise ValueError('Las referencias de audio deben durar entre 2 y 15 segundos')
            audio_seconds += probe['duration']
        if video_seconds > 15.05 or audio_seconds > 15.05:
            raise ValueError('Las referencias suman más de 15 s de vídeo o de audio; recórtalas o usa un vídeo sin sonido')
        if body.model == "kandinsky6":
            if not kandinsky6_ready(SETTINGS.model_root, SETTINGS.h3_model_root):
                raise ValueError("Kandinsky 6 is not installed; no automatic substitution")
            return {"ok": True, **creative.submit("video", body.model_dump(), 0, key=idempotency_key)}
        require_h3_profile(body.profile)
        resolve_loras(store, body.loras, "h3")
        return {"ok": True, **creative.submit("video", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (ValueError, subprocess.SubprocessError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/upscale", status_code=202)
def upscale_job(body: UpscaleRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if not flashvsr_ready(SETTINGS.model_root):
            raise ValueError("FlashVSR v1.1 is not installed; no automatic substitution")
        path = artifacts.resolve(body.video.uri, body.video.sha256)
        check_upscale_input(video_info(path), body.scale, body.quality)
        return {"ok": True, **creative.submit("upscale", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (ValueError, subprocess.SubprocessError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/remove", status_code=202)
def remove_job(body: RemoveRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if not remover_ready(SETTINGS.model_root, SETTINGS.h3_model_root):
            raise ValueError("Person Remover is not installed; no automatic substitution")
        if body.clean_frame:
            artifacts.resolve(body.clean_frame.uri, body.clean_frame.sha256)
        else:
            require_image_model("base", "int8")
        check_remove_input(video_info(artifacts.resolve(body.video.uri, body.video.sha256)))
        return {"ok": True, **creative.submit("remove", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (ValueError, subprocess.SubprocessError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/stems", status_code=202)
def stems_job(body: StemsRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if not stems_ready(SETTINGS.model_root):
            raise ValueError("The stems model is not installed")
        check_stems_input(media_probe(artifacts.resolve(body.audio.uri, body.audio.sha256)))
        return {"ok": True, **creative.submit("stems", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (ValueError, subprocess.SubprocessError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/sound", status_code=202)
def sound_job(body: SoundRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if not sa3_ready(SETTINGS.model_root, body.kind):
            raise ValueError("Stable Audio 3 is not installed; no automatic substitution")
        return {"ok": True, **creative.submit("sound", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/speech", status_code=202)
def speech_job(body: SpeechRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if not tts_ready(SETTINGS.model_root, body.voice):
            raise ValueError("Qwen3-TTS is not installed; no automatic substitution")
        if body.reference:
            probe = media_probe(artifacts.resolve(body.reference.uri, body.reference.sha256))
            if not any(stream.get("codec_type") == "audio" for stream in probe["streams"]):
                raise ValueError("La referencia no tiene audio")
            if probe["duration"] < TTS_REFERENCE_SECONDS[0]:
                raise ValueError(f"La voz de referencia debe durar al menos {TTS_REFERENCE_SECONDS[0]} s")
        return {"ok": True, **creative.submit("speech", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (ValueError, subprocess.SubprocessError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/face_refine", status_code=202)
def face_refine_job(body: FaceRefineRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if not face_refine_ready(SETTINGS.model_root, SETTINGS.h3_model_root):
            raise ValueError("Face refine is not installed; no automatic substitution")
        check_face_input(video_info(artifacts.resolve(body.video.uri, body.video.sha256)))
        if body.identity:
            artifacts.resolve(body.identity.uri, body.identity.sha256)
        return {"ok": True, **creative.submit("face_refine", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (ValueError, subprocess.SubprocessError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/swap", status_code=202)
def swap_job(body: SwapRequest, idempotency_key: str | None = Header(default=None)):
    try:
        ready = {"head": head_swap_ready, "scail": scail_ready}.get(body.mode, swap_ready)
        if not ready(SETTINGS.model_root, SETTINGS.h3_model_root):
            raise ValueError(f"The {body.mode} swap is not installed; no automatic substitution")
        check_swap_input(video_info(artifacts.resolve(body.video.uri, body.video.sha256)))
        artifacts.resolve(body.character.uri, body.character.sha256)
        return {"ok": True, **creative.submit("swap", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (ValueError, subprocess.SubprocessError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/song", status_code=202)
def song_job(body: SongRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if body.model == "ace_step" and not ace_ready(SETTINGS.model_root):
            raise ValueError("ACE-Step 1.5 is not installed; no automatic substitution")
        if body.source_audio:
            artifacts.resolve(body.source_audio.uri, body.source_audio.sha256)
        return {"ok": True, **creative.submit("song", body.model_dump(), 1, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/production", status_code=202)
def production_job(body: ProductionRequest, idempotency_key: str | None = Header(default=None)):
    try:
        artifacts.resolve(body.song.uri, body.song.sha256)
        require_image_model(body.keyframe_variant, body.keyframe_precision)
        if any(not scene.get('image') and not scene.get('video') for scene in body.scenes):
            keyframe = GenerateRequest(prompt=body.brief, aspect_ratio=body.aspect_ratio,
                                       resolution_tier='2k' if body.keyframe_resolution == '2k' else '1mp',
                                       model_precision=body.keyframe_precision, model_variant=body.keyframe_variant,
                                       options=body.keyframe_options)
            if keyframe.resolution_tier == '2k' and keyframe.model_precision == 'bf16':
                raise ValueError('BF16 a 2K no está habilitado')
            image_canvas(keyframe, SETTINGS.enable_2k, generation_size(keyframe, SETTINGS.enable_2k))
        for scene in body.scenes:
            for name in ("image", "video"):
                if scene.get(name):
                    artifacts.resolve(scene[name]["uri"], scene[name]["sha256"])
        if any(not scene.get("video") for scene in body.scenes):
            require_h3_profile(body.video_profile)
        return {"ok": True, **creative.submit("production", body.model_dump(), 0, key=idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def require_h3_profile(profile: str) -> None:
    if not h3_profiles(SETTINGS.h3_model_root, SETTINGS.h3_fused_root, SETTINGS.model_root)[profile]["ready"]:
        raise ValueError(f"H3 {profile} is unavailable; no automatic model substitution")


@app.post("/v1/jobs/{job_id}/resume", status_code=202)
def resume_job(job_id: str, idempotency_key: str | None = Header(default=None)):
    old = store.get_job(job_id)
    if not old:
        raise HTTPException(status_code=404, detail="job not found")
    if old["status"] not in {"failed", "cancelled", "interrupted", "blocked_gpu"}:
        raise HTTPException(status_code=409, detail="job is not resumable")
    try:
        request = {**old["request"], "session_id": old["session_id"]}
        if old["operation"] == "generate":
            body = GenerateRequest.model_validate(request)
            image_canvas(body, SETTINGS.enable_2k, generation_size(body, SETTINGS.enable_2k))
            return {"ok": True, **jobs.submit_generate(body, idempotency_key, f"resume:{job_id}")}
        if old["operation"] == "edit":
            return {"ok": True, **jobs.submit_edit(EditRequest.model_validate(request), idempotency_key, f"resume:{job_id}")}
        if old["operation"] in CREATIVE_OPERATIONS - {"production"}:
            return {"ok": True, **creative.submit(old["operation"], request, 0,
                                                  key=idempotency_key, scope=f"resume:{job_id}")}
        return {"ok": True, **creative.submit("production", request, 0, old["result"],
                                              key=idempotency_key, scope=f"resume:{job_id}")}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/uploads")
async def upload(file: UploadFile = File(...), session_id: str = Form(default="direct")):
    try:
        data = await file.read(SETTINGS.upload_max_bytes + 1)
        media = artifacts.put_upload(session_id, data, file.content_type or "application/octet-stream")
        return {"ok": True, "data": media}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/generate", status_code=202)
def generate(body: GenerateRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if body.resolution_tier == "2k" and not SETTINGS.enable_2k:
            raise ValueError("2K is not enabled on this host")
        if body.resolution_tier == "2k" and body.model_precision == "bf16":
            raise ValueError("BF16 at 2K has not passed the memory gate")
        if body.model == "moss":
            if not moss_ready(SETTINGS.model_root):
                raise ValueError("MOSS-Image is not installed; no automatic substitution")
        elif body.model == "flux3":
            if not flux3_ready(SETTINGS.model_root, body.quality):
                raise ValueError("FLUX 3 Image Klein is not installed; no automatic substitution")
        else:
            require_image_model(body.model_variant, body.model_precision)
        if body.control is not None:
            if not control_ready(SETTINGS.model_root, body.control.mode):
                raise ValueError("El control de estructura no está instalado")
            artifacts.resolve(body.control.reference.uri, body.control.reference.sha256)
        image_canvas(body, SETTINGS.enable_2k, generation_size(body, SETTINGS.enable_2k))
        resolve_loras(store, body.loras, "qwen")
        return {"ok": True, **jobs.submit_generate(body, idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/v1/jobs/edit", status_code=202)
def edit(body: EditRequest, idempotency_key: str | None = Header(default=None)):
    try:
        if body.resolution > 1024:
            raise ValueError("2K editing is unavailable; use 1024")
        if body.model == "flux3":
            if not flux3_ready(SETTINGS.model_root, "draft"):
                raise ValueError("FLUX 3 Image Klein is not installed; no automatic substitution")
        else:
            require_image_model(body.model_variant, body.model_precision)
        if body.camera is not None and not camera_ready(SETTINGS.model_root):
            raise ValueError("El cambio de ángulo no está instalado")
        for reference in body.references:
            artifacts.resolve(reference.uri, reference.sha256)
        # Klein resizes every reference to about 1 MP itself.
        if body.resolution == 0 and body.model == "qwen":
            with Image.open(artifacts.resolve(body.references[0].uri, body.references[0].sha256)) as source:
                if source.width * source.height > 1_200_000:
                    raise ValueError("Editing a >1 MP reference requires resolution=1024; 2K editing is unavailable")
        resolve_loras(store, body.loras, "qwen")
        return {"ok": True, **jobs.submit_edit(body, idempotency_key)}
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QueueFull as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/jobs/by-idempotency")
def lookup_job(scope: str = Query(max_length=128), key: str = Query(max_length=128)):
    job_id = store.lookup_idempotency(scope, key)
    if not job_id:
        raise HTTPException(status_code=404, detail="idempotency record not found")
    return {"ok": True, **store.job_receipt(job_id)}


@app.get("/v1/jobs/{job_id}")
def job_status(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] == "queued":
        job["queue_position"] = store.queue_position(job_id)
    job["preview_seq"] = jobs.preview_seq(job_id)
    job["gpu"] = next((int(a.split(":", 1)[1]) for a in job["activity"]
                       if a in {"gpu:0", "gpu:1"}), None)
    return {"ok": True, **job}


@app.get("/v1/jobs/{job_id}/preview")
def job_preview(job_id: str):
    item = jobs.preview(job_id)
    if not item:
        return Response(status_code=204)
    return Response(item["data"], media_type=item["mime"],
                    headers={"Cache-Control": "no-store", "X-Preview-Seq": str(item["seq"])})


@app.delete("/v1/jobs/{job_id}")
def cancel_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["status"] in {"completed", "failed", "cancelled", "interrupted", "blocked_gpu"}:
        return {"ok": True, "status": job["status"]}
    if job["operation"] in CREATIVE_OPERATIONS:
        creative.cancel(job_id)
    else:
        jobs.cancel(job_id)
    updated = store.get_job(job_id)
    status = updated["status"] if updated and updated["status"] == "cancelled" else "cancelling"
    return {"ok": True, "status": status}


@app.get("/v1/gallery")
def gallery(limit: int = Query(default=100, ge=1, le=500)):
    return {"ok": True, "items": artifacts.gallery(limit)}


@app.delete("/v1/gallery")
def delete_gallery_item(uri: str, sha256: str):
    try:
        artifacts.delete_image(uri, sha256)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/v1/artifacts/{session_id}/{kind}/{name}")
def artifact(session_id: str, kind: str, name: str):
    try:
        path = artifacts.resolve(f"artifact://{session_id}/{kind}/{name}")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media_type = {".png": "image/png", ".flac": "audio/flac", ".wav": "audio/wav",
                  ".mp3": "audio/mpeg", ".opus": "audio/ogg", ".ogg": "audio/ogg", ".webm": "video/webm", ".mp4": "video/mp4", ".mkv": "video/x-matroska"}.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@app.post("/v1/artifacts/export")
def export_artifact(body: ExportRequest):
    try:
        data, content_type = artifacts.export_image(
            body.uri, body.sha256, body.format, body.quality, body.background,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    extension = "jpg" if body.format == "jpeg" else body.format
    return Response(
        data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="rinari-export.{extension}"'},
    )


@app.get("/v1/review")
def review(uri: str, sha256: str):
    try:
        data, content_type, stats = artifacts.review_preview(uri, sha256)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(data, media_type=content_type, headers={"X-Alpha-Stats": json.dumps(stats)})


@app.post("/v1/prompts/check")
def prompt_check(body: PromptCheck):
    return check_prompt(body)


@app.get("/v1/sessions")
def sessions():
    return {"ok": True, "sessions": store.list_sessions()}


@app.get("/v1/sessions/{session_id}")
def session(session_id: str):
    data = store.session(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True, **data}


@app.post("/v1/sessions/{session_id}/messages")
def add_message(session_id: str, body: SessionMessage):
    store.add_message(session_id, body.role, body.content, [m.model_dump() for m in body.media])
    return {"ok": True}


@app.post("/v1/doctor")
def doctor():
    results: list[dict] = []
    required_nodes = {"UNETLoader", "CLIPLoader", "VAELoader", "TextEncodeQwenImage21",
                      "QwenImage21Cache", "KSampler", "VAEDecode", "SaveImage",
                      "MiniMaxH3ImageToVideo", "MiniMaxH3ReferenceToVideo", "CreateVideo",
                      "SaveVideo", "YuE2GenerateABC", "YuE2GenerateMusic",
                      "EmptyYuE2LatentAudio", "SaveAudioAdvanced", "SheetSage2AudioToABC",
                      "ManualSigmas", "CFGGuider", "RandomNoise", "KSamplerSelect", "SamplerCustomAdvanced",
                      "LoadVideo", "GetVideoComponents", "FlashVSRInitPipe", "FlashVSRNodeAdv"}
    for index, worker in enumerate(creative.clients):
        state = worker.health()
        results.append({"check": f"comfyui_gpu{index}", "ok": state["ok"],
                        "detail": "reachable" if state["ok"] else state.get("error", "unreachable")})
        if state["ok"]:
            try:
                info = worker.object_info()
                nodes = set(info)
                missing = sorted(required_nodes - nodes)
                results.append({"check": f"native_nodes_gpu{index}", "ok": not missing,
                                "detail": "ok" if not missing else f"missing: {', '.join(missing)}"})
                for label, module in (("h3_storyboard", "custom_nodes.ComfyUI-MiniMaxH3"),
                                      ("h3_audio_t8", "custom_nodes.minimax-h3-audio-T8"),
                                      ("yue2_abc", "custom_nodes.ComfyUI-YuE2"),
                                      ("yue2_piano_roll", "custom_nodes.YuE2-ComfyUI"),
                                      ("flashvsr", "custom_nodes.ComfyUI-FlashVSR_Ultra_Fast")):
                    count = sum(node.get("python_module") == module for node in info.values())
                    results.append({"check": f"package:{label}:gpu{index}",
                                    "ok": count > 0, "detail": f"{count} nodes"})
            except Exception as exc:
                results.append({"check": f"native_nodes_gpu{index}", "ok": False, "detail": str(exc)})
    model_files = [
        SETTINGS.model_root / "diffusion_models" / UNET,
        SETTINGS.model_root / "diffusion_models" / UNET_TURBO,
        SETTINGS.model_root / "text_encoders" / __import__("os").environ.get("QWEN21_ENCODER", ENCODER),
        SETTINGS.model_root / "vae" / VAE,
    ]
    for path in model_files:
        results.append({"check": f"model:{path.name}", "ok": path.is_file(),
                        "detail": str(path)})
    for folder, name in (("diffusion_models", H3_FL), ("diffusion_models", H3_REF),
                         ("text_encoders", H3_CLIP), ("vae", H3_VIDEO_VAE),
                         ("vae", H3_AUDIO_VAE)):
        path = SETTINGS.h3_model_root / folder / name
        results.append({"check": f"model:{name}", "ok": path.is_file(), "detail": str(path)})
    for name in FLASHVSR_FILES:
        path = SETTINGS.model_root / FLASHVSR_MODEL / name
        results.append({"check": f"model:{FLASHVSR_MODEL}/{name}", "ok": path.is_file(), "detail": str(path)})
    for folder, name in (("checkpoints", YUE2), ("audio_encoders", SHEETSAGE)):
        path = SETTINGS.model_root / folder / name
        results.append({"check": f"model:{name}", "ok": path.is_file(), "detail": str(path)})
    results.append({"check": "artifact_store", "ok": SETTINGS.artifacts_root.is_dir(),
                    "detail": str(SETTINGS.artifacts_root)})
    results.append({"check": "gpu_guard", **guard.status()})
    return {"ok": all(r.get("ok", r.get("available", False)) for r in results), "results": results}
