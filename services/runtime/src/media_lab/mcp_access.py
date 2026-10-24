"""Account-owned, hashed, expiring MCP credentials. Browser management only."""
import json
import secrets
import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .accounts import AccessDenied
from .security import digest, owner, password_matches
from .tenancy import NotOwned

SCOPES = {"read", "create", "agent", "delete"}


class Credential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=80)
    days: int = Field(default=90, ge=1, le=365)
    scopes: list[str] = Field(default_factory=lambda: ["read", "create", "agent"], min_length=1, max_length=4)
    password: str = Field(max_length=128)
    code: str = Field(default="", max_length=30)


class Toggle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class McpAccess:
    def __init__(self, accounts, origin):
        self.accounts, self.origin = accounts, origin
        with accounts.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS mcp_accounts(
                    owner_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS mcp_tokens(
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash TEXT UNIQUE NOT NULL, label TEXT NOT NULL, scopes TEXT NOT NULL,
                    created_at REAL NOT NULL, expires_at REAL NOT NULL, last_used_at REAL, revoked_at REAL);
                CREATE INDEX IF NOT EXISTS mcp_token_owner ON mcp_tokens(owner_id);
            """)

    def status(self):
        with self.accounts.db() as db:
            row = db.execute('SELECT enabled FROM mcp_accounts WHERE owner_id=?', (owner(),)).fetchone()
            items = [dict(r) for r in db.execute('SELECT id,label,scopes,created_at,expires_at,last_used_at,revoked_at FROM mcp_tokens WHERE owner_id=? ORDER BY created_at DESC LIMIT 100', (owner(),))]
        for item in items:
            item['scopes'] = json.loads(item['scopes'])
        return {'enabled': bool(row and row[0]), 'endpoint': self.origin + '/mcp', 'items': items}

    def toggle(self, enabled):
        uid = owner()
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO mcp_accounts VALUES(?,?) ON CONFLICT(owner_id) DO UPDATE SET enabled=excluded.enabled', (uid, enabled))
            if not enabled:
                db.execute('UPDATE mcp_tokens SET revoked_at=? WHERE owner_id=? AND revoked_at IS NULL', (time.time(), uid))
            self.accounts.audit(db, uid, 'mcp-enabled' if enabled else 'mcp-disabled', uid)
        return self.status()

    def mint(self, body, session, rotate=None):
        uid = owner()
        self.accounts.limit(session['ip'], uid, 'mcp-mint')
        scopes = sorted(set(body.scopes))
        if not set(scopes) <= SCOPES or 'read' not in scopes or not body.label.strip():
            raise HTTPException(422, 'Incluye lectura y selecciona permisos válidos')
        token, tid, now = 'rvl_mcp_' + secrets.token_urlsafe(32), uuid.uuid4().hex, time.time()
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            user = db.execute('SELECT * FROM users WHERE id=? AND enabled=1', (uid,)).fetchone()
            if not user or not password_matches(user['password_hash'], body.password):
                raise AccessDenied('Credenciales inválidas')
            if user['totp_secret']:
                self.accounts._factor(db, uid, body.code)
            enabled = db.execute('SELECT enabled FROM mcp_accounts WHERE owner_id=?', (uid,)).fetchone()
            if not enabled or not enabled[0]:
                raise HTTPException(409, 'Habilita MCP antes de crear un token')
            if rotate and not db.execute('UPDATE mcp_tokens SET revoked_at=? WHERE id=? AND owner_id=? AND revoked_at IS NULL', (now, rotate, uid)).rowcount:
                raise NotOwned()
            if db.execute('SELECT COUNT(*) FROM mcp_tokens WHERE owner_id=? AND revoked_at IS NULL AND expires_at>?', (uid, now)).fetchone()[0] >= 20:
                raise HTTPException(409, 'Revoca un token antes de añadir otro (máximo 20 activos)')
            db.execute('INSERT INTO mcp_tokens VALUES(?,?,?,?,?,?,?,NULL,NULL)', (tid, uid, digest(token), body.label.strip(), json.dumps(scopes), now, now + body.days * 86400))
            self.accounts.audit(db, uid, 'mcp-token-rotated' if rotate else 'mcp-token-created', tid)
        return {'token': token, 'id': tid, 'expires_at': now + body.days * 86400}

    def authenticate(self, token, touch=True):
        if not token.startswith('rvl_mcp_') or len(token) > 128:
            raise AccessDenied('Token MCP inválido o caducado')
        with self.accounts.db() as db:
            row = db.execute('SELECT t.id,t.owner_id,t.scopes FROM mcp_tokens t JOIN mcp_accounts m ON m.owner_id=t.owner_id JOIN users u ON u.id=t.owner_id WHERE t.token_hash=? AND t.revoked_at IS NULL AND t.expires_at>? AND m.enabled=1 AND u.enabled=1', (digest(token), time.time())).fetchone()
            if not row:
                raise AccessDenied('Token MCP inválido o caducado')
            if touch:
                db.execute('UPDATE mcp_tokens SET last_used_at=? WHERE id=? AND (last_used_at IS NULL OR last_used_at<?)', (time.time(), row['id'], time.time() - 60))
        return {'id': row['id'], 'owner_id': row['owner_id'], 'scopes': json.loads(row['scopes'])}

    def revoke(self, tid):
        with self.accounts.db() as db:
            if not db.execute('UPDATE mcp_tokens SET revoked_at=COALESCE(revoked_at,?) WHERE id=? AND owner_id=?', (time.time(), tid, owner())).rowcount:
                raise NotOwned()
            self.accounts.audit(db, owner(), 'mcp-token-revoked', tid)
        return {'ok': True}

    def router(self):
        router = APIRouter(prefix='/v1/account/mcp')
        router.add_api_route('', self.status, methods=['GET'])

        @router.put('')
        def toggle(body: Toggle):
            return self.toggle(body.enabled)

        @router.post('/tokens')
        def create(body: Credential, request: Request):
            return self.mint(body, request.state.account)

        @router.post('/tokens/{tid}/rotate')
        def rotate(tid: str, body: Credential, request: Request):
            return self.mint(body, request.state.account, tid)

        router.add_api_route('/tokens/{tid}', self.revoke, methods=['DELETE'])
        return router
