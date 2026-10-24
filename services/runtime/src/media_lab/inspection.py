"""Reduced, ephemeral inspection. Never writes previews into the library."""
import base64
import io
import json
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from .creative import media_probe, audio_analysis


def inspect_media(artifacts, uri: str, sha256: str) -> dict:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
        raise ValueError("SHA-256 required")
    path = artifacts.resolve(uri, sha256)
    metadata = {}
    sidecar = path.with_name(path.name + ".json")
    if sidecar.is_file():
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    result = {"uri": uri, "sha256": sha256, "metadata": metadata}
    if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        data, mime, alpha = artifacts.review_preview(uri, sha256)
        with Image.open(path) as image:
            result.update(kind="image", width=image.width, height=image.height, alpha=alpha)
        result["preview"] = {"mime": mime, "base64": base64.b64encode(data).decode("ascii")}
        return result
    if path.suffix.lower() in {".flac", ".wav", ".mp3", ".opus", ".ogg"}:
        return {**result, "kind": "audio", "probe": media_probe(path), "analysis": audio_analysis(path),
                "note": "Technical analysis only; the external agent has not listened to the audio."}
    if path.suffix.lower() not in {".mp4", ".mkv", ".webm"}:
        raise ValueError("unsupported inspection format")
    probe = media_probe(path)
    # Legacy productions may have a longer audio track than video stream.
    timestamps = [round(probe.get("video_duration", probe["duration"]) * (i + .5) / 6, 3) for i in range(6)]
    sheet = Image.new("RGB", (768, 3 * 244), "#181818")
    draw = ImageDraw.Draw(sheet)
    try:
        with tempfile.TemporaryDirectory(prefix="media-lab-inspect-") as directory:
            for i, timestamp in enumerate(timestamps):
                frame = Path(directory) / f"frame-{i}.jpg"
                subprocess.run(["ffmpeg", "-v", "error", "-ss", str(timestamp), "-i", str(path),
                                "-frames:v", "1", "-vf", "scale=384:216:force_original_aspect_ratio=decrease",
                                "-y", str(frame)], check=True, capture_output=True, timeout=30)
                with Image.open(frame) as image:
                    x, y = i % 2 * 384, i // 2 * 244
                    sheet.paste(image, (x, y))
                    draw.text((x + 5, y + 219), f"Frame {i + 1} / {timestamp:.3f}s", fill="white")
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError("video inspection failed") from exc
    stream = io.BytesIO()
    sheet.save(stream, "JPEG", quality=78)
    return {**result, "kind": "video", "probe": probe, "timestamps": timestamps,
            "preview": {"mime": "image/jpeg", "base64": base64.b64encode(stream.getvalue()).decode("ascii")}}
