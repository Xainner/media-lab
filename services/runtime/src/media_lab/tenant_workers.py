"""Fair, central admission: an account waiting for its limit never holds a GPU."""
from __future__ import annotations

import threading
import time
from contextvars import copy_context

from .gpu_workers import GpuWorkers


class TenantWorkers(GpuWorkers):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pending = []
        self.executing = set()
        self.stopping = threading.Event()
        self.wakeup = threading.Event()
        self.dispatcher = threading.Thread(target=self._loop, name="visual-admission", daemon=True)
        self.dispatcher.start()

    def submit(self, job_id, preferred, execute):
        context = copy_context()
        with self.lock:
            self.pending.append((job_id, preferred, execute, context))
        self.wakeup.set()
        return None  # No GPU is reserved while queued.

    def _claim(self, job_id):
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT * FROM jobs WHERE id=? AND status='queued' AND cancel_requested=0", (job_id,)).fetchone()
            if not job:
                return "remove"
            user = db.execute("SELECT enabled,active_limit FROM users WHERE id=?", (job["owner_id"],)).fetchone()
            if not user or not user["enabled"]:
                db.execute("UPDATE jobs SET status='cancelled',cancel_requested=1,updated_at=? WHERE id=?", (time.time(), job_id))
                return "remove"
            active = db.execute("SELECT COUNT(*) FROM jobs WHERE owner_id=? AND status='running'", (job["owner_id"],)).fetchone()[0]
            if user["active_limit"] and active >= user["active_limit"]:
                return "wait"
            db.execute("UPDATE jobs SET status='running',started_at=?,updated_at=? WHERE id=?", (time.time(), time.time(), job_id))
            return "ready"

    def _loop(self):
        while not self.stopping.is_set():
            self.wakeup.wait(.5)
            self.wakeup.clear()
            try:
                self._dispatch()
            except Exception:
                # Retry admission without generating a replacement or leaking request content.
                continue

    def _dispatch(self):
        states = self.status()
        with self.lock:
            available = [s for s in states if s["health"]["ok"] and s["gpu_guard"]["available"]
                         and not s["busy"] and s["gpu"] not in self.assigned.values()
                         and not s["comfy_queue"].get("queue_pending")]
            for item in list(self.pending):
                if not available:
                    break
                job_id, preferred, execute, context = item
                decision = self._claim(job_id)
                if decision == "wait":
                    continue  # Later users can use the free worker.
                self.pending.remove(item)
                if decision == "remove":
                    continue
                chosen = min(available, key=lambda s: s["gpu"] != preferred)
                gpu = chosen["gpu"]
                available.remove(chosen)
                self.assigned[job_id] = gpu
                context.run(self.store.update_job, job_id, activity_json=[f"gpu:{gpu}"])
                self.pools[gpu].submit(context.run, self._execute, job_id, gpu, self._callback(execute))

    def _callback(self, execute):
        def run(job_id, gpu):
            with self.lock:
                self.executing.add(job_id)
            try:
                execute(job_id, gpu)
            finally:
                with self.lock:
                    self.executing.discard(job_id)
                self.wakeup.set()
        return run

    def cancel(self, job_id):
        with self.lock:
            changed = self.store.request_cancel(job_id)
            gpu = self.active.get(job_id)
            if changed and gpu is not None and job_id in self.executing:
                self.clients[gpu].interrupt()
            elif changed:
                self.store.update_job(job_id, status="cancelled", error="cancelled", completed_at=time.time())
                self.pending = [p for p in self.pending if p[0] != job_id]
        self.wakeup.set()
        return changed

    def shutdown(self):
        self.stopping.set()
        self.wakeup.set()
        self.dispatcher.join(timeout=5)
        super().shutdown()

