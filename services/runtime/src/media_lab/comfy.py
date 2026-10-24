from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode, urlparse

import httpx
import websocket


ProgressCallback = Callable[[dict], None]
CancelCallback = Callable[[], bool]
PreviewCallback = Callable[[bytes, str], None]

# ComfyUI binary websocket frame: 4-byte event type + 4-byte image type + image bytes.
PREVIEW_IMAGE_EVENT = 1
PREVIEW_MIME = {1: "image/jpeg", 2: "image/png"}


def parse_preview_frame(raw: bytes) -> tuple[bytes, str] | None:
    if len(raw) <= 8 or int.from_bytes(raw[:4], "big") != PREVIEW_IMAGE_EVENT:
        return None
    mime = PREVIEW_MIME.get(int.from_bytes(raw[4:8], "big"))
    return (raw[8:], mime) if mime else None


class ComfyError(RuntimeError):
    pass


class ComfyClient:
    def __init__(self, base_url: str, timeout: int):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict:
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.base_url}/system_stats")
                response.raise_for_status()
                data = response.json()
            return {"ok": True, "system": data}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def queue(self) -> dict:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{self.base_url}/queue")
            response.raise_for_status()
            return response.json()

    def object_info(self) -> dict:
        with httpx.Client(timeout=20) as client:
            response = client.get(f"{self.base_url}/object_info")
            response.raise_for_status()
            return response.json()

    def upload_image(self, path: Path, prefix: str) -> str:
        filename = f"{prefix}_{path.name}"
        with path.open("rb") as handle, httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.base_url}/upload/image",
                data={"overwrite": "true", "type": "input"},
                files={"image": (filename, handle, "image/png")},
            )
            response.raise_for_status()
            data = response.json()
        subfolder = data.get("subfolder") or ""
        return f"{subfolder}/{data.get('name', filename)}".lstrip("/")

    def upload_audio(self, path: Path, prefix: str) -> str:
        filename = f"{prefix}_{path.name}"
        with path.open("rb") as handle, httpx.Client(timeout=120) as client:
            response = client.post(f"{self.base_url}/upload/image",
                data={"overwrite": "true", "type": "input"},
                files={"image": (filename, handle, __import__("mimetypes").guess_type(path.name)[0] or "application/octet-stream")})
            response.raise_for_status()
            data = response.json()
        return f"{data.get('subfolder') or ''}/{data.get('name', filename)}".lstrip("/")

    def run(self, workflow: dict, progress: ProgressCallback,
            cancelled: CancelCallback, preview: PreviewCallback | None = None) -> tuple[bytes, dict]:
        return self.run_output(workflow, "images", progress, cancelled, preview)

    def run_output(self, workflow: dict, output_kind: str, progress: ProgressCallback,
                   cancelled: CancelCallback, preview: PreviewCallback | None = None) -> tuple[bytes, dict]:
        history, prompt_id = self._execute(workflow, progress, cancelled, preview)
        image_info = self._first_output(history, prompt_id, output_kind)
        with httpx.Client(timeout=120) as client:
            response = client.get(f"{self.base_url}/view", params=image_info)
            response.raise_for_status()
            return response.content, {"prompt_id": prompt_id, **image_info}

    def run_outputs(self, workflow: dict, nodes: list[str], output_kind: str, progress: ProgressCallback,
                    cancelled: CancelCallback) -> tuple[dict[str, bytes], dict]:
        """Run a graph with several save nodes and fetch the first file each of them wrote."""
        history, prompt_id = self._execute(workflow, progress, cancelled, None)
        outputs = (history.get(prompt_id) or {}).get("outputs") or {}
        files = {}
        with httpx.Client(timeout=120) as client:
            for node in nodes:
                media = [item for item in (outputs.get(node) or {}).get(output_kind) or []
                         if item.get("type", "output") != "input"]
                if not media:
                    raise ComfyError(f"ComfyUI completed without {output_kind} from {node}")
                response = client.get(f"{self.base_url}/view", params={
                    "filename": media[0]["filename"], "subfolder": media[0].get("subfolder", ""),
                    "type": media[0].get("type", "output")})
                response.raise_for_status()
                files[node] = response.content
        return files, {"prompt_id": prompt_id}

    def run_text(self, workflow: dict, node: str, progress: ProgressCallback, cancelled: CancelCallback) -> str:
        """Run a graph whose result is the text of one PreviewAny node (e.g. detection boxes)."""
        history, prompt_id = self._execute(workflow, progress, cancelled, None)
        text = ((history.get(prompt_id) or {}).get("outputs") or {}).get(node, {}).get("text") or []
        if not text:
            raise ComfyError(f"ComfyUI completed without text from {node}")
        return text[0]

    def output_text(self, prompt_id: str, node: str) -> str:
        """Text a PreviewAny node showed in a finished run (e.g. the caption a prompt upsampler wrote); '' if none."""
        try:
            text = (self.history(prompt_id).get("outputs") or {}).get(node, {}).get("text") or []
        except (httpx.HTTPError, ValueError):
            return ""
        return text[0] if text else ""

    def _execute(self, workflow: dict, progress: ProgressCallback, cancelled: CancelCallback,
                 preview: PreviewCallback | None) -> tuple[dict, str]:
        client_id = uuid.uuid4().hex
        ws = None
        try:
            ws = websocket.create_connection(self._ws_url(client_id), timeout=5)
        except Exception:
            ws = None
        started = time.monotonic()
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": workflow, "client_id": client_id},
                )
                if response.status_code >= 400:
                    raise ComfyError(f"ComfyUI rejected workflow: {response.text[:1000]}")
                prompt_id = response.json()["prompt_id"]
            progress({"pct": 0, "step": 0, "steps": 0, "node": "submitted",
                      "prompt_id": prompt_id})
            if ws is not None:
                self._watch_ws(ws, prompt_id, started, progress, cancelled, preview)
            return self._wait_history(prompt_id, started, progress, cancelled), prompt_id
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    def _watch_ws(self, ws, prompt_id: str, started: float, progress: ProgressCallback,
                  cancelled: CancelCallback, preview: PreviewCallback | None = None) -> None:
        ws.settimeout(1)
        while time.monotonic() - started < self.timeout:
            if cancelled():
                self.interrupt()
                raise ComfyError("cancelled")
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception:
                return
            if not isinstance(raw, str):
                frame = parse_preview_frame(raw) if preview and isinstance(raw, bytes) else None
                if frame:
                    preview(*frame)
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            data = message.get("data") or {}
            if data.get("prompt_id") not in (None, prompt_id):
                continue
            kind = message.get("type")
            if kind == "progress":
                value, maximum = int(data.get("value", 0)), int(data.get("max", 0))
                progress({"pct": round(value * 100 / maximum) if maximum else 0,
                          "step": value, "steps": maximum, "node": data.get("node", "")})
            elif kind == "executing":
                node = data.get("node")
                progress({"pct": 100 if node is None else 0, "step": 0, "steps": 0,
                          "node": node or "done"})
                if node is None:
                    return
            elif kind in {"execution_error", "execution_interrupted"}:
                raise ComfyError(data.get("exception_message") or kind)

    def _wait_history(self, prompt_id: str, started: float, progress: ProgressCallback,
                      cancelled: CancelCallback) -> dict:
        while time.monotonic() - started < self.timeout:
            if cancelled():
                self.interrupt()
                raise ComfyError("cancelled")
            try:
                with httpx.Client(timeout=10) as client:
                    response = client.get(f"{self.base_url}/history/{prompt_id}")
                    response.raise_for_status()
                    history = response.json()
                if prompt_id in history:
                    entry = history[prompt_id]
                    status = entry.get("status") or {}
                    if status.get("status_str") == "error":
                        raise ComfyError("ComfyUI execution failed")
                    return history
            except ComfyError:
                raise
            except Exception:
                pass
            time.sleep(1)
        self.interrupt()
        raise ComfyError(f"generation timed out after {self.timeout}s")

    def history(self, prompt_id: str) -> dict:
        with httpx.Client(timeout=20) as client:
            response = client.get(f"{self.base_url}/history/{prompt_id}")
            response.raise_for_status()
            return response.json().get(prompt_id) or {}

    @staticmethod
    def _first_image(history: dict, prompt_id: str) -> dict:
        return ComfyClient._first_output(history, prompt_id, "images")

    @staticmethod
    def _first_output(history: dict, prompt_id: str, kind: str) -> dict:
        outputs = (history.get(prompt_id) or {}).get("outputs") or {}
        for node in outputs.values():
            media = node.get(kind) or []
            if not media and kind == "videos":
                media = [item for item in (node.get("images") or [])
                         if str(item.get("filename", "")).lower().endswith((".mp4", ".mkv", ".webm"))]
            # LoadVideo/LoadImage previews list the graph's own input files; never return those.
            media = [item for item in media if item.get("type", "output") != "input"]
            if media:
                item = media[0]
                return {"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                        "type": item.get("type", "output")}
        raise ComfyError(f"ComfyUI completed without an output in {kind}")

    def interrupt(self) -> None:
        try:
            with httpx.Client(timeout=5) as client:
                client.post(f"{self.base_url}/interrupt")
        except Exception:
            pass

    def free(self) -> None:
        try:
            with httpx.Client(timeout=15) as client:
                client.post(f"{self.base_url}/free", json={"unload_models": True, "free_memory": True})
        except Exception:
            pass

    def _ws_url(self, client_id: str) -> str:
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{scheme}://{parsed.netloc}/ws?{urlencode({'clientId': client_id})}"
