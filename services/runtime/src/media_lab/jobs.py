from __future__ import annotations

import os
import secrets
import threading
import time
import uuid
from io import BytesIO

from PIL import Image

from .artifacts import ArtifactStore
from .comfy import ComfyClient, ComfyError
from .config import Settings
from .contracts import EditRequest, GenerateRequest, compile_prompt, generation_size, steps_for
from .gpu_guard import GpuBlocked
from .gpu_workers import GpuWorkers
from .store import Store
from .workflows import (REMOVE_BACKGROUND_PROMPT, REMOVE_BACKGROUND_STEPS, CAMERA_STEPS, CONTROL_STRENGTH, ENCODER, FLUX3_STEPS, FLUX3_UNETS,
                        MOSS_STEPS, MOSS_UNET, apply_camera, apply_control, camera_prompt, chain_loras, diffusion_model,
                        edit_workflow, flux3_edit_workflow, flux3_workflow, moss_workflow, t2i_workflow)
from .loras import resolve_loras


PREVIEW_MIN_INTERVAL = 0.35


def clean_cutout(raw: bytes) -> bytes:
    """Snap the near-zero alpha Qwen leaves over a removed background to fully clear (and near-opaque to opaque)."""
    image = Image.open(BytesIO(raw)).convert("RGBA")
    image.putalpha(image.getchannel("A").point(lambda a: 0 if a < 8 else 255 if a > 247 else a))
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


class QueueFull(RuntimeError):
    pass


class JobManager:
    def __init__(self, settings: Settings, store: Store, artifacts: ArtifactStore,
                 workers: GpuWorkers):
        self.settings = settings
        self.store = store
        self.artifacts = artifacts
        self.workers = workers
        self.clients = [ComfyClient(url, settings.generation_timeout) for url in settings.worker_urls()]
        self._previews: dict[str, dict] = {}
        self._preview_lock = threading.Lock()

    def preview(self, job_id: str) -> dict | None:
        with self._preview_lock:
            return self._previews.get(job_id)

    def preview_seq(self, job_id: str) -> int:
        item = self.preview(job_id)
        return item["seq"] if item else 0

    def _store_preview(self, job_id: str, data: bytes, mime: str) -> None:
        now = time.monotonic()
        with self._preview_lock:
            current = self._previews.get(job_id)
            if current and now - current["at"] < PREVIEW_MIN_INTERVAL:
                return
            self._previews[job_id] = {"seq": (current["seq"] if current else 0) + 1,
                                      "data": data, "mime": mime, "at": now}

    def submit_generate(self, body: GenerateRequest, key: str | None = None, scope: str | None = None) -> dict:
        session = body.session_id or f"sess_{uuid.uuid4().hex[:12]}"
        return self._submit("generate", session, body.model_dump(), key, scope)

    def submit_edit(self, body: EditRequest, key: str | None = None, scope: str | None = None) -> dict:
        session = body.session_id or f"sess_{uuid.uuid4().hex[:12]}"
        return self._submit("edit", session, body.model_dump(), key, scope)

    def _submit(self, operation: str, session: str, request: dict, key: str | None = None, scope: str | None = None) -> dict:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job_id, created = self.store.create_job_once(job_id, session, operation, request, self.settings.max_pending, key, scope)
        if not job_id:
            raise QueueFull("job queue is full")
        if not created:
            return self.store.job_receipt(job_id)
        gpu = self.workers.submit(job_id, 0, self._execute)
        return {"job_id": job_id, "session_id": session, "status": "queued",
                "gpu": gpu, "queue_position": self.store.queue_position(job_id)}

    def cancel(self, job_id: str) -> bool:
        return self.workers.cancel(job_id)

    def _execute(self, job_id: str, gpu: int) -> None:
        job = self.store.get_job(job_id)
        if not job:
            return
        if self.store.cancel_requested(job_id):
            self.store.update_job(job_id, status="cancelled", completed_at=time.time(), error="cancelled")
            return
        try:
            if self.store.cancel_requested(job_id):
                self.store.update_job(job_id, status="cancelled", completed_at=time.time(), error="cancelled")
                return
            self.store.update_job(job_id, status="running", started_at=time.time(),
                                  activity_json=[f"gpu:{gpu}", "gpu_guard"])
            self.workers.guards[gpu].require_available()
            self.store.update_job(job_id, activity_json=[f"gpu:{gpu}", "gpu_guard", "preparing_workflow"])
            if job["operation"] == "generate":
                result = self._generate(job_id, job, gpu)
            else:
                result = self._edit(job_id, job, gpu)
            if self.store.cancel_requested(job_id):
                raise ComfyError("cancelled")
            self.store.update_job(
                job_id, status="completed", result_json=result, error=None,
                activity_json=[f"gpu:{gpu}", "gpu_guard", "preparing_workflow", "generating", "importing", "completed"],
                progress_json={"pct": 100, "step": 0, "steps": 0, "node": "done"},
                completed_at=time.time(),
            )
        except GpuBlocked as exc:
            self.store.update_job(job_id, status="blocked_gpu", error=str(exc),
                                  activity_json=[f"gpu:{gpu}", "gpu_guard", "blocked"], completed_at=time.time())
        except Exception as exc:
            status = "cancelled" if self.store.cancel_requested(job_id) or str(exc) == "cancelled" else "failed"
            self.store.update_job(job_id, status=status, error=str(exc),
                                  activity_json=[f"gpu:{gpu}", "failed"], completed_at=time.time())
        finally:
            with self._preview_lock:
                self._previews.pop(job_id, None)

    def _progress(self, job_id: str, data: dict, gpu: int) -> None:
        self.store.update_job(job_id, activity_json=[f"gpu:{gpu}", "gpu_guard", "preparing_workflow", "generating"],
                              progress_json=data)

    def _generate(self, job_id: str, job: dict, gpu: int) -> dict:
        body = GenerateRequest.model_validate(job["request"])
        width, height = generation_size(body, self.settings.enable_2k)
        from .model_options import image_canvas
        width, height = image_canvas(body, self.settings.enable_2k, (width, height))
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        compiled = compile_prompt(body.prompt, body.transparent)
        loras = []
        if body.model == "moss":
            steps, unet, workflow = MOSS_STEPS[body.quality], MOSS_UNET, "moss_image_sft_t2i_v1"
            graph = moss_workflow(compiled, width, height, seed, steps)
        elif body.model == "flux3":
            steps, unet = FLUX3_STEPS[body.quality], FLUX3_UNETS[body.quality]
            workflow = "flux3_klein_t2i_v1" if body.quality == "draft" else "flux3_klein_base_t2i_v1"
            graph = flux3_workflow(compiled, width, height, seed, body.quality, body.aspect_ratio)
        else:
            steps = steps_for(body.model_variant, body.quality, body.options)
            encoder = os.environ.get("QWEN21_ENCODER", ENCODER)
            unet = diffusion_model(body.model_variant, body.model_precision)
            turbo = body.model_variant == "turbo"
            workflow = "qwen21_turbo_t2i_v1" if turbo else "qwen21_t2i_v1"
            graph = t2i_workflow(compiled, width, height, seed, steps, encoder, unet, options=body.options, turbo=turbo)
            if body.control is not None:
                source = self.artifacts.resolve(body.control.reference.uri, body.control.reference.sha256)
                upload = self.clients[gpu].upload_image(source, f"{job_id}_control")
                strength = body.control.strength if body.control.strength is not None else CONTROL_STRENGTH[body.control.mode]
                apply_control(graph, upload, body.control.mode, strength, width, height)
                workflow = workflow.replace("_t2i_", "_control_t2i_")
            loras = resolve_loras(self.store, body.loras, "qwen")
            chain_loras(graph, "1", loras)
        started = time.monotonic()
        raw, backend = self.clients[gpu].run(graph, lambda p: self._progress(job_id, p, gpu),
                                      lambda: self.store.cancel_requested(job_id),
                                      lambda data, mime: self._store_preview(job_id, data, mime))
        if body.model == "flux3":
            compiled = self.clients[gpu].output_text(backend["prompt_id"], "caption") or compiled
        media = self.artifacts.import_image(job["session_id"], raw, {
            "operation": "generate", "workflow": workflow, "gpu": gpu,
            "input_prompt": body.prompt, "compiled_prompt": compiled,
            "transparent": body.transparent, "seed": seed, "steps": steps,
            "options": body.options.values() if body.options else {},
            "width": width, "height": height,
            "model_precision": body.model_precision, "model_variant": body.model_variant,
            "model": body.model, "diffusion_model": unet,
            "control": body.control.model_dump() if body.control else None,
            "loras": [{"file": f, "strength": s} for f, s in loras],
            "generation_ms": round((time.monotonic() - started) * 1000),
            "backend": backend,
        })
        return {"media": [media], "data": {"workflow": workflow, "seed": seed,
                "steps": steps, "width": width, "height": height, "gpu": gpu,
                "model_precision": body.model_precision, "model_variant": body.model_variant,
                "generation_ms": round((time.monotonic() - started) * 1000)}}

    def _edit(self, job_id: str, job: dict, gpu: int) -> dict:
        body = EditRequest.model_validate(job["request"])
        if body.model == "flux3":
            return self._flux3_edit(job_id, job, gpu, body)
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        steps = steps_for(body.model_variant, body.quality, body.options)
        compiled = compile_prompt(body.prompt, body.transparent)
        if body.remove_background:
            steps, compiled = REMOVE_BACKGROUND_STEPS, REMOVE_BACKGROUND_PROMPT
        if body.camera is not None:
            steps = CAMERA_STEPS
            compiled = camera_prompt(body.camera.azimuth, body.camera.elevation, body.camera.distance, body.prompt)
        uploaded: list[str] = []
        for index, reference in enumerate(body.references, start=1):
            source = self.artifacts.resolve(reference.uri, reference.sha256)
            uploaded.append(self.clients[gpu].upload_image(source, f"{job_id}_{index}"))
        encoder = os.environ.get("QWEN21_ENCODER", ENCODER)
        unet = diffusion_model(body.model_variant, body.model_precision)
        turbo = body.model_variant == "turbo"
        workflow = "qwen21_turbo_edit_v1" if turbo else "qwen21_edit_v1"
        graph = edit_workflow(compiled, uploaded, seed, steps, body.resolution, encoder, unet,
                              options=body.options, turbo=turbo)
        if body.camera is not None:
            apply_camera(graph)
            workflow = "qwen21_camera_edit_v1"
        if body.remove_background:
            workflow = "qwen21_remove_background_v1"
        loras = resolve_loras(self.store, body.loras, "qwen")
        chain_loras(graph, "1", loras)
        started = time.monotonic()
        raw, backend = self.clients[gpu].run(graph, lambda p: self._progress(job_id, p, gpu),
                                      lambda: self.store.cancel_requested(job_id),
                                      lambda data, mime: self._store_preview(job_id, data, mime))
        if body.remove_background:
            raw = clean_cutout(raw)
        media = self.artifacts.import_image(job["session_id"], raw, {
            "operation": "edit", "remove_background": body.remove_background, "workflow": workflow, "gpu": gpu,
            "input_prompt": body.prompt, "compiled_prompt": compiled,
            "transparent": body.transparent, "seed": seed, "steps": steps,
            "options": body.options.values() if body.options else {},
            "references": [r.model_dump() for r in body.references],
            "camera": body.camera.model_dump() if body.camera else None,
            "loras": [{"file": f, "strength": s} for f, s in loras],
            "model_precision": body.model_precision, "model_variant": body.model_variant,
            "diffusion_model": unet,
            "generation_ms": round((time.monotonic() - started) * 1000),
            "backend": backend,
        })
        return {"media": [media], "data": {"workflow": workflow, "seed": seed,
                "steps": steps, "model_precision": body.model_precision,
                "model_variant": body.model_variant, "gpu": gpu,
                "generation_ms": round((time.monotonic() - started) * 1000)}}

    def _flux3_edit(self, job_id: str, job: dict, gpu: int, body: EditRequest) -> dict:
        seed = body.seed if body.seed is not None else secrets.randbits(53)
        uploaded = [self.clients[gpu].upload_image(self.artifacts.resolve(ref.uri, ref.sha256), f"{job_id}_{index}")
                    for index, ref in enumerate(body.references, start=1)]
        graph = flux3_edit_workflow(body.prompt, uploaded, seed)
        started = time.monotonic()
        raw, backend = self.clients[gpu].run(graph, lambda p: self._progress(job_id, p, gpu),
                                             lambda: self.store.cancel_requested(job_id),
                                             lambda data, mime: self._store_preview(job_id, data, mime))
        compiled = self.clients[gpu].output_text(backend["prompt_id"], "caption") or body.prompt
        workflow, steps = "flux3_klein_edit_v1", FLUX3_STEPS["draft"]
        media = self.artifacts.import_image(job["session_id"], raw, {
            "operation": "edit", "workflow": workflow, "gpu": gpu, "model": "flux3",
            "input_prompt": body.prompt, "compiled_prompt": compiled, "seed": seed, "steps": steps,
            "references": [r.model_dump() for r in body.references], "diffusion_model": FLUX3_UNETS["draft"],
            "generation_ms": round((time.monotonic() - started) * 1000), "backend": backend,
        })
        return {"media": [media], "data": {"workflow": workflow, "seed": seed, "steps": steps, "model": "flux3", "gpu": gpu,
                "generation_ms": round((time.monotonic() - started) * 1000)}}
