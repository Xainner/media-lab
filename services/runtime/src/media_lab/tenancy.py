"""Owner-scoped runtime persistence. No administrator content bypass exists."""
from __future__ import annotations

import hashlib
import json
import re
import time
import shutil
from pathlib import Path

from .artifacts import ArtifactStore
from .security import owner
from .store import IdempotencyConflict, Store


class NotOwned(Exception):
    pass


class ResourceLimit(Exception):
    pass


class TenantStore(Store):
    def _init(self):
        with self._db() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='web_schema'").fetchone():
                raise RuntimeError("initialize accounts in a fresh web state first")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
                    session_id TEXT NOT NULL REFERENCES sessions(id), operation TEXT NOT NULL,
                    status TEXT NOT NULL, request_json TEXT NOT NULL, result_json TEXT, error TEXT,
                    activity_json TEXT NOT NULL DEFAULT '[]', progress_json TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL, started_at REAL, completed_at REAL
                );
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL REFERENCES users(id),
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content TEXT NOT NULL, media_json TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts(
                    uri TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id),
                    session_id TEXT NOT NULL REFERENCES sessions(id), sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL, bytes INTEGER NOT NULL, metadata TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS artifacts_owner ON artifacts(owner_id,created_at DESC);
                CREATE INDEX IF NOT EXISTS jobs_owner ON jobs(owner_id,status,created_at);
                CREATE TABLE IF NOT EXISTS user_preferences(
                    owner_id TEXT NOT NULL REFERENCES users(id),key TEXT NOT NULL,value TEXT NOT NULL,updated_at REAL NOT NULL,
                    PRIMARY KEY(owner_id,key)
                );
                CREATE TABLE IF NOT EXISTS agent_runs(
                    id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id),session_id TEXT NOT NULL REFERENCES sessions(id),
                    status TEXT NOT NULL,updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS loras(
                    id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,base TEXT,
                    source_url TEXT NOT NULL,page TEXT,revision TEXT,file TEXT,sha256 TEXT,bytes INTEGER,total INTEGER,
                    trigger TEXT NOT NULL DEFAULT '',strength REAL NOT NULL DEFAULT 1.0,status TEXT NOT NULL,error TEXT,
                    created_at REAL NOT NULL,updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS loras_owner ON loras(owner_id,created_at DESC);
                CREATE TABLE IF NOT EXISTS characters(
                    id TEXT PRIMARY KEY,owner_id TEXT NOT NULL REFERENCES users(id),handle TEXT NOT NULL,name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',references_json TEXT NOT NULL,lora_id TEXT,
                    created_at REAL NOT NULL,updated_at REAL NOT NULL,UNIQUE(owner_id,handle)
                );
            """)
        super()._init()

    @staticmethod
    def _ensure(db, sid: str, uid: str, title: str):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", sid):
            raise ValueError("invalid session id")
        if not db.execute('SELECT 1 FROM users WHERE id=? AND enabled=1', (uid,)).fetchone():
            raise NotOwned('resource not found')
        existing = db.execute("SELECT owner_id FROM sessions WHERE id=?", (sid,)).fetchone()
        if existing and existing[0] != uid:
            raise NotOwned("resource not found")
        now = time.time()
        db.execute("INSERT OR IGNORE INTO sessions VALUES(?,?,?,?,?)", (sid, uid, title[:120] or "Nueva sesión", now, now))
        db.execute("UPDATE sessions SET updated_at=? WHERE id=? AND owner_id=?", (now, sid, uid))

    def ensure_session(self, session_id, title="Nueva sesión"):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure(db, session_id, owner(), title)
        return session_id

    def create_job_once(self, job_id, session_id, operation, request, max_pending=None, key=None, scope=None):
        uid = owner()
        if key is not None and (not key or len(key) > 128 or not key.isascii() or any(ord(c) < 33 for c in key)):
            raise ValueError("invalid Idempotency-Key")
        scope = f"{uid}:{scope or operation}"
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        now = time.time()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT * FROM users WHERE id=? AND enabled=1", (uid,)).fetchone()
            if not user:
                raise NotOwned("resource not found")
            prior = db.execute("SELECT * FROM idempotency WHERE scope=? AND key=?", (scope, key)).fetchone() if key else None
            if prior:
                if prior["body_hash"] != fingerprint:
                    raise IdempotencyConflict("Idempotency-Key already used with a different request")
                return prior["job_id"], False
            # Session and nested reference authorization are inside the admission transaction.
            self._ensure(db, session_id, uid, request.get("prompt") or request.get("title") or "Nueva sesión")
            self._check_refs(db, request, uid)
            if shutil.disk_usage(self.path.parent).free < 10 * 1024 ** 3:
                raise ResourceLimit("Protección global: quedan menos de 10 GiB libres")
            counts = dict(db.execute("SELECT status,COUNT(*) FROM jobs WHERE status IN ('queued','running') GROUP BY status"))
            if max_pending is not None and counts.get("queued", 0) >= max_pending:
                return "", False
            own = db.execute("SELECT COUNT(*) FROM jobs WHERE owner_id=? AND status IN ('queued','running')", (uid,)).fetchone()[0]
            if user["active_limit"] and own >= user["active_limit"] + (user["pending_limit"] or 0):
                raise ResourceLimit("Se alcanzó el límite de trabajos de tu perfil")
            if user["daily_limit"] is not None:
                today = int(now // 86400) * 86400
                used = db.execute("SELECT COUNT(*) FROM jobs WHERE owner_id=? AND created_at>=?", (uid, today)).fetchone()[0]
                if used >= user["daily_limit"]:
                    raise ResourceLimit("Se alcanzó el cupo diario")
            db.execute("INSERT INTO jobs(id,owner_id,session_id,operation,status,request_json,created_at,updated_at) "
                       "VALUES(?,?,?,?,'queued',?,?,?)", (job_id, uid, session_id, operation, self._json(request), now, now))
            if key:
                db.execute("INSERT INTO idempotency VALUES(?,?,?,?)", (scope, key, fingerprint, job_id))
        return job_id, True

    @classmethod
    def _check_refs(cls, db, value, uid):
        if isinstance(value, list):
            for item in value:
                cls._check_refs(db, item, uid)
        elif isinstance(value, dict):
            if "uri" in value:
                row = db.execute("SELECT sha256 FROM artifacts WHERE uri=? AND owner_id=?", (value["uri"], uid)).fetchone()
                if not row or not secrets_equal(row[0], value.get("sha256", "")):
                    raise NotOwned("resource not found")
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    cls._check_refs(db, nested, uid)

    def get_job(self, job_id):
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND owner_id=?", (job_id, owner())).fetchone()
        return self._job(row) if row else None

    def update_job(self, job_id, **values):
        if not self.get_job(job_id):
            raise NotOwned("resource not found")
        super().update_job(job_id, **values)

    def request_cancel(self, job_id):
        return bool(self.get_job(job_id)) and super().request_cancel(job_id)

    def cancel_requested(self, job_id):
        job = self.get_job(job_id)
        return bool(job and job["cancel_requested"])

    def queue_position(self, job_id):
        return super().queue_position(job_id) if self.get_job(job_id) else None

    def lookup_idempotency(self, scope, key):
        return super().lookup_idempotency(f"{owner()}:{scope}", key)

    def add_message(self, session_id, role, content, media):
        uid = owner()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure(db, session_id, uid, content)
            self._check_refs(db, media, uid)
            db.execute("INSERT INTO messages(owner_id,session_id,role,content,media_json,created_at) VALUES(?,?,?,?,?,?)",
                       (uid, session_id, role, content, self._json(media), time.time()))

    def list_sessions(self, limit=100):
        with self._db() as db:
            return [dict(r) for r in db.execute("SELECT id,title,created_at,updated_at FROM sessions WHERE owner_id=? "
                                               "ORDER BY updated_at DESC LIMIT ?", (owner(), limit))]

    def session(self, session_id):
        with self._db() as db:
            if not db.execute("SELECT 1 FROM sessions WHERE id=? AND owner_id=?", (session_id, owner())).fetchone():
                return None
        return super().session(session_id)

    def set_setting(self, key, value):
        with self._db() as db:
            db.execute("INSERT INTO user_preferences VALUES(?,?,?,?) ON CONFLICT(owner_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                       (owner(), key, value, time.time()))

    def get_setting(self, key, default=""):
        with self._db() as db:
            row = db.execute("SELECT value FROM user_preferences WHERE owner_id=? AND key=?", (owner(), key)).fetchone()
        return row[0] if row else default

    def register_artifact(self, path, meta):
        uid, size = owner(), path.stat().st_size
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT storage_limit,enabled FROM users WHERE id=?", (uid,)).fetchone()
            if not user or not user["enabled"]:
                raise NotOwned("resource not found")
            used = db.execute("SELECT COALESCE(SUM(bytes),0) FROM artifacts WHERE owner_id=?", (uid,)).fetchone()[0]
            if user["storage_limit"] is not None and used + size > user["storage_limit"]:
                raise ResourceLimit("Se alcanzó la cuota de almacenamiento")
            self._ensure(db, meta["uri"].split("/")[2], uid, "Nueva sesión")
            self._check_refs(db, meta.get("references", []), uid)
            db.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?)", (meta["uri"], uid,
                       meta["uri"].split("/")[2], meta["sha256"], meta["uri"].split("/")[3], size,
                       self._json(meta), meta.get("created_at", time.time())))

    def artifact(self, uri, sha=None):
        with self._db() as db:
            row = db.execute("SELECT * FROM artifacts WHERE uri=? AND owner_id=?", (uri, owner())).fetchone()
        if not row or (sha is not None and not secrets_equal(row["sha256"], sha)):
            raise NotOwned("resource not found")
        return dict(row)

    def library(self, query="", kind=""):
        with self._db() as db:
            rows = db.execute("SELECT metadata,kind FROM artifacts WHERE owner_id=? ORDER BY created_at DESC", (owner(),)).fetchall()
        return [{**self._decode(r["metadata"], {}), "kind": r["kind"]} for r in rows
                if (not kind or r["kind"] == kind) and query.casefold() in r["metadata"].casefold()]


def secrets_equal(left, right):
    import secrets
    return isinstance(right, str) and secrets.compare_digest(left, right.lower())


class TenantArtifacts(ArtifactStore):
    def __init__(self, store, *args):
        self.store = store
        super().__init__(*args)

    def _session(self, value):
        if value == "direct":
            value = owner() + "_direct"
        value = ArtifactStore._session(value)
        with self.store._db() as db:
            existing = db.execute("SELECT owner_id FROM sessions WHERE id=?", (value,)).fetchone()
        if existing and existing[0] != owner():
            raise NotOwned("resource not found")
        if not existing:
            self.store.ensure_session(value)
        return value

    def _sidecar(self, path, data):
        try:
            if shutil.disk_usage(self.root).free < 10 * 1024 ** 3:
                raise ResourceLimit("Protección global de espacio libre")
            self.store.register_artifact(path, data)
        except Exception:
            # Only remove this newly created, unregistered file.
            path.unlink(missing_ok=True)
            raise
        super()._sidecar(path, data)

    def resolve(self, uri, sha256=None):
        row = self.store.artifact(uri, sha256)
        return super().resolve(uri, row["sha256"])

    def gallery(self, limit=100):
        return self.store.library(kind="images")[:limit]

    def search_library(self, query="", kind_filter=""):
        return self.store.library(query, kind_filter)

    def delete_image(self, uri, sha256):
        return self.delete_media(uri, sha256)

    def delete_media(self, uri, sha256):
        row = self.store.artifact(uri, sha256)
        path = self.resolve(uri, sha256)
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT request_json,result_json FROM jobs WHERE status IN ('queued','running') AND owner_id=?", (owner(),)).fetchall()
            if any(uri in (job["request_json"] + (job["result_json"] or "")) for job in active):
                raise ResourceLimit("El archivo está en uso por un trabajo activo")
            # Commit after filesystem removal; never expose a file outside its registry.
            path.unlink()
            path.with_name(path.name + ".json").unlink(missing_ok=True)
            db.execute("DELETE FROM artifacts WHERE uri=? AND owner_id=?", (row["uri"], owner()))


