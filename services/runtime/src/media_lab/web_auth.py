"""Browser authentication boundary: deny by default, origin + synchronizer CSRF."""
from __future__ import annotations

import ipaddress
import os
import secrets
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse

from .accounts import Accounts, AccessDenied, RateLimited
from .security import OWNER, digest

SESSION_COOKIE = "__Host-rvl-session"
PREAUTH_COOKIE = "__Host-rvl-preauth"
STATIC_PREFIXES = ("/assets/", "/art/", "/brand/")
PUBLIC = {"/v1/auth/session", "/v1/auth/login", "/v1/auth/accept", "/v1/auth/forgot", "/v1/auth/reset"}
PARTIAL = {"/v1/auth/session", "/v1/auth/logout", "/v1/auth/2fa/setup", "/v1/auth/2fa/confirm", "/v1/auth/2fa/verify"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Strict):
    identity: str = Field(min_length=1, max_length=254)
    password: str = Field(max_length=128)
    remember: bool = False


class Accept(Strict):
    token: str = Field(min_length=32, max_length=128)
    email: str = Field(max_length=254)
    username: str = Field(max_length=40)
    password: str = Field(min_length=15, max_length=128)


class Email(Strict):
    email: str = Field(max_length=254)


class Reset(Strict):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=15, max_length=128)


class ChangePassword(Strict):
    current: str = Field(max_length=128)
    password: str = Field(min_length=15, max_length=128)
    code: str = Field(default="", max_length=30)


class Factor(Strict):
    code: str = Field(min_length=6, max_length=30)
    remember: bool = False


def cookie(response: Response, key: str, value: str, max_age: int | None = None):
    response.set_cookie(key, value, secure=True, httponly=True, samesite="lax", path="/", max_age=max_age)


class BrowserBoundary:
    def __init__(self, app, accounts: Accounts, origin: str, service_key: str = "", mcp_app=None):
        self.app, self.accounts, self.origin = app, accounts, origin
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise RuntimeError("PUBLIC_ORIGIN must be an exact HTTPS origin")
        self.host = parsed.netloc
        # The reverse proxy's address (TRUSTED_PROXY_IP); only its X-Forwarded-For is believed.
        self.trusted_proxy = os.getenv("TRUSTED_PROXY_IP", "").strip()
        self.service_key = service_key
        self.mcp_app = mcp_app
        with accounts.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS preauth(token_hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL)")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        path = scope["path"]
        headers = request.headers
        peer = scope.get("client", (None,))[0]
        # Uvicorn proxy rewriting is disabled. NPM appends its actual remote peer last.
        if self.trusted_proxy and peer == self.trusted_proxy:
            forwarded = headers.get("x-forwarded-for", "").split(",")[-1].strip()
            try:
                actual = str(ipaddress.ip_address(forwarded))
                scope["client"] = (actual, 0)
            except ValueError:
                return await JSONResponse({"detail": "Proxy headers invalid"}, 400)(scope, receive, send)
        range_header = headers.get("range", "")
        if len(range_header) > 200 or "," in range_header:
            return await JSONResponse({"detail": "Range no permitido"}, 416)(scope, receive, send)
        if headers.get("host") != self.host:
            return await JSONResponse({"detail": "Invalid host"}, 400)(scope, receive, send)
        if self.mcp_app and (path == '/mcp' or path.startswith('/mcp/')):
            return await self.mcp_app(scope, receive, send)
        session = None
        internal = False
        if (self.service_key and peer in {"127.0.0.1", "::1"}
                and secrets.compare_digest(self.service_key, headers.get("x-service-key", ""))):
            uid = headers.get("x-owner", "")
            with self.accounts.db() as db:
                user = db.execute("SELECT id,role,email,username FROM users WHERE id=? AND enabled=1", (uid,)).fetchone()
            if user:
                internal = True
                session = {"user_id": uid, "role": "member", "mfa": 1, "csrf": "", "totp_enabled": True}
        scope.setdefault("state", {})["internal"] = internal
        try:
            if not internal:
                session = self.accounts.authenticate(request.cookies.get(SESSION_COOKIE, ""))
        except AccessDenied:
            pass
        mutating = request.method not in {"GET", "HEAD", "OPTIONS"}
        # Bound multipart spooling as well as JSON, including chunked requests.
        body_limit = (501 if path == "/v1/media/uploads" else 21 if path == "/v1/uploads"
                      else 8 if internal else 2) * 1024 * 1024
        if mutating:
            try:
                declared = int(headers.get("content-length", "0"))
            except ValueError:
                return await JSONResponse({"detail": "Invalid length"}, 400)(scope, receive, send)
            if declared < 0 or declared > body_limit:
                return await JSONResponse({"detail": "Solicitud demasiado grande"}, 413)(scope, receive, send)
        if path.startswith("/v1/private/") and not internal:
            return await JSONResponse({"detail": "Not found"}, 404)(scope, receive, send)
        if internal and (not path.startswith("/v1/") or path.startswith(("/v1/auth/", "/v1/admin/", "/v1/agent/"))):
            return await JSONResponse({"detail": "Not found"}, 404)(scope, receive, send)
        if mutating and not internal:
            if headers.get("origin") != self.origin or headers.get("sec-fetch-site", "same-origin") not in {"same-origin", "none"}:
                return await JSONResponse({"detail": "Origen no permitido"}, 403)(scope, receive, send)
            expected = session["csrf"] if session else None
            if not expected:
                with self.accounts.db() as db:
                    row = db.execute("SELECT csrf FROM preauth WHERE token_hash=? AND expires>?",
                                     (digest(request.cookies.get(PREAUTH_COOKIE, "")), time.time())).fetchone()
                expected = row[0] if row else None
            if not expected or not secrets.compare_digest(expected, headers.get("x-csrf-token", "")):
                return await JSONResponse({"detail": "CSRF inválido"}, 403)(scope, receive, send)
        if path.startswith("/v1/") and path not in PUBLIC:
            if not session:
                return await JSONResponse({"detail": "Inicia sesión"}, 401)(scope, receive, send)
            if not session["mfa"] and path not in PARTIAL:
                return await JSONResponse({"detail": "Verifica 2FA antes de continuar"}, 403)(scope, receive, send)
            if path.startswith("/v1/admin/") and (session["role"] != "admin" or not session["totp_enabled"]):
                return await JSONResponse({"detail": "Acceso denegado"}, 403)(scope, receive, send)
        scope.setdefault("state", {})["account"] = session
        # Drain authenticated requests before erasure; exclude the long-lived event stream.
        admitted = session is not None and path.startswith('/v1/') and path != '/v1/agent/events'
        if admitted:
            uid = session['user_id']
            with self.accounts.request_lock:
                with self.accounts.db() as db:
                    enabled = db.execute('SELECT 1 FROM users WHERE id=? AND enabled=1', (uid,)).fetchone()
                if enabled:
                    self.accounts.inflight_requests[uid] = self.accounts.inflight_requests.get(uid, 0) + 1
            if not enabled:
                return await JSONResponse({'detail': 'Inicia sesión'}, 401)(scope, receive, send)
        token = OWNER.set(session["user_id"] if session else None)
        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > body_limit:
                    raise HTTPException(413, "Solicitud demasiado grande")
            return message
        async def secure_send(message):
            if message["type"] == "http.response.start":
                # Only real static files (marked by the SPA route) may be cached; never the SPA shell.
                cache = next((v for k, v in message.get("headers", []) if k.lower() == b"cache-control"), b"")
                static = request.method in {"GET", "HEAD"} and path.startswith(STATIC_PREFIXES) and cache.startswith(b"public")
                extra = [(b"cache-control", cache if static else b"no-store"), (b"x-content-type-options", b"nosniff"),
                         (b"referrer-policy", b"no-referrer"), (b"x-frame-options", b"DENY"),
                         (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                         # Existing React components use dynamic inline geometry/progress styles,
                         # never raw CSS from user content. Scripts remain self-only, without eval.
                         (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'")]
                names = {h[0] for h in extra}
                message["headers"] = [(k, v) for k, v in message.get("headers", []) if k.lower() not in names] + extra
            await send(message)
        try:
            await self.app(scope, bounded_receive, secure_send)
        finally:
            OWNER.reset(token)
            if admitted:
                with self.accounts.request_lock:
                    remaining = self.accounts.inflight_requests[uid] - 1
                    if remaining:
                        self.accounts.inflight_requests[uid] = remaining
                    else:
                        self.accounts.inflight_requests.pop(uid, None)


def auth_routes(accounts: Accounts, mail):
    router = APIRouter(prefix="/v1/auth")

    @router.get("/session")
    def current(request: Request, response: Response):
        session = request.state.account
        if session:
            return {"authenticated": True, **accounts.public_session(session)}
        with accounts.db() as db:
            existing = db.execute("SELECT csrf FROM preauth WHERE token_hash=? AND expires>?",
                                  (digest(request.cookies.get(PREAUTH_COOKIE, "")), time.time())).fetchone()
        if existing:
            return {"authenticated": False, "csrf": existing[0]}
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with accounts.db() as db:
            db.execute("DELETE FROM preauth WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO preauth VALUES(?,?,?)", (digest(token), csrf, time.time() + 1800))
        cookie(response, PREAUTH_COOKIE, token)
        return {"authenticated": False, "csrf": csrf}

    @router.post("/login")
    def login(body: Login, request: Request, response: Response):
        token, session = accounts.login(body.identity, body.password, body.remember,
                                        request.client.host, request.headers.get("user-agent", ""))
        persistent = body.remember and session["role"] != "admin"
        cookie(response, SESSION_COOKIE, token, 7 * 86400 if persistent else None)
        response.delete_cookie(PREAUTH_COOKIE, secure=True, httponly=True, samesite="lax")
        return {"authenticated": True, **accounts.public_session(session)}

    @router.post("/accept")
    def accept(body: Accept, request: Request):
        accounts.limit(request.client.host, body.email, "accept")
        accounts.accept(body.token, body.email, body.username, body.password)
        return {"ok": True}

    @router.post("/forgot")
    def forgot(body: Email, request: Request):
        email = accounts.email(body.email)
        accounts.limit(request.client.host, email, "reset")
        # Availability and response are identical for existing and nonexistent accounts.
        mail.request_reset(email)
        return {"ok": True, "message": "Si la cuenta existe y el correo está disponible, recibirás un enlace"}

    @router.post("/reset")
    def reset(body: Reset, request: Request):
        accounts.limit(request.client.host, digest(body.token), "reset-consume")
        accounts.reset_password(body.token, body.password)
        return {"ok": True}

    @router.post("/logout")
    def logout(request: Request, response: Response):
        session = request.state.account
        accounts.revoke(session["user_id"], session["id"])
        response.delete_cookie(SESSION_COOKIE, secure=True, httponly=True, samesite="lax")
        return {"ok": True}

    @router.get("/sessions")
    def sessions(request: Request):
        return {"items": accounts.sessions(request.state.account["user_id"]), "current": request.state.account["id"]}

    @router.delete("/sessions/{sid}")
    def revoke(sid: str, request: Request):
        accounts.revoke(request.state.account["user_id"], None if sid == "all" else sid)
        return {"ok": True}

    @router.post("/password")
    def password(body: ChangePassword, request: Request):
        accounts.change_password(request.state.account, body.current, body.password, body.code)
        return {"ok": True, "login_required": True}

    @router.post("/2fa/setup")
    def setup(request: Request):
        if request.state.account["created_at"] < time.time() - 300:
            raise AccessDenied("Vuelve a iniciar sesión antes de configurar 2FA")
        return accounts.setup_totp(request.state.account["user_id"])

    @router.post("/2fa/confirm")
    def confirm(body: Factor, request: Request):
        return {"recovery_codes": accounts.confirm_totp(request.state.account, body.code)}

    @router.post("/2fa/verify")
    def verify(body: Factor, request: Request):
        accounts.verify_totp(request.state.account, body.code, body.remember)
        return {"ok": True}

    return router


def install_errors(app):
    @app.exception_handler(RateLimited)
    async def throttled(_request, _exc):
        return JSONResponse({"detail": "Demasiados intentos"}, 429, headers={"Retry-After": "900"})

    @app.exception_handler(AccessDenied)
    async def denied(_request, exc):
        return JSONResponse({"detail": str(exc)}, 400)

