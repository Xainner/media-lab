import io
import threading
import time
from dataclasses import replace

import pytest
from PIL import Image

from media_lab.artifacts import ArtifactStore
from media_lab.comfy import ComfyError
from media_lab.config import SETTINGS
from media_lab.contracts import GenerateRequest, EditRequest, VideoRequest
from media_lab.creative import CreativeJobs
from media_lab.gpu_workers import GpuWorkers
from media_lab.jobs import JobManager
from media_lab.store import Store


class FakeGuard:
    def __init__(self):
        self.available = True
        self.checked = 0

    def status(self):
        return {"available": self.available}

    def require_available(self):
        self.checked += 1
        assert self.available


class FakeComfy:
    def __init__(self, gpu):
        self.base_url = f"http://gpu{gpu}"
        self.online = True
        self.started = threading.Event()
        self.release = threading.Event()
        self.interrupted = 0
        self.freed = 0
        self.uploaded = []
        self.error = False
        self.external = False

    def health(self):
        return {"ok": self.online}

    def queue(self):
        return {"queue_running": ["external"] if self.external else [], "queue_pending": []}

    def interrupt(self):
        self.interrupted += 1

    def free(self):
        self.freed += 1

    def free_and_wait(self):
        self.free()

    def upload_image(self, path, prefix):
        self.uploaded.append(path)
        return path.name

    def run(self, graph, progress, cancelled, preview=None):
        self.started.set()
        deadline = time.monotonic() + 5
        while not self.release.wait(.01):
            if cancelled():
                raise ComfyError("cancelled")
            assert time.monotonic() < deadline, "test did not release GPU"
        if self.error:
            raise ComfyError("CUDA out of memory")
        output = io.BytesIO()
        Image.new("RGB", (32, 32), "blue").save(output, "PNG")
        progress({"pct": 90})
        return output.getvalue(), {"prompt_id": "fake"}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    settings = replace(SETTINGS, db_path=tmp_path / "lab.db", artifacts_root=tmp_path / "artifacts")
    store = Store(settings.db_path)
    artifacts = ArtifactStore(settings.artifacts_root, settings.upload_max_bytes, settings.upload_max_pixels)
    clients = [FakeComfy(i) for i in range(2)]
    guards = [FakeGuard(), FakeGuard()]
    workers = GpuWorkers(settings, store, clients, guards)
    jobs = JobManager(settings, store, artifacts, workers)
    jobs.clients = clients
    creative = CreativeJobs(settings, store, artifacts, workers)
    yield jobs, creative, workers, clients, store, artifacts
    for client in clients:
        client.release.set()
    workers.shutdown()


def finished(store, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = store.get_job(job["job_id"])
        if result["status"] not in {"queued", "running"}:
            return result
        time.sleep(.01)
    pytest.fail("job did not finish")


def test_images_use_both_gpus_and_cancel_only_their_worker(lab):
    jobs, _, workers, clients, store, _ = lab
    first = jobs.submit_generate(GenerateRequest(prompt="first"))
    assert clients[0].started.wait(2)
    second = jobs.submit_generate(GenerateRequest(prompt="second"))
    assert clients[1].started.wait(2)
    assert (first["gpu"], second["gpu"]) == (0, 1)
    assert all(s["busy"] for s in workers.status())
    workers.free_idle(1)
    assert clients[1].freed == 0
    assert jobs.cancel(first["job_id"])
    assert clients[0].interrupted == 1 and clients[1].interrupted == 0
    clients[1].release.set()
    assert finished(store, first)["status"] == "cancelled"
    result = finished(store, second)
    assert result["status"] == "completed"
    assert result["result"]["data"]["gpu"] == 1
    assert result["activity"][0] == "gpu:1"
    assert workers.guards[1].checked == 1


def test_queued_cancellation_does_not_interrupt_running_images(lab):
    jobs, _, _, clients, store, _ = lab
    first = jobs.submit_generate(GenerateRequest(prompt="first"))
    assert clients[0].started.wait(2)
    second = jobs.submit_generate(GenerateRequest(prompt="second"))
    assert clients[1].started.wait(2)
    third = jobs.submit_generate(GenerateRequest(prompt="third"))
    assert jobs.cancel(third["job_id"])
    assert finished(store, third)["status"] == "cancelled"
    assert not any(c.interrupted for c in clients)
    for client in clients:
        client.release.set()
    assert finished(store, first)["status"] == finished(store, second)["status"] == "completed"


def test_music_and_images_share_the_same_scheduler(lab, monkeypatch):
    jobs, creative, workers, clients, store, _ = lab
    def song(job_id, job, gpu):
        clients[gpu].run({}, lambda p: None, lambda: False)
        return {"media": [], "data": {"gpu": gpu}}
    monkeypatch.setattr(creative, "_song", song)
    music = creative.submit("song", {}, 1)
    assert clients[1].started.wait(2)
    image = jobs.submit_generate(GenerateRequest(prompt="image"))
    assert clients[0].started.wait(2)
    assert music["gpu"] == 1 and image["gpu"] == 0
    assert workers.status()[1]["operation"] == "song"
    for client in clients:
        client.release.set()
    assert finished(store, music)["status"] == finished(store, image)["status"] == "completed"


def test_edit_uses_gpu1_and_uploads_references_to_that_instance(lab):
    jobs, _, _, clients, store, artifacts = lab
    blocker = jobs.submit_generate(GenerateRequest(prompt="block gpu0"))
    assert clients[0].started.wait(2)
    data = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(data, "PNG")
    ref = artifacts.put_upload("test", data.getvalue(), "image/png")
    edit = jobs.submit_edit(EditRequest(prompt="blue", references=[ref]))
    assert clients[1].started.wait(2)
    assert edit["gpu"] == 1
    assert len(clients[1].uploaded) == 1 and not clients[0].uploaded
    for client in clients:
        client.release.set()
    assert finished(store, edit)["status"] == finished(store, blocker)["status"] == "completed"


def test_offline_or_guard_blocked_worker_is_not_selected(lab):
    jobs, _, workers, clients, store, _ = lab
    clients[0].online = False
    clients[1].release.set()
    first = jobs.submit_generate(GenerateRequest(prompt="fallback"))
    assert first["gpu"] == 1
    assert finished(store, first)["status"] == "completed"
    clients[0].online = True
    workers.guards[0].available = False
    second = jobs.submit_generate(GenerateRequest(prompt="guard fallback"))
    assert second["gpu"] == 1
    assert finished(store, second)["status"] == "completed"



def test_error_releases_worker_and_next_job_succeeds(lab):
    jobs, _, workers, clients, store, _ = lab
    clients[1].online = False
    clients[0].error = True
    clients[0].release.set()
    failed = jobs.submit_generate(GenerateRequest(prompt="oom"))
    assert finished(store, failed)["status"] == "failed"
    clients[0].error = False
    success = jobs.submit_generate(GenerateRequest(prompt="recovery"))
    assert finished(store, success)["status"] == "completed"
    workers.shutdown()
    workers.free_idle(0)
    assert clients[0].freed == 1


def test_cancelling_wait_for_external_graph_does_not_interrupt_it(lab):
    jobs, _, _, clients, store, _ = lab
    clients[0].external = True
    clients[1].online = False
    job = jobs.submit_generate(GenerateRequest(prompt="wait for graph"))
    assert jobs.cancel(job["job_id"])
    assert finished(store, job)["status"] == "cancelled"
    assert clients[0].interrupted == 0


@pytest.mark.parametrize('profile', ['base', 'fused_turbo'])
def test_h3_jobs_use_both_workers_and_cancellation_stays_scoped(lab, monkeypatch, profile):
    _, creative, _, clients, store, _ = lab
    def render(job_id, session, gpu, body):
        clients[gpu].run({}, lambda _: None, lambda: store.cancel_requested(job_id))
        return {'media': [], 'data': {'gpu': gpu}}
    # Mock only the GPU graph execution, retaining H3 locking and real scheduling.
    monkeypatch.setattr(creative, '_video_locked', render)
    body = VideoRequest(prompt='coherent action', profile=profile).model_dump()
    first = creative.submit('video', body, 1)
    assert clients[1].started.wait(2)
    second = creative.submit('video', body, 1)
    try:
        assert clients[0].started.wait(2), 'GPU0 was stranded behind the global H3 lock'
        assert (first['gpu'], second['gpu']) == (1, 0)
        assert creative.cancel(first['job_id'])
        # The cancelled callback may already have exited before interrupt is sent.
        assert clients[1].interrupted <= 1 and clients[0].interrupted == 0
        clients[0].release.set()
        assert finished(store, first)['status'] == 'cancelled'
        assert finished(store, second)['status'] == 'completed'
    finally:
        for client in clients:
            client.release.set()


def test_director_video_lock_does_not_block_a_video_on_the_other_gpu(lab, monkeypatch):
    _, creative, _, clients, store, _ = lab
    # A Director scene holds GPU0's H3 lock exactly as _production does.
    creative.h3_locks[0].acquire()
    def render(job_id, session, gpu, body):
        clients[gpu].run({}, lambda _: None, lambda: store.cancel_requested(job_id))
        return {'media': [], 'data': {'gpu': gpu}}
    monkeypatch.setattr(creative, '_video_locked', render)
    try:
        job = creative.submit('video', VideoRequest(prompt='x').model_dump(), 1)
        assert clients[1].started.wait(2)
        clients[1].release.set()
        assert finished(store, job)['status'] == 'completed'
    finally:
        creative.h3_locks[0].release()
