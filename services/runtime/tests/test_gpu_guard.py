import pytest

from media_lab.config import SETTINGS
from media_lab.gpu_guard import GpuBlocked, GpuGuard


def test_gpu_guard_blocks_external_comfy_queue(monkeypatch):
    guard = GpuGuard(SETTINGS)
    monkeypatch.setattr(guard, "_image_lab_running", lambda: False)
    monkeypatch.setattr(guard, "_external_comfy_busy", lambda: True)
    monkeypatch.setattr(guard, "_foreign_gpu_bytes", lambda: 0)

    status = guard.status()
    assert not status["available"]
    assert status["external_comfy_busy"]
    with pytest.raises(GpuBlocked, match="ComfyUI queue"):
        guard.require_available()


def test_gpu_guard_blocks_foreign_gigabyte(monkeypatch):
    guard = GpuGuard(SETTINGS)
    monkeypatch.setattr(guard, "_image_lab_running", lambda: False)
    monkeypatch.setattr(guard, "_external_comfy_busy", lambda: False)
    monkeypatch.setattr(guard, "_foreign_gpu_bytes", lambda: 1024**3)

    status = guard.status()
    assert not status["available"]
    assert "1024 MiB" in status["reason"]


def test_gpu_guard_prioritizes_image_lab(monkeypatch):
    guard = GpuGuard(SETTINGS)
    monkeypatch.setattr(guard, "_image_lab_running", lambda: True)
    monkeypatch.setattr(guard, "_external_comfy_busy", lambda: True)
    monkeypatch.setattr(guard, "_foreign_gpu_bytes", lambda: 2 * 1024**3)

    assert "Image Lab" in guard.status()["reason"]


def test_dynamic_vram_small_allocator_does_not_block_own_loaded_model(monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"devices": [{"vram_total": 24 * 1024**3,
                "vram_free": 9 * 1024**3, "torch_vram_total": 32 * 1024**2}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            return Response()

    monkeypatch.setattr("media_lab.gpu_guard.httpx.Client", Client)
    assert GpuGuard(SETTINGS)._foreign_gpu_bytes() == 0


@pytest.mark.parametrize('reserved', [32 * 1024**2, 544 * 1024**2, 2 * 1024**3])
@pytest.mark.parametrize('disabled', [False, True])
def test_aimdo_allocations_are_not_foreign_memory_when_torch_pool_grows(monkeypatch, reserved, disabled):
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'system': {'pytorch_version': '2.12.1+cu130',
                    'comfy_package_versions': [{'name': 'comfy-aimdo', 'installed': '0.5.5'}],
                    'argv': ['main.py'] + (['--disable-dynamic-vram'] if disabled else [])},
                    'devices': [{'vram_total': 24 * 1024**3, 'vram_free': 512 * 1024**2,
                                 'torch_vram_total': reserved}]}
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url): return Response()
    monkeypatch.setattr('media_lab.gpu_guard.httpx.Client', Client)
    value = GpuGuard(SETTINGS)._foreign_gpu_bytes()
    if disabled and reserved >= 128 * 1024**2:
        assert value > 20 * 1024**3
    else:
        assert value == 0
