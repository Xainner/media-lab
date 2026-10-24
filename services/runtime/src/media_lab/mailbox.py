"""TLS-only SMTP and an encrypted, leased, bounded-retry SQLite outbox."""
from __future__ import annotations

import json
import secrets
import smtplib
import ssl
import threading
import time
import uuid
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import urlsplit

from pydantic import Field

from .accounts import AccessDenied
from .security import digest
from .web_auth import Strict
from .mail_templates import render_email


class SMTPConfig(Strict):
    host: str = Field(min_length=1, max_length=253, pattern=r"^[a-zA-Z0-9.-]+$")
    port: int = Field(default=587, ge=1, le=65535)
    tls: str = Field(default="starttls", pattern="^(starttls|implicit)$")
    username: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    sender: str = Field(max_length=254)


class Mailbox:
    def __init__(self, accounts, origin):
        self.accounts, self.origin = accounts, origin
        self.stop_event = threading.Event()
        with accounts.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS smtp_config(id INTEGER PRIMARY KEY CHECK(id=1), encrypted TEXT NOT NULL,
                    revision TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS mail_outbox(id TEXT PRIMARY KEY, payload TEXT NOT NULL, kind TEXT NOT NULL,
                    revision TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    next_at REAL NOT NULL, lease_until REAL NOT NULL DEFAULT 0, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS invitation_records(id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,
                    email TEXT NOT NULL,created_at REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
            """)

    def configure(self, body: SMTPConfig, actor):
        sender = self.accounts.email(body.sender)
        data = {**body.model_dump(), "sender": sender}
        with self.accounts.db() as db:
            db.execute("INSERT OR REPLACE INTO smtp_config VALUES(1,?,?,0)",
                       (self.accounts.vault.seal(json.dumps(data), "smtp"), uuid.uuid4().hex))
            self.accounts.audit(db, actor, "smtp-configure")

    def state(self):
        with self.accounts.db() as db:
            row = db.execute("SELECT * FROM smtp_config WHERE id=1").fetchone()
            items = [dict(r) for r in db.execute("SELECT id,kind,status,attempts,created_at FROM mail_outbox ORDER BY created_at DESC LIMIT 50")]
        config = json.loads(self.accounts.vault.open(row["encrypted"], "smtp")) if row else {}
        config.pop("password", None)
        return {"configured": bool(row), "verified": bool(row and row["verified"]), "settings": config, "outbox": items}

    def _enqueue(self, db, email, kind, content):
        config = db.execute("SELECT revision FROM smtp_config WHERE id=1").fetchone()
        if not config:
            raise AccessDenied("Configura SMTP antes de enviar correo")
        mid = uuid.uuid4().hex
        encrypted = self.accounts.vault.seal(json.dumps({"recipient": email, "content": content}), f"mail:{mid}")
        db.execute("INSERT INTO mail_outbox(id,payload,kind,revision,status,next_at,created_at) VALUES(?,?,?,?,'pending',?,?)",
                   (mid, encrypted, kind, config[0], time.time(), time.time()))
        return mid

    def test(self, email, actor):
        with self.accounts.db() as db:
            mid = self._enqueue(db, email, "test", "Prueba de correo de Media Lab. Uso de investigación no comercial.")
            self.accounts.audit(db, actor, "smtp-test")
        return mid

    def invite(self, email, actor):
        email, token = self.accounts.email(email), secrets.token_urlsafe(32)
        with self.accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM smtp_config WHERE verified=1").fetchone():
                raise AccessDenied("Verifica el envío SMTP antes de invitar")
            if db.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
                raise AccessDenied('Ya existe una cuenta con ese correo')
            db.execute("UPDATE invitation_records SET revoked=1 WHERE email=?", (email,))
            db.execute("UPDATE account_links SET consumed=1 WHERE kind='invite' AND email=?", (email,))
            db.execute("INSERT INTO account_links VALUES(?,'invite',?,NULL,?,0)", (digest(token), email, time.time() + 72 * 3600))
            db.execute('INSERT INTO invitation_records VALUES(?,?,?,?,0)', (uuid.uuid4().hex, digest(token), email, time.time()))
            mid = self._enqueue(db, email, "invite", f"Tu invitación (72 horas): {self.origin}/#invite={token}")
            self.accounts.audit(db, actor, "invite", email)
        return mid

    def request_reset(self, email, actor=None):
        # Never reveal account existence or unconfigured SMTP through the HTTP response.
        with self.accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            user = db.execute("SELECT id FROM users WHERE email=? AND enabled=1", (email,)).fetchone()
            ready = db.execute("SELECT 1 FROM smtp_config WHERE verified=1").fetchone()
            if not user or not ready:
                return
            token = secrets.token_urlsafe(32)
            db.execute("UPDATE account_links SET consumed=1 WHERE kind='reset' AND user_id=?", (user[0],))
            db.execute("INSERT INTO account_links VALUES(?,'reset',?,?,?,0)", (digest(token), email, user[0], time.time() + 1800))
            self._enqueue(db, email, "reset", f"Restablecer contraseña (30 minutos): {self.origin}/#reset={token}\n2FA seguirá activo.")
            if actor:
                self.accounts.audit(db, actor, "password-reset-request", user[0])

    def deliver_one(self):
        with self.accounts.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM mail_outbox WHERE status IN ('pending','sending') AND next_at<=? "
                             "AND lease_until<=? ORDER BY created_at LIMIT 1", (time.time(), time.time())).fetchone()
            if not row:
                return False
            config = db.execute("SELECT * FROM smtp_config WHERE id=1").fetchone()
            if not config or config["revision"] != row["revision"]:
                db.execute("UPDATE mail_outbox SET status='failed' WHERE id=?", (row["id"],))
                return True
            db.execute("UPDATE mail_outbox SET status='sending',lease_until=?,attempts=attempts+1 WHERE id=?",
                       (time.time() + 120, row["id"]))
        success = False
        try:
            data = json.loads(self.accounts.vault.open(row["payload"], f"mail:{row['id']}"))
            smtp = json.loads(self.accounts.vault.open(config["encrypted"], "smtp"))
            message = EmailMessage()
            message["From"], message["To"] = formataddr(('Media Lab', smtp["sender"])), data["recipient"]
            subject, text, html = render_email(row["kind"], data["content"], self.origin)
            message["Subject"] = subject
            # Stable Message-ID helps receivers deduplicate after a process crash.
            message["Message-ID"] = f"<{row['id']}@{urlsplit(self.origin).hostname}>"
            message.set_content(text)
            message.add_alternative(html, subtype='html')
            context = ssl.create_default_context()
            if smtp["tls"] == "implicit":
                client = smtplib.SMTP_SSL(smtp["host"], smtp["port"], timeout=20, context=context)
            else:
                client = smtplib.SMTP(smtp["host"], smtp["port"], timeout=20)
            with client:
                if smtp["tls"] == "starttls":
                    client.starttls(context=context)
                client.login(smtp["username"], smtp["password"])
                client.send_message(message)
            success = True
        except Exception:
            pass  # SMTP exceptions can echo credentials, recipient and reset links.
        with self.accounts.db() as db:
            status = "delivered" if success else "failed" if row["attempts"] + 1 >= 4 else "pending"
            db.execute("UPDATE mail_outbox SET status=?,lease_until=0,next_at=? WHERE id=?",
                       (status, time.time() + 30 * 2 ** row["attempts"], row["id"]))
            if success and row["kind"] == "test":
                db.execute("UPDATE smtp_config SET verified=1 WHERE revision=?", (row["revision"],))
            if status in {"delivered", "failed"}:
                # Links need not remain in the outbox after retries end.
                db.execute("UPDATE mail_outbox SET payload='' WHERE id=?", (row["id"],))
        return True

    def start(self):
        def loop():
            while not self.stop_event.wait(1):
                try:
                    self.deliver_one()
                except Exception:
                    pass
        self.thread = threading.Thread(target=loop, name="visual-mail", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if hasattr(self, "thread"):
            self.thread.join(timeout=25)

