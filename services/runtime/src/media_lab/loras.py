"""Per-account LoRA library.

A Hugging Face or Civitai link becomes a pinned, checked .safetensors in LORA_ROOT/loras, which
ComfyUI reads read-only through extra_model_paths (media_lab_loras). Files are named by content hash,
so two accounts adding the same LoRA share one file; the rows stay private to each account.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import struct
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import httpx

from .security import owner

LORA_BASES = {"qwen": "Qwen-Image 2.1 · imagen", "h3": "MiniMax H3 · vídeo"}
LORA_MAX_BYTES = 2 * 1024 ** 3
LORA_LIMIT = 30
LORA_USE_MAX = 4
FREE_SPACE = 20 * 1024 ** 3
HEADER_MAX = 64 * 1024 ** 2
_downloads = threading.BoundedSemaphore(2)
_LORA_TENSOR = re.compile(r"[._]lora[._](A|B|up|down)\.|\.lokr_w|\.hada_w")


def lora_root() -> Path | None:
    raw = os.environ.get("LORA_ROOT", "").strip()
    return Path(raw) if raw else None


def lora_file(sha256: str) -> str:
    return f"ml_{sha256[:24]}.safetensors"


def _secret(name: str) -> str:
    path = os.environ.get(f"{name}_FILE", "")
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8").strip()
    return os.environ.get(name, "").strip()


def parse_source(url: str) -> dict:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme != "https" or host not in {"huggingface.co", "hf.co", "civitai.com"}:
        raise ValueError("Pega un enlace https de Hugging Face o Civitai")
    parts = [p for p in parsed.path.split("/") if p]
    if host in {"huggingface.co", "hf.co"}:
        if len(parts) < 2 or parts[0] in {"datasets", "spaces", "api"}:
            raise ValueError("Enlace de Hugging Face no válido: usa el de un modelo o el de su archivo .safetensors")
        repo, revision, path = "/".join(parts[:2]), "main", ""
        if len(parts) >= 4 and parts[2] in {"blob", "resolve", "tree"}:
            revision, path = parts[3], "/".join(parts[4:])
        if (not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not re.fullmatch(r"[\w.-]{1,100}", revision)
                or ".." in path.split("/")):
            raise ValueError("Enlace de Hugging Face no válido")
        return {"site": "hf", "repo": repo, "revision": revision, "path": path}
    query = parse_qs(parsed.query)
    version = query.get("modelVersionId", [""])[0]
    model = parts[1] if len(parts) >= 2 and parts[0] == "models" else ""
    if parts[:3] == ["api", "download", "models"] and len(parts) >= 4:
        version, model = parts[3], ""
    if not (version.isdigit() or model.isdigit()):
        raise ValueError("Enlace de Civitai no válido: usa el de la página del modelo")
    return {"site": "civitai", "model": model if model.isdigit() else "", "version": version if version.isdigit() else ""}


def lora_base(header: dict) -> str:
    """Which Media Lab model a LoRA patches, from its tensor names and shapes."""
    tensors = {k: v for k, v in header.items() if k != "__metadata__" and isinstance(v, dict)}
    lora = {k: v for k, v in tensors.items() if _LORA_TENSOR.search(k)}
    if not lora:
        raise ValueError("Ese archivo no es un LoRA (no tiene capas lora_A/lora_B ni lora_up/lora_down)")
    dims = {d for v in lora.values() for d in v.get("shape") or [] if isinstance(d, int)}
    names = "\n".join(lora)
    if 5376 in dims and "qkv_proj" in names:
        return "h3"
    if re.search(r"transformer_blocks[._]\d+[._]", names):
        if 3072 in dims:
            raise ValueError("Es un LoRA de Qwen-Image 1 (o 2512); Media Lab usa Qwen-Image 2.1 y no son compatibles")
        if 4096 in dims:
            return "qwen"
    raise ValueError("LoRA no compatible: Media Lab acepta LoRAs de Qwen-Image 2.1 (imagen) y MiniMax H3 (vídeo)")


def inspect_lora(path: Path) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(8)
        if len(head) < 8:
            raise ValueError("No es un archivo .safetensors")
        length = struct.unpack("<Q", head)[0]
        if not 2 <= length <= min(HEADER_MAX, size - 8):
            raise ValueError("No es un archivo .safetensors válido")
        try:
            header = json.loads(handle.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("La cabecera del .safetensors está dañada") from exc
    if not isinstance(header, dict):
        raise ValueError("No es un archivo .safetensors válido")
    end = 0
    for key, value in header.items():
        if key == "__metadata__":
            continue
        offsets = value.get("data_offsets") if isinstance(value, dict) else None
        if not (isinstance(offsets, list) and len(offsets) == 2 and all(isinstance(o, int) for o in offsets)
                and 0 <= offsets[0] <= offsets[1]):
            raise ValueError("No es un archivo .safetensors válido")
        end = max(end, offsets[1])
    if 8 + length + end != size:
        raise ValueError("El .safetensors está incompleto o dañado")
    return lora_base(header)


def _get(client: httpx.Client, url: str, headers: dict, site: str) -> dict:
    response = client.get(url, headers=headers, follow_redirects=True)
    if response.status_code in {401, 403}:
        raise ValueError(f"{site} pide permiso para ese modelo" + (": falta configurar el token de Civitai" if site == "Civitai" and "Authorization" not in headers else ""))
    if response.status_code == 404:
        raise ValueError(f"{site} no encuentra ese modelo")
    response.raise_for_status()
    return response.json()


def resolve_source(source: dict, client: httpx.Client) -> dict:
    """Exact download URL pinned to a revision, plus what the site says about the file."""
    if source["site"] == "hf":
        token = _secret("HF_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        info = _get(client, f"https://huggingface.co/api/models/{source['repo']}/revision/{quote(source['revision'], safe='')}?blobs=true",
                    headers, "Hugging Face")
        files = {s["rfilename"]: s for s in info.get("siblings", []) if str(s.get("rfilename", "")).endswith(".safetensors")}
        path = source["path"]
        if path and not path.endswith(".safetensors"):
            raise ValueError("Solo se aceptan archivos .safetensors")
        if path and path not in files:
            raise ValueError("Ese archivo no está en el repositorio")
        if not path:
            if len(files) != 1:
                raise ValueError(f"El repositorio tiene {len(files)} archivos .safetensors: pega el enlace del archivo que quieres")
            path = next(iter(files))
        entry = files[path]
        return {"url": f"https://huggingface.co/{source['repo']}/resolve/{info['sha']}/{quote(path)}", "headers": headers,
                "name": Path(path).stem, "trigger": "", "revision": info["sha"],
                "sha256": ((entry.get("lfs") or {}).get("sha256") or "").lower() or None,
                "size": (entry.get("lfs") or {}).get("size") or entry.get("size") or 0,
                "page": f"https://huggingface.co/{source['repo']}", "hint": ""}
    token = _secret("CIVITAI_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if source["version"]:
        data = _get(client, f"https://civitai.com/api/v1/model-versions/{source['version']}", headers, "Civitai")
    else:
        model = _get(client, f"https://civitai.com/api/v1/models/{source['model']}", headers, "Civitai")
        if not model.get("modelVersions"):
            raise ValueError("Ese modelo de Civitai no tiene versiones")
        data = {**model["modelVersions"][0], "modelId": model.get("id"),
                "model": {"name": model.get("name"), "type": model.get("type"), "poi": model.get("poi")}}
    meta = data.get("model") or {}
    kind = str(meta.get("type") or "")
    if kind and kind.upper() not in {"LORA", "LOCON", "DORA"}:
        raise ValueError(f"Ese modelo de Civitai es {kind}, no un LoRA")
    if meta.get("poi"):
        raise ValueError("Civitai marca ese modelo como el parecido de una persona real; Media Lab no lo descarga")
    # Civitai names the base model; skip the download when it plainly is another family.
    hint = str(data.get("baseModel") or "")
    if hint and not re.search(r"qwen|minimax|h3|other", hint, re.I):
        raise ValueError(f"Ese LoRA es para {hint}; Media Lab acepta LoRAs de Qwen-Image 2.1 (imagen) y MiniMax H3 (vídeo)")
    files = [f for f in data.get("files") or [] if f.get("type") == "Model"
             and (f.get("metadata") or {}).get("format") == "SafeTensor"]
    chosen = next((f for f in files if f.get("primary")), files[0] if files else None)
    if not chosen:
        raise ValueError("Esa versión de Civitai no tiene un archivo .safetensors")
    name = " · ".join(str(v) for v in (meta.get("name"), data.get("name")) if v)
    return {"url": chosen["downloadUrl"], "headers": headers, "name": name or Path(chosen.get("name", "lora")).stem,
            "trigger": ", ".join(str(w).strip() for w in data.get("trainedWords") or [] if str(w).strip())[:300],
            "revision": str(data.get("id", "")), "sha256": str((chosen.get("hashes") or {}).get("SHA256", "")).lower() or None,
            "size": int(float(chosen.get("sizeKB") or 0) * 1024),
            "page": f"https://civitai.com/models/{data.get('modelId', source['model'])}?modelVersionId={data.get('id', '')}",
            "hint": hint}


def download(client: httpx.Client, url: str, headers: dict, target: Path, progress=None) -> tuple[str, int]:
    digest, size, reported = hashlib.sha256(), 0, 0
    with client.stream("GET", url, headers=headers, follow_redirects=True) as response:
        if response.status_code in {401, 403}:
            raise ValueError("El sitio no permite descargar ese archivo sin permiso o token")
        response.raise_for_status()
        if int(response.headers.get("content-length") or 0) > LORA_MAX_BYTES:
            raise ValueError("El LoRA supera el límite de 2 GB")
        with target.open("wb") as out:
            for chunk in response.iter_bytes(1 << 20):
                size += len(chunk)
                if size > LORA_MAX_BYTES:
                    raise ValueError("El LoRA supera el límite de 2 GB")
                digest.update(chunk)
                out.write(chunk)
                if progress and size - reported >= 32 << 20:
                    reported = size
                    progress(size)
    return digest.hexdigest(), size


def resolve_loras(store, uses, base: str) -> list[tuple[str, float]]:
    """(ComfyUI file name, strength) for each owned, ready LoRA of this base, in request order."""
    if not uses:
        return []
    root = lora_root()
    if root is None:
        raise ValueError("La biblioteca de LoRAs no está configurada en este servidor")
    chain = []
    with store._db() as db:
        for use in uses:
            try:
                row = db.execute("SELECT * FROM loras WHERE id=? AND owner_id=?", (use.id, owner())).fetchone()
            except sqlite3.OperationalError as exc:
                raise ValueError("Los LoRAs solo están disponibles en el estudio web") from exc
            if not row or row["status"] != "ready":
                raise ValueError("Ese LoRA no está en tu biblioteca o aún no terminó de descargarse")
            if row["base"] != base:
                raise ValueError(f"«{row['name']}» es un LoRA de {LORA_BASES[row['base']]}; aquí hace falta uno de {LORA_BASES[base]}")
            if not (root / "loras" / row["file"]).is_file():
                raise ValueError(f"Falta el archivo de «{row['name']}»; vuelve a añadirlo")
            chain.append((row["file"], use.strength if use.strength is not None else row["strength"]))
    return chain


class LoraLibrary:
    COLUMNS = "id,name,base,source_url,page,trigger,strength,status,error,bytes,total,sha256,created_at,updated_at"

    def __init__(self, store, root: Path | None, client_factory=None):
        self.store, self.root = store, root
        self.client_factory = client_factory or (lambda: httpx.Client(
            timeout=httpx.Timeout(30, read=120), headers={"User-Agent": "MediaLab/1.0"}))
        with store._db() as db:
            db.execute("UPDATE loras SET status='error',error='La descarga se interrumpió; vuelve a añadirlo',updated_at=? "
                       "WHERE status='downloading'", (time.time(),))

    @property
    def ready(self) -> bool:
        return self.root is not None

    def items(self) -> list[dict]:
        with self.store._db() as db:
            return [dict(r) for r in db.execute(f"SELECT {self.COLUMNS} FROM loras WHERE owner_id=? ORDER BY created_at DESC", (owner(),))]

    def get(self, lid: str) -> dict:
        from .tenancy import NotOwned
        with self.store._db() as db:
            row = db.execute(f"SELECT {self.COLUMNS} FROM loras WHERE id=? AND owner_id=?", (lid, owner())).fetchone()
        if not row:
            raise NotOwned("resource not found")
        return dict(row)

    def add(self, url: str, name: str = "") -> dict:
        from .tenancy import ResourceLimit
        if self.root is None:
            raise ValueError("La biblioteca de LoRAs no está configurada en este servidor")
        source, url, uid, now = parse_source(url), url.strip(), owner(), time.time()
        lid = "lora_" + secrets.token_hex(8)
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM loras WHERE owner_id=?", (uid,)).fetchone()[0] >= LORA_LIMIT:
                raise ResourceLimit(f"Máximo {LORA_LIMIT} LoRAs por cuenta; borra alguno primero")
            if db.execute("SELECT 1 FROM loras WHERE owner_id=? AND source_url=? AND status!='error'", (uid, url)).fetchone():
                raise ValueError("Ya añadiste ese enlace")
            db.execute("INSERT INTO loras(id,owner_id,name,source_url,status,created_at,updated_at) VALUES(?,?,?,?,'downloading',?,?)",
                       (lid, uid, name.strip()[:80] or "LoRA", url, now, now))
        context = contextvars.copy_context()
        threading.Thread(target=context.run, args=(self._fetch, lid, source, name.strip()), daemon=True, name=lid).start()
        return self.get(lid)

    def update(self, lid: str, values: dict) -> dict:
        self.get(lid)
        allowed = {k: v for k, v in values.items() if k in {"name", "trigger", "strength"} and v is not None}
        if allowed:
            self._set(lid, **allowed)
        return self.get(lid)

    def delete(self, lid: str) -> None:
        from .tenancy import ResourceLimit
        row = self.get(lid)
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT request_json FROM jobs WHERE owner_id=? AND status IN ('queued','running')", (owner(),)).fetchall()
            if any(lid in job["request_json"] for job in active):
                raise ResourceLimit("Ese LoRA está en uso por un trabajo activo")
            db.execute("UPDATE characters SET lora_id=NULL WHERE owner_id=? AND lora_id=?", (owner(), lid))
            db.execute("DELETE FROM loras WHERE id=? AND owner_id=?", (lid, owner()))
        self._collect(row["sha256"])

    def _set(self, lid: str, **values) -> int:
        values["updated_at"] = time.time()
        with self.store._db() as db:
            return db.execute(f"UPDATE loras SET {','.join(f'{k}=?' for k in values)} WHERE id=?", (*values.values(), lid)).rowcount

    def _collect(self, sha256: str | None) -> None:
        """Remove a hash-named file once no account's library points at it."""
        if not sha256 or self.root is None:
            return
        with self.store._db() as db:
            if db.execute("SELECT 1 FROM loras WHERE sha256=?", (sha256,)).fetchone():
                return
        (self.root / "loras" / lora_file(sha256)).unlink(missing_ok=True)

    def _fetch(self, lid: str, source: dict, name: str) -> None:
        part = self.root / "loras" / f".{lid}.part"
        try:
            with _downloads, self.client_factory() as client:
                info = resolve_source(source, client)
                if info["size"] > LORA_MAX_BYTES:
                    raise ValueError("El LoRA supera el límite de 2 GB")
                part.parent.mkdir(parents=True, exist_ok=True)
                if shutil.disk_usage(part.parent).free < FREE_SPACE + (info["size"] or LORA_MAX_BYTES):
                    raise ValueError("No queda espacio libre en el servidor para más LoRAs")
                self._set(lid, name=name[:80] or info["name"][:80], trigger=info["trigger"], page=info["page"],
                          revision=info["revision"], total=info["size"] or None)
                sha, size = download(client, info["url"], info["headers"], part, lambda done: self._set(lid, bytes=done))
            if info["sha256"] and sha != info["sha256"]:
                raise ValueError("El archivo descargado no coincide con el hash que publica el sitio")
            base = inspect_lora(part)
            target = part.parent / lora_file(sha)
            if target.exists():
                part.unlink()
            else:
                part.chmod(0o644)
                os.replace(part, target)
            if not self._set(lid, status="ready", base=base, file=target.name, sha256=sha, bytes=size, total=size, error=None):
                self._collect(sha)  # Deleted while downloading.
        except Exception as exc:
            if isinstance(exc, ValueError):
                message = str(exc)
            elif isinstance(exc, httpx.HTTPStatusError):
                message = f"El sitio respondió {exc.response.status_code}; revisa el enlace"
            elif isinstance(exc, httpx.HTTPError):
                message = "No se pudo conectar con el sitio; inténtalo más tarde"
            else:
                message = "No se pudo añadir el LoRA"
            self._set(lid, status="error", error=message[:300])
        finally:
            part.unlink(missing_ok=True)
