"""Run one real workflow against a staged ComfyUI without touching the live runtime DB."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from media_lab.comfy import ComfyClient
from media_lab.creative_workflows import h3_workflow, yue2_workflow
from media_lab.workflows import edit_workflow, t2i_workflow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["qwen", "qwen-edit", "song", "song-abc", "song-plan", "song-cover",
                                          "h3-t2v", "h3-i2v", "h3-r2v"])
    parser.add_argument("--url", default="http://127.0.0.1:8389")
    parser.add_argument("--out", type=Path, default=Path("/smoke"))
    parser.add_argument("--width", type=int, default=480)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--steps", type=int, default=8)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    client = ComfyClient(args.url, 7200)
    nodes = client.object_info()
    required = {"SaveVideo", "SaveAudioAdvanced", "MiniMaxH3ImageToVideo",
                "MiniMaxH3ReferenceToVideo", "YuE2GenerateMusic", "YuE2GenerateABC",
                "SheetSage2AudioToABC", "TextEncodeQwenImage21"}
    missing = required - set(nodes)
    if missing:
        raise RuntimeError(f"missing nodes: {sorted(missing)}")
    image_path = args.out / "qwen.png"
    song_path = args.out / "song.flac"
    seed = 12345
    if args.kind == "qwen":
        graph, output, extension = t2i_workflow("Small red ceramic fox on a pale blue table", 512, 512, seed, 4), "images", "png"
    elif args.kind == "qwen-edit":
        reference = client.upload_image(image_path, "smoke")
        graph, output, extension = edit_workflow("Make the ceramic fox green", [reference], seed, 4, 512), "images", "png"
    elif args.kind.startswith("song"):
        abc = "X:1\nT:Test\nM:4/4\nL:1/4\nQ:1/4=100\nK:C\nC D E G|G E D C|" if args.kind == "song-abc" else ""
        source = client.upload_audio(song_path, "smoke") if args.kind == "song-cover" else None
        graph = yue2_workflow("Spanish indie pop, warm female vocal, acoustic guitar, 100 BPM",
                              "[Verse]\nLuz de la mañana", "melody" if args.kind == "song-cover" else "full" if abc or args.kind == "song-plan" else "direct",
                              abc, 10, 4, seed, source)
        output, extension = "audio", "flac"
    else:
        first = client.upload_image(image_path, "smoke") if args.kind != "h3-t2v" else None
        mode = {"h3-t2v": "t2v", "h3-i2v": "i2v", "h3-r2v": "r2v"}[args.kind]
        graph = h3_workflow("A red ceramic fox on a blue table, subtle camera pan, soft room ambience",
                            mode, args.width, args.height, 5, args.steps, seed, first,
                            references=[first] if mode == "r2v" else None)
        output, extension = "videos", "mp4"
    started = time.monotonic()
    last = None
    def progress(value: dict) -> None:
        nonlocal last
        current = (value.get("node"), value.get("step"), value.get("steps"))
        if current != last:
            print("progress", current, flush=True)
            last = current
    raw, backend = client.run_output(graph, output, progress, lambda: False)
    path = args.out / f"{args.kind}.{extension}"
    path.write_bytes(raw)
    print(json.dumps({"kind": args.kind, "seconds": round(time.monotonic() - started, 1),
                      "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                      "path": str(path), "backend": backend}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
