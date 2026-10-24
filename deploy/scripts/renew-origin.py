"""Renew the dedicated origin leaf only; keep CA, master/service and leaf keys.

No remote CA, credential logs, global Docker operations or busy-work interruption.
The public Let's Encrypt certificate is independently renewed by NPM.
"""
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

# The systemd unit loads /etc/media-lab/media-lab.env (MEDIA_LAB_SECRETS_DIR, MEDIA_LAB_STATE_DIR).
SECRETS = Path(os.environ["MEDIA_LAB_SECRETS_DIR"])
STATE = Path(os.environ["MEDIA_LAB_STATE_DIR"])
WORKERS = {"media-lab-comfyui": 8388, "media-lab-comfyui-gpu1": 8389}


def running(container):
    state = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container],
                           capture_output=True, text=True)
    return state.stdout.strip() == "true"


def idle():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    # A worker stopped on purpose has no queue to check.
    for port in (port for container, port in WORKERS.items() if running(container)):
        with opener.open(f"http://127.0.0.1:{port}/queue", timeout=5) as response:
            queue = json.load(response)
        if queue.get("queue_running") or queue.get("queue_pending"):
            return False
    with sqlite3.connect(f"file:{STATE / 'media-lab.db'}?mode=ro", uri=True) as db:
        if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running')").fetchone():
            return False
        if db.execute("SELECT 1 FROM agent_runs WHERE status IN ('running','recovering')").fetchone():
            return False
    request = urllib.request.Request("http://127.0.0.1:8392/active-count",
                                    headers={"X-Service-Key": (SECRETS / "agent.key").read_bytes().hex()})
    with opener.open(request, timeout=5) as response:
        agent = json.load(response)
    return not (agent["count"] or agent["recoveringAtBoot"])


def main():
    os.umask(0o077)
    assert SECRETS.resolve() == SECRETS and not SECRETS.is_symlink()
    for name in ("origin-ca.key", "origin-ca.crt", "origin.key", "origin.crt", "agent.key"):
        file = SECRETS / name
        assert not file.is_symlink() and file.stat().st_uid == os.getuid() and not file.stat().st_mode & 0o077
    certificate = x509.load_pem_x509_certificate((SECRETS / "origin.crt").read_bytes())
    now = dt.datetime.now(dt.timezone.utc)
    print("Origin certificate expiry:", certificate.not_valid_after_utc.isoformat())
    if "--check" in sys.argv or certificate.not_valid_after_utc > now + dt.timedelta(days=30):
        return
    if not idle():
        print("Renewal deferred: authorized work is active.")
        return
    ca = x509.load_pem_x509_certificate((SECRETS / "origin-ca.crt").read_bytes())
    assert ca.not_valid_after_utc > now + dt.timedelta(days=91), "Origin CA must be renewed by operator"
    ca_key = serialization.load_pem_private_key((SECRETS / "origin-ca.key").read_bytes(), password=None)
    leaf_key = serialization.load_pem_private_key((SECRETS / "origin.key").read_bytes(), password=None)
    assert ca.public_key().public_numbers() == ca_key.public_key().public_numbers()
    assert certificate.public_key().public_numbers() == leaf_key.public_key().public_numbers()
    renewed = (x509.CertificateBuilder().subject_name(certificate.subject).issuer_name(ca.subject)
               .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=90)))
    for extension in certificate.extensions:
        renewed = renewed.add_extension(extension.value, extension.critical)
    renewed = renewed.sign(ca_key, hashes.SHA256())
    if not idle():
        print("Renewal deferred: work started during preparation.")
        return
    temporary = SECRETS / "origin.crt.renewing"
    with temporary.open("xb") as file:
        file.write(renewed.public_bytes(serialization.Encoding.PEM))
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(SECRETS / "origin.crt")
    # This is run only after a second idle check; no ComfyUI/agent restart.
    subprocess.run(["docker", "restart", "media-lab-runtime"], check=True, stdout=subprocess.DEVNULL)
    print("Renewed origin certificate; reloaded only the idle web runtime.")


if __name__ == "__main__":
    main()
