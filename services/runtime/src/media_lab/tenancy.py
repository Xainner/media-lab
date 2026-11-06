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
            # Messages the agent mirrors name their run, so deleting the run deletes them too.
            if "run_id" not in {r[1] for r in db.execute("PRAGMA table_info(messages)")}:
                db.execute("ALTER TABLE messages ADD COLUMN run_id TEXT")
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
            self._ensure(db, session_id, uid, request.get("prompt") or request.get("title")
                         or " · ".join(request.get("phrases") or []) or "Nueva sesión")
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

    def add_message(self, session_id, role, content, media, run=None):
        uid = owner()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._ensure(db, session_id, uid, content)
            self._check_refs(db, media, uid)
            db.execute("INSERT INTO messages(owner_id,session_id,role,content,media_json,created_at,run_id) VALUES(?,?,?,?,?,?,?)",
                       (uid, session_id, role, content, self._json(media), time.time(), run))

    def forget_run(self, run_id, mirrored=()):
        """Delete an agent run's record and the messages it mirrored into its session.

        Messages mirrored before run_id existed are matched by role and exact content.
        """
        uid = owner()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT session_id FROM agent_runs WHERE id=? AND owner_id=?", (run_id, uid)).fetchone()
            if not row:
                raise NotOwned("resource not found")
            db.execute("DELETE FROM messages WHERE owner_id=? AND run_id=?", (uid, run_id))
            for message in mirrored:
                db.execute("DELETE FROM messages WHERE owner_id=? AND session_id=? AND run_id IS NULL AND role=? AND content=?",
                           (uid, row[0], str(message.get("role", "")), str(message.get("content", ""))))
            db.execute("DELETE FROM agent_runs WHERE id=? AND owner_id=?", (run_id, uid))
        self.flush_deleted()

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
    KINDS = {"images", "references", "sources", "songs", "videos", "productions"}

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

    # Deleting is complete: the file, its registry row and every record that only existed for it
    # (the job with its prompt once its last output is gone, transfer links, attachments in
    # messages and character references). Each returns {"uris", "jobs"} so the agent can forget
    # them too. Files are removed inside the transaction; a file never outlives its registry row.

    def delete_media(self, uri, sha256):
        row = self.store.artifact(uri, sha256)
        uid = owner()
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._refuse_in_use(db, uid, {row["uri"]})
            self._unlink(row["uri"])
            jobs = self._forget(db, uid, {row["uri"]})
        self.store.flush_deleted()
        return {"uris": [row["uri"]], "jobs": jobs}

    def delete_job(self, job_id):
        uid = owner()
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT status,result_json FROM jobs WHERE id=? AND owner_id=?", (job_id, uid)).fetchone()
            if not job:
                raise NotOwned("resource not found")
            if job["status"] in {"queued", "running"}:
                raise ResourceLimit("Cancela el trabajo antes de borrarlo")
            outputs = self._live(db, uid, self._outputs(job["result_json"]))
            self._refuse_in_use(db, uid, outputs)
            for uri in outputs:
                self._unlink(uri)
            jobs = self._forget(db, uid, outputs)
            if job_id not in jobs:
                self._drop_job(db, job_id)
                jobs.append(job_id)
        self.store.flush_deleted()
        return {"uris": sorted(outputs), "jobs": jobs}

    def delete_session(self, session_id):
        uid = owner()
        with self.store._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM sessions WHERE id=? AND owner_id=?", (session_id, uid)).fetchone():
                raise NotOwned("resource not found")
            if db.execute("SELECT 1 FROM jobs WHERE session_id=? AND owner_id=? AND status IN ('queued','running')",
                          (session_id, uid)).fetchone():
                raise ResourceLimit("La sesión tiene trabajos activos")
            uris = {r[0] for r in db.execute("SELECT uri FROM artifacts WHERE session_id=? AND owner_id=?", (session_id, uid))}
            self._refuse_in_use(db, uid, uris)
            folder = self._folder(session_id)
            if folder.exists():
                shutil.rmtree(folder)
            jobs = self._forget(db, uid, uris)
            for (job_id,) in db.execute("SELECT id FROM jobs WHERE session_id=? AND owner_id=?", (session_id, uid)).fetchall():
                self._drop_job(db, job_id)
                jobs.append(job_id)
            db.execute("DELETE FROM agent_runs WHERE session_id=? AND owner_id=?", (session_id, uid))
            if self._has(db, "mcp_transfers"):
                db.execute("DELETE FROM mcp_transfers WHERE session_id=? AND owner_id=?", (session_id, uid))
            db.execute("DELETE FROM messages WHERE session_id=? AND owner_id=?", (session_id, uid))
            db.execute("DELETE FROM sessions WHERE id=? AND owner_id=?", (session_id, uid))
        self.store.flush_deleted()
        return {"uris": sorted(uris), "jobs": jobs}

    @staticmethod
    def _refuse_in_use(db, uid, uris):
        active = db.execute("SELECT request_json,result_json FROM jobs WHERE status IN ('queued','running') AND owner_id=?", (uid,)).fetchall()
        if any(uri in job["request_json"] + (job["result_json"] or "") for job in active for uri in uris):
            raise ResourceLimit("El archivo está en uso por un trabajo activo")

    @staticmethod
    def _outputs(result_json):
        """URIs a job produced: its result media, not the inputs its provenance mentions."""
        result = TenantStore._decode(result_json, {})
        media = result.get("media") if isinstance(result, dict) else None
        return {m["uri"] for m in media or [] if isinstance(m, dict) and isinstance(m.get("uri"), str)}

    @staticmethod
    def _live(db, uid, uris):
        uris = list(uris)
        if not uris:
            return set()
        marks = ",".join("?" * len(uris))
        return {r[0] for r in db.execute(f"SELECT uri FROM artifacts WHERE owner_id=? AND uri IN ({marks})", (uid, *uris))}

    @staticmethod
    def _has(db, table):
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())

    def _drop_job(self, db, job_id):
        job = db.execute("SELECT owner_id,session_id,request_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        db.execute("DELETE FROM idempotency WHERE job_id=?", (job_id,))
        db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        if job:
            request = TenantStore._decode(job["request_json"], {})
            prompt = request.get("prompt") or request.get("title") if isinstance(request, dict) else None
            self._prune_session(db, job["owner_id"], job["session_id"], prompt)

    def _prune_session(self, db, uid, session_id, prompt):
        """A session left empty goes too; one whose title is the deleted prompt loses that title."""
        checks = [("jobs", "session_id"), ("artifacts", "session_id"), ("messages", "session_id"),
                  ("agent_runs", "session_id")]
        if self._has(db, "mcp_transfers"):
            checks.append(("mcp_transfers", "session_id"))
        if not any(db.execute(f"SELECT 1 FROM {table} WHERE {column}=? AND owner_id=? LIMIT 1",
                              (session_id, uid)).fetchone() for table, column in checks):
            db.execute("DELETE FROM sessions WHERE id=? AND owner_id=?", (session_id, uid))
            try:
                folder = self._folder(session_id)
            except ValueError:
                return
            for sub in sorted(folder.glob("*"), reverse=True) if folder.is_dir() else ():
                if sub.is_dir() and not sub.is_symlink() and not any(sub.iterdir()):
                    sub.rmdir()
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        elif isinstance(prompt, str) and prompt:
            db.execute("UPDATE sessions SET title='Nueva sesión' WHERE id=? AND owner_id=? AND title=?",
                       (session_id, uid, prompt[:120]))

    def _forget(self, db, uid, uris):
        """Remove every record of these deleted files; returns the jobs deleted with them."""
        if not uris:
            return []
        marks = ",".join("?" * len(uris))
        db.execute(f"DELETE FROM artifacts WHERE owner_id=? AND uri IN ({marks})", (uid, *uris))
        if self._has(db, "mcp_transfers"):
            db.execute(f"DELETE FROM mcp_transfers WHERE owner_id=? AND uri IN ({marks})", (uid, *uris))
        gone = []
        for job in db.execute("SELECT id,result_json FROM jobs WHERE owner_id=? AND status NOT IN ('queued','running')",
                              (uid,)).fetchall():
            outputs = self._outputs(job["result_json"])
            if not outputs & uris:
                continue
            if self._live(db, uid, outputs - uris):
                # Other outputs remain and the prompt is theirs too; only this one is dropped.
                result = TenantStore._decode(job["result_json"], {})
                result["media"] = [m for m in result["media"] if not (isinstance(m, dict) and m.get("uri") in uris)]
                db.execute("UPDATE jobs SET result_json=? WHERE id=?", (TenantStore._json(result), job["id"]))
            else:
                self._drop_job(db, job["id"])
                gone.append(job["id"])
        for table, column in (("messages", "media_json"), ("characters", "references_json")):
            for row in db.execute(f"SELECT rowid,{column} FROM {table} WHERE owner_id=?", (uid,)).fetchall():
                refs = TenantStore._decode(row[1], [])
                kept = [r for r in refs if not (isinstance(r, dict) and r.get("uri") in uris)] if isinstance(refs, list) else refs
                if kept != refs:
                    db.execute(f"UPDATE {table} SET {column}=? WHERE rowid=?", (TenantStore._json(kept), row[0]))
        return gone

    def _folder(self, session_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session_id):
            raise ValueError("invalid session id")
        root = self.root.resolve()
        folder = root / session_id
        if folder.resolve() != folder or root not in folder.parents:
            raise ValueError("Unsafe artifact directory")
        return folder

    def _unlink(self, uri):
        parts = uri.removeprefix("artifact://").split("/")
        if not uri.startswith("artifact://") or len(parts) != 3 or parts[1] not in self.KINDS or Path(parts[2]).name != parts[2]:
            raise ValueError("invalid artifact uri")
        path = self._folder(parts[0]) / parts[1] / parts[2]
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".json").unlink(missing_ok=True)


