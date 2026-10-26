"""One shared executor per physical GPU for every Media Lab operation."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .comfy import ComfyClient, ComfyError
from .gpu_guard import GpuGuard


class GpuWorkers:
    def __init__(self, settings, store, clients=None, guards=None):
        self.settings, self.store = settings, store
        urls = settings.worker_urls()
        self.clients = clients or [ComfyClient(url, max(settings.generation_timeout, 3600)) for url in urls]
        self.guards = guards or [GpuGuard(settings, url) for url in urls]
        self.locks = [threading.Lock() for _ in self.clients]
        self.pools = [ThreadPoolExecutor(1, thread_name_prefix=f"visual-gpu{i}") for i in range(len(self.clients))]
        self.lock = threading.RLock()
        self.assigned: dict[str, int] = {}
        self.active: dict[str, int] = {}
        self.operations: dict[int, str] = {}
        self.timers: dict[int, threading.Timer] = {}

    def status(self):
        states = []
        for gpu, client in enumerate(self.clients):
            health = client.health()
            guard = self.guards[gpu].status()
            queue = {}
            if health["ok"]:
                try:
                    queue = client.queue()
                except Exception as exc:
                    health = {"ok": False, "error": str(exc)}
            with self.lock:
                states.append({"gpu": gpu, "url": client.base_url, "health": health,
                    "gpu_guard": guard, "busy": self.locks[gpu].locked() or bool(queue.get("queue_running")),
                    "active_job": next((job for job, i in self.active.items() if i == gpu), None),
                    "operation": self.operations.get(gpu),
                    "pending": sum(i == gpu and job not in self.active for job, i in self.assigned.items()),
                    "comfy_queue": queue})
        return states

    def submit(self, job_id, preferred, execute):
        preferred = min(preferred, len(self.clients) - 1)  # a one-GPU host has no GPU 1
        states = self.status()
        healthy = [s for s in states if s["health"]["ok"]]
        available = [s for s in healthy if s["gpu_guard"]["available"]]
        candidates = available or healthy or states[preferred:preferred + 1]
        with self.lock:
            gpu = min(candidates, key=lambda s: (
                self.locks[s["gpu"]].locked() or s["busy"],
                sum(i == s["gpu"] for i in self.assigned.values()) +
                len(s["comfy_queue"].get("queue_pending", [])), s["gpu"] != preferred))["gpu"]
            self.assigned[job_id] = gpu
            self.store.update_job(job_id, activity_json=[f"gpu:{gpu}"])
            self.pools[gpu].submit(self._execute, job_id, gpu, execute)
        return gpu

    def _execute(self, job_id, gpu, execute):
        with self.locks[gpu]:
            try:
                if self.store.cancel_requested(job_id):
                    return
                with self.lock:
                    timer = self.timers.pop(gpu, None)
                    if timer:
                        timer.cancel()
                    self.active[job_id] = gpu
                    self.operations[gpu] = (self.store.get_job(job_id) or {}).get("operation", "job")
                # Graph jobs can bypass this scheduler; never interrupt or overlap them.
                started = time.monotonic()
                while True:
                    queue = self.clients[gpu].queue()
                    if not (queue.get("queue_running") or queue.get("queue_pending")):
                        break
                    if self.store.cancel_requested(job_id):
                        return
                    if time.monotonic() - started > self.settings.generation_timeout:
                        raise ComfyError("dedicated ComfyUI queue remained busy")
                    time.sleep(.5)
                execute(job_id, gpu)
            except Exception as exc:
                self.store.update_job(job_id, status="cancelled" if self.store.cancel_requested(job_id) else "failed",
                                      error=str(exc), completed_at=time.time())
            finally:
                with self.lock:
                    self.active.pop(job_id, None)
                    self.assigned.pop(job_id, None)
                    self.operations.pop(gpu, None)
                    self._schedule_unload(gpu)

    def cancel(self, job_id):
        with self.lock:
            changed = self.store.request_cancel(job_id)
            gpu = self.active.get(job_id)
            job = self.store.get_job(job_id)
            # Only a running runtime job owns the backend prompt. A queued job
            # waiting for a Graph job must not interrupt that unrelated prompt.
            if changed and gpu is not None and job["status"] == "running":
                self.clients[gpu].interrupt()
            elif changed:
                self.store.update_job(job_id, status="cancelled", error="cancelled", completed_at=time.time())
                self.assigned.pop(job_id, None)
            return changed

    def _schedule_unload(self, gpu):
        old = self.timers.pop(gpu, None)
        if old:
            old.cancel()
        timer = threading.Timer(self.settings.idle_unload_seconds, self.free_idle, args=(gpu,))
        timer.daemon = True
        self.timers[gpu] = timer
        timer.start()

    def free_idle(self, gpu):
        if not self.locks[gpu].acquire(blocking=False):
            return
        try:
            with self.lock:
                if gpu in self.assigned.values():
                    return
            queue = self.clients[gpu].queue()
            if not (queue.get("queue_running") or queue.get("queue_pending")):
                self.clients[gpu].free()
        finally:
            self.locks[gpu].release()

    def shutdown(self):
        for pool in self.pools:
            pool.shutdown(wait=True)
        with self.lock:
            for timer in self.timers.values():
                timer.cancel()
