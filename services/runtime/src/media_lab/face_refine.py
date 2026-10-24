"""Face refine for video: follow one face with a smoothed square window, re-diffuse that window with
H3 at a partial noise level and paste it back with a feathered oval. Pure helpers; the GPU work is
in creative.py (detection and refine graphs) so this module stays testable without ComfyUI."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

FACE_DETECTOR = "mediapipe_face_fp32.safetensors"
FACE_DETECTOR_SHA256 = "a98c4806081d40eba35102a0f6dc0000c2e1388b72cf24e691703d0605bd888a"
FACE_CROP = 512        # H3 renders the face window at this square size
FACE_MARGIN = 2.4      # window side = this × the largest face side seen in the clip
FACE_SMOOTH = 9        # moving-average window (frames) for the window centre
FACE_MIN_SIDE = 32     # faces smaller than this (px) are too small to refine usefully


def parse_boxes(text: str) -> list[dict | None]:
    """PreviewAny text of MediaPipeFaceLandmarker boxes → one box (largest face) or None per frame."""
    frames = json.loads(text)
    out = []
    for faces in frames:
        faces = [f for f in faces or [] if f.get("width", 0) > 0 and f.get("height", 0) > 0]
        out.append(max(faces, key=lambda f: f["width"] * f["height"]) if faces else None)
    return out


def drop_outliers(boxes: list[dict | None], span: int = 12, ratio: float = 1.5) -> list[dict | None]:
    """Detectors misfire for a few frames when a head turns (boxes 3-4× the real face). Drop boxes
    whose size strays more than `ratio` from the median of their ±`span` neighbours."""
    sizes = [max(b["width"], b["height"]) if b else None for b in boxes]
    kept = []
    for i, box in enumerate(boxes):
        near = sorted(s for s in sizes[max(0, i - span):i + span + 1] if s)
        if box and near:
            median = near[len(near) // 2]
            box = box if median / ratio <= sizes[i] <= median * ratio else None
        kept.append(box)
    return kept


def face_windows(boxes: list[dict | None], width: int, height: int) -> list[tuple[int, int, int]]:
    """One (left, top, side) square per frame around a smoothed track of the face: the centre is
    averaged over FACE_SMOOTH frames and the side (face × FACE_MARGIN) over three times that, so the
    window glides and zooms gently instead of jittering. Frames without a face hold the nearest one."""
    boxes = drop_outliers(boxes)
    found = [i for i, b in enumerate(boxes) if b]
    if not found:
        raise ValueError("No se detectó ninguna cara en el vídeo")
    if max(max(boxes[i]["width"], boxes[i]["height"]) for i in found) < FACE_MIN_SIDE:
        raise ValueError("La cara es demasiado pequeña para refinarla; escala el vídeo primero")
    track = []
    for i, box in enumerate(boxes):
        box = box or boxes[min(found, key=lambda j: abs(j - i))]
        track.append((box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, max(box["width"], box["height"])))

    def mean(i: int, half: int, key: int) -> float:
        near = track[max(0, i - half):i + half + 1]
        return sum(t[key] for t in near) / len(near)

    windows = []
    for i in range(len(track)):
        side = min(width, height, max(64, round(mean(i, FACE_SMOOTH * 3 // 2, 2) * FACE_MARGIN / 2) * 2))
        cx, cy = mean(i, FACE_SMOOTH // 2, 0), mean(i, FACE_SMOOTH // 2, 1)
        left = int(round(min(max(cx - side / 2, 0), width - side)))
        top = int(round(min(max(cy - side / 2, 0), height - side)))
        windows.append((left, top, side))
    return windows


def crop_frames(frames: list[Path], windows: list[tuple[int, int, int]], out: Path, size: int = FACE_CROP) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, (frame, (left, top, side)) in enumerate(zip(frames, windows)):
        with Image.open(frame) as image:
            crop = image.convert("RGB").crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
        path = out / f"{index:05d}.png"
        crop.save(path)
        paths.append(path)
    return paths


def oval_mask(side: int) -> Image.Image:
    """Feathered oval: full strength over the face, fading to zero well inside the window edge."""
    mask = Image.new("L", (side, side), 0)
    inset = side * 0.14
    ImageDraw.Draw(mask).ellipse((inset, inset * 0.8, side - inset, side - inset * 0.8), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(side * 0.07))


def paste_frames(frames: list[Path], refined: list[Path], windows: list[tuple[int, int, int]], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    masks: dict[int, Image.Image] = {}
    paths = []
    for index, (frame, face, (left, top, side)) in enumerate(zip(frames, refined, windows)):
        mask = masks.setdefault(side, oval_mask(side))
        with Image.open(frame) as base, Image.open(face) as patch:
            base = base.convert("RGB")
            base.paste(patch.convert("RGB").resize((side, side), Image.LANCZOS), (left, top), mask)
        path = out / f"{index:05d}.png"
        base.save(path)
        paths.append(path)
    return paths
