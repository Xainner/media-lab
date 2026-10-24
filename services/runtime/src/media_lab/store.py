from __future__ import annotations

import json
import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any


class IdempotencyConflict(ValueError):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _init(self) -> None:
        with self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    activity_json TEXT NOT NULL DEFAULT '[]',
                    progress_json TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    media_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    scope TEXT NOT NULL, key TEXT NOT NULL, body_hash TEXT NOT NULL,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    PRIMARY KEY(scope, key)
                );
                """
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _decode(value: str | None, default: Any = None) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    def mark_interrupted_on_boot(self) -> int:
        now = time.time()
        with self._db() as db:
            cur = db.execute(
                "UPDATE jobs SET status='interrupted', error='runtime restarted', "
                "updated_at=?, completed_at=? WHERE status IN ('queued','running')",
                (now, now),
            )
            return cur.rowcount

    def ensure_session(self, session_id: str, title: str = "Nueva sesión") -> str:
        now = time.time()
        with self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO sessions(id,title,created_at,updated_at) VALUES(?,?,?,?)",
                (session_id, title[:120] or "Nueva sesión", now, now),
            )
            db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
        return session_id

    def create_job(self, job_id: str, session_id: str, operation: str, request: dict,
                   max_pending: int | None = None) -> bool:
        return self.create_job_once(job_id, session_id, operation, request, max_pending)[1]

    def create_job_once(self, job_id: str, session_id: str, operation: str, request: dict,
                        max_pending: int | None = None, key: str | None = None,
                        scope: str | None = None) -> tuple[str, bool]:
        if key is not None and (not key or len(key) > 128 or not key.isascii() or any(ord(c) < 33 for c in key)):
            raise ValueError("invalid Idempotency-Key")
        scope = scope or operation
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False,
                                                separators=(",", ":")).encode()).hexdigest()
        now = time.time()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            if key is not None:
                prior = db.execute("SELECT body_hash,job_id FROM idempotency WHERE scope=? AND key=?",
                                   (scope, key)).fetchone()
                if prior:
                    if prior["body_hash"] != fingerprint:
                        raise IdempotencyConflict("Idempotency-Key already used with a different request")
                    return prior["job_id"], False
            if max_pending is not None:
                pending = db.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status='queued'"
                ).fetchone()[0]
                if pending >= max_pending:
                    return "", False
            db.execute("INSERT OR IGNORE INTO sessions(id,title,created_at,updated_at) VALUES(?,?,?,?)",
                       (session_id, (request.get("prompt") or request.get("title") or "Nueva sesión")[:120], now, now))
            db.execute(
                "INSERT INTO jobs(id,session_id,operation,status,request_json,created_at,updated_at) "
                "VALUES(?,?,?,'queued',?,?,?)",
                (job_id, session_id, operation, self._json(request), now, now),
            )
            if key is not None:
                db.execute("INSERT INTO idempotency(scope,key,body_hash,job_id) VALUES(?,?,?,?)",
                           (scope, key, fingerprint, job_id))
        return job_id, True

    def job_receipt(self, job_id: str) -> dict:
        job = self.get_job(job_id)
        return {"job_id": job_id, "session_id": job["session_id"], "status": job["status"],
                "queue_position": self.queue_position(job_id),
                "gpu": next((int(a[-1]) for a in job["activity"] if a in {"gpu:0", "gpu:1"}), None)}

    def lookup_idempotency(self, scope: str, key: str) -> str | None:
        with self._db() as db:
            row = db.execute("SELECT job_id FROM idempotency WHERE scope=? AND key=?", (scope, key)).fetchone()
        return row[0] if row else None

    def update_job(self, job_id: str, **values: Any) -> None:
        allowed = {
            "status", "result_json", "error", "activity_json", "progress_json",
            "cancel_requested", "started_at", "completed_at",
        }
        fields: list[str] = []
        args: list[Any] = []
        for key, value in values.items():
            if key not in allowed:
                continue
            if key.endswith("_json") and not isinstance(value, str):
                value = self._json(value)
            fields.append(f"{key}=?")
            args.append(value)
        if not fields:
            return
        fields.append("updated_at=?")
        args.extend([time.time(), job_id])
        with self._db() as db:
            db.execute(f"UPDATE jobs SET {','.join(fields)} WHERE id=?", args)

    def request_cancel(self, job_id: str) -> bool:
        with self._db() as db:
            cur = db.execute(
                "UPDATE jobs SET cancel_requested=1, updated_at=? "
                "WHERE id=? AND status IN ('queued','running')",
                (time.time(), job_id),
            )
            return cur.rowcount > 0

    def cancel_requested(self, job_id: str) -> bool:
        with self._db() as db:
            row = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
        return bool(row and row[0])

    def get_job(self, job_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def _job(self, row: sqlite3.Row) -> dict:
        out = dict(row)
        out["request"] = self._decode(out.pop("request_json"), {})
        out["result"] = self._decode(out.pop("result_json"), None)
        out["activity"] = self._decode(out.pop("activity_json"), [])
        out["progress"] = self._decode(out.pop("progress_json"), None)
        out["cancel_requested"] = bool(out["cancel_requested"])
        return out

    def queue_counts(self) -> dict:
        with self._db() as db:
            rows = db.execute(
                "SELECT status,COUNT(*) n FROM jobs WHERE status IN ('queued','running') GROUP BY status"
            ).fetchall()
        counts = {r["status"]: r["n"] for r in rows}
        return {"running": counts.get("running", 0), "pending": counts.get("queued", 0)}

    def active_count(self) -> int:
        q = self.queue_counts()
        return q["running"] + q["pending"]

    def queue_position(self, job_id: str) -> int | None:
        with self._db() as db:
            row = db.execute("SELECT created_at,status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row or row["status"] != "queued":
                return None
            return db.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='queued' AND created_at < ?",
                (row["created_at"],),
            ).fetchone()[0]

    def add_message(self, session_id: str, role: str, content: str, media: list[dict]) -> None:
        self.ensure_session(session_id, content)
        now = time.time()
        with self._db() as db:
            db.execute(
                "INSERT INTO messages(session_id,role,content,media_json,created_at) VALUES(?,?,?,?,?)",
                (session_id, role, content, self._json(media), now),
            )
            db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))

    def list_sessions(self, limit: int = 100) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT id,title,created_at,updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def session(self, session_id: str) -> dict | None:
        with self._db() as db:
            sess = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not sess:
                return None
            rows = db.execute(
                "SELECT role,content,media_json,created_at FROM messages WHERE session_id=? ORDER BY id",
                (session_id,),
            ).fetchall()
        out = dict(sess)
        out["messages"] = [
            {"role": r["role"], "content": r["content"],
             "media": self._decode(r["media_json"], []), "created_at": r["created_at"]}
            for r in rows
        ]
        return out

    def set_setting(self, key: str, value: str) -> None:
        with self._db() as db:
            db.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, value, time.time()),
            )

    def get_setting(self, key: str, default: str = "") -> str:
        with self._db() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default
