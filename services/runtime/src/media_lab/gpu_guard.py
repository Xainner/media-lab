from __future__ import annotations

import httpx
import re

from .config import Settings


class GpuBlocked(RuntimeError):
    pass


class GpuGuard:
    """Best-effort guard for non-cooperating GPU services on the same host."""

    def __init__(self, settings: Settings, comfy_url: str | None = None):
        self.settings = settings
        self.comfy_url = comfy_url or settings.comfy_url

    def status(self) -> dict:
        if not self.settings.gpu_guard_enabled:
            return {"enabled": False, "available": True, "reason": "disabled"}
        image_lab = self._image_lab_running()
        external = self._external_comfy_busy()
        foreign_gpu_bytes = self._foreign_gpu_bytes()
        reason = ""
        if image_lab:
            reason = "Image Lab runtime is running; stop image-studio-lab-* first"
        elif external:
            reason = "another ComfyUI queue is active"
        elif foreign_gpu_bytes >= 1024**3:
            reason = f"a foreign GPU process is using about {foreign_gpu_bytes // 1024**2} MiB"
        return {"enabled": True, "available": not bool(reason), "reason": reason,
                "image_lab_running": image_lab, "external_comfy_busy": external,
                "foreign_gpu_bytes": foreign_gpu_bytes}

    def require_available(self) -> None:
        state = self.status()
        if not state["available"]:
            raise GpuBlocked(state["reason"])

    def _image_lab_running(self) -> bool:
        try:
            with httpx.Client(timeout=1.5) as client:
                response = client.get(f"{self.settings.image_lab_url}/v1/health")
                return response.status_code == 200
        except Exception:
            return False

    def _external_comfy_busy(self) -> bool:
        try:
            with httpx.Client(timeout=1.5) as client:
                response = client.get(f"{self.settings.external_comfy_url}/queue")
                if response.status_code != 200:
                    return False
                data = response.json()
                return bool(data.get("queue_running") or data.get("queue_pending"))
        except Exception:
            return False

    def _foreign_gpu_bytes(self) -> int:
        """Estimate allocations outside the dedicated ComfyUI torch allocator."""
        try:
            with httpx.Client(timeout=2) as client:
                response = client.get(f"{self.comfy_url}/system_stats")
                response.raise_for_status()
                data = response.json()
                device = (data.get("devices") or [])[0]
            system = data.get('system', {})
            argv = system.get('argv') or []
            packages = system.get('comfy_package_versions') or []
            aimdo = any(isinstance(p, dict) and p.get('name') == 'comfy-aimdo' for p in packages)
            version = re.match(r'^(\d+)\.(\d+)', system.get('pytorch_version') or '')
            modern_torch = version and tuple(map(int, version.groups())) >= (2, 8)
            dynamic_disabled = any(flag in argv for flag in (
                '--disable-dynamic-vram', '--highvram', '--gpu-only', '--novram', '--cpu'))
            if '--enable-dynamic-vram' in argv or (aimdo and modern_torch and not dynamic_disabled):
                # Aimdo model allocations are outside torch's allocator even
                # while sampling expands that allocator past 128 MiB. Device
                # usage minus torch reserves cannot identify foreign processes.
                # Keep the external-service/queue guards and let Comfy's native
                # NVML memory-pressure handling account for dynamic allocations.
                return 0
            total = int(device.get("vram_total") or 0)
            free = int(device.get("vram_free") or 0)
            dedicated_reserved = int(device.get("torch_vram_total") or 0)
            # DynamicVRAM on PyTorch 2.12 can report only a 32 MiB allocator
            # while this same ComfyUI process owns 15+ GiB of model memory.
            # That counter cannot distinguish its own allocations from another
            # process, so do not turn every subsequent local job into a false block.
            if dedicated_reserved < 128 * 1024**2:
                return 0
            return max(0, total - free - dedicated_reserved)
        except Exception:
            return 0
