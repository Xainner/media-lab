"""0.7 web entrypoint. Start with uvicorn media_lab.web:create_app --factory.

Requires fresh STATE_ROOT, an externally provisioned master key and service key.
Never mount legacy state into this process.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import secrets
import time
from contextlib import suppress
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from pydantic import Field

from .accounts import Accounts
from .mailbox import Mailbox, SMTPConfig
from .providers import Endpoint, Providers, ProviderSettings, ProviderCredential, ProviderSelection, ProviderBusy
from .admin_ops import AdminOperations, protect_last_admin
from .security import Vault, as_owner, owner
from .tenancy import TenantStore, TenantArtifacts, NotOwned, ResourceLimit
from .web_auth import BrowserBoundary, Email, Strict, auth_routes, install_errors, SESSION_COOKIE
from .mcp_access import McpAccess
from .mcp_server import build_mcp
from .prompt_check import PromptCheck, check_prompt
from .characters import CharacterBody, Characters
from .loras import LORA_BASES, LORA_LIMIT, LORA_MAX_BYTES, LoraLibrary, lora_root


class Profile(Strict):
    profile: str = Field(pattern="^(free|limited)$")
    active_limit: int | None = Field(default=None, ge=1, le=2)
    pending_limit: int | None = Field(default=None, ge=0, le=4)
    daily_limit: int | None = Field(default=None, ge=1)
    storage_limit: int | None = Field(default=None, ge=1)


class Enabled(Strict):
    enabled: bool


class AgentStart(Strict):
    prompt: str = Field(min_length=1, max_length=20000)
    session: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    references: list[dict] = Field(default_factory=list, max_length=16)


class AgentAction(Strict):
    jobId: str | None = Field(default=None, max_length=80)


class LoraAdd(Strict):
    url: str = Field(min_length=10, max_length=600)
    name: str = Field(default="", max_length=80)


class LoraEdit(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    trigger: str | None = Field(default=None, max_length=300)
    strength: float | None = Field(default=None, ge=0.05, le=2.0)


def explained(call, *args):
    """Library errors are written for the person using the page; say them instead of the generic answer."""
    try:
        return call(*args)
    except ResourceLimit as exc:
        raise HTTPException(429, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


# Slim images ship without /etc/mime.types; the web build needs these to be served correctly.
for _type, _ext in (("image/webp", ".webp"), ("image/avif", ".avif"), ("font/woff2", ".woff2"), ("font/woff", ".woff")):
    mimetypes.add_type(_type, _ext)


def create_app(*, state_root: Path | None = None, key_path: Path | None = None,
               origin: str | None = None, attach_runtime: bool = True):
    state = state_root or Path(os.environ["STATE_ROOT"])
    origin = origin or os.getenv("PUBLIC_ORIGIN", "https://media.example.com")
    vault = Vault(key_path or Path(os.environ["MASTER_KEY_FILE"]))
    accounts = Accounts(state / "media-lab.db", vault)
    store = TenantStore(accounts.path)
    artifacts = TenantArtifacts(store, state / "artifacts", 20 * 1024 * 1024, 32 * 1024 * 1024)
    mail, providers = Mailbox(accounts, origin), Providers(accounts)
    loras, characters = LoraLibrary(store, lora_root()), Characters(store)
    mcp_access = McpAccess(accounts, origin)
    runtime = None
    service_key_path = os.getenv("AGENT_SERVICE_KEY_FILE")
    service_key = ""
    if attach_runtime:
        if not service_key_path:
            raise RuntimeError("AGENT_SERVICE_KEY_FILE is required")
        path = Path(service_key_path)
        # Same permission/length checks as the master key, with a different key.
        Vault(path)
        service_key = path.read_bytes().hex()
        from . import main as runtime
        from .jobs import JobManager
        from .creative import CreativeJobs
        from .tenant_workers import TenantWorkers
        if runtime.SETTINGS.db_path.resolve() != accounts.path.resolve():
            raise RuntimeError("DB_PATH must match fresh STATE_ROOT/media-lab.db")
        runtime.workers.shutdown()
        runtime.store, runtime.artifacts = store, artifacts
        store.mark_interrupted_on_boot()
        runtime.workers = TenantWorkers(runtime.SETTINGS, store)
        runtime.jobs = JobManager(runtime.SETTINGS, store, artifacts, runtime.workers)
        runtime.creative = CreativeJobs(runtime.SETTINGS, store, artifacts, runtime.workers)

    @asynccontextmanager
    async def lifespan(_app):
        mail.start()
        cleanup = asyncio.create_task(app.state.admin_ops.run())
        async with app.state.mcp.session_manager.run(), app.state.mcp_streaming.run():
            yield
        cleanup.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup
        mail.stop()
        if runtime:
            runtime.workers.shutdown()

    app = FastAPI(title="Media Lab Web", version="0.9.1", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.state.accounts, app.state.store, app.state.artifacts = accounts, store, artifacts
    app.state.mail, app.state.providers = mail, providers
    app.state.loras, app.state.characters = loras, characters
    install_errors(app)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        # FastAPI's default validation response echoes input, including passwords/API keys.
        return JSONResponse({"detail": [{"loc": e["loc"], "type": e["type"], "msg": e["msg"]} for e in exc.errors()]}, 422)
    app.include_router(auth_routes(accounts, mail))
    app.include_router(mcp_access.router())
    app.state.mcp_access = mcp_access

    @app.exception_handler(NotOwned)
    async def nonexistent(_request, _exc):
        return JSONResponse({"detail": "resource not found"}, 404)

    @app.exception_handler(ResourceLimit)
    async def limit(_request, _exc):
        return JSONResponse({"detail": "Límite de recursos alcanzado o archivo en uso"}, 429)

    @app.exception_handler(ValueError)
    async def invalid(_request, _exc):
        return JSONResponse({"detail": "Datos inválidos"}, 422)

    @app.exception_handler(ProviderBusy)
    async def provider_busy(_request, _exc):
        return JSONResponse({"detail": "Espera a que termine el agente antes de cambiar el proveedor"}, 409)

    @app.get("/health")
    def public_health():
        return {"status": "ok", "version": app.version}

    @app.get("/v1/health")
    def health():
        if not runtime:
            return {"status": "isolated", "queue": store.queue_counts(), "workers": []}
        result = runtime.health()
        # Do not leak other people's job IDs, Comfy prompts, IPs or process names.
        states = []
        for worker in result["workers"]:
            active = worker.get("active_job")
            states.append({"gpu": worker["gpu"], "health": {"ok": worker["health"]["ok"]},
                           "busy": worker["busy"], "pending": worker["pending"],
                           "gpu_guard": {"available": worker["gpu_guard"]["available"]},
                           "active_job": active if active and store.get_job(active) else None})
        return {"status": result["status"], "runtime": {"ok": True, "version": app.version},
                "queue": result["queue"], "workers": states,
                "models": {"ok": result["models"]["ok"]},
                "gpu_guard": {"available": any(s["gpu_guard"]["available"] for s in states)}}

    @app.get("/v1/account/provider")
    def provider():
        return providers.get()

    @app.get("/v1/account/endpoints")
    def endpoints():
        return {"items": providers.endpoints()}

    @app.post('/v1/account/endpoints', status_code=201)
    def add_personal_endpoint(body: Endpoint):
        try:
            return providers.register(body)
        except ProviderBusy:
            raise
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get('/v1/account/providers')
    def provider_configurations():
        return {"items": providers.configurations(), "active": providers.get()}

    @app.put('/v1/account/providers/{eid}')
    def configure_provider(eid: str, body: ProviderCredential):
        return providers.save_configuration(eid, body)

    @app.delete('/v1/account/providers/{eid}')
    def remove_provider(eid: str):
        return providers.remove_configuration(eid)

    @app.get('/v1/account/providers/{eid}/models')
    def discover_models(eid: str):
        return providers.models(eid)

    @app.post('/v1/account/providers/activate')
    def activate_provider(body: ProviderSelection):
        return providers.activate(body)

    @app.put("/v1/account/provider")
    def save_provider(body: ProviderSettings):
        return providers.save(body)

    @app.post("/v1/account/provider/test")
    def test_provider():
        return providers.test()

    @app.post("/v1/private/provider/chat")
    def private_chat(body: dict):
        if set(body) - {"messages", "tools", "maxTokens"} or not isinstance(body.get("messages"), list):
            raise ValueError("invalid chat request")
        return providers.chat(body["messages"], body.get("tools"), min(8000, max(1, int(body.get("maxTokens", 1200)))))

    @app.get("/v1/private/provider/status")
    def private_provider():
        return providers.get()

    @app.post("/v1/private/agent/record")
    def record_agent(body: dict):
        import re
        if set(body) != {"id", "session", "status"} or not re.fullmatch(r"run_[a-f0-9]{24}", body.get("id", "")):
            raise ValueError("invalid run record")
        store.ensure_session(body["session"])
        with store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT owner_id FROM agent_runs WHERE id=?", (body["id"],)).fetchone()
            if row and row[0] != owner():
                raise NotOwned()
            db.execute("INSERT INTO agent_runs VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at",
                       (body["id"], owner(), body["session"], str(body["status"])[:40], time.time()))
        return {"ok": True}

    @app.get("/v1/account/preferences")
    def preferences():
        return json.loads(store.get_setting("preferences", "{}"))

    @app.get("/v1/jobs")
    def recent_jobs():
        with store._db() as db:
            rows = db.execute("SELECT * FROM jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT 100", (owner(),)).fetchall()
        return {"items": [store._job(r) for r in rows]}

    @app.put("/v1/account/preferences")
    def save_preferences(body: dict):
        allowed = {"format", "jpegQuality", "webpQuality", "jpegBackground", "enhancer", "animation"}
        if set(body) - allowed:
            raise ValueError("invalid preferences")
        current = json.loads(store.get_setting("preferences", "{}"))
        current.update(body)
        if current.get("format", "png") not in {"png", "jpeg", "webp"}:
            raise ValueError("invalid format")
        for name in ("jpegQuality", "webpQuality"):
            if name in current and (type(current[name]) is not int or not 1 <= current[name] <= 100):
                raise ValueError("invalid quality")
        import re
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", current.get("jpegBackground", "#ffffff")):
            raise ValueError("invalid background")
        if current.get("enhancer", "manual") not in {"off", "manual", "external"} or current.get("animation", "live") not in {"off", "live", "simulated"}:
            raise ValueError("invalid preference")
        store.set_setting("preferences", json.dumps(current))
        return current

    @app.get("/v1/admin/users")
    def users():
        with accounts.db() as db:
            # Deliberately excludes prompts, content, provider configuration and secrets.
            rows = db.execute("SELECT id,email,username,role,enabled,profile,active_limit,pending_limit,daily_limit,storage_limit,created_at FROM users ORDER BY created_at").fetchall()
            result = []
            for row in rows:
                data = dict(row)
                data["storage_bytes"] = db.execute("SELECT COALESCE(SUM(bytes),0) FROM artifacts WHERE owner_id=?", (row["id"],)).fetchone()[0]
                data["jobs"] = dict(db.execute("SELECT status,COUNT(*) FROM jobs WHERE owner_id=? GROUP BY status", (row["id"],)))
                deletion = db.execute("SELECT status FROM account_deletions WHERE user_id=?", (row['id'],)).fetchone()
                data['deletion_status'] = deletion[0] if deletion else None
                result.append(data)
        return {"items": result}

    @app.post("/v1/admin/invitations")
    def invite(body: Email):
        return {"outbox_id": mail.invite(body.email, owner())}

    @app.put("/v1/admin/users/{uid}/profile")
    def profile(uid: str, body: Profile):
        with accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM account_deletions WHERE user_id=?", (uid,)).fetchone():
                raise HTTPException(409, 'La cuenta está en proceso de eliminación')
            active = body.active_limit or 1 if body.profile == "limited" else None
            pending = (body.pending_limit if body.pending_limit is not None else 1) if body.profile == "limited" else None
            changed = db.execute("UPDATE users SET profile=?,active_limit=?,pending_limit=?,daily_limit=?,storage_limit=? WHERE id=?",
                                 (body.profile, active, pending, body.daily_limit, body.storage_limit, uid)).rowcount
            if not changed:
                raise NotOwned()
            accounts.audit(db, owner(), "resource-profile", uid)
        return {"ok": True}

    @app.put("/v1/admin/users/{uid}/enabled")
    async def enabled(uid: str, body: Enabled):
        actor = owner()
        if uid == actor and not body.enabled:
            raise HTTPException(409, "No puedes desactivar tu propia cuenta")
        with accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM account_deletions WHERE user_id=?", (uid,)).fetchone():
                raise HTTPException(409, 'La cuenta está en proceso de eliminación')
            if not body.enabled:
                protect_last_admin(db, uid)
            if not db.execute("UPDATE users SET enabled=? WHERE id=?", (body.enabled, uid)).rowcount:
                raise NotOwned()
            pending = [r[0] for r in db.execute("SELECT id FROM jobs WHERE owner_id=? AND status IN ('running','queued')", (uid,))]
            if not body.enabled:
                db.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid,))
                accounts.revoke_external_tokens(db, uid)
                db.execute("UPDATE jobs SET cancel_requested=1 WHERE owner_id=? AND status IN ('queued','running')", (uid,))
                db.execute("UPDATE agent_runs SET status='cancelled',updated_at=? WHERE owner_id=? AND status IN ('running','recovering')", (time.time(), uid))
            accounts.audit(db, actor, "reactivate" if body.enabled else "deactivate", uid)
        if not body.enabled and runtime:
            with as_owner(uid):
                for jid in pending:
                    runtime.workers.cancel(jid)
            try:
                await agent_request(uid, "POST", "/disable", {})
            except HTTPException:
                pass
        return {"ok": True}

    @app.post("/v1/admin/users/{uid}/recovery")
    def recovery(uid: str):
        with accounts.db() as db:
            row = db.execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()
        if not row:
            raise NotOwned()
        mail.request_reset(row[0], owner())
        return {"ok": True}

    @app.get("/v1/admin/smtp")
    def smtp():
        return mail.state()

    @app.put("/v1/admin/smtp")
    def configure_smtp(body: SMTPConfig):
        mail.configure(body, owner())
        return mail.state()

    @app.post("/v1/admin/smtp/test")
    def test_smtp(request: Request):
        return {"outbox_id": mail.test(request.state.account["email"], owner())}

    @app.get("/v1/admin/providers")
    def approved_providers():
        with accounts.db() as db:
            return {"items": [dict(r) for r in db.execute('SELECT id,label,base_url,enabled FROM provider_endpoints WHERE owner_id IS NULL ORDER BY label')]}

    @app.post("/v1/admin/providers")
    def approve(body: Endpoint):
        providers.approve(body, owner())
        return {"ok": True}

    @app.delete("/v1/admin/providers/{eid}")
    def revoke_provider(eid: str):
        with accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM provider_endpoints WHERE id=? AND owner_id IS NULL', (eid,)).fetchone():
                raise NotOwned()
            for row in db.execute('SELECT owner_id FROM user_providers WHERE endpoint_id=?', (eid,)).fetchall():
                providers.assert_idle(db, row[0])
            db.execute("UPDATE provider_endpoints SET enabled=0 WHERE id=?", (eid,))
            accounts.audit(db, owner(), "provider-disable", eid)
        return {"ok": True}

    @app.put('/v1/admin/providers/{eid}/enabled')
    def restore_provider(eid: str, body: Enabled):
        if not body.enabled:
            return revoke_provider(eid)
        with accounts.db() as db:
            row = db.execute('SELECT base_url FROM provider_endpoints WHERE id=? AND owner_id IS NULL', (eid,)).fetchone()
        if not row:
            raise NotOwned()
        from .providers import public_destination
        public_destination(row[0])
        with accounts.db() as db:
            db.execute('UPDATE provider_endpoints SET enabled=1 WHERE id=?', (eid,))
            accounts.audit(db, owner(), 'provider-enable', eid)
        return {'ok': True}

    @app.get("/v1/admin/audit")
    def audit():
        with accounts.db() as db:
            return {"items": [dict(r) for r in db.execute("SELECT * FROM admin_audit ORDER BY created_at DESC LIMIT 200")]}

    async def agent_request(uid, method, path, body=None):
        if not service_key:
            raise HTTPException(503, "Agente privado no configurado; modos directos disponibles")
        try:
            async with httpx.AsyncClient(timeout=240, trust_env=False) as client:
                response = await client.request(method, "http://127.0.0.1:8392" + path, json=body,
                                                headers={"X-Service-Key": service_key, "X-Owner": uid})
            if response.status_code in {404, 409}:
                raise HTTPException(response.status_code, "Recurso inexistente o solicitud en conflicto")
            if response.status_code != 200:
                try:
                    reason = str(response.json().get("error") or "")[:300]
                except ValueError:
                    reason = ""
                raise HTTPException(502, "El agente no pudo completar la operación" + (f": {reason}" if reason else ""))
            return response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Agente temporalmente no disponible; modos directos disponibles") from exc

    @app.post("/v1/agent/runs")
    async def agent_start(body: AgentStart, idempotency_key: str | None = Header(default=None)):
        store.ensure_session(body.session)
        with store._db() as db:
            store._check_refs(db, body.references, owner())
        if idempotency_key is not None and (not idempotency_key or len(idempotency_key) > 128 or not idempotency_key.isascii()):
            raise ValueError("invalid Idempotency-Key")
        uid = owner()
        with accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM agent_admissions WHERE owner_id=? AND expires_at>?', (uid, time.time())).fetchone():
                raise HTTPException(409, 'Ya se está iniciando una ejecución')
            db.execute('INSERT OR REPLACE INTO agent_admissions VALUES(?,?)', (uid, time.time() + 300))
        try:
            run = await agent_request(uid, "POST", "/start", {**body.model_dump(), "idempotencyKey": idempotency_key})
            record_agent({"id": run["id"], "session": run["session"], "status": run["status"]})
            return run
        finally:
            with accounts.db() as db:
                db.execute('DELETE FROM agent_admissions WHERE owner_id=?', (uid,))

    def own_run(rid):
        import re
        if not re.fullmatch(r"run_[a-f0-9]{24}", rid):
            raise NotOwned()
        with store._db() as db:
            if not db.execute("SELECT 1 FROM agent_runs WHERE id=? AND owner_id=?", (rid, owner())).fetchone():
                raise NotOwned()

    @app.get("/v1/agent/runs")
    async def agent_runs(session: str = ""):
        if session and not store.session(session):
            return []
        return await agent_request(owner(), "GET", "/runs?session=" + __import__("urllib.parse", fromlist=["quote"]).quote(session))

    @app.get("/v1/agent/runs/{rid}")
    async def agent_run(rid: str):
        own_run(rid)
        return await agent_request(owner(), "GET", "/runs?id=" + rid)

    @app.post("/v1/agent/runs/{rid}/cancel")
    async def agent_cancel(rid: str, body: AgentAction):
        own_run(rid)
        return await agent_request(owner(), "POST", "/cancel", {"id": rid, **body.model_dump()})

    @app.post("/v1/agent/runs/{rid}/continue")
    async def agent_continue(rid: str):
        own_run(rid)
        uid = owner()
        with accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            providers.assert_idle(db, uid)
            db.execute('INSERT OR REPLACE INTO agent_admissions VALUES(?,?)', (uid, time.time() + 300))
        try:
            run = await agent_request(uid, "POST", "/continue", {"id": rid})
            record_agent({"id": run['id'], "session": run['session'], "status": run['status']})
            return run
        finally:
            with accounts.db() as db:
                db.execute('DELETE FROM agent_admissions WHERE owner_id=?', (uid,))

    @app.post("/v1/agent/improve")
    async def agent_improve(body: dict):
        if set(body) - {"prompt", "mode", "references", "seconds"}:
            raise ValueError("invalid prompt request")
        if body.get("mode", "t2i") not in {"t2i", "i2i", "moss", "t2v", "i2v", "r2v", "kandinsky", "song", "ace_song"}:
            raise ValueError("invalid prompt mode")
        with store._db() as db:
            store._check_refs(db, body.get("references", []), owner())
        return await agent_request(owner(), "POST", "/improve", body)

    @app.post("/v1/agent/review")
    async def agent_review(body: dict):
        if set(body) - {"prompt", "media"}:
            raise ValueError("invalid review request")
        with store._db() as db:
            store._check_refs(db, body.get("media", {}), owner())
        return await agent_request(owner(), "POST", "/review", body)

    @app.post("/v1/prompts/check")
    def prompt_check(body: PromptCheck):
        return check_prompt(body)

    @app.post("/v1/agent/director")
    async def agent_director(body: dict):
        if set(body) - {"brief", "lyrics", "analysis"}:
            raise ValueError("invalid storyboard request")
        return await agent_request(owner(), "POST", "/director", body)

    @app.get("/v1/agent/events")
    async def agent_events(request: Request):
        uid, token = owner(), request.cookies.get(SESSION_COOKIE, "")
        async def events():
            last = ""
            while not await request.is_disconnected():
                try:
                    valid = accounts.authenticate(token)
                    if not valid["mfa"]:
                        return
                    current = await agent_request(uid, "GET", "/runs")
                    data = json.dumps(current, ensure_ascii=False, separators=(",", ":"))
                    if data != last:
                        yield "data: " + data + "\n\n"
                        last = data
                    else:
                        yield ": keepalive\n\n"
                except Exception:
                    return
                await asyncio.sleep(2)
        return StreamingResponse(events(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.delete("/v1/library")
    def delete_media(uri: str, sha256: str):
        artifacts.delete_media(uri, sha256)
        return {"ok": True}

    @app.get("/v1/loras")
    def list_loras():
        return {"ready": loras.ready, "bases": LORA_BASES, "limit": LORA_LIMIT, "max_bytes": LORA_MAX_BYTES,
                "items": loras.items()}

    @app.post("/v1/loras", status_code=202)
    def add_lora(body: LoraAdd):
        return explained(loras.add, body.url, body.name)

    @app.patch("/v1/loras/{lid}")
    def edit_lora(lid: str, body: LoraEdit):
        return loras.update(lid, body.model_dump())

    @app.delete("/v1/loras/{lid}")
    def delete_lora(lid: str):
        explained(loras.delete, lid)
        return {"ok": True}

    @app.get("/v1/characters")
    def list_characters():
        return {"items": characters.items()}

    @app.post("/v1/characters", status_code=201)
    def add_character(body: CharacterBody):
        return explained(characters.save, body)

    @app.put("/v1/characters/{cid}")
    def edit_character(cid: str, body: CharacterBody):
        return explained(characters.save, body, cid)

    @app.delete("/v1/characters/{cid}")
    def delete_character(cid: str):
        characters.delete(cid)
        return {"ok": True}

    if runtime:
        # Existing contracts/workflows reused, but ONLY behind the web auth boundary.
        skip = {"/v1/health", "/v1/doctor", "/v1/nodes/status", "/v1/jobs/{job_id}/preview"}
        app.router.routes.extend(r for r in runtime.app.routes if getattr(r, "path", "").startswith("/v1/") and r.path not in skip)

        @app.get("/v1/jobs/{jid}/preview")
        def preview(jid: str):
            if not store.get_job(jid):
                raise NotOwned()
            return runtime.job_preview(jid)

        @app.get("/v1/admin/diagnostics")
        def diagnostics():
            return {"models": runtime.model_status(), "nodes": runtime.node_status()}

    app.state.admin_ops = AdminOperations(app, accounts, store, mail, artifacts, agent_request, runtime)
    app.state.mcp, mcp_transport = build_mcp(app, mcp_access)
    app.add_middleware(BrowserBoundary, accounts=accounts, origin=origin, service_key=service_key, mcp_app=mcp_transport)
    web_root = Path(os.getenv("WEB_ROOT", str(state / "web"))).resolve()

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith(("v1/", "internal/", "mcp/")) or path in {"mcp", "docs", "redoc", "openapi.json"}:
            raise HTTPException(404)
        target = (web_root / path).resolve()
        if web_root not in target.parents and target != web_root:
            raise HTTPException(404)
        if target.is_file() and path.startswith(("assets/", "art/", "brand/")):
            # Vite assets are content-hashed; art and brand files keep stable names, so revalidate daily.
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "public, max-age=86400, stale-while-revalidate=604800"
            return FileResponse(target, headers={"Cache-Control": cache})
        if not target.is_file():
            target = web_root / "index.html"
        if not target.is_file():
            raise HTTPException(503, "Web build not installed")
        return FileResponse(target)

    return app

