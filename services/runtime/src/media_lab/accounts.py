"""Transactional accounts, opaque sessions, single-use links and TOTP.

All token values are returned only at creation; the database stores hashes.
Mail links are persisted encrypted by the outbox, not here.
"""
from __future__ import annotations

import re
import base64
import io
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path

import pyotp
import qrcode

from .security import Vault, digest, password_hash, password_matches, PASSWORDS


class AccessDenied(ValueError):
    pass


class RateLimited(AccessDenied):
    pass


class Accounts:
    def __init__(self, path: Path, vault: Vault):
        self.path, self.vault = path, vault
        self.request_lock = threading.Lock()
        self.inflight_requests = {}
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            # Refuse the old global database rather than silently importing it.
            old = db.execute("SELECT 1 FROM sqlite_master WHERE name='jobs'").fetchone()
            web = db.execute("SELECT 1 FROM sqlite_master WHERE name='web_schema'").fetchone()
            if old and not web:
                raise RuntimeError("0.7.0 requires a NEW isolated state directory; legacy state was not modified")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS web_schema(version TEXT NOT NULL);
                INSERT INTO web_schema SELECT '0.7.0' WHERE NOT EXISTS(SELECT 1 FROM web_schema);
                CREATE TABLE IF NOT EXISTS users(
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','member')),
                    enabled INTEGER NOT NULL DEFAULT 1, profile TEXT NOT NULL DEFAULT 'free',
                    active_limit INTEGER, pending_limit INTEGER, daily_limit INTEGER, storage_limit INTEGER,
                    totp_secret TEXT, totp_pending TEXT, totp_pending_until REAL, totp_step INTEGER NOT NULL DEFAULT -1,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS identities(
                    identity TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS auth_sessions(
                    id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
                    csrf TEXT NOT NULL, expires_at REAL NOT NULL, mfa INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL, ip TEXT NOT NULL, agent TEXT NOT NULL, duration INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS account_links(
                    token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL, email TEXT,
                    user_id TEXT REFERENCES users(id), expires_at REAL NOT NULL, consumed INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS recovery_codes(
                    user_id TEXT NOT NULL REFERENCES users(id), code_hash TEXT NOT NULL,
                    PRIMARY KEY(user_id,code_hash)
                );
                CREATE TABLE IF NOT EXISTS auth_limits(
                    bucket TEXT PRIMARY KEY, start REAL NOT NULL, attempts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_audit(
                    id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
                    target TEXT, created_at REAL NOT NULL
                );
            """)

    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        return db

    @staticmethod
    def email(value: str) -> str:
        value = value.strip().casefold()
        if len(value) > 254 or not re.fullmatch(r"[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+", value):
            raise ValueError("correo inválido")
        return value

    @staticmethod
    def username(value: str) -> str:
        value = value.strip().casefold()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", value):
            raise ValueError("username: 3–40 caracteres (letras, números, punto, guion)")
        return value

    def limit(self, ip: str, identity: str, action: str = "login"):
        now = time.time()
        buckets = [(f"{action}:ip:{digest(ip)}", 30), (f"{action}:identity:{digest(identity.casefold())}", 8)]
        denied = False
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for bucket, maximum in buckets:
                row = db.execute("SELECT * FROM auth_limits WHERE bucket=?", (bucket,)).fetchone()
                start, count = (row["start"], row["attempts"]) if row and row["start"] > now - 900 else (now, 0)
                denied |= count >= maximum
                db.execute("INSERT OR REPLACE INTO auth_limits VALUES(?,?,?)", (bucket, start, count + 1))
            db.execute("DELETE FROM auth_limits WHERE start<?", (now - 3600,))
        if denied:
            raise RateLimited("Demasiados intentos; espera antes de volver a intentarlo")

    def bootstrap(self) -> str:
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
                raise AccessDenied("Ya existe un administrador")
            db.execute("UPDATE account_links SET consumed=1 WHERE kind='bootstrap'")
            db.execute("INSERT INTO account_links VALUES(?,'bootstrap',NULL,NULL,?,0)",
                       (digest(token), time.time() + 1800))
        return token

    def invitation(self, email: str, actor: str) -> str:
        email, token = self.email(email), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE account_links SET consumed=1 WHERE kind='invite' AND email=?", (email,))
            db.execute("INSERT INTO account_links VALUES(?,'invite',?,NULL,?,0)",
                       (digest(token), email, time.time() + 72 * 3600))
            self.audit(db, actor, "invite", email)
        return token

    def accept(self, token: str, email: str, username: str, password: str) -> str:
        email, username, encoded = self.email(email), self.username(username), password_hash(password)
        uid = uuid.uuid4().hex
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM account_links WHERE token_hash=? AND consumed=0 AND expires_at>?",
                             (digest(token), time.time())).fetchone()
            if not row or row["kind"] not in {"invite", "bootstrap"} or (row["email"] and row["email"] != email):
                raise AccessDenied("Enlace inválido o expirado")
            role = "admin" if row["kind"] == "bootstrap" else "member"
            if role == "admin" and db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
                raise AccessDenied("Enlace inválido o expirado")
            try:
                db.execute("INSERT INTO users(id,email,username,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                           (uid, email, username, encoded, role, time.time()))
                db.executemany("INSERT INTO identities VALUES(?,?)", [(email, uid), (username, uid)])
            except sqlite3.IntegrityError as exc:
                raise AccessDenied("No se pudo crear la cuenta con esos datos") from exc
            db.execute("UPDATE account_links SET consumed=1 WHERE token_hash=?", (digest(token),))
        return uid

    def login(self, identity: str, password: str, remember: bool, ip: str, agent: str) -> tuple[str, dict]:
        identity = identity.strip().casefold()
        self.limit(ip, identity)
        with self.db() as db:
            row = db.execute("SELECT u.* FROM users u JOIN identities i ON i.user_id=u.id WHERE i.identity=?",
                             (identity,)).fetchone()
        matched = password_matches(row["password_hash"] if row else None, password)
        if not matched or not row["enabled"]:
            raise AccessDenied("Credenciales inválidas")
        user = dict(row)
        if PASSWORDS.check_needs_rehash(user["password_hash"]):
            with self.db() as db:
                db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash(password), user["id"]))
        # Until a second factor is verified this session lasts only five minutes.
        needs_mfa = bool(user["totp_secret"]) or user["role"] == "admin"
        lifetime = 7 * 86400 if remember and user["role"] != "admin" else 8 * 3600
        token = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("INSERT INTO auth_sessions VALUES(?,?,?,?,?,?,?,?,?,?)", (
                uuid.uuid4().hex, digest(token), user["id"], secrets.token_urlsafe(32),
                time.time() + (300 if needs_mfa else lifetime), 0 if needs_mfa else 1,
                time.time(), ip[:100], agent[:200], lifetime))
        return token, self.authenticate(token)

    def authenticate(self, token: str) -> dict:
        with self.db() as db:
            row = db.execute("SELECT s.*,u.username,u.email,u.role,u.enabled,u.totp_secret FROM auth_sessions s "
                             "JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1",
                             (digest(token), time.time())).fetchone()
        if not row:
            raise AccessDenied("Sesión inválida")
        result = dict(row)
        result["totp_enabled"] = bool(result.pop("totp_secret"))
        result.pop("token_hash")
        return result

    @staticmethod
    def public_session(session: dict) -> dict:
        return {key: session[key] for key in ("user_id", "username", "email", "role", "csrf", "expires_at", "mfa", "totp_enabled")}

    def revoke(self, user_id: str, session_id: str | None = None):
        with self.db() as db:
            if session_id:
                db.execute("DELETE FROM auth_sessions WHERE user_id=? AND id=?", (user_id, session_id))
            else:
                db.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))

    def sessions(self, user_id: str):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT id,created_at,expires_at,ip,agent FROM auth_sessions "
                                               "WHERE user_id=? AND expires_at>? ORDER BY created_at DESC",
                                               (user_id, time.time()))]

    def setup_totp(self, user_id: str) -> dict:
        secret = pyotp.random_base32()
        with self.db() as db:
            user = db.execute("SELECT email,totp_secret FROM users WHERE id=? AND enabled=1", (user_id,)).fetchone()
            if not user or user["totp_secret"]:
                raise AccessDenied("2FA ya está habilitado o la cuenta no está disponible")
            db.execute("UPDATE users SET totp_pending=?,totp_pending_until=? WHERE id=?",
                       (self.vault.seal(secret, f"totp:{user_id}"), time.time() + 300, user_id))
        uri = pyotp.TOTP(secret).provisioning_uri(user["email"], issuer_name="Media Lab")
        # Enrollment-only image, generated in memory; no external QR service,
        # gallery entry, file, log or cache containing the TOTP secret.
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=4)
        qr.add_data(uri)
        qr.make(fit=True)
        image = io.BytesIO()
        qr.make_image(fill_color="black", back_color="white").save(image, format="PNG")
        return {"secret": secret, "uri": uri,
                "qr_data_uri": "data:image/png;base64," + base64.b64encode(image.getvalue()).decode("ascii")}

    def _factor(self, db, uid: str, code: str, pending: bool = False):
        user = db.execute("SELECT * FROM users WHERE id=? AND enabled=1", (uid,)).fetchone()
        encrypted = user["totp_pending" if pending else "totp_secret"] if user else None
        if pending and (not user or (user["totp_pending_until"] or 0) <= time.time()):
            raise AccessDenied("La configuración 2FA expiró; vuelve a iniciarla")
        if encrypted and re.fullmatch(r"\d{6}", code):
            secret = self.vault.open(encrypted, f"totp:{uid}")
            totp, step = pyotp.TOTP(secret), int(time.time() // 30)
            for candidate in (step - 1, step, step + 1):
                if candidate > user["totp_step"] and secrets.compare_digest(totp.at(candidate * 30), code):
                    db.execute("UPDATE users SET totp_step=? WHERE id=?", (candidate, uid))
                    return
        if not pending:
            consumed = db.execute("DELETE FROM recovery_codes WHERE user_id=? AND code_hash=?",
                                  (uid, digest(code))).rowcount
            if consumed:
                return
        raise AccessDenied("Código inválido")

    def confirm_totp(self, session: dict, code: str) -> list[str]:
        self.limit(session["ip"], session["user_id"], "totp")
        codes = [secrets.token_hex(10) for _ in range(10)]
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._factor(db, session["user_id"], code, pending=True)
            db.execute("UPDATE users SET totp_secret=totp_pending,totp_pending=NULL,totp_pending_until=NULL WHERE id=?", (session["user_id"],))
            db.executemany("INSERT INTO recovery_codes VALUES(?,?)", [(session["user_id"], digest(c)) for c in codes])
            db.execute("UPDATE auth_sessions SET mfa=1,expires_at=? WHERE id=?", (time.time() + session["duration"], session["id"]))
        return codes

    def verify_totp(self, session: dict, code: str, remember: bool = False):
        self.limit(session["ip"], session["user_id"], "totp")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._factor(db, session["user_id"], code)
            duration = session["duration"] if session["role"] != "admin" else 8 * 3600
            db.execute("UPDATE auth_sessions SET mfa=1,expires_at=? WHERE id=?", (time.time() + duration, session["id"]))

    def reset_link(self, email: str) -> str | None:
        email, token = self.email(email), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT id FROM users WHERE email=? AND enabled=1", (email,)).fetchone()
            if not user:
                return None
            db.execute("UPDATE account_links SET consumed=1 WHERE kind='reset' AND user_id=?", (user[0],))
            db.execute("INSERT INTO account_links VALUES(?,'reset',?,?,?,0)", (digest(token), email, user[0], time.time() + 1800))
        return token

    def reset_password(self, token: str, password: str):
        encoded = password_hash(password)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM account_links WHERE token_hash=? AND kind='reset' AND consumed=0 AND expires_at>?",
                             (digest(token), time.time())).fetchone()
            if not row:
                raise AccessDenied("Enlace inválido o expirado")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded, row["user_id"]))
            db.execute("UPDATE account_links SET consumed=1 WHERE kind='reset' AND user_id=?", (row["user_id"],))
            db.execute("DELETE FROM auth_sessions WHERE user_id=?", (row["user_id"],))
            self.revoke_external_tokens(db, row['user_id'])

    def change_password(self, session: dict, current: str, password: str, code: str = ""):
        self.limit(session["ip"], session["user_id"], "password")
        encoded = password_hash(password)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
            if not password_matches(user["password_hash"], current):
                raise AccessDenied("Credenciales inválidas")
            if user["totp_secret"]:
                self._factor(db, user["id"], code)
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (encoded, user["id"]))
            db.execute("DELETE FROM auth_sessions WHERE user_id=?", (user["id"],))
            self.revoke_external_tokens(db, user['id'])

    @staticmethod
    def revoke_external_tokens(db, uid):
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='mcp_tokens'").fetchone():
            db.execute('UPDATE mcp_tokens SET revoked_at=? WHERE owner_id=? AND revoked_at IS NULL', (time.time(), uid))

    @staticmethod
    def audit(db, actor: str, action: str, target: str | None = None):
        db.execute("INSERT INTO admin_audit(actor,action,target,created_at) VALUES(?,?,?,?)", (actor, action, target, time.time()))

