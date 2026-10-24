"""SSH-only bootstrap and exceptional administrator recovery. Never logs secrets."""
import argparse
import getpass
import os
import sys
from pathlib import Path

from .accounts import Accounts
from .security import Vault, password_hash

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["bootstrap", "recover-admin"])
    parser.add_argument("--username")
    args = parser.parse_args()
    accounts = Accounts(Path(os.environ["STATE_ROOT"]) / "media-lab.db", Vault(Path(os.environ["MASTER_KEY_FILE"])))
    if args.action == "bootstrap":
        token = accounts.bootstrap()
        # Intentionally displayed only by the human's SSH terminal, not application logs.
        print(os.getenv("PUBLIC_ORIGIN", "https://media.example.com") + "/#bootstrap=" + token)
        print("Single use · 30 minutes. Do not paste this link into chat or logs.")
        return
    if not sys.stdin.isatty() or not args.username:
        raise SystemExit("Administrator recovery requires an interactive SSH terminal and --username")
    if input("Reset this administrator's 2FA and revoke all sessions? Type RECOVER: ") != "RECOVER":
        raise SystemExit("Cancelled")
    password = getpass.getpass("New password (15–128 characters): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords differ")
    encoded = password_hash(password)
    with accounts.db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT id FROM users WHERE username=? AND role='admin'", (args.username.casefold(),)).fetchone()
        if not row:
            raise SystemExit("Administrator not found")
        uid = row[0]
        db.execute("UPDATE users SET password_hash=?,totp_secret=NULL,totp_pending=NULL,totp_pending_until=NULL,totp_step=-1,enabled=1 WHERE id=?", (encoded, uid))
        db.execute("DELETE FROM auth_sessions WHERE user_id=?", (uid,))
        db.execute("DELETE FROM recovery_codes WHERE user_id=?", (uid,))
        accounts.audit(db, "ssh-owner", "administrator-recovery", uid)
    print("Recovery complete. Login still requires administrator TOTP enrollment.")

if __name__ == "__main__":
    main()
