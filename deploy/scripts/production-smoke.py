"""Exercise the Director API with a complete ten-second song and reusable clips."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from pathlib import Path

import httpx

from media_lab.artifacts import ArtifactStore


def encoded_audio_hash(path: Path) -> str:
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path),
        "-map", "0:a:0", "-c:a", "copy", "-f", "hash", "-hash", "SHA256", "-"],
        capture_output=True, text=True, check=True)
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true", help="Generate a new Qwen image and H3 scene")
    parser.add_argument("--full", action="store_true", help="Assemble a 30-second song with six scenes")
    args = parser.parse_args()
    store = ArtifactStore(Path("/data/artifacts"), 20 * 1024 * 1024, 50_000_000)
    song_path = Path("/smoke/song.flac")
    if args.generate:
        song_path = Path("/smoke/song-short.flac")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "/smoke/song.flac",
            "-t", "5", "-c:a", "flac", str(song_path)], check=True)
    elif args.full:
        song_path = Path("/smoke/song-full.flac")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-stream_loop", "2",
            "-i", "/smoke/song.flac", "-t", "30", "-c:a", "flac", str(song_path)], check=True)
    video_path = Path("/smoke/h3-t2v.mp4")
    song = store.put_media("sess_director_smoke", song_path, "audio/flac", "sources")
    video = store.put_media("sess_director_smoke", video_path, "video/mp4", "videos")
    duration = float(json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "json", str(song_path)], capture_output=True,
        text=True, check=True).stdout)["format"]["duration"])
    scenes = [{"start": i * 5, "end": min(duration, (i + 1) * 5),
               "image_prompt": "red ceramic fox", "video_prompt": "subtle camera pan",
               **({} if args.generate else {"video": {"uri": video["uri"], "sha256": video["sha256"]}})}
              for i in range(math.ceil(duration / 5))]
    base = "http://127.0.0.1:8399"
    with httpx.Client(timeout=30) as client:
        for _ in range(30):
            try:
                if client.get(base + "/v1/health").status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(1)
        accepted = client.post(base + "/v1/jobs/production", json={
            "title": "Director smoke", "song": {"uri": song["uri"], "sha256": song["sha256"]},
            "brief": "Ceramic fox on a blue table", "scenes": scenes,
            "session_id": "sess_director_smoke"}).json()
        job_id = accepted["job_id"]
        for _ in range(900):
            job = client.get(base + f"/v1/jobs/{job_id}").json()
            if job["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(1)
        else:
            raise TimeoutError(job_id)
    if job["status"] != "completed":
        raise RuntimeError(json.dumps(job))
    preview, master = job["result"]["media"]
    master_path = store.resolve(master["uri"], master["sha256"])
    source_hash = encoded_audio_hash(song_path)
    master_hash = encoded_audio_hash(master_path)
    if source_hash != master_hash:
        raise RuntimeError(f"audio stream differs: {source_hash} != {master_hash}")
    print(json.dumps({"job_id": job_id, "status": job["status"],
                      "preview": preview["uri"], "master": master["uri"],
                      "audio_stream_sha256": source_hash, "scenes": len(job["result"]["scenes"])}))


if __name__ == "__main__":
    main()
