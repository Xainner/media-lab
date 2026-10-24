"""Opt-in, real 1024px GPU routing/cancellation smoke; no desktop interaction."""
import argparse
import io
import json
import time
import uuid

import httpx
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://192.0.2.10:8390")
    parser.add_argument("--bf16", action="store_true")
    args = parser.parse_args()
    session = "dual_gpu_smoke_" + uuid.uuid4().hex[:12]
    own = []
    with httpx.Client(base_url=args.url, timeout=60) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        health = request("GET", "/v1/health")
        assert health["queue"] == {"running": 0, "pending": 0}, "wait for existing runtime jobs first"
        assert all(not w["busy"] and w["health"]["ok"] for w in health["workers"]), "workers must be idle"
        fixture = Image.new("RGB", (1024, 1024), "white")
        ImageDraw.Draw(fixture).ellipse((256, 256, 768, 768), fill="red")
        data = io.BytesIO()
        fixture.save(data, "PNG")
        reference = request("POST", "/v1/uploads", data={"session_id": session},
            files={"file": ("dual-gpu-fixture.png", data.getvalue(), "image/png")})["data"]

        def submit(operation, body):
            job = request("POST", f"/v1/jobs/{operation}", json={
                "session_id": session, "quality": "quality" if args.bf16 else "draft",
                "model_precision": "bf16" if args.bf16 else "int8", "seed": 30903090, **body})
            own.append(job["job_id"])
            print(json.dumps({"event": "submitted", "operation": operation, **job}), flush=True)
            return job

        try:
            first = submit("generate", {"prompt": "A studio photograph of a blue ceramic cup on a white table.",
                                        "aspect_ratio": "1:1"})
            second = submit("edit", {"prompt": "Change the red circle to blue. Keep the white background.",
                                     "references": [reference], "resolution": 1024})
            assert [first["gpu"], second["gpu"]] == [0, 1], "smoke requires both workers"
            observed_parallel = False
            cancelled = False
            recovery = None
            completed = {}
            deadline = time.monotonic() + 1500
            last = None
            while time.monotonic() < deadline:
                jobs = [request("GET", f"/v1/jobs/{job_id}") for job_id in own]
                states = [(job["id"], job["gpu"], job["status"], (job.get("progress") or {}).get("pct")) for job in jobs]
                if states != last:
                    print(json.dumps({"event": "progress", "jobs": states}), flush=True)
                    last = states
                observed_parallel |= len([j for j in jobs if j["status"] == "running"]) == 2
                original = jobs[0]
                if not cancelled and observed_parallel and (original.get("progress") or {}).get("step", 0) >= 2:
                    request("DELETE", f"/v1/jobs/{first['job_id']}")
                    cancelled = True
                    print(json.dumps({"event": "cancelled_gpu0", "job": first["job_id"]}), flush=True)
                if cancelled and original["status"] == "cancelled" and recovery is None:
                    workers = request("GET", "/v1/health")["workers"]
                    if not workers[0]["busy"]:
                        recovery = submit("generate", {"prompt": "A detailed studio photograph of a yellow ceramic cup on a white table.",
                                                       "aspect_ratio": "1:1"})
                        assert recovery["gpu"] == 0
                for job in jobs:
                    assert job["status"] not in {"failed", "blocked_gpu", "interrupted"}, job.get("error")
                    if job["status"] == "completed":
                        completed[job["id"]] = job
                if recovery and second["job_id"] in completed and recovery["job_id"] in completed:
                    break
                time.sleep(3)
            else:
                raise AssertionError("smoke timed out")
            assert observed_parallel and cancelled
            for job in completed.values():
                media = job["result"]["media"][0]
                assert (media["width"], media["height"]) == (1024, 1024)
            print(json.dumps({"event": "passed", "session": session,
                "parallel": True, "cancel_isolated": True,
                "completed": [{"id": job["id"], "operation": job["operation"],
                    "gpu": job["gpu"], "data": job["result"]["data"],
                    "media": job["result"]["media"]} for job in completed.values()]}), flush=True)
        finally:
            # Never cancel somebody else's job; leave results for inspection.
            for job_id in own:
                request("DELETE", f"/v1/jobs/{job_id}")


if __name__ == "__main__":
    main()
