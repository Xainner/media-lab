from __future__ import annotations

import hashlib
import io
import json
import re
import time
import uuid
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageStat


SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
MEDIA_TYPES = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/flac": "flac",
               "audio/mpeg": "mp3", "audio/ogg": "opus", "audio/opus": "opus", "video/webm": "webm", "video/mp4": "mp4", "video/x-matroska": "mkv"}


class ArtifactStore:
    def __init__(self, root: Path, max_bytes: int, max_pixels: int):
        self.root = root
        self.max_bytes = max_bytes
        self.max_pixels = max_pixels
        root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _session(value: str) -> str:
        if not SAFE_ID.fullmatch(value):
            raise ValueError("invalid session id")
        return value

    def _validate_image(self, data: bytes) -> Image.Image:
        if not data or len(data) > self.max_bytes:
            raise ValueError("image is empty or exceeds upload limit")
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception as exc:
            raise ValueError("invalid image") from exc
        if image.width * image.height > self.max_pixels:
            raise ValueError("image dimensions exceed pixel limit")
        return image

    @staticmethod
    def _has_meaningful_alpha(image: Image.Image) -> bool:
        return "A" in image.getbands() and image.getchannel("A").getextrema()[0] < 255

    def put_upload(self, session_id: str, data: bytes, content_type: str) -> dict:
        session_id = self._session(session_id)
        if content_type not in ALLOWED_TYPES:
            raise ValueError("unsupported image type")
        image = self._validate_image(data)
        has_alpha = self._has_meaningful_alpha(image)
        image = image.convert("RGBA" if has_alpha else "RGB")
        folder = self.root / session_id / "references"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex[:12]}.png"
        path = folder / name
        image.save(path, "PNG")
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        uri = f"artifact://{session_id}/references/{name}"
        self._sidecar(path, {"uri": uri, "sha256": sha, "kind": "reference", "created_at": time.time()})
        return {"uri": uri, "sha256": sha, "content_type": "image/png",
                "width": image.width, "height": image.height, "has_alpha": has_alpha}

    def import_image(self, session_id: str, data: bytes, provenance: dict) -> dict:
        session_id = self._session(session_id)
        image = self._validate_image(data)
        has_alpha = self._has_meaningful_alpha(image)
        image = image.convert("RGBA" if has_alpha else "RGB")
        folder = self.root / session_id / "images"
        folder.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex[:12]}.png"
        path = folder / name
        image.save(path, "PNG")
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        uri = f"artifact://{session_id}/images/{name}"
        meta = {**provenance, "uri": uri, "sha256": sha, "content_type": "image/png",
                "width": image.width, "height": image.height, "has_alpha": has_alpha,
                "created_at": time.time()}
        self._sidecar(path, meta)
        return {"uri": uri, "sha256": sha, "content_type": "image/png",
                "kind": "image", "width": image.width, "height": image.height,
                "has_alpha": has_alpha, "user_visible": True, "model_visible": True}

    def put_media(self, session_id: str, data: bytes | Path, content_type: str,
                  kind: str = "sources", provenance: dict | None = None) -> dict:
        session_id = self._session(session_id)
        if kind not in {"sources", "songs", "videos", "productions"}:
            raise ValueError("invalid media kind")
        extension = MEDIA_TYPES.get(content_type)
        if not extension:
            raise ValueError("unsupported media type")
        size = data.stat().st_size if isinstance(data, Path) else len(data)
        limit = 500 * 1024 * 1024 if kind == "sources" else 5 * 1024 * 1024 * 1024
        if not size or size > limit:
            raise ValueError("media is empty or exceeds its size limit")
        folder = self.root / session_id / kind
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid.uuid4().hex[:12]}.{extension}"
        digest = hashlib.sha256()
        if isinstance(data, Path):
            with data.open("rb") as source, path.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                    digest.update(chunk)
        else:
            path.write_bytes(data)
            digest.update(data)
        sha = digest.hexdigest()
        uri = f"artifact://{session_id}/{kind}/{path.name}"
        meta = {**(provenance or {}), "uri": uri, "sha256": sha, "kind": kind,
                "content_type": content_type, "created_at": time.time(), "size": size}
        self._sidecar(path, meta)
        return meta

    def provenance(self, uri: str, sha256: str | None = None) -> dict:
        """Recorded metadata of an (owned) artifact; empty when it has none."""
        path = self.resolve(uri, sha256)
        try:
            return json.loads(path.with_name(path.name + ".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _sidecar(path: Path, data: dict) -> None:
        path.with_name(path.name + ".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def resolve(self, uri: str, sha256: str | None = None) -> Path:
        if not uri.startswith("artifact://"):
            raise ValueError("invalid artifact uri")
        parts = uri.removeprefix("artifact://").split("/")
        if len(parts) != 3 or parts[1] not in {"images", "references", "sources", "songs", "videos", "productions"}:
            raise ValueError("invalid artifact uri")
        session = self._session(parts[0])
        name = Path(parts[2]).name
        if name != parts[2]:
            raise ValueError("invalid artifact name")
        path = (self.root / session / parts[1] / name).resolve()
        expected_root = self.root.resolve()
        if expected_root not in path.parents or not path.is_file():
            raise ValueError("artifact not found")
        if sha256:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual.lower() != sha256.lower():
                raise ValueError("artifact checksum mismatch")
        return path

    def review_preview(self, uri: str, sha256: str, max_side: int = 768) -> tuple[bytes, str, dict]:
        path = self.resolve(uri, sha256)
        image = Image.open(path)
        image.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        if self._has_meaningful_alpha(image):
            rgba = image.convert("RGBA")
            alpha = rgba.getchannel("A")
            extrema = alpha.getextrema()
            mean = ImageStat.Stat(alpha).mean[0]
            rgba.save(buf, "PNG", optimize=True)
            stats = {"has_alpha": True, "alpha_min": extrema[0], "alpha_max": extrema[1],
                     "alpha_mean": round(mean, 2)}
            return buf.getvalue(), "image/png", stats
        image.convert("RGB").save(buf, "JPEG", quality=78, optimize=True)
        return buf.getvalue(), "image/jpeg", {"has_alpha": False}

    def export_image(self, uri: str, sha256: str, output_format: str,
                     quality: int = 90, background: str = "#ffffff") -> tuple[bytes, str]:
        path = self.resolve(uri, sha256)
        if output_format == "png":
            return path.read_bytes(), "image/png"

        image = Image.open(path)
        image.load()
        stream = io.BytesIO()
        if output_format == "jpeg":
            if self._has_meaningful_alpha(image):
                rgba = image.convert("RGBA")
                rgb = tuple(int(background[i:i + 2], 16) for i in (1, 3, 5))
                canvas = Image.new("RGBA", rgba.size, (*rgb, 255))
                canvas.alpha_composite(rgba)
                image = canvas.convert("RGB")
            else:
                image = image.convert("RGB")
            image.save(stream, "JPEG", quality=quality, optimize=True)
            return stream.getvalue(), "image/jpeg"
        if output_format == "webp":
            mode = "RGBA" if self._has_meaningful_alpha(image) else "RGB"
            image.convert(mode).save(stream, "WEBP", quality=quality, method=6)
            return stream.getvalue(), "image/webp"
        raise ValueError("unsupported export format")

    def delete_image(self, uri: str, sha256: str) -> None:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            raise ValueError("valid artifact checksum required")
        if not uri.startswith("artifact://") or "/images/" not in uri:
            raise ValueError("only gallery images can be deleted")
        path = self.resolve(uri, sha256)
        sidecar = path.with_name(path.name + ".json")
        if not sidecar.is_file():
            raise ValueError("gallery metadata not found")
        trash = self.root / ".trash" / uuid.uuid4().hex
        trash.mkdir(parents=True)
        try:
            sidecar.rename(trash / sidecar.name)
            try:
                path.rename(trash / path.name)
            except OSError:
                (trash / sidecar.name).rename(sidecar)
                raise
        except BaseException:
            trash.rmdir()
            raise

    def gallery(self, limit: int = 100) -> list[dict]:
        items: list[dict] = []
        for sidecar in self.root.glob("*/images/*.json"):
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                data["created_at"] = data.get("created_at", sidecar.stat().st_mtime)
                items.append(data)
            except Exception:
                continue
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items[: max(1, min(limit, 500))]

    def library(self, limit: int = 100) -> list[dict]:
        return self.search_library()[:max(1, min(limit, 500))]

    def search_library(self, query: str = "", kind_filter: str = "") -> list[dict]:
        items = []
        for kind in ("images", "songs", "videos", "productions", "sources", "references"):
            if kind_filter and kind_filter != kind:
                continue
            for sidecar in self.root.glob(f"*/{kind}/*.json"):
                try:
                    data = json.loads(sidecar.read_text(encoding="utf-8"))
                    if query.casefold() in json.dumps(data, ensure_ascii=False).casefold():
                        data["kind"] = kind
                        data["created_at"] = data.get("created_at", sidecar.stat().st_mtime)
                        items.append(data)
                except (OSError, ValueError):
                    continue
        items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return items
