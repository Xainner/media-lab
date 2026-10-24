"""Security primitives for the web product (no Electron/legacy credential import)."""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import stat
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


OWNER: ContextVar[str | None] = ContextVar("media_lab_owner", default=None)
PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
_DUMMY = PASSWORDS.hash(secrets.token_urlsafe(32))


def owner() -> str:
    value = OWNER.get()
    if not value:
        raise PermissionError("authentication required")
    return value


@contextmanager
def as_owner(user_id: str):
    token = OWNER.set(user_id)
    try:
        yield
    finally:
        OWNER.reset(token)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_hash(value: str) -> str:
    if not 15 <= len(value) <= 128:
        raise ValueError("La contraseña debe tener entre 15 y 128 caracteres")
    return PASSWORDS.hash(value)


def password_matches(encoded: str | None, value: str) -> bool:
    # Reject huge inputs before invoking Argon2; verify unknown identities too.
    if len(value) > 128:
        value = "invalid oversized password"
    try:
        PASSWORDS.verify(encoded or _DUMMY, value)
        return encoded is not None
    except (VerificationError, InvalidHashError):
        return False


class Vault:
    """A separately provisioned, owner-readable 32-byte master key is mandatory."""

    def __init__(self, path: Path):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("provision an external master key before starting the web service")
        if os.name != "nt":
            info = path.stat()
            if stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid():
                raise RuntimeError("master key must belong to the service user and have mode 0600")
        key = path.read_bytes()
        if len(key) != 32:
            raise RuntimeError("master key must contain exactly 32 bytes")
        self.cipher = AESGCM(key)

    def seal(self, value: str, purpose: str) -> str:
        nonce = secrets.token_bytes(12)
        return base64.b64encode(nonce + self.cipher.encrypt(nonce, value.encode(), purpose.encode())).decode()

    def open(self, value: str, purpose: str) -> str:
        raw = base64.b64decode(value, validate=True)
        return self.cipher.decrypt(raw[:12], raw[12:], purpose.encode()).decode()

