"""Approved HTTPS providers; public DNS destinations pinned for each TLS request."""
from __future__ import annotations

import base64
import io
import ipaddress
import json
import socket
import time
import uuid
from urllib.parse import urlsplit

import httpx
from PIL import Image
from pydantic import Field

from .security import owner
from .tenancy import NotOwned
from .web_auth import Strict


class ProviderSettings(Strict):
    endpoint_id: str = Field(max_length=40)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)


class Endpoint(Strict):
    label: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)


class ProviderCredential(Strict):
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    model: str = Field(default="", max_length=200)


class ProviderSelection(Strict):
    endpoint_id: str = Field(max_length=40)
    model: str = Field(min_length=1, max_length=200)


class ProviderBusy(ValueError):
    pass


def public_destination(base_url):
    url = urlsplit(base_url)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Se requiere un endpoint HTTPS sin credenciales, query ni fragmento")
    if url.port not in {None, 443} or "%" in url.netloc or "\\" in base_url:
        raise ValueError("Sólo se admite HTTPS en puerto 443")
    if url.hostname.casefold() == "localhost":
        raise ValueError("Destino privado no permitido")
    try:
        addresses = sorted({a[4][0] for a in socket.getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)})
    except socket.gaierror as exc:
        raise ValueError('No se pudo resolver el dominio del proveedor') from exc
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("El endpoint debe resolver exclusivamente a direcciones públicas")
    return url, addresses[0]


# Reasoning models (OpenRouter and others) count their thinking against max_tokens, so a
# probe needs room to think before it answers; 80 tokens made such models fail every check.
PROBE_MAX_TOKENS = 2048


def provider_error(response, key):
    """Short, secret-free reason from a non-200 provider response."""
    detail = ""
    try:
        body = json.loads(response.read()[:20000].decode(errors="replace"))
        error = body.get("error") if isinstance(body, dict) else None
        detail = (error.get("message") if isinstance(error, dict) else error) or body.get("message") or ""
    except Exception:
        pass
    detail = str(detail).replace(key, "[secret omitted]").strip()[:240]
    return f"Proveedor HTTP {response.status_code}" + (f": {detail}" if detail else "")


def normalize_message(message):
    """Accept OpenAI-compatible variants: content as a list of parts, arguments as objects."""
    content = message.get("content")
    if isinstance(content, list):
        message["content"] = "".join(part.get("text", "") for part in content
                                     if isinstance(part, dict) and part.get("type") in (None, "text", "output_text"))
    for call in message.get("tool_calls") or []:
        function = call.get("function") if isinstance(call, dict) else None
        if isinstance(function, dict) and isinstance(function.get("arguments"), dict):
            function["arguments"] = json.dumps(function["arguments"])
    return message


class Providers:
    def __init__(self, accounts):
        self.accounts = accounts
        with accounts.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS provider_endpoints(id TEXT PRIMARY KEY,label TEXT NOT NULL,base_url TEXT UNIQUE NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS user_providers(owner_id TEXT PRIMARY KEY REFERENCES users(id),
                    endpoint_id TEXT NOT NULL REFERENCES provider_endpoints(id),model TEXT NOT NULL,encrypted_key TEXT NOT NULL,capabilities TEXT);
                CREATE TABLE IF NOT EXISTS saved_providers(owner_id TEXT NOT NULL REFERENCES users(id),
                    endpoint_id TEXT NOT NULL REFERENCES provider_endpoints(id),model TEXT NOT NULL DEFAULT '',
                    encrypted_key TEXT NOT NULL,capabilities TEXT,PRIMARY KEY(owner_id,endpoint_id));
                INSERT OR IGNORE INTO saved_providers SELECT owner_id,endpoint_id,model,encrypted_key,capabilities FROM user_providers;
                CREATE TABLE IF NOT EXISTS agent_admissions(owner_id TEXT PRIMARY KEY,expires_at REAL NOT NULL);
            """)
            # Replace the legacy global URL constraint atomically. Existing IDs,
            # keys and references remain unchanged; old endpoints stay shared.
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('BEGIN IMMEDIATE')
            if 'owner_id' not in {r['name'] for r in db.execute('PRAGMA table_info(provider_endpoints)')}:
                db.execute('CREATE TABLE provider_endpoints_next(id TEXT PRIMARY KEY,label TEXT NOT NULL,base_url TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,owner_id TEXT REFERENCES users(id))')
                db.execute('INSERT INTO provider_endpoints_next SELECT id,label,base_url,enabled,NULL FROM provider_endpoints')
                db.execute('DROP TABLE provider_endpoints')
                db.execute('ALTER TABLE provider_endpoints_next RENAME TO provider_endpoints')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS provider_shared_url ON provider_endpoints(base_url) WHERE owner_id IS NULL')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS provider_personal_url ON provider_endpoints(owner_id,base_url) WHERE owner_id IS NOT NULL')
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Provider migration failed foreign key validation')
            db.commit()
            db.execute('PRAGMA foreign_keys=ON')

    @staticmethod
    def assert_idle(db, uid):
        if db.execute("SELECT 1 FROM agent_admissions WHERE owner_id=? AND expires_at>?", (uid, time.time())).fetchone():
            raise ProviderBusy("Espera a que termine el agente antes de cambiar el proveedor")
        if db.execute("SELECT 1 FROM agent_runs WHERE owner_id=? AND status IN ('running','recovering')", (uid,)).fetchone():
            raise ProviderBusy("Espera a que termine el agente antes de cambiar el proveedor")

    def configurations(self):
        with self.accounts.db() as db:
            rows = db.execute("SELECT p.endpoint_id,p.model,p.capabilities,e.label,e.base_url,e.enabled,e.owner_id "
                              "FROM saved_providers p JOIN provider_endpoints e ON e.id=p.endpoint_id WHERE p.owner_id=? AND (e.owner_id IS NULL OR e.owner_id=?) ORDER BY e.label", (owner(), owner())).fetchall()
        active = self.get()
        return [{"endpoint_id": r["endpoint_id"], "label": r["label"], "base_url": r["base_url"],
                 "enabled": bool(r["enabled"]), "personal": r['owner_id'] is not None, "configured": True, "model": r["model"],
                 "active": active["endpoint_id"] == r["endpoint_id"],
                 "capabilities": json.loads(r["capabilities"]) if r["capabilities"] else None} for r in rows]

    def save_configuration(self, eid, body):
        uid = owner()
        with self.accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM provider_endpoints WHERE id=? AND enabled=1 AND (owner_id IS NULL OR owner_id=?)", (eid, uid)).fetchone():
                raise NotOwned()
            previous = db.execute("SELECT * FROM saved_providers WHERE owner_id=? AND endpoint_id=?", (uid, eid)).fetchone()
            active = db.execute("SELECT * FROM user_providers WHERE owner_id=? AND endpoint_id=?", (uid, eid)).fetchone()
            if active:
                self.assert_idle(db, uid)
            if not body.api_key and not previous:
                raise ValueError("Introduce la clave de este proveedor")
            encrypted = self.accounts.vault.seal(body.api_key, f"provider:{uid}") if body.api_key else previous["encrypted_key"]
            changed = bool(body.api_key or not previous or previous["model"] != body.model)
            capabilities = None if changed else previous["capabilities"]
            db.execute("INSERT OR REPLACE INTO saved_providers VALUES(?,?,?,?,?)", (uid, eid, body.model, encrypted, capabilities))
            if active:
                db.execute("UPDATE user_providers SET model=?,encrypted_key=?,capabilities=? WHERE owner_id=?", (body.model, encrypted, capabilities, uid))
        return {"ok": True}

    def activate(self, body):
        uid = owner()
        with self.accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.assert_idle(db, uid)
            row = db.execute("SELECT p.* FROM saved_providers p JOIN provider_endpoints e ON e.id=p.endpoint_id WHERE p.owner_id=? AND p.endpoint_id=? AND e.enabled=1 AND (e.owner_id IS NULL OR e.owner_id=?)", (uid, body.endpoint_id, uid)).fetchone()
            if not row:
                raise ValueError("Guarda una clave para este proveedor")
            caps = row["capabilities"] if row["model"] == body.model else None
            db.execute("UPDATE saved_providers SET model=?,capabilities=? WHERE owner_id=? AND endpoint_id=?", (body.model, caps, uid, body.endpoint_id))
            db.execute("INSERT OR REPLACE INTO user_providers VALUES(?,?,?,?,?)", (uid, body.endpoint_id, body.model, row["encrypted_key"], caps))
        return self.get()

    def remove_configuration(self, eid):
        uid = owner()
        with self.accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.assert_idle(db, uid)
            if not db.execute('SELECT 1 FROM provider_endpoints WHERE id=? AND (owner_id IS NULL OR owner_id=?)', (eid, uid)).fetchone():
                raise NotOwned()
            db.execute("DELETE FROM user_providers WHERE owner_id=? AND endpoint_id=?", (uid, eid))
            db.execute("DELETE FROM saved_providers WHERE owner_id=? AND endpoint_id=?", (uid, eid))
            db.execute('DELETE FROM provider_endpoints WHERE id=? AND owner_id=?', (eid, uid))
        return {"ok": True}

    def models(self, eid):
        uid = owner()
        with self.accounts.db() as db:
            row = db.execute("SELECT p.encrypted_key,e.base_url FROM saved_providers p JOIN provider_endpoints e ON e.id=p.endpoint_id WHERE p.owner_id=? AND p.endpoint_id=? AND e.enabled=1 AND (e.owner_id IS NULL OR e.owner_id=?)", (uid, eid, uid)).fetchone()
        if not row:
            raise ValueError("Guarda primero la clave del proveedor")
        key = self.accounts.vault.open(row["encrypted_key"], f"provider:{uid}")
        data = self._request(row["base_url"], key, "GET", "/models", timeout=30)
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise ValueError("El proveedor no ofrece un catálogo compatible; introduce el modelo manualmente")
        ids = sorted({m["id"] for m in data["data"] if isinstance(m, dict) and isinstance(m.get("id"), str) and 0 < len(m["id"]) <= 200})
        return {"items": [{"id": mid} for mid in ids[:5000]]}

    @staticmethod
    def _request(base_url, key, method, suffix, payload=None, timeout=180):
        url, address = public_destination(base_url)
        host = f"[{address}]" if ":" in address else address
        try:
            with httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False) as client:
                request = client.build_request(method, f"https://{host}{url.path.rstrip('/')}{suffix}",
                    **({"json": payload} if payload is not None else {}),
                    headers={"Host": url.hostname, "Authorization": f"Bearer {key}"})
                request.extensions["sni_hostname"] = url.hostname
                response = client.send(request, stream=True)
                try:
                    if response.status_code != 200:
                        raise ValueError(f"El proveedor respondió HTTP {response.status_code}")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 4 * 1024 * 1024:
                            raise ValueError("Respuesta del proveedor demasiado grande")
                        chunks.append(chunk)
                    return json.loads(b"".join(chunks).decode().replace(key, "[secret omitted]"))
                finally:
                    response.close()
        except (httpx.HTTPError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Proveedor no disponible o respuesta inválida") from exc

    def endpoints(self):
        with self.accounts.db() as db:
            return [dict(r) for r in db.execute("SELECT id,label,base_url,owner_id IS NOT NULL AS personal FROM provider_endpoints WHERE enabled=1 AND (owner_id IS NULL OR owner_id=?) ORDER BY owner_id IS NULL,label", (owner(),))]

    def register(self, body):
        uid = owner()
        base_url, label = body.base_url.strip().rstrip('/'), body.label.strip()
        if not label:
            raise ValueError('Introduce un nombre para el proveedor')
        public_destination(base_url)
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.assert_idle(db, uid)
            row = db.execute('SELECT id,label,base_url FROM provider_endpoints WHERE owner_id=? AND base_url=?', (uid, base_url)).fetchone()
            if row:
                return {**dict(row), 'personal': True}
            if db.execute('SELECT COUNT(*) FROM provider_endpoints WHERE owner_id=?', (uid,)).fetchone()[0] >= 20:
                raise ValueError('Puedes guardar hasta 20 proveedores personales')
            eid = uuid.uuid4().hex
            db.execute('INSERT INTO provider_endpoints(id,label,base_url,enabled,owner_id) VALUES(?,?,?,1,?)', (eid, label, base_url, uid))
        return {'id': eid, 'label': label, 'base_url': base_url, 'personal': True}

    def approve(self, body, actor):
        public_destination(body.base_url)
        with self.accounts.db() as db:
            db.execute("INSERT INTO provider_endpoints(id,label,base_url,enabled) VALUES(?,?,?,1)", (uuid.uuid4().hex, body.label, body.base_url.rstrip("/")))
            self.accounts.audit(db, actor, "provider-approve", body.label)

    def save(self, body):
        uid = owner()
        with self.accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.assert_idle(db, uid)
            endpoint = db.execute("SELECT * FROM provider_endpoints WHERE id=? AND enabled=1 AND (owner_id IS NULL OR owner_id=?)", (body.endpoint_id, uid)).fetchone()
            if not endpoint:
                raise NotOwned()
            previous = db.execute("SELECT * FROM user_providers WHERE owner_id=?", (uid,)).fetchone()
            if body.api_key is None and (not previous or previous["endpoint_id"] != body.endpoint_id):
                raise ValueError("Introduce una clave para este endpoint")
            encrypted = self.accounts.vault.seal(body.api_key, f"provider:{uid}") if body.api_key else previous["encrypted_key"]
            db.execute("INSERT OR REPLACE INTO user_providers VALUES(?,?,?,?,NULL)", (uid, body.endpoint_id, body.model, encrypted))
            db.execute("INSERT OR REPLACE INTO saved_providers VALUES(?,?,?,?,NULL)", (uid, body.endpoint_id, body.model, encrypted))
        return self.get()

    def get(self):
        with self.accounts.db() as db:
            row = db.execute("SELECT p.endpoint_id,p.model,p.capabilities,e.base_url,e.enabled FROM user_providers p "
                             "JOIN provider_endpoints e ON e.id=p.endpoint_id WHERE p.owner_id=? AND (e.owner_id IS NULL OR e.owner_id=?)", (owner(), owner())).fetchone()
        return {"configured": bool(row and row["enabled"]), "endpoint_id": row["endpoint_id"] if row else "",
                "model": row["model"] if row else "", "baseUrl": row["base_url"] if row else "",
                "capabilities": json.loads(row["capabilities"]) if row and row["capabilities"] else None}

    def chat(self, messages, tools=None, max_tokens=1200):
        uid = owner()
        with self.accounts.db() as db:
            row = db.execute("SELECT p.*,e.base_url FROM user_providers p JOIN provider_endpoints e ON e.id=p.endpoint_id "
                             "WHERE p.owner_id=? AND e.enabled=1 AND (e.owner_id IS NULL OR e.owner_id=?)", (uid, uid)).fetchone()
        if not row:
            raise ValueError("Configura un proveedor para tu cuenta")
        url, address = public_destination(row["base_url"])
        key = self.accounts.vault.open(row["encrypted_key"], f"provider:{uid}")
        host = f"[{address}]" if ":" in address else address
        target = f"https://{host}{url.path.rstrip('/')}/chat/completions"
        payload = {"model": row["model"], "messages": messages, "max_tokens": max_tokens, "stream": False}
        if tools:
            # "auto" is the OpenAI default; sending tool_choice explicitly breaks models that
            # support tools but not that parameter (e.g. some OpenRouter routes).
            payload["tools"] = tools
        # No environment proxy, redirect, second DNS lookup or unchecked TLS hop.
        try:
            with httpx.Client(timeout=180, trust_env=False, follow_redirects=False) as client:
                request = client.build_request("POST", target, json=payload,
                                               headers={"Host": url.hostname, "Authorization": f"Bearer {key}"})
                request.extensions["sni_hostname"] = url.hostname
                response = client.send(request, stream=True)
                try:
                    if response.status_code != 200:
                        raise ValueError(provider_error(response, key))
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 4 * 1024 * 1024:
                            raise ValueError("Respuesta del proveedor demasiado grande")
                        chunks.append(chunk)
                    raw = b"".join(chunks).decode().replace(key, "[secret omitted]")
                    data = json.loads(raw)
                    if isinstance(data, dict) and data.get("error") and not data.get("choices"):
                        error = data["error"]
                        raise ValueError("Proveedor: " + str(error.get("message") if isinstance(error, dict) else error)[:240])
                    choice = data["choices"][0]
                    result = choice["message"]
                    if not isinstance(result, dict) or result.get("role", "assistant") != "assistant":
                        raise ValueError("Respuesta del proveedor inválida")
                    result = normalize_message({**result, "role": "assistant"})
                    if choice.get("finish_reason") == "length" and not (result.get("content") or "").strip() and not result.get("tool_calls"):
                        raise ValueError("El modelo agotó el límite de tokens sin responder (suele pasar con modelos que razonan)")
                    return result
                finally:
                    response.close()
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("Proveedor no disponible o respuesta inválida") from exc

    def test(self):
        uid = owner()
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            self.assert_idle(db, uid)
            db.execute('INSERT OR REPLACE INTO agent_admissions VALUES(?,?)', (uid, time.time() + 900))
        try:
            return self._test()
        finally:
            with self.accounts.db() as db:
                db.execute('DELETE FROM agent_admissions WHERE owner_id=?', (uid,))

    def _test(self):
        selection = self.get()
        result = {"chat": False, "tools": False, "vision": False, "checkedAt": int(time.time() * 1000), "errors": {}}
        tests = [
            ("chat", [{"role": "user", "content": "Reply only OK"}], None),
            ("tools", [{"role": "user", "content": "Call capability_probe with ok=true"}],
             [{"type": "function", "function": {"name": "capability_probe", "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}}}]),
        ]
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), "red").save(buf, "PNG")
        tests.append(("vision", [{"role": "user", "content": [{"type": "text", "text": "Name the color"},
                      {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}}]}], None))
        for name, messages, tools in tests:
            try:
                reply = self.chat(messages, tools, PROBE_MAX_TOKENS)
                if name == "tools":
                    calls = reply.get("tool_calls") or []
                    if not any(c.get("function", {}).get("name") == "capability_probe" and
                               json.loads(c["function"].get("arguments") or "{}").get("ok") in (True, "true") for c in calls):
                        raise ValueError("El modelo respondió sin llamar a la herramienta de prueba")
                elif not isinstance(reply.get("content"), str) or not reply["content"].strip():
                    raise ValueError("El modelo respondió sin texto")
                result[name] = True
            except (ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError) as exc:
                reason = str(exc) if isinstance(exc, ValueError) and str(exc) else "respuesta inesperada"
                result["errors"][name] = f"La prueba no pasó: {reason}. Los modos directos siguen disponibles."
        with self.accounts.db() as db:
            current = db.execute("SELECT endpoint_id,model FROM user_providers WHERE owner_id=?", (owner(),)).fetchone()
            if current and (current["endpoint_id"], current["model"]) == (selection["endpoint_id"], selection["model"]):
                db.execute("UPDATE user_providers SET capabilities=? WHERE owner_id=?", (json.dumps(result), owner()))
                db.execute("UPDATE saved_providers SET capabilities=? WHERE owner_id=? AND endpoint_id=? AND model=?", (json.dumps(result), owner(), selection["endpoint_id"], selection["model"]))
        return result

