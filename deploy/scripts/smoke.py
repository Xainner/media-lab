from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://192.0.2.10:8390"
TERMINAL = {"completed", "failed", "cancelled", "blocked_gpu", "interrupted"}


def request(method: str, path: str, body=None, timeout: int = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def wait_job(job_id: str, label: str, timeout: int = 1200):
    started = time.monotonic()
    deadline = started + timeout
    last = None
    while time.monotonic() < deadline:
        job = request("GET", f"/v1/jobs/{job_id}")
        progress = job.get("progress") or {}
        current = (job["status"], progress.get("step"), progress.get("steps"))
        if current != last:
            print(f"[{label}] {current[0]} {current[1] or 0}/{current[2] or 0}", flush=True)
            last = current
        if job["status"] in TERMINAL:
            job["wall_seconds"] = round(time.monotonic() - started, 2)
            return job
        time.sleep(2)
    raise TimeoutError(f"{label} timed out")


def run(path: str, body: dict, label: str):
    accepted = request("POST", path, body)
    job = wait_job(accepted["job_id"], label)
    if job["status"] != "completed":
        raise RuntimeError(f"{label}: {job['status']}: {job.get('error')}")
    return job


def alpha_stats(media: dict):
    query = urllib.parse.urlencode({"uri": media["uri"], "sha256": media["sha256"]})
    with urllib.request.urlopen(BASE + "/v1/review?" + query, timeout=30) as response:
        response.read()
        return json.loads(response.headers.get("X-Alpha-Stats", "{}"))


def swap_used_kib():
    try:
        values = {}
        with open("/proc/meminfo", encoding="utf-8") as stream:
            for line in stream:
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0])
        return values["SwapTotal"] - values["SwapFree"]
    except (OSError, KeyError, ValueError):
        return None


def gate_2k():
    capabilities = request("GET", "/v1/capabilities")
    if not capabilities.get("two_k_enabled"):
        raise RuntimeError("Set ENABLE_2K=true temporarily before running the 2K gate")
    swap_before = swap_used_kib()
    summary = {"t2i_seconds": []}
    for index in range(2):
        job = run("/v1/jobs/generate", {
            "prompt": f"2K validation still life, cyan glass and charcoal, run {index + 1}",
            "aspect_ratio": "1:1" if index == 0 else "16:9", "quality": "quality",
            "transparent": False, "resolution_tier": "2k", "model_precision": "int8",
        }, f"2k-t2i-{index + 1}")
        summary["t2i_seconds"].append(job["wall_seconds"])
    swap_after = swap_used_kib()
    if swap_before is not None and swap_after is not None:
        delta = max(0, swap_after - swap_before)
        summary["swap_growth_kib"] = delta
        if delta > 2 * 1024 * 1024:
            raise RuntimeError(f"2K gate caused extreme swap growth: {delta} KiB")
    print(json.dumps(summary, indent=2))
    return 0


def gate_bf16():
    capabilities = request("GET", "/v1/capabilities")
    if not capabilities.get("model_precisions", {}).get("bf16"):
        raise RuntimeError("Set ENABLE_BF16=true only after checksum verification")
    summary = {}
    for precision in ("int8", "bf16"):
        job = run("/v1/jobs/generate", {
            "prompt": "A studio portrait of a ceramic fox with finely textured fur, warm rim light",
            "aspect_ratio": "1:1", "quality": "quality", "seed": 21092026,
            "resolution_tier": "1mp", "model_precision": precision,
        }, f"precision-{precision}")
        summary[precision] = {"seconds": job["wall_seconds"],
                              "sha256": job["result"]["media"][0]["sha256"]}
    print(json.dumps(summary, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="run only the 1024px T2I gate")
    parser.add_argument("--two-k", action="store_true", help="run two 40-step T2I jobs at 2K; editing remains disabled")
    parser.add_argument("--bf16", action="store_true", help="compare INT8 and BF16 with identical 1 MP inputs")
    args = parser.parse_args()
    doctor = request("POST", "/v1/doctor")
    if not doctor.get("ok"):
        print(json.dumps(doctor, indent=2), file=sys.stderr)
        return 2
    if args.two_k:
        return gate_2k()
    if args.bf16:
        return gate_bf16()

    summary = {}
    t2i = run("/v1/jobs/generate", {
        "prompt": "A translucent cyan glass cube on a matte charcoal surface, studio light",
        "aspect_ratio": "1:1", "quality": "draft", "transparent": False,
    }, "t2i-1024")
    summary["t2i_1024_seconds"] = t2i["wall_seconds"]
    if args.quick:
        print(json.dumps(summary, indent=2))
        return 0

    first = t2i["result"]["media"][0]
    edit = run("/v1/jobs/edit", {
        "prompt": "Keep the cube unchanged and add a small warm amber light on its right side.",
        "references": [{"uri": first["uri"], "sha256": first["sha256"]}],
        "quality": "draft", "transparent": False, "resolution": 0,
    }, "edit-one-reference")
    summary["edit_one_seconds"] = edit["wall_seconds"]

    second = edit["result"]["media"][0]
    composition = run("/v1/jobs/edit", {
        "prompt": "Create one balanced product composition using <image1> as the target and <image2> as a visual reference.",
        "references": [
            {"uri": first["uri"], "sha256": first["sha256"]},
            {"uri": second["uri"], "sha256": second["sha256"]},
        ],
        "quality": "draft", "transparent": False, "resolution": 0,
    }, "composition-two-references")
    summary["composition_seconds"] = composition["wall_seconds"]

    rgba = run("/v1/jobs/generate", {
        "prompt": "A single cyan glass cube isolated as a clean product cutout",
        "aspect_ratio": "1:1", "quality": "draft", "transparent": True,
    }, "rgba")
    stats = alpha_stats(rgba["result"]["media"][0])
    summary["rgba_seconds"] = rgba["wall_seconds"]
    summary["alpha"] = stats
    if not stats.get("has_alpha") or stats.get("alpha_min", 255) >= 255:
        raise RuntimeError(f"RGBA gate failed: {stats}")

    accepted = request("POST", "/v1/jobs/generate", {
        "prompt": "Cancellation control image", "aspect_ratio": "1:1", "quality": "quality",
    })
    request("DELETE", f"/v1/jobs/{accepted['job_id']}")
    cancelled = wait_job(accepted["job_id"], "cancel")
    if cancelled["status"] != "cancelled":
        raise RuntimeError(f"cancellation gate failed: {cancelled['status']}")
    summary["cancel"] = "ok"

    recovery = run("/v1/jobs/generate", {
        "prompt": "A minimal white ceramic sphere on a charcoal background",
        "aspect_ratio": "1:1", "quality": "draft", "transparent": False,
    }, "post-cancel-recovery")
    summary["post_cancel_seconds"] = recovery["wall_seconds"]
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
