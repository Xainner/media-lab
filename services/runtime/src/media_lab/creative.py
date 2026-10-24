"""ComfyUI-backed video, music, and resumable production jobs."""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
import math
import threading
import time
import uuid
from pathlib import Path

from PIL import Image

from .artifacts import ArtifactStore
from .comfy import ComfyError
from .config import Settings
from .contracts import (ArtifactRef, FaceRefineRequest, RemoveRequest, ProductionRequest, SoundRequest, SpeechRequest, StemsRequest, SongRequest, SwapRequest, UpscaleRequest, VideoRequest, PRESETS_1MP, PRESETS_2K,
                        UPSCALE_MAX_INPUT_PIXELS, UPSCALE_MAX_SECONDS, UPSCALE_MAX_WORK_SECONDS,
                        steps_for, upscale_estimate)
from .creative_workflows import (h3_workflow, yue2_workflow, flashvsr_workflow, flashvsr_tile, FLASHVSR_MODES,
                                swap_prompt, swap_size, swap_workflow, SWAP_LORA, SWAP_LORA_SHA256, SWAP_STEPS, SWAP_TURBO,
                                head_swap_workflow, h3_length, HEAD_FACE_SIZE, HEAD_LORA, HEAD_LORA_SHA256, HEAD_STEPS,
                                HEAD_TURBO, face_detect_workflow, face_refine_workflow, FACE_STRENGTHS,
                                ace_step_workflow, ace_language, ace_tempo, ACE_KEYS, ACE_STEPS,
                                H3_FUSED, H3_FUSED_REVISION,
                                H3_FUSED_SHA256, H3_FUSED_VIDEO_VAE, H3_FUSED_VAE_SHA256,
                                H3_TURBO_FL_LORA, H3_TURBO_REF_LORA, H3_OMNI, CLEAN_FRAME_PROMPT, REMOVER_LORA, REMOVER_STEPS,
                                SAM_MODEL, remover_mask_workflow, remover_workflow, STEMS, STEMS_MODEL, stems_workflow,
                                H3_CONTROL_PATCH, VIDEO_CONTROL_SECONDS, SCAIL_MODEL, SCAIL_DPO_LORA, SCAIL_DISTILL_LORA,
                                SCAIL_STEPS, scail_frames, scail_size, scail_workflow, SA3_CHECKPOINTS, SA3_KINDS, SA3_STEPS,
                                sa3_workflow, kandinsky6_workflow, K6_DIT, K6_SIZES, K6_STEPS, speech_workflow, TTS_CHECKPOINTS,
                                TTS_REFERENCE_SECONDS)
from .face_refine import FACE_CROP, crop_frames, face_windows, parse_boxes, paste_frames
from .store import Store
from .gpu_workers import GpuWorkers
from .workflows import t2i_workflow, edit_workflow, chain_loras, diffusion_model, ENCODER
from .loras import resolve_loras
from .jobs import QueueFull


# The 3090's 24 GiB budget is dominated by the H3 DiT and Qwen3-VL encoder.
# These aligned canvases keep the initial guided path inside the measured gate.
from .model_options import video_size, image_canvas


def nearest_video_aspect(width: int, height: int) -> str:
    return min(("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0), key=lambda a: abs(math.log(a[1] * height / width)))[0]


def check_control_input(info: dict) -> None:
    if not VIDEO_CONTROL_SECONDS[0] <= info["duration"] <= VIDEO_CONTROL_SECONDS[1]:
        raise ValueError("El vídeo de control debe durar entre 2 y 15 segundos")
VIDEO_SIZE = {"16:9": (640, 352), "9:16": (352, 640), "1:1": (480, 480)}


def media_probe(path: Path) -> dict:
    output = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_name,codec_type,width,height,sample_rate,channels,duration:stream_tags=DURATION",
        "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=30)
    data = json.loads(output.stdout)
    duration = round(float(data["format"]["duration"]), 3)
    video_durations = []
    for stream in data.get("streams", []):
        if stream.get("codec_type") != "video":
            continue
        value = stream.get("duration")
        if not value or value == "N/A":
            tag = stream.get("tags", {}).get("DURATION", "")
            if tag:
                hours, minutes, seconds = tag.split(":")
                value = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        if value and value != "N/A":
            video_durations.append(float(value))
    return {"duration": duration, "video_duration": round(max(video_durations), 3) if video_durations else duration,
            "streams": data.get("streams", [])}


def video_info(path: Path) -> dict:
    """Frame-exact probe of the first video stream plus the first audio codec, if any."""
    output = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-show_entries",
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,nb_read_packets:format=duration",
        "-of", "json", str(path)], capture_output=True, text=True, check=True, timeout=120)
    data = json.loads(output.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("El archivo no contiene vídeo")
    num, _, den = (video.get("r_frame_rate") or "24/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 24.0
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    frames = int(video.get("nb_read_packets") or 0)
    duration = float(data.get("format", {}).get("duration") or (frames / fps if fps else 0))
    return {"width": int(video["width"]), "height": int(video["height"]), "fps": round(fps, 3),
            "frames": frames or round(duration * fps), "duration": round(duration, 3),
            "audio_codec": audio.get("codec_name") if audio else None}


def ffmpeg(command: list[str], timeout: int) -> None:
    """Run ffmpeg, surfacing its last error lines instead of a bare exit status."""
    done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if done.returncode:
        raise RuntimeError("ffmpeg: " + " ".join(done.stderr.strip().splitlines()[-3:])[:600])


def check_upscale_input(info: dict, scale: int, quality: str = "fast") -> None:
    if not 0 < info["duration"] <= UPSCALE_MAX_SECONDS:
        raise ValueError(f"El escalado admite vídeos de hasta {UPSCALE_MAX_SECONDS // 60} minutos")
    if info["width"] * info["height"] > UPSCALE_MAX_INPUT_PIXELS[scale]:
        limit = UPSCALE_MAX_INPUT_PIXELS[scale] / 1_000_000
        raise ValueError(f"x{scale} admite vídeos de hasta {limit:.2f} MP por fotograma; prueba x2 o un vídeo más pequeño")
    if not 1 <= info["fps"] <= 60:
        raise ValueError("El vídeo debe tener entre 1 y 60 fotogramas por segundo")
    estimate = upscale_estimate(info["duration"], info["width"], info["height"], scale, quality)
    if estimate > UPSCALE_MAX_WORK_SECONDS:
        raise ValueError(f"Este escalado tardaría unos {round(estimate / 60)} min y el máximo por trabajo es "
                         f"{UPSCALE_MAX_WORK_SECONDS // 60} min: prueba x2, el modo rápido o un fragmento más corto")


# FlashVSR runs per chunk so host RAM stays bounded for any length. Each chunk after the
# first re-reads OVERLAP frames, and the stitch crossfades over them: a hard cut shows a
# small jump where the next chunk's streaming state starts fresh.
UPSCALE_OVERLAP = 8
# Measured: ComfyUI holds ~0.03 GiB per output megapixel-frame on top of ~8 GiB resident, so
# 400 MP-frames keeps a chunk near 12 GiB extra (17 GiB measured at 720p x2), so two jobs
# (one per GPU) still fit in host RAM; fewer, longer chunks cut the per-tile overhead.
UPSCALE_CHUNK_MP_FRAMES = 400


SWAP_SECONDS = (2, 15)


def check_swap_input(info: dict) -> None:
    if not SWAP_SECONDS[0] <= info["duration"] <= SWAP_SECONDS[1]:
        raise ValueError("El vídeo para cambiar de personaje debe durar entre 2 y 15 segundos (mejor hasta 5)")


REMOVE_SECONDS = (1, 10)


def check_remove_input(info: dict) -> None:
    if not REMOVE_SECONDS[0] <= info["duration"] <= REMOVE_SECONDS[1]:
        raise ValueError("El vídeo para quitar a una persona debe durar entre 1 y 10 segundos (mejor hasta 5)")


STEMS_SECONDS = (1, 900)


def check_stems_input(probe: dict) -> None:
    if not any(s.get("codec_type") == "audio" for s in probe["streams"]):
        raise ValueError("El archivo no contiene audio")
    if not STEMS_SECONDS[0] <= probe["duration"] <= STEMS_SECONDS[1]:
        raise ValueError("Para separar pistas el audio debe durar entre 1 segundo y 15 minutos")


FACE_SECONDS = (1, 15)


def check_face_input(info: dict) -> None:
    if not FACE_SECONDS[0] <= info["duration"] <= FACE_SECONDS[1]:
        raise ValueError("El vídeo para refinar caras debe durar entre 1 y 15 segundos")


def upscale_chunk_frames(output_pixels: int) -> int:
    return max(41, min(121, int(UPSCALE_CHUNK_MP_FRAMES * 1_000_000 / output_pixels)))


def upscale_chunks(frames: int, size: int = 121, overlap: int = UPSCALE_OVERLAP) -> list[tuple[int, int, int]]:
    """(first input frame, input frame count, leading frames shared with the previous chunk)."""
    # Equal-sized chunks: a short trailing chunk starts its stream state too late to settle.
    size = -(-frames // -(-frames // size)) if frames else size
    plan, start = [], 0
    while start < frames:
        end = min(frames, start + size)
        lead = min(overlap, start)
        plan.append((start - lead, end - start + lead, lead))
        start = end
    return plan


def audio_analysis(path: Path) -> dict:
    try:
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "json", str(path)], capture_output=True,
            text=True, timeout=30, check=True)
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except (subprocess.SubprocessError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid audio file") from exc
    if not 1 <= duration <= 900:
        raise ValueError("audio duration must be between 1 and 900 seconds")
    # Short-time RMS envelope is computed locally; no source audio leaves Saturno.
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1",
            "-ar", "11025", "-f", "s16le", "-"], capture_output=True,
            timeout=180, check=True).stdout
    except subprocess.SubprocessError as exc:
        raise ValueError("audio analysis failed") from exc
    from array import array
    samples = array("h")
    samples.frombytes(raw[:len(raw) // 2 * 2])
    hop = 2205
    energy = []
    for start in range(0, len(samples) - hop, hop):
        chunk = samples[start:start + hop]
        energy.append((sum(int(x) * int(x) for x in chunk) / hop) ** .5)
    if not energy:
        return {"duration": duration, "bpm_estimate": None, "sections": []}
    onset = [max(0.0, energy[i] - energy[i - 1]) for i in range(1, len(energy))]
    scores = []
    for bpm in range(60, 181):
        lag = round(60 * 5 / bpm)
        scores.append((sum(onset[i] * onset[i - lag] for i in range(lag, len(onset))), bpm))
    bpm = max(scores)[1] if any(onset) else None
    # Energy changes mark candidate sections, not guaranteed musical boundaries.
    sections = [{"start": 0.0, "end": round(min(duration, 10.0), 2), "energy": "intro"}]
    for start in range(10, int(duration), 10):
        current = energy[start * 5:(start + 10) * 5]
        if not current:
            break
        mean = sum(current) / len(current)
        sections.append({"start": float(start), "end": round(min(duration, start + 10), 2),
                         "energy": "high" if mean > sum(energy) / len(energy) else "low"})
    return {"duration": round(duration, 2), "bpm_estimate": bpm, "sections": sections}


class CreativeJobs:
    def __init__(self, settings: Settings, store: Store, artifacts: ArtifactStore, workers: GpuWorkers):
        self.settings, self.store, self.artifacts = settings, store, artifacts
        self.workers = workers
        self.clients = workers.clients
        # Each ComfyUI process owns a distinct GPU and input/output volume.
        # Serialize only within a worker; a global lock strands the other GPU.
        self.h3_locks = [threading.Lock() for _ in self.clients]

    def status(self) -> list[dict]:
        return self.workers.status()

    def submit(self, operation: str, request: dict, preferred: int,
               partial: dict | None = None, key: str | None = None, scope: str | None = None) -> dict:
        # Keep the canonical default-base body identical to 0.7.0 so replaying
        # a pre-upgrade idempotency key returns the original job, not a conflict.
        request = dict(request)
        if operation == "video" and request.get("profile", "base") == "base":
            request.pop("profile", None)
        if operation == "production" and request.get("video_profile", "base") == "base":
            request.pop("video_profile", None)
            if request.get("video_steps") in (None, 20):
                request.pop("video_steps", None)
        session = request.get("session_id") or f"sess_{uuid.uuid4().hex[:12]}"
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job_id, created = self.store.create_job_once(job_id, session, operation, request,
                                                     self.settings.max_pending, key, scope)
        if not job_id:
            raise QueueFull("job queue is full")
        if not created:
            return self.store.job_receipt(job_id)
        if partial:
            self.store.update_job(job_id, result_json=partial)
        gpu = self.workers.submit(job_id, preferred, self._execute)
        return {"job_id": job_id, "session_id": session, "status": "queued", "gpu": gpu}

    def cancel(self, job_id: str) -> bool:
        return self.workers.cancel(job_id)

    def _execute(self, job_id: str, gpu: int) -> None:
        job = self.store.get_job(job_id)
        if not job or self.store.cancel_requested(job_id):
            return
        try:
            if self.store.cancel_requested(job_id):
                return
            self.workers.guards[gpu].require_available()
            self.store.update_job(job_id, status="running", started_at=time.time(),
                                  activity_json=[f"gpu:{gpu}"])
            operation = job["operation"]
            if operation == "song":
                result = self._song(job_id, job, gpu)
            elif operation == "video":
                result = self._video(job_id, job, gpu)
            elif operation == "upscale":
                result = self._upscale(job_id, job, gpu)
            elif operation == "swap":
                result = self._swap(job_id, job, gpu)
            elif operation == "face_refine":
                result = self._face_refine(job_id, job, gpu)
            elif operation == "remove":
                result = self._remove(job_id, job, gpu)
            elif operation == "stems":
                result = self._stems(job_id, job, gpu)
            elif operation == "sound":
                result = self._sound(job_id, job, gpu)
            elif operation == "speech":
                result = self._speech(job_id, job, gpu)
            else:
                result = self._production(job_id, job, gpu)
            if self.store.cancel_requested(job_id):
                raise ComfyError("cancelled")
            self.store.update_job(job_id, status="completed", result_json=result,
                progress_json={"pct": 100, "node": "done"}, completed_at=time.time())
        except Exception as exc:
            status = "cancelled" if self.store.cancel_requested(job_id) else "failed"
            self.store.update_job(job_id, status=status, error=str(exc), completed_at=time.time())

    def _run(self, job_id: str, gpu: int, graph: dict, kind: str) -> tuple[bytes, dict]:
        return self.clients[gpu].run_output(graph, kind,
            lambda p: self.store.update_job(job_id, progress_json=p),
            lambda: self.store.cancel_requested(job_id))

    def _song(self, job_id: str, job: dict, gpu: int) -> dict:
        body = SongRequest.model_validate(job["request"])
        if body.model == "ace_step":
            return self._ace_song(job_id, job, gpu, body)
        client = self.clients[gpu]
        source = None
        if body.source_audio:
            path = self.artifacts.resolve(body.source_audio.uri, body.source_audio.sha256)
            source = client.upload_audio(path, job_id)
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        graph = yue2_workflow(body.style, body.lyrics, body.mode, body.abc,
                              body.max_duration, body.steps, seed, source, options=body.options)
        raw, backend = self._run(job_id, gpu, graph, "audio")
        score = body.abc
        if "save_abc" in graph:
            history = client.history(backend["prompt_id"])
            score = ((history.get("outputs") or {}).get("save_abc") or {}).get("text", [""])[0]
        media = self.artifacts.put_media(job["session_id"], raw, {"flac": "audio/flac", "mp3": "audio/mpeg", "opus": "audio/ogg"}[body.options.format if body.options else "flac"], "songs",
            {"model": "YuE2-3B", "style": body.style, "lyrics": body.lyrics,
             "abc": score, "mode": body.mode, "seed": seed, "backend": backend,
             "steps": body.steps, "options": body.options.values() if body.options else {}})
        return {"media": [media], "data": {"seed": seed, "mode": body.mode, "gpu": gpu,
                                          "abc": score, "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _ace_song(self, job_id: str, job: dict, gpu: int, body: SongRequest) -> dict:
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        named_bpm, named_key = ace_tempo(body.style)
        bpm, key = body.bpm or named_bpm, body.key if body.key in ACE_KEYS else named_key
        language = body.language or ace_language(body.lyrics)
        fmt = body.options.format if body.options else "flac"
        graph = ace_step_workflow(body.style, body.lyrics, body.max_duration, seed, bpm, key, language,
                                  fmt, body.options.audio_quality if body.options else None)
        raw, backend = self._run(job_id, gpu, graph, "audio")
        media = self.artifacts.put_media(job["session_id"], raw, {"flac": "audio/flac", "mp3": "audio/mpeg", "opus": "audio/ogg"}[fmt], "songs",
            {"model": "ACE-Step 1.5 XL Turbo", "style": body.style, "lyrics": body.lyrics, "bpm": bpm, "key": key,
             "language": language, "seconds": body.max_duration, "seed": seed, "steps": ACE_STEPS, "backend": backend})
        return {"media": [media], "data": {"seed": seed, "model": "ace_step", "bpm": bpm, "key": key, "language": language,
                                          "gpu": gpu, "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _video(self, job_id: str, job: dict, gpu: int) -> dict:
        body = VideoRequest.model_validate(job["request"])
        if body.model == "kandinsky6":
            return self._kandinsky6(job_id, job["session_id"], gpu, body)
        with self.h3_locks[gpu]:
            return self._video_locked(job_id, job["session_id"], gpu, body)

    def _video_locked(self, job_id: str, session: str, gpu: int, body: VideoRequest) -> dict:
        client = self.clients[gpu]
        def upload(ref):
            return client.upload_image(self.artifacts.resolve(ref.uri, ref.sha256), job_id) if ref else None
        first = upload(body.first_frame)
        last = upload(body.last_frame)
        refs = [upload(ref) for ref in body.references]
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        width, height = video_size(body.aspect_ratio, body.options)
        seconds, control, source = body.seconds, None, None
        work = tempfile.TemporaryDirectory()
        if body.control:
            # The source clip decides shape and length; it is fitted to H3's canvas, 24 fps and 17n+5 frames.
            source = self.artifacts.resolve(body.control.video.uri, body.control.video.sha256)
            info = video_info(source)
            check_control_input(info)
            width, height = video_size(nearest_video_aspect(info["width"], info["height"]), body.options)
            seconds = min(15.0, max(5.0, info["duration"]))
            length = h3_length(seconds)
            clip = Path(work.name) / "control.mp4"
            ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:v:0", "-an",
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=24,"
                           f"tpad=stop_mode=clone:stop={length},trim=end_frame={length}",
                    "-c:v", "libx264", "-crf", "14", str(clip)], 300)
            control = (client.upload_audio(clip, f"{job_id}_control"), body.control.mode, body.control.strength)
        videos, soundtracks = [], []
        for index, ref in enumerate(body.reference_videos):
            path = self.artifacts.resolve(ref.uri, ref.sha256)
            probe = media_probe(path)
            if not 2 <= probe['duration'] <= 15:
                raise ValueError('Los vídeos de referencia deben durar entre 2 y 15 segundos')
            soundtracks.append(any(stream.get('codec_type') == 'audio' for stream in probe['streams']))
            with tempfile.TemporaryDirectory() as directory:
                converted = Path(directory) / 'reference.mp4'
                subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', str(path), '-map', '0:v:0', '-map', '0:a:0?',
                                '-vf', "scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2,fps=24", '-c:v', 'libx264', '-crf', '18',
                                '-c:a', 'aac', str(converted)], check=True, capture_output=True, timeout=120)
                videos.append(client.upload_audio(converted, f'{job_id}_v{index}'))
        audios = [client.upload_audio(self.artifacts.resolve(ref.uri, ref.sha256), f'{job_id}_a{index}')
                  for index, ref in enumerate(body.reference_audios)]
        graph = h3_workflow(body.prompt, body.mode, width, height,
                            seconds, body.steps, seed, first, last, refs, profile=body.profile, options=body.options,
                            reference_videos=videos, reference_audios=audios, video_soundtracks=soundtracks, control=control)
        loras = resolve_loras(self.store, body.loras, "h3")
        chain_loras(graph, "unet", loras)
        container = body.options.container if body.options else "mp4"
        with work:
            raw, backend = self._run(job_id, gpu, graph, "videos")
            if body.control:
                raw = self._control_finish(raw, source, Path(work.name), container, body.control.keep_audio)
        media = self.artifacts.put_media(session, raw, {"mp4": "video/mp4", "mkv": "video/x-matroska", "webm": "video/webm"}[body.options.container if body.options else "mp4"], "videos",
            {"model": {"fused_turbo": "MiniMax-H3 Fused Turbo", "turbo": "MiniMax-H3 Turbo", "omni": "FastH3 Omni"}.get(body.profile, "MiniMax-H3"),
             "profile": body.profile, "steps": body.steps, "width": width, "height": height,
             "options": body.options.values() if body.options else {},
             "attention": "dense", "workflow": f"h3_{body.profile}_control_v1" if body.control else f"h3_{body.profile}_v1",
             **({"control": body.control.model_dump(), "control_patch": H3_CONTROL_PATCH} if body.control else {}),
             **({"lora": H3_TURBO_REF_LORA if body.mode == "r2v" else H3_TURBO_FL_LORA,
                 "video_vae": H3_FUSED_VIDEO_VAE} if body.profile == "turbo" else {}),
             **({"checkpoint": H3_OMNI, "video_vae": H3_FUSED_VIDEO_VAE} if body.profile == "omni" else {}),
             **({"checkpoint": H3_FUSED, "revision": H3_FUSED_REVISION,
                 "checkpoint_sha256": H3_FUSED_SHA256, "video_vae": H3_FUSED_VIDEO_VAE,
                 "video_vae_sha256": H3_FUSED_VAE_SHA256} if body.profile == "fused_turbo" else {}),
             **({"loras": [{"file": f, "strength": s} for f, s in loras]} if loras else {}),
             "prompt": body.prompt, "mode": body.mode,
             "seed": seed, "backend": backend, "gpu": gpu})
        return {"media": [media], "data": {"seed": seed, "gpu": gpu, "mode": body.mode,
                                          "profile": body.profile, "steps": body.steps, "attention": "dense",
                                          "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _kandinsky6(self, job_id: str, session: str, gpu: int, body: VideoRequest) -> dict:
        client = self.clients[gpu]
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        first = (client.upload_image(self.artifacts.resolve(body.first_frame.uri, body.first_frame.sha256), job_id)
                 if body.mode == "i2v" else None)
        graph = kandinsky6_workflow(body.prompt, body.audio_prompt or "", body.aspect_ratio, seed, first, not body.literal_prompt)
        raw, backend = self._run(job_id, gpu, graph, "videos")
        captions = client.output_text(backend["prompt_id"], "caption")
        width, height = K6_SIZES[body.aspect_ratio]
        media = self.artifacts.put_media(session, raw, "video/mp4", "videos",
            {"model": "Kandinsky 6.0 Lite Distill", "checkpoint": K6_DIT, "steps": K6_STEPS, "width": width, "height": height,
             "workflow": f"kandinsky6_lite_distill_{'i2va' if first else 't2va'}_v1", "prompt": body.prompt,
             "audio_prompt": body.audio_prompt or "", "compiled_prompt": captions, "mode": body.mode,
             "seed": seed, "backend": backend, "gpu": gpu})
        return {"media": [media], "data": {"seed": seed, "gpu": gpu, "mode": body.mode, "model": "kandinsky6",
                                          "steps": K6_STEPS, "prompt": captions,
                                          "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    @staticmethod
    def _control_finish(raw: bytes, source: Path, work: Path, container: str, keep_audio: bool) -> bytes:
        """Cut a controlled clip back to its source's length and, if asked, lay the source soundtrack on it."""
        info = video_info(source)
        generated, final = work / f"generated.{container}", work / f"final.{container}"
        generated.write_bytes(raw)
        sound = keep_audio and info["audio_codec"]
        command = ["ffmpeg", "-y", "-v", "error", "-i", str(generated), "-i", str(source), "-t", f"{info['duration']:.3f}",
                   "-map", "0:v:0", "-c:v", "copy", "-map", "1:a:0" if sound else "0:a:0?"]
        command += ["-c:a", "libopus" if container == "webm" else "aac", "-b:a", "256k"] if sound else ["-c:a", "copy"]
        ffmpeg(command + [str(final)], 300)
        return final.read_bytes()

    def _swap(self, job_id: str, job: dict, gpu: int) -> dict:
        body = SwapRequest.model_validate(job["request"])
        with self.h3_locks[gpu]:
            return self._swap_locked(job_id, job["session_id"], gpu, body)

    def _swap_locked(self, job_id: str, session: str, gpu: int, body: SwapRequest) -> dict:
        if body.mode == "scail":
            return self._scail(job_id, session, gpu, body)
        client = self.clients[gpu]
        source = self.artifacts.resolve(body.video.uri, body.video.sha256)
        info = video_info(source)
        check_swap_input(info)
        width, height = swap_size(info["width"], info["height"])
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        head = body.mode == "head"
        prompt = None if head else body.prompt or swap_prompt(body.target)
        seconds = max(5.0, info["duration"])
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            clip = work / "source.mp4"
            # Same size and 24 fps as the target, so <Video 1> lines up frame for frame. The head swap
            # guide must cover every generated frame: hold the last frame up to H3's frame count.
            filters = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=24"
            if head:
                length = h3_length(seconds)
                filters += f",tpad=stop_mode=clone:stop={length},trim=end_frame={length}"
            ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
                    "-vf", filters, "-c:v", "libx264", "-crf", "16", "-c:a", "aac", str(clip)], 300)
            video = client.upload_audio(clip, f"{job_id}_source")
            picture = self.artifacts.resolve(body.character.uri, body.character.sha256)
            if head:
                # The Head Swap workflow letterboxes the face into a small square reference.
                face = work / "face.png"
                size = HEAD_FACE_SIZE
                ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(picture), "-frames:v", "1", "-vf",
                        f"scale={size}:{size}:force_original_aspect_ratio=decrease:flags=lanczos,"
                        f"pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:black", str(face)], 60)
                picture = face
            character = client.upload_image(picture, job_id)
            if head:
                graph = head_swap_workflow(width, height, seconds, seed, video, character,
                                           bool(info["audio_codec"]), body.target, body.details)
            else:
                graph = swap_workflow(prompt, width, height, seconds, seed, video, character,
                                      bool(info["audio_codec"]))
            raw, backend = self._run(job_id, gpu, graph, "videos")
            generated, final = work / "generated.mp4", work / "swap.mp4"
            generated.write_bytes(raw)
            # H3 renders at least 5 s: cut back to the source length and keep the original soundtrack verbatim.
            command = ["ffmpeg", "-y", "-v", "error", "-i", str(generated), "-i", str(source),
                       "-t", f"{info['duration']:.3f}", "-map", "0:v:0", "-c:v", "copy"]
            command += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "256k"] if info["audio_codec"] else ["-an"]
            ffmpeg(command + ["-movflags", "+faststart", str(final)], 300)
            recipe = ({"model": "MiniMax-H3 Head Swap v1.0", "lora": HEAD_LORA, "lora_sha256": HEAD_LORA_SHA256,
                       "turbo": HEAD_TURBO, "steps": HEAD_STEPS, "details": body.details} if head else
                      {"model": "MiniMax-H3 Character Swap v1.5", "lora": SWAP_LORA, "lora_sha256": SWAP_LORA_SHA256,
                       "turbo": SWAP_TURBO, "steps": SWAP_STEPS, "prompt": prompt})
            media = self.artifacts.put_media(session, final, "video/mp4", "videos",
                {**recipe, "operation": "swap", "mode": body.mode, "target": body.target,
                 "width": width, "height": height, "source": body.video.uri, "character": body.character.uri,
                 "character_sha256": body.character.sha256,
                 "seed": seed, "backend": backend, "gpu": gpu})
        return {"media": [media], "data": {"seed": seed, "gpu": gpu, "mode": body.mode, "width": width, "height": height,
                                          "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _scail(self, job_id: str, session: str, gpu: int, body: SwapRequest) -> dict:
        client = self.clients[gpu]
        source = self.artifacts.resolve(body.video.uri, body.video.sha256)
        info = video_info(source)
        check_swap_input(info)
        width, height = scail_size(info["width"], info["height"])
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        prompt = body.prompt or ""
        frames = round(info["duration"] * 24)
        chunks, covered = scail_frames(frames)
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            clip = work / "source.mp4"
            # SCAIL-2 renders 81-frame chunks that step by 76: hold the last frame until the chunks are full.
            ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:v:0", "-an", "-vf",
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=24,"
                    f"tpad=stop_mode=clone:stop={covered},trim=end_frame={covered}",
                    "-c:v", "libx264", "-crf", "14", str(clip)], 300)
            graph = scail_workflow(client.upload_audio(clip, f"{job_id}_source"),
                                   client.upload_image(self.artifacts.resolve(body.character.uri, body.character.sha256), job_id),
                                   prompt, body.target, width, height, frames, seed,
                                   encoder=os.environ.get("QWEN21_ENCODER", ENCODER))
            raw, backend = self._run(job_id, gpu, graph, "videos")
            generated, final = work / "generated.mp4", work / "swap.mp4"
            generated.write_bytes(raw)
            command = ["ffmpeg", "-y", "-v", "error", "-i", str(generated), "-i", str(source),
                       "-t", f"{info['duration']:.3f}", "-map", "0:v:0", "-c:v", "copy"]
            command += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "256k"] if info["audio_codec"] else ["-an"]
            ffmpeg(command + ["-movflags", "+faststart", str(final)], 300)
            media = self.artifacts.put_media(session, final, "video/mp4", "videos",
                {"model": "SCAIL-2", "checkpoint": SCAIL_MODEL, "loras": [SCAIL_DPO_LORA, SCAIL_DISTILL_LORA],
                 "steps": SCAIL_STEPS, "chunks": chunks, "prompt": prompt or "described from the character image",
                 "operation": "swap", "mode": body.mode, "target": body.target,
                 "width": width, "height": height, "source": body.video.uri, "character": body.character.uri,
                 "character_sha256": body.character.sha256, "seed": seed, "backend": backend, "gpu": gpu})
        return {"media": [media], "data": {"seed": seed, "gpu": gpu, "mode": body.mode, "width": width, "height": height,
                                          "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _remove(self, job_id: str, job: dict, gpu: int) -> dict:
        body = RemoveRequest.model_validate(job["request"])
        with self.h3_locks[gpu]:
            return self._remove_locked(job_id, job["session_id"], gpu, body)

    def _remove_locked(self, job_id: str, session: str, gpu: int, body: RemoveRequest) -> dict:
        client = self.clients[gpu]
        source = self.artifacts.resolve(body.video.uri, body.video.sha256)
        info = video_info(source)
        check_remove_input(info)
        width, height = swap_size(info["width"], info["height"])
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        length = h3_length(max(5.0, info["duration"]))
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            clip = work / "source.mp4"
            # H3's canvas, 24 fps and 17n+5 frames (last frame held), so the green clip lines up with the target.
            ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
                    "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},fps=24,"
                           f"tpad=stop_mode=clone:stop={length},trim=end_frame={length}",
                    "-c:v", "libx264", "-crf", "14", "-c:a", "aac", str(clip)], 300)
            green = work / "green.mp4"
            green.write_bytes(self._run(job_id, gpu, remover_mask_workflow(client.upload_audio(clip, f"{job_id}_source"),
                                                                           body.target), "videos")[0])
            first = work / "first.png"
            if body.clean_frame is not None:
                picture = self.artifacts.resolve(body.clean_frame.uri, body.clean_frame.sha256)
                ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(picture), "-frames:v", "1", "-vf",
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                        str(first)], 60)
            else:
                ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(green), "-frames:v", "1", str(first)], 60)
                edited = self._run(job_id, gpu, edit_workflow(
                    CLEAN_FRAME_PROMPT, [client.upload_image(first, f"{job_id}_green")], seed, 40,
                    encoder=os.environ.get("QWEN21_ENCODER", ENCODER)), "images")[0]
                (work / "edited.png").write_bytes(edited)
                ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(work / "edited.png"), "-vf",
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                        str(first)], 60)
            graph = remover_workflow(width, height, length, seed, client.upload_audio(green, f"{job_id}_green"),
                                     client.upload_image(first, f"{job_id}_clean"), bool(info["audio_codec"]))
            raw, backend = self._run(job_id, gpu, graph, "videos")
            generated, final = work / "generated.mp4", work / "removed.mp4"
            generated.write_bytes(raw)
            command = ["ffmpeg", "-y", "-v", "error", "-i", str(generated), "-i", str(source),
                       "-t", f"{info['duration']:.3f}", "-map", "0:v:0", "-c:v", "copy"]
            command += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "256k"] if info["audio_codec"] else ["-an"]
            ffmpeg(command + ["-movflags", "+faststart", str(final)], 300)
            media = self.artifacts.put_media(session, final, "video/mp4", "videos",
                {"model": "MiniMax-H3 Person Remover V1", "operation": "remove", "lora": REMOVER_LORA,
                 "segmenter": SAM_MODEL, "steps": REMOVER_STEPS, "target": body.target,
                 "clean_frame": body.clean_frame.uri if body.clean_frame else "qwen21_edit",
                 "width": width, "height": height, "source": body.video.uri,
                 "seed": seed, "backend": backend, "gpu": gpu})
        return {"media": [media], "data": {"seed": seed, "gpu": gpu, "width": width, "height": height,
                                          "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _stems(self, job_id: str, job: dict, gpu: int) -> dict:
        body = StemsRequest.model_validate(job["request"])
        client = self.clients[gpu]
        source = self.artifacts.resolve(body.audio.uri, body.audio.sha256)
        check_stems_input(media_probe(source))
        names = STEMS[body.stems]
        files, backend = client.run_outputs(stems_workflow(client.upload_audio(source, job_id), body.stems, body.format),
                                            [f"save_{name}" for name in names], "audio",
                                            lambda p: self.store.update_job(job_id, progress_json=p),
                                            lambda: self.store.cancel_requested(job_id))
        mime = {"flac": "audio/flac", "mp3": "audio/mpeg"}[body.format]
        media = [self.artifacts.put_media(job["session_id"], files[f"save_{name}"], mime, "songs",
                    {"model": "Hybrid Demucs", "operation": "stems", "stem": name, "weights": STEMS_MODEL,
                     "source": body.audio.uri, "backend": backend, "gpu": gpu}) for name in names]
        return {"media": media, "data": {"gpu": gpu, "stems": list(names)}}

    def _sound(self, job_id: str, job: dict, gpu: int) -> dict:
        body = SoundRequest.model_validate(job["request"])
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        checkpoint = SA3_KINDS[body.kind][0]
        raw, backend = self._run(job_id, gpu, sa3_workflow(body.prompt, body.kind, body.seconds, seed, body.enhance, body.format), "audio")
        rewritten = self.clients[gpu].output_text(backend["prompt_id"], "caption") if body.enhance else ""
        label = {"medium": "Stable Audio 3 Medium", "small_sfx": "Stable Audio 3 Small SFX"}[checkpoint]
        media = self.artifacts.put_media(job["session_id"], raw, {"flac": "audio/flac", "mp3": "audio/mpeg"}[body.format], "songs",
            {"model": label, "operation": "sound", "kind": body.kind, "prompt": body.prompt, "compiled_prompt": rewritten or body.prompt,
             "seconds": body.seconds, "seed": seed, "steps": SA3_STEPS, "checkpoint": SA3_CHECKPOINTS[checkpoint],
             "backend": backend, "gpu": gpu})
        return {"media": [media], "data": {"seed": seed, "model": label, "kind": body.kind, "prompt": rewritten or body.prompt,
                                          "gpu": gpu, "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _speech(self, job_id: str, job: dict, gpu: int) -> dict:
        body = SpeechRequest.model_validate(job["request"])
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        reference = None
        with tempfile.TemporaryDirectory() as work:
            if body.voice == "clone":
                # Mono 24 kHz WAV of the first 30 s: works for any owned audio or video upload.
                clip = Path(work) / "reference.wav"
                ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(self.artifacts.resolve(body.reference.uri, body.reference.sha256)),
                        "-vn", "-ac", "1", "-ar", "24000", "-t", str(TTS_REFERENCE_SECONDS[1]), str(clip)], 120)
                reference = self.clients[gpu].upload_audio(clip, f"{job_id}_voice")
            graph = speech_workflow(body.text, body.voice, body.language, body.speaker, body.instruct, seed,
                                    reference, body.reference_text, body.format)
            raw, backend = self._run(job_id, gpu, graph, "audio")
        meta = {"model": "Qwen3-TTS 1.7B", "operation": "speech", "voice": body.voice, "checkpoint": TTS_CHECKPOINTS[body.voice],
                "text": body.text, "language": body.language, "seed": seed, "backend": backend, "gpu": gpu}
        if body.voice == "preset":
            meta.update(speaker=body.speaker, instruct=body.instruct)
        elif body.voice == "design":
            meta["instruct"] = body.instruct
        else:
            meta.update(reference=body.reference.uri, reference_text=body.reference_text, consent=True)
        media = self.artifacts.put_media(job["session_id"], raw, {"flac": "audio/flac", "mp3": "audio/mpeg"}[body.format], "songs", meta)
        return {"media": [media], "data": {"seed": seed, "voice": body.voice, "gpu": gpu,
                                          "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _face_refine(self, job_id: str, job: dict, gpu: int) -> dict:
        body = FaceRefineRequest.model_validate(job["request"])
        with self.h3_locks[gpu]:
            return self._face_refine_locked(job_id, job["session_id"], gpu, body)

    def _face_refine_locked(self, job_id: str, session: str, gpu: int, body: FaceRefineRequest) -> dict:
        client = self.clients[gpu]
        source = self.artifacts.resolve(body.video.uri, body.video.sha256)
        info = video_info(source)
        check_face_input(info)
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        identity = body.identity
        if identity is None:
            # A swap result already knows who the face should be.
            made = self.artifacts.provenance(body.video.uri, body.video.sha256)
            if made.get("operation") == "swap" and made.get("character") and made.get("character_sha256"):
                identity = ArtifactRef(uri=made["character"], sha256=made["character_sha256"])
        report = lambda p: self.store.update_job(job_id, progress_json=p)
        cancelled = lambda: self.store.cancel_requested(job_id)
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            clip = work / "source.mp4"
            # 24 fps, even size, so detection, the H3 window and the paste share one frame grid.
            ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:v:0", "-an",
                    "-vf", "fps=24,scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-crf", "12",
                    "-pix_fmt", "yuv420p", str(clip)], 600)
            frames_dir = work / "frames"
            frames_dir.mkdir()
            ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(clip), str(frames_dir / "%05d.png")], 600)
            frames = sorted(frames_dir.glob("*.png"))
            width, height = Image.open(frames[0]).size
            uploaded = client.upload_audio(clip, f"{job_id}_source")
            boxes = client.run_text(face_detect_workflow(uploaded), "boxes", report, cancelled)
            windows = face_windows(parse_boxes(boxes)[:len(frames)], width, height)
            crops = crop_frames(frames, windows, work / "crops")
            length = h3_length(max(5.0, len(crops) / 24))
            window = work / "window.mp4"
            ffmpeg(["ffmpeg", "-y", "-v", "error", "-framerate", "24", "-i", str(work / "crops" / "%05d.png"),
                    "-vf", f"tpad=stop_mode=clone:stop={length},trim=end_frame={length}",
                    "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(window)], 600)
            if identity is not None:
                picture = self.artifacts.resolve(identity.uri, identity.sha256)
            else:
                picture = crops[len(crops) // 2]
            graph = face_refine_workflow(client.upload_audio(window, f"{job_id}_face"),
                                         client.upload_image(picture, job_id), FACE_CROP, length, seed, body.strength)
            raw, backend = self._run(job_id, gpu, graph, "videos")
            refined_clip = work / "refined.mp4"
            refined_clip.write_bytes(raw)
            refined_dir = work / "refined"
            refined_dir.mkdir()
            ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(refined_clip), "-frames:v", str(len(frames)),
                    str(refined_dir / "%05d.png")], 600)
            pasted = paste_frames(frames, sorted(refined_dir.glob("*.png")), windows, work / "pasted")
            final = work / "face_refine.mp4"
            command = ["ffmpeg", "-y", "-v", "error", "-framerate", "24", "-i", str(work / "pasted" / "%05d.png"),
                       "-i", str(source), "-map", "0:v:0", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p"]
            command += ["-map", "1:a:0", "-c:a", "aac", "-b:a", "256k", "-shortest"] if info["audio_codec"] else ["-an"]
            ffmpeg(command + ["-movflags", "+faststart", str(final)], 600)
            media = self.artifacts.put_media(session, final, "video/mp4", "videos",
                {"model": "MiniMax-H3 Face Refine", "operation": "face_refine", "strength": body.strength,
                 "sigmas": FACE_STRENGTHS[body.strength], "lora": HEAD_TURBO, "source": body.video.uri,
                 "identity": identity.uri if identity else None, "window": windows[0][2], "seed": seed,
                 "backend": backend, "gpu": gpu})
        return {"media": [media], "data": {"seed": seed, "gpu": gpu, "strength": body.strength,
                                          "identity": bool(identity),
                                          "output": media_probe(self.artifacts.resolve(media["uri"]))}}

    def _upscale(self, job_id: str, job: dict, gpu: int) -> dict:
        body = UpscaleRequest.model_validate(job["request"])
        source = self.artifacts.resolve(body.video.uri, body.video.sha256)
        info = video_info(source)
        check_upscale_input(info, body.scale, body.quality)
        seed = body.seed if body.seed is not None else secrets.randbits(50)
        client = self.clients[gpu]
        width, height, fps = info["width"] // 2 * 2, info["height"] // 2 * 2, info["fps"]
        # Pad (edge-smeared) to multiples of 128/scale so no tile is center-cropped; crop at the end.
        align = 128 // body.scale
        padded_w, padded_h = -(-width // align) * align, -(-height // align) * align
        tile = flashvsr_tile(body.scale, padded_w, padded_h)
        plan = upscale_chunks(info["frames"], upscale_chunk_frames(padded_w * padded_h * body.scale ** 2))
        started = time.monotonic()
        # Qwen or H3 weights left resident would share the 24 GiB with FlashVSR.
        client.free()
        try:
            with self.h3_locks[gpu], tempfile.TemporaryDirectory() as directory:
                tmp = Path(directory)
                normalized = tmp / "source.mp4"
                ffmpeg(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-map", "0:v:0", "-an",
                                "-vf", f"crop={width}:{height}:0:0,pad={padded_w}:{padded_h}:0:0,"
                                       f"fillborders=right={padded_w - width}:bottom={padded_h - height}:mode=smear",
                                "-fps_mode", "cfr", "-r", str(fps),
                                "-c:v", "libx264", "-crf", "10", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                                str(normalized)], 1800)
                outputs = []
                for index, (first, count, drop) in enumerate(plan):
                    if self.store.cancel_requested(job_id):
                        raise ComfyError("cancelled")
                    part = tmp / f"chunk_{index}.mp4"
                    ffmpeg(["ffmpeg", "-y", "-v", "error", "-ss", f"{first / fps:.6f}", "-i", str(normalized),
                            "-frames:v", str(count), "-c:v", "libx264", "-crf", "10", "-preset", "veryfast",
                            "-pix_fmt", "yuv420p", str(part)], 600)
                    name = client.upload_audio(part, f"{job_id}_{index}")
                    graph = flashvsr_workflow(name, body.scale, body.quality, seed, tile)

                    def progress(data, index=index, seen=[0]):
                        # Several nodes report progress; keep the overall bar monotonic.
                        local = max(0, min(100, data.get("pct") or 0))
                        seen[0] = max(seen[0], round((index + local / 100) * 95 / len(plan)))
                        self.store.update_job(job_id, progress_json={
                            "pct": seen[0], "node": f"tramo {index + 1}/{len(plan)}"})
                    raw, _ = client.run_output(graph, "videos", progress, lambda: self.store.cancel_requested(job_id))
                    upscaled = tmp / f"upscaled_{index}.mp4"
                    upscaled.write_bytes(raw)
                    outputs.append((upscaled, count, drop))
                self.store.update_job(job_id, progress_json={"pct": 96, "node": "uniendo tramos"})
                final = tmp / "upscaled.mp4"
                command = ["ffmpeg", "-y", "-v", "error"]
                for path, _, _ in outputs:
                    command += ["-i", str(path)]
                command += ["-i", str(source)]
                out_w, out_h = width * body.scale, height * body.scale
                filters = [f"[{i}:v]setpts=PTS-STARTPTS,crop={out_w}:{out_h}:0:0,fps={fps},settb=AVTB,format=yuv420p[c{i}]"
                           for i in range(len(outputs))]
                label, length = "c0", outputs[0][1]
                for i, (_, count, shared) in enumerate(outputs[1:], start=1):
                    filters.append(f"[{label}][c{i}]xfade=transition=fade:duration={shared / fps:.6f}:"
                                   f"offset={(length - shared) / fps:.6f}[x{i}]")
                    label, length = f"x{i}", length + count - shared
                filters.append(f"[{label}]null[v]")
                command += ["-filter_complex", ";".join(filters), "-map", "[v]"]
                copy_audio = info["audio_codec"] in {"aac", "mp3", "alac"}
                if info["audio_codec"]:
                    command += ["-map", f"{len(outputs)}:a:0", "-c:a", "copy" if copy_audio else "aac"]
                    command += [] if copy_audio else ["-b:a", "320k"]
                command += ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
                            "-r", str(fps), "-t", f"{info['frames'] / fps:.6f}", "-movflags", "+faststart", str(final)]
                ffmpeg(command, 3600)
                result = video_info(final)
                origin = self.artifacts.provenance(body.video.uri, body.video.sha256)
                media = self.artifacts.put_media(job["session_id"], final, "video/mp4", "videos", {
                    "operation": "upscale", "model": "FlashVSR v1.1", "workflow": "flashvsr_v11_chunked_v1",
                    "scale": body.scale, "quality": body.quality, "mode": FLASHVSR_MODES[body.quality],
                    "source": body.video.model_dump(), "source_width": info["width"], "source_height": info["height"],
                    "width": result["width"], "height": result["height"], "fps": fps, "frames": result["frames"],
                    "chunks": len(plan), "tile": tile, "seed": seed, "gpu": gpu,
                    "prompt": origin.get("prompt") or origin.get("title") or f"Vídeo escalado x{body.scale}",
                    "audio": ("original stream copied" if copy_audio else "original re-encoded to AAC 320k")
                             if info["audio_codec"] else "none",
                    "generation_ms": round((time.monotonic() - started) * 1000)})
        finally:
            client.free()
        return {"media": [media], "data": {"scale": body.scale, "quality": body.quality, "gpu": gpu,
                                          "seed": seed, "chunks": len(plan), "source": info, "output": result,
                                          "generation_ms": round((time.monotonic() - started) * 1000)}}

    def _song_segment(self, session: str, song_path: Path, start: float, end: float, index: int) -> dict:
        """Lossless excerpt of the scene's part of the song, kept as a traceable source."""
        with tempfile.TemporaryDirectory() as directory:
            segment = Path(directory) / "segment.flac"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{min(15.0, end - start):.3f}",
                            "-i", str(song_path), "-vn", "-c:a", "flac", str(segment)],
                           check=True, capture_output=True, timeout=120)
            ref = self.artifacts.put_media(session, segment, "audio/flac", "sources",
                {"operation": "production_lip_sync_audio", "scene": index + 1, "start": start, "end": end})
        return {"uri": ref["uri"], "sha256": ref["sha256"]}

    def _production(self, job_id: str, job: dict, gpu: int) -> dict:
        body = ProductionRequest.model_validate(job["request"])
        song_path = self.artifacts.resolve(body.song.uri, body.song.sha256)
        analysis = audio_analysis(song_path)
        scenes = body.scenes
        if abs(float(scenes[0].get("start", -1))) > .1:
            raise ValueError("storyboard must start at 0 seconds")
        if abs(float(scenes[-1].get("end", 0)) - analysis["duration"]) > .1:
            raise ValueError("storyboard does not cover the whole song")
        for index, scene in enumerate(scenes):
            start, end = float(scene["start"]), float(scene["end"])
            if not math.isfinite(start) or not math.isfinite(end) or end <= start or end - start > 15 or (index and abs(start - float(scenes[index - 1]["end"])) > .1):
                raise ValueError(f"invalid scene timing at {index + 1}")
            if not str(scene.get("video_prompt") or "").strip() or not str(scene.get("image_prompt") or "").strip():
                raise ValueError(f"scene {index + 1} needs image and video prompts")
            if scene.get("lip_sync") and not scene.get("video"):
                # The song segment becomes an H3 r2v audio reference (official 2 s minimum).
                if end - start < 2:
                    raise ValueError(f"scene {index + 1}: lip-sync needs at least 2 seconds")
                if "subject_definitions:" not in str(scene.get("video_prompt")):
                    raise ValueError(f"scene {index + 1}: lip-sync needs a Ref2VA video prompt")
        completed = (job.get("result") or {}).get("scenes", [])
        for index, scene in enumerate(scenes):
            if index < len(completed):
                continue
            if self.store.cancel_requested(job_id):
                raise ComfyError("cancelled")
            start, end = float(scene["start"]), float(scene["end"])
            prompt = str(scene.get("video_prompt") or "").strip()
            image_prompt = str(scene.get("image_prompt") or "").strip()
            image = scene.get("image")
            video_ref = scene.get("video")
            if image:
                if not image["uri"].endswith(".png"):
                    raise ValueError(f"scene {index + 1} image must be PNG")
                self.artifacts.resolve(image["uri"], image["sha256"])
            if video_ref:
                if not video_ref["uri"].endswith((".mp4", ".mkv", ".webm")):
                    raise ValueError(f"scene {index + 1} clip must be MP4, MKV or WebM")
                self.artifacts.resolve(video_ref["uri"], video_ref["sha256"])
            if not image and not video_ref:
                width, height = ({'1mp': PRESETS_1MP, '2k': PRESETS_2K, 'legacy': VIDEO_SIZE}[body.keyframe_resolution])[body.aspect_ratio]
                from types import SimpleNamespace
                width, height = image_canvas(SimpleNamespace(options=body.keyframe_options, model_precision=body.keyframe_precision),
                                             self.settings.enable_2k, (width, height))
                keyframe_steps = steps_for(body.keyframe_variant, body.keyframe_quality, body.keyframe_options)
                raw_image, _ = self._run(job_id, gpu,
                    t2i_workflow(image_prompt, width, height, ((body.seed + index) % 2**53 if body.seed is not None else secrets.randbits(53)),
                                 keyframe_steps, options=body.keyframe_options,
                                 unet=diffusion_model(body.keyframe_variant, body.keyframe_precision),
                                 encoder=os.environ.get("QWEN21_ENCODER", ENCODER),
                                 turbo=body.keyframe_variant == "turbo"), "images")
                image = self.artifacts.import_image(job["session_id"], raw_image,
                    {"operation": "production_keyframe", "scene": index + 1, "prompt": image_prompt,
                     "model_precision": body.keyframe_precision, "model_variant": body.keyframe_variant,
                     "steps": keyframe_steps,
                     "options": body.keyframe_options.values() if body.keyframe_options else {},
                     "width": width, "height": height})
            if not video_ref:
                frames = {"mode": "i2v", "first_frame": image}
                if scene.get("lip_sync"):
                    frames = {"mode": "r2v", "references": [image],
                              "reference_audios": [self._song_segment(job["session_id"], song_path, start, end, index)]}
                request = VideoRequest(prompt=prompt, **frames,
                    aspect_ratio=body.aspect_ratio, seconds=max(5, end - start),
                    profile=body.video_profile, steps=body.video_steps, options=body.video_options,
                    seed=((body.seed + index) % 2**53 if body.seed is not None else None))
                with self.h3_locks[gpu]:
                    video = self._video_locked(job_id, job["session_id"], gpu, request)
                video_ref = video["media"][0]
            completed.append({"start": start, "end": end, "image": image,
                              "video": video_ref, "prompt": prompt,
                              "clip_policy": "repeat to cover scene; trim excess"})
            self.store.update_job(job_id, result_json={"scenes": completed},
                progress_json={"pct": round(len(completed) * 95 / len(scenes)),
                               "node": f"scene {index + 1}/{len(scenes)}"})
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "production.mp4"
            command = ["ffmpeg", "-y", "-v", "error"]
            for item in completed:
                # A reused clip can be shorter than its scene. Loop the INPUT,
                # then trim below; otherwise the soundtrack outlasts the video.
                command.extend(["-stream_loop", "-1", "-i", str(self.artifacts.resolve(item["video"]["uri"], item["video"]["sha256"]))])
            command.extend(["-i", str(song_path)])
            filters = []
            labels = []
            width, height = video_size(body.aspect_ratio, body.video_options)
            for index, item in enumerate(completed):
                length = item["end"] - item["start"]
                filters.append(f"[{index}:v]trim=duration={length:.3f},setpts=PTS-STARTPTS,"
                               f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24[v{index}]")
                labels.append(f"[v{index}]")
            filters.append("".join(labels) + f"concat=n={len(completed)}:v=1:a=0[v]")
            command.extend(["-filter_complex", ";".join(filters), "-map", "[v]",
                "-map", f"{len(completed)}:a:0", "-c:v", "libx264", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "320k", "-t",
                str(analysis["duration"]), str(output)])
            subprocess.run(command, check=True, capture_output=True, timeout=3600)
            media = self.artifacts.put_media(job["session_id"], output,
                "video/mp4", "productions", {"title": body.title, "song": body.song.model_dump(),
                 "brief": body.brief, "scenes": completed, "analysis": analysis,
                 "audio": "preview AAC from original song"})
            master_path = Path(tmp) / "production-master.mkv"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(output),
                "-i", str(song_path), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                "-c:a", "copy", str(master_path)],
                check=True, capture_output=True, timeout=600)
            master = self.artifacts.put_media(job["session_id"], master_path,
                "video/x-matroska", "productions", {"title": body.title,
                 "song": body.song.model_dump(), "audio": "original encoded stream copied without transcoding"})
        return {"media": [media, master], "scenes": completed,
                "data": {"analysis": analysis, "master_uri": master["uri"]}}
