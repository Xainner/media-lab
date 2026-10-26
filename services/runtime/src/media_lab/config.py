from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    comfy_url: str
    comfy_gpu1_url: str
    artifacts_root: Path
    db_path: Path
    bundles_dir: Path
    model_root: Path
    h3_model_root: Path
    generation_timeout: int
    max_pending: int
    idle_unload_seconds: int
    external_comfy_url: str
    image_lab_url: str
    gpu_guard_enabled: bool
    enable_2k: bool
    enable_bf16: bool
    upload_max_bytes: int
    upload_max_pixels: int
    h3_fused_root: Path = Path("/fused-models")
    # One ComfyUI endpoint per GPU (COMFYUI_ENDPOINTS); empty keeps the two-worker pair above.
    comfy_urls: tuple[str, ...] = ()

    def worker_urls(self) -> tuple[str, ...]:
        """The ComfyUI workers in GPU order: one job at a time on each."""
        return self.comfy_urls or (self.comfy_url, self.comfy_gpu1_url)


def load_settings() -> Settings:
    state = Path(os.environ.get("STATE_ROOT", "/data"))
    artifacts = Path(os.environ.get("ARTIFACTS_ROOT", str(state / "artifacts")))
    endpoints = tuple(url.strip().rstrip("/") for url in os.environ.get("COMFYUI_ENDPOINTS", "").split(",")
                      if url.strip())
    return Settings(
        comfy_urls=endpoints,
        comfy_url=endpoints[0] if endpoints else
        os.environ.get("COMFYUI_ENDPOINT", "http://media-lab-comfyui:8188").rstrip("/"),
        comfy_gpu1_url=os.environ.get("COMFYUI_GPU1_ENDPOINT", "http://127.0.0.1:8389").rstrip("/"),
        artifacts_root=artifacts,
        db_path=Path(os.environ.get("DB_PATH", str(state / "media-lab.db"))),
        bundles_dir=Path(os.environ.get("BUNDLES_DIR", "/app/assets/bundles")),
        model_root=Path(os.environ.get("MODEL_ROOT", "/models")),
        h3_model_root=Path(os.environ.get("H3_MODEL_ROOT", "/h3-models")),
        h3_fused_root=Path(os.environ.get("H3_FUSED_ROOT", "/fused-models")),
        generation_timeout=int(os.environ.get("GENERATION_TIMEOUT_SECONDS", "900")),
        max_pending=int(os.environ.get("MAX_PENDING", "4")),
        idle_unload_seconds=int(os.environ.get("IDLE_UNLOAD_SECONDS", "120")),
        external_comfy_url=os.environ.get("EXTERNAL_COMFY_URL", "http://host.docker.internal:8188").rstrip("/"),
        image_lab_url=os.environ.get("IMAGE_LAB_URL", "http://host.docker.internal:8290").rstrip("/"),
        gpu_guard_enabled=_bool("GPU_GUARD_ENABLED", True),
        enable_2k=_bool("ENABLE_2K", False),
        enable_bf16=_bool("ENABLE_BF16", False),
        upload_max_bytes=int(os.environ.get("UPLOAD_MAX_BYTES", str(20 * 1024 * 1024))),
        upload_max_pixels=int(os.environ.get("UPLOAD_MAX_PIXELS", str(50_000_000))),
    )


SETTINGS = load_settings()
