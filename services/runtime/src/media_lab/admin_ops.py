"""Account administration and resumable, owner-scoped account erasure."""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import sqlite3
import time

from fastapi import HTTPException, Request
from pydantic import Field

from .security import as_owner, owner, password_matches
from .tenancy import NotOwned
from .web_auth import Strict


class Identity(Strict):
    username: str = Field(min_length=3, max_length=40)


class UserUpdate(Identity):
    role: str = Field(pattern="^(admin|member)$")


class Erasure(Strict):
    confirmation: str = Field(max_length=40)
    password: str = Field(max_length=128)
    code: str = Field(max_length=30)


def protect_last_admin(db, uid):
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        raise NotOwned()
    if row["role"] == "admin" and row["enabled"] and db.execute(
        "SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0] <= 1:
        raise HTTPException(409, "Debe quedar al menos un administrador habilitado")
    return row


class AdminOperations:
    def __init__(self, app, accounts, store, mail, artifacts, agent_request, runtime):
        self.accounts, self.store, self.mail = accounts, store, mail
        self.artifacts, self.agent_request, self.runtime = artifacts, agent_request, runtime
        self.app = app
        self.lock = asyncio.Lock()
        with accounts.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account_deletions(user_id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL,status TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS invitation_records(id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,
                    email TEXT NOT NULL,created_at REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
            """)
            import uuid
            for row in db.execute("SELECT token_hash,email FROM account_links WHERE kind='invite'").fetchall():
                db.execute("INSERT OR IGNORE INTO invitation_records VALUES(?,?,?,?,0)",
                           (uuid.uuid4().hex, row["token_hash"], row["email"], time.time()))

        def editable(db, uid):
            if db.execute("SELECT 1 FROM account_deletions WHERE user_id=? AND status!='completed'", (uid,)).fetchone():
                raise HTTPException(409, "La cuenta está en proceso de eliminación")

        def rename(db, uid, value):
            value = accounts.username(value)
            previous = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
            if not previous:
                raise NotOwned()
            try:
                db.execute("DELETE FROM identities WHERE identity=? AND user_id=?", (previous[0], uid))
                db.execute("INSERT INTO identities VALUES(?,?)", (value, uid))
                db.execute("UPDATE users SET username=? WHERE id=?", (value, uid))
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, "El nombre de usuario ya está en uso") from exc

        @app.get('/v1/account/profile')
        def own_profile():
            with accounts.db() as db:
                row = db.execute("SELECT id,username,email,role,profile,daily_limit,storage_limit,created_at FROM users WHERE id=?", (owner(),)).fetchone()
                return dict(row)

        @app.put('/v1/account/profile')
        def edit_own(body: Identity):
            with accounts.db() as db:
                db.execute('BEGIN IMMEDIATE')
                editable(db, owner())
                rename(db, owner(), body.username)
            return {"ok": True}

        @app.put('/v1/admin/users/{uid}')
        def edit_user(uid: str, body: UserUpdate):
            with accounts.db() as db:
                db.execute('BEGIN IMMEDIATE')
                editable(db, uid)
                previous = db.execute('SELECT role FROM users WHERE id=?', (uid,)).fetchone()
                if not previous:
                    raise NotOwned()
                if previous[0] != body.role:
                    if body.role != 'admin':
                        protect_last_admin(db, uid)
                    db.execute('DELETE FROM auth_sessions WHERE user_id=?', (uid,))
                    self.accounts.revoke_external_tokens(db, uid)
                rename(db, uid, body.username)
                db.execute('UPDATE users SET role=? WHERE id=?', (body.role, uid))
                accounts.audit(db, owner(), 'user-update', uid)
            return {"ok": True}

        @app.get('/v1/admin/users/{uid}/sessions')
        def sessions(uid: str):
            return {"items": accounts.sessions(uid)}

        @app.delete('/v1/admin/users/{uid}/sessions/{sid}')
        def revoke(uid: str, sid: str):
            accounts.revoke(uid, None if sid == 'all' else sid)
            with accounts.db() as db:
                accounts.audit(db, owner(), 'sessions-revoke', uid)
            return {"ok": True}

        @app.get('/v1/admin/invitations')
        def invitations():
            with accounts.db() as db:
                rows = db.execute("SELECT r.id,r.email,r.created_at,r.revoked,l.expires_at,l.consumed FROM invitation_records r JOIN account_links l ON l.token_hash=r.token_hash ORDER BY r.created_at DESC LIMIT 500").fetchall()
            return {"items": [{**dict(r), "status": 'revoked' if r['revoked'] else 'accepted' if r['consumed'] else 'expired' if r['expires_at'] <= time.time() else 'pending'} for r in rows]}

        @app.post('/v1/admin/invitations/{iid}/resend')
        def resend(iid: str):
            with accounts.db() as db:
                row = db.execute('SELECT email FROM invitation_records WHERE id=?', (iid,)).fetchone()
            if not row:
                raise NotOwned()
            return {"outbox_id": mail.invite(row[0], owner())}

        @app.delete('/v1/admin/invitations/{iid}')
        def revoke_invitation(iid: str):
            with accounts.db() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT token_hash FROM invitation_records WHERE id=?', (iid,)).fetchone()
                if not row:
                    raise NotOwned()
                db.execute('UPDATE invitation_records SET revoked=1 WHERE id=?', (iid,))
                db.execute('UPDATE account_links SET consumed=1 WHERE token_hash=?', (row[0],))
                accounts.audit(db, owner(), 'invite-revoke', iid)
            return {"ok": True}

        @app.post('/v1/admin/users/{uid}/delete', status_code=202)
        async def delete_user(uid: str, body: Erasure, request: Request):
            actor = owner()
            if uid == actor:
                raise HTTPException(409, 'No puedes eliminar tu propia cuenta administrativa')
            accounts.limit(request.state.account['ip'], actor, 'delete-account')
            with accounts.db() as db:
                db.execute('BEGIN IMMEDIATE')
                target = protect_last_admin(db, uid)
                admin = db.execute('SELECT password_hash FROM users WHERE id=?', (actor,)).fetchone()
                if body.confirmation != target['username'] or not password_matches(admin[0], body.password):
                    raise HTTPException(403, 'Confirma el usuario y tu contraseña')
                accounts._factor(db, actor, body.code)
                now = time.time()
                db.execute("INSERT INTO account_deletions VALUES(?,?,'pending',?,?) ON CONFLICT(user_id) DO UPDATE SET status='pending',updated_at=excluded.updated_at", (uid, actor, now, now))
                db.execute('UPDATE users SET enabled=0 WHERE id=?', (uid,))
                db.execute('DELETE FROM auth_sessions WHERE user_id=?', (uid,))
                db.execute('UPDATE account_links SET consumed=1 WHERE user_id=? OR email=?', (uid, target['email']))
                db.execute("UPDATE jobs SET cancel_requested=1 WHERE owner_id=? AND status IN ('running','queued')", (uid,))
                accounts.audit(db, actor, 'user-delete-request', uid)
            return {"status": "pending"}

        @app.get('/v1/admin/deletions')
        def deletion_states():
            with accounts.db() as db:
                return {"items": [dict(r) for r in db.execute('SELECT * FROM account_deletions ORDER BY created_at DESC LIMIT 100')]}

        @app.post('/v1/admin/users/{uid}/delete/retry', status_code=202)
        def retry(uid: str):
            with accounts.db() as db:
                if not db.execute("UPDATE account_deletions SET status='pending',updated_at=? WHERE user_id=? AND status='failed'", (time.time(), uid)).rowcount:
                    raise HTTPException(409, 'No hay una eliminación pendiente de reintento')
            return {"status": "pending"}

    async def run(self):
        while True:
            await self.tick()
            await asyncio.sleep(2)

    async def tick(self):
        async with self.lock:
            with self.accounts.db() as db:
                rows = db.execute("SELECT * FROM account_deletions WHERE status IN ('pending','waiting')").fetchall()
            for row in rows:
                try:
                    await self.purge(row['user_id'])
                except HTTPException as exc:
                    self.state(row['user_id'], 'waiting' if exc.status_code == 409 else 'failed')
                except Exception:
                    self.state(row['user_id'], 'failed')

    def state(self, uid, status):
        with self.accounts.db() as db:
            db.execute('UPDATE account_deletions SET status=?,updated_at=? WHERE user_id=?', (status, time.time(), uid))

    async def purge(self, uid):
        with self.accounts.request_lock:
            if self.accounts.inflight_requests.get(uid):
                raise HTTPException(409, 'Esperando que finalicen las solicitudes de la cuenta')
        with self.accounts.db() as db:
            user = db.execute('SELECT email FROM users WHERE id=?', (uid,)).fetchone()
            if not user:
                self.state(uid, 'completed')
                return
            all_jobs = [r[0] for r in db.execute('SELECT id FROM jobs WHERE owner_id=?', (uid,))]
            jobs = [r[0] for r in db.execute("SELECT id FROM jobs WHERE owner_id=? AND status IN ('queued','running')", (uid,))]
            sessions = [r[0] for r in db.execute('SELECT id FROM sessions WHERE owner_id=?', (uid,))]
        if self.runtime:
            with as_owner(uid):
                for jid in jobs:
                    self.runtime.workers.cancel(jid)
            with self.runtime.workers.lock:
                if any(j in self.runtime.workers.assigned or j in self.runtime.workers.executing for j in all_jobs):
                    raise HTTPException(409, 'Esperando la detención de los trabajos')
            await self.agent_request(uid, 'POST', '/purge', {})
        root = self.artifacts.root.resolve()
        for sid in sessions:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', sid):
                raise ValueError('Unsafe session')
            folder = root / sid
            if folder.resolve() != folder or root not in folder.resolve().parents:
                raise ValueError('Unsafe artifact directory')
            if folder.exists():
                shutil.rmtree(folder)
        with self.accounts.db() as db:
            db.execute('BEGIN IMMEDIATE')
            for item in db.execute('SELECT id,payload FROM mail_outbox').fetchall():
                data = json.loads(self.accounts.vault.open(item['payload'], f"mail:{item['id']}"))
                if data.get('recipient') == user['email']:
                    db.execute('DELETE FROM mail_outbox WHERE id=?', (item['id'],))
            db.execute('DELETE FROM invitation_records WHERE email=?', (user['email'],))
            db.execute('DELETE FROM account_links WHERE user_id=? OR email=?', (uid, user['email']))
            db.execute('DELETE FROM idempotency WHERE job_id IN (SELECT id FROM jobs WHERE owner_id=?)', (uid,))
            loras = [r[0] for r in db.execute('SELECT sha256 FROM loras WHERE owner_id=? AND sha256 IS NOT NULL', (uid,))]
            for table in ('messages', 'agent_runs', 'artifacts', 'jobs', 'sessions', 'user_preferences', 'user_providers', 'saved_providers',
                          'characters', 'loras'):
                db.execute(f'DELETE FROM {table} WHERE owner_id=?', (uid,))
            for table in ('identities', 'auth_sessions', 'recovery_codes'):
                db.execute(f'DELETE FROM {table} WHERE user_id=?', (uid,))
            db.execute('DELETE FROM agent_admissions WHERE owner_id=?', (uid,))
            db.execute('DELETE FROM provider_endpoints WHERE owner_id=?', (uid,))
            db.execute('DELETE FROM users WHERE id=?', (uid,))
            self.accounts.audit(db, 'system', 'user-delete-completed', uid)
            db.execute("UPDATE account_deletions SET status='completed',updated_at=? WHERE user_id=?", (time.time(), uid))
        library = getattr(self.app.state, 'loras', None)
        for sha in loras if library else ():
            library._collect(sha)
