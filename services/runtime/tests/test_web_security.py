import io
import base64
import json
import os
import secrets
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor

import pyotp
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from media_lab.accounts import Accounts, AccessDenied, RateLimited
from media_lab.security import Vault, as_owner, digest, password_hash, password_matches
from media_lab.tenancy import TenantStore, TenantArtifacts, NotOwned, ResourceLimit
from media_lab.web import create_app

PASSWORD = "una contraseña de prueba privada 2026"
ORIGIN = "https://media.example.com"


@pytest.fixture
def lab(tmp_path):
    key = tmp_path / "external-master.key"
    key.write_bytes(secrets.token_bytes(32))
    key.chmod(0o600)
    app = create_app(state_root=tmp_path / "state", key_path=key, origin=ORIGIN, attach_runtime=False)
    accounts = app.state.accounts
    admin = accounts.accept(accounts.bootstrap(), "admin@example.org", "admin", PASSWORD)
    alice = accounts.accept(accounts.invitation("alice@example.org", admin), "alice@example.org", "alice", PASSWORD)
    bob = accounts.accept(accounts.invitation("bob@example.org", admin), "bob@example.org", "bob", PASSWORD)
    return app, accounts, app.state.store, app.state.artifacts, admin, alice, bob


def sign_in(client, identity, remember=False):
    csrf = client.get("/v1/auth/session").json()["csrf"]
    return client.post("/v1/auth/login", json={"identity": identity, "password": PASSWORD, "remember": remember},
                       headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})


def image():
    data = io.BytesIO()
    Image.new("RGBA", (32, 32), (255, 0, 0, 80)).save(data, "PNG")
    return data.getvalue()


def test_argon_and_no_password_truncation():
    value = "a" * 127 + "ñ"
    encoded = password_hash(value)
    assert encoded.startswith("$argon2id$")
    assert password_matches(encoded, value)
    assert not password_matches(encoded, "a" * 128)
    for bad in ("a" * 14, "a" * 129):
        with pytest.raises(ValueError):
            password_hash(bad)


def test_vault_associated_data_and_external_key(tmp_path):
    key = tmp_path / "key"
    key.write_bytes(secrets.token_bytes(32))
    key.chmod(0o600)
    vault = Vault(key)
    value = vault.seal("smtp-and-provider-secret", "alice")
    assert vault.open(value, "alice") == "smtp-and-provider-secret"
    with pytest.raises(Exception):
        vault.open(value, "bob")
    assert "smtp-and-provider-secret" not in value


def test_old_state_refused_without_modification(tmp_path):
    key = tmp_path / "key"
    key.write_bytes(secrets.token_bytes(32))
    key.chmod(0o600)
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE jobs(id TEXT)")
        db.execute("INSERT INTO jobs VALUES('old')")
    with pytest.raises(RuntimeError, match="NEW isolated"):
        Accounts(path, Vault(key))
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT id FROM jobs").fetchone()[0] == "old"
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone()


def test_invites_email_bound_single_use_expiration_atomic(lab):
    _, accounts, _, _, admin, *_ = lab
    token = accounts.invitation("new@example.org", admin)
    with pytest.raises(AccessDenied):
        accounts.accept(token, "wrong@example.org", "new", PASSWORD)
    def consume(_):
        try:
            return accounts.accept(token, "NEW@example.org", "NeW", PASSWORD)
        except AccessDenied:
            return None
    with ThreadPoolExecutor(2) as pool:
        assert sum(v is not None for v in pool.map(consume, range(2))) == 1
    expired = accounts.invitation("expired@example.org", admin)
    with accounts.db() as db:
        db.execute("UPDATE account_links SET expires_at=0 WHERE token_hash=?", (digest(expired),))
    with pytest.raises(AccessDenied):
        accounts.accept(expired, "expired@example.org", "expired", PASSWORD)
    with pytest.raises(AccessDenied):
        accounts.bootstrap()


def test_casefold_login_and_generic_failures(lab):
    _, accounts, *_ = lab
    for identity in ("ALICE", "ALICE@EXAMPLE.ORG"):
        _, session = accounts.login(identity, PASSWORD, False, "test", "test")
        assert session["username"] == "alice"
    errors = []
    for identity in ("unknown", "bob"):
        with pytest.raises(AccessDenied) as error:
            accounts.login(identity, "wrong", False, identity, "test")
        errors.append(str(error.value))
    assert errors[0] == errors[1]


def test_login_limits_are_transactional(lab):
    _, accounts, *_ = lab
    for i in range(8):
        with pytest.raises(AccessDenied):
            accounts.login("missing", "wrong", False, str(i), "test")
    with pytest.raises(RateLimited):
        accounts.login("MISSING", "wrong", False, "fresh ip", "test")


def test_cookie_origin_csrf_and_admin_mfa_gate(lab):
    app, accounts, store, _, admin, *_ = lab
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.get("/health").status_code == 200
        for path in ("/v1/health", "/v1/account/provider", "/v1/admin/users"):
            assert client.get(path).status_code == 401
        assert client.get("/docs").status_code != 200
        assert client.post("/v1/auth/login", json={"identity": "alice", "password": PASSWORD}).status_code == 403
        login = sign_in(client, "admin", remember=True)
        assert login.status_code == 200
        assert login.json()["mfa"] == 0
        cookie_header = login.headers["set-cookie"]
        assert "Secure" in cookie_header and "HttpOnly" in cookie_header and "SameSite=lax" in cookie_header
        assert "Domain=" not in cookie_header
        assert "Max-Age=604800" not in cookie_header
        assert client.get("/v1/admin/users").status_code == 403
        csrf = login.json()["csrf"]
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        setup = client.post("/v1/auth/2fa/setup", headers=headers)
        secret = setup.json()["secret"]
        confirm = client.post("/v1/auth/2fa/confirm", headers=headers, json={"code": pyotp.TOTP(secret).now()})
        assert confirm.status_code == 200
        assert len(confirm.json()["recovery_codes"]) == 10
        assert client.get("/v1/admin/users").status_code == 200
        bad_origin = {**headers, "Origin": "https://attacker.example"}
        assert client.post("/v1/auth/logout", headers=bad_origin).status_code == 403
        assert client.post("/v1/auth/logout", headers={"Origin": ORIGIN}).status_code == 403
        assert client.post("/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/v1/admin/users").status_code == 401


def test_remember_and_revocation(lab):
    app, accounts, _, _, _, alice, _ = lab
    with TestClient(app, base_url=ORIGIN) as client:
        response = sign_in(client, "alice", True)
        assert response.status_code == 200
        assert "Max-Age=604800" in response.headers["set-cookie"]
        assert 6 * 86400 < response.json()["expires_at"] - time.time() <= 7 * 86400
        accounts.revoke(alice)
        assert client.get("/v1/account/preferences").status_code == 401


def test_totp_replay_recovery_single_use_password_reset_keeps_2fa(lab):
    _, accounts, _, _, _, alice, _ = lab
    token, session = accounts.login("alice", PASSWORD, False, "totp", "test")
    secret = accounts.setup_totp(alice)["secret"]
    code = pyotp.TOTP(secret).now()
    recovery = accounts.confirm_totp(session, code)
    with pytest.raises(AccessDenied):
        accounts.verify_totp(session, code)
    accounts.verify_totp(session, recovery[0])
    with pytest.raises(AccessDenied):
        accounts.verify_totp(session, recovery[0])
    link = accounts.reset_link("alice@example.org")
    accounts.reset_password(link, PASSWORD + " nuevo")
    with pytest.raises(AccessDenied):
        accounts.authenticate(token)
    _, session = accounts.login("alice", PASSWORD + " nuevo", False, "new", "test")
    assert session["totp_enabled"] and not session["mfa"]
    with accounts.db() as db:
        assert secret not in db.execute("SELECT totp_secret FROM users WHERE id=?", (alice,)).fetchone()[0]


def test_totp_qr_decodes_to_exact_enrollment_uri_without_persisting_image(lab):
    cv2 = pytest.importorskip("cv2")  # Optional decoder for local acceptance, not runtime dependency.
    import numpy as np
    _, accounts, _, artifacts, _, alice, _ = lab
    setup = accounts.setup_totp(alice)
    assert setup["qr_data_uri"].startswith("data:image/png;base64,")
    raw = base64.b64decode(setup["qr_data_uri"].split(",", 1)[1], validate=True)
    image = Image.open(io.BytesIO(raw))
    assert image.format == "PNG" and image.width == image.height
    decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(np.array(image.convert("RGB")))
    assert decoded == setup["uri"]
    assert pyotp.parse_uri(decoded).secret == setup["secret"]
    assert not list(artifacts.root.rglob("*.png"))
    with accounts.db() as db:
        assert setup["qr_data_uri"] not in "\n".join(db.iterdump())
        encrypted = db.execute("SELECT totp_pending FROM users WHERE id=?", (alice,)).fetchone()[0]
        assert accounts.vault.open(encrypted, f"totp:{alice}") == setup["secret"]


def test_tenant_artifacts_jobs_sessions_and_preferences(lab):
    _, _, store, artifacts, _, alice, bob = lab
    with as_owner(alice):
        ref = artifacts.put_upload("alice_session", image(), "image/png")
        jid, created = store.create_job_once("alice_job", "alice_session", "edit", {"references": [ref]}, 4, "same")
        assert created
        store.add_message("alice_session", "user", "private prompt", [ref])
        store.set_setting("preferences", "alice")
    with as_owner(bob):
        assert store.get_job(jid) is None
        assert store.session("alice_session") is None
        assert not store.request_cancel(jid)
        assert store.lookup_idempotency("edit", "same") is None
        assert store.list_sessions() == [] and artifacts.search_library() == []
        assert store.get_setting("preferences") == ""
        for call in (
            lambda: artifacts.resolve(ref["uri"], ref["sha256"]),
            lambda: artifacts.export_image(ref["uri"], ref["sha256"], "png"),
            lambda: artifacts.delete_media(ref["uri"], ref["sha256"]),
            lambda: store.ensure_session("alice_session"),
            lambda: store.add_message("bob_session", "user", "reuse", [ref]),
            lambda: store.create_job_once("attack", "bob_session", "production", {"scenes": [{"nested": {"image": ref}}]}, 4),
        ):
            with pytest.raises(NotOwned):
                call()
        assert store.create_job_once("bob_job", "bob_session", "edit", {}, 4, "same")[1]
    with as_owner(alice):
        assert artifacts.resolve(ref["uri"], ref["sha256"]).is_file()
        assert store.session("alice_session")["messages"][0]["content"] == "private prompt"


def test_idempotency_quotas_and_storage(lab):
    _, accounts, store, artifacts, _, alice, _ = lab
    with accounts.db() as db:
        db.execute("UPDATE users SET active_limit=1,pending_limit=1,daily_limit=1,storage_limit=1 WHERE id=?", (alice,))
    with as_owner(alice):
        with pytest.raises(ResourceLimit):
            artifacts.put_upload("alice_session", image(), "image/png")
        assert not list(artifacts.root.rglob("*.png"))
        first = store.create_job_once("first", "alice_session", "generate", {"prompt": "one"}, 4, "key")
        assert store.create_job_once("second", "alice_session", "generate", {"prompt": "one"}, 4, "key") == (first[0], False)
        with pytest.raises(ResourceLimit):
            store.create_job_once("third", "alice_session", "generate", {"prompt": "two"}, 4, "new-key")


def test_global_queue_has_at_most_four_pending_even_before_worker_dispatch(lab):
    _, _, store, _, _, alice, _ = lab
    with as_owner(alice):
        for i in range(4):
            assert store.create_job_once(f"q{i}", "global_queue", "generate", {}, 4)[1]
        assert store.create_job_once("overflow", "global_queue", "generate", {}, 4) == ("", False)
        store.update_job("q0", status="running")
        assert store.create_job_once("q4", "global_queue", "generate", {}, 4)[1]


def test_delete_blocks_active_references_and_is_real_disk_cleanup(lab):
    _, _, store, artifacts, _, alice, _ = lab
    with as_owner(alice):
        ref = artifacts.put_upload("session", image(), "image/png")
        store.create_job_once("using", "session", "edit", {"references": [ref]}, 4)
        with pytest.raises(ResourceLimit):
            artifacts.delete_media(ref["uri"], ref["sha256"])
        store.update_job("using", status="cancelled")
        artifacts.delete_media(ref["uri"], ref["sha256"])
        assert not list(artifacts.root.rglob("*.png"))
        assert artifacts.library() == []


def test_ssrf_private_dns_and_redirect_scheme_rejected(monkeypatch):
    from media_lab.providers import public_destination
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("127.0.0.1", 443))])
    for url in ("http://example.org/v1", "https://user:pass@example.org", "https://example.org/v1", "https://example.org:8443", "https://example.org/?x=1"):
        with pytest.raises(ValueError):
            public_destination(url)


def test_validation_does_not_echo_credentials_and_private_routes_deny_browser(lab):
    app, *_ = lab
    with TestClient(app, base_url=ORIGIN) as client:
        login = sign_in(client, "alice")
        headers = {"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf"]}
        secret = "an-invalid-api-key-that-must-never-return"
        response = client.put("/v1/account/provider", headers=headers,
                              json={"endpoint_id": "x", "model": "m", "api_key": secret, "invalid": secret})
        assert response.status_code == 422 and secret not in response.text
        assert client.get("/v1/private/provider/status").status_code == 404
        assert client.get("/v1/admin/users").status_code == 403


def test_body_limit_and_foreign_agent_runs_are_not_found(lab):
    app, _, store, _, _, alice, _ = lab
    with as_owner(alice):
        store.ensure_session("own_agent_session")
        with store._db() as db:
            db.execute("INSERT INTO agent_runs VALUES(?,?,?,?,?)",
                       ("run_" + "a" * 24, alice, "own_agent_session", "completed", time.time()))
    with TestClient(app, base_url=ORIGIN) as client:
        response = sign_in(client, "bob")
        headers = {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrf"]}
        assert client.post("/v1/account/provider/test", headers={**headers, "Content-Length": str(3 * 1024 * 1024)}).status_code == 413
        for path in ("/v1/agent/runs/run_" + "a" * 24, "/v1/agent/runs/invalid"):
            assert client.get(path).status_code == 404
            assert client.post(path + "/continue", headers=headers).status_code == 404


def test_smtp_gate_outbox_encryption_and_bounded_failures(lab, monkeypatch):
    app, accounts, _, _, admin, alice, _ = lab
    from media_lab.mailbox import SMTPConfig
    mail = app.state.mail
    with pytest.raises(AccessDenied):
        mail.invite("new@example.org", admin)
    mail.configure(SMTPConfig(host="smtp.example.org", username="user", password="smtp-secret", sender="admin@example.org"), admin)
    assert "smtp-secret" not in json.dumps(mail.state())
    mid = mail.test("admin@example.org", admin)
    monkeypatch.setattr("smtplib.SMTP", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("smtp-secret")))
    for i in range(4):
        with accounts.db() as db:
            db.execute("UPDATE mail_outbox SET next_at=0 WHERE id=?", (mid,))
        assert mail.deliver_one()
    assert mail.state()["outbox"][0]["status"] == "failed"
    assert not mail.state()["verified"]
    assert not mail.deliver_one()
    with accounts.db() as db:
        db.execute("UPDATE smtp_config SET verified=1")
    mail.invite("private-invite@example.org", admin)
    with accounts.db() as db:
        record = db.execute("SELECT payload FROM mail_outbox WHERE kind='invite'").fetchone()[0]
        assert "#invite=" not in record and "private-invite@example.org" not in record


def test_limited_user_waits_without_holding_second_gpu(lab):
    import threading
    from dataclasses import replace
    from media_lab.config import SETTINGS
    from media_lab.tenant_workers import TenantWorkers
    app, accounts, store, _, _, alice, bob = lab
    class Client:
        base_url = "private"
        def health(self): return {"ok": True}
        def queue(self): return {"queue_running": [], "queue_pending": []}
        def free(self): pass
        def interrupt(self): pass
    class Guard:
        def status(self): return {"available": True}
    settings = replace(SETTINGS, idle_unload_seconds=120)
    workers = TenantWorkers(settings, store, [Client(), Client()], [Guard(), Guard()])
    started = {name: threading.Event() for name in ("a1", "a2", "b1")}
    release = threading.Event()
    assigned = {}
    def execute(jid, gpu):
        assigned[jid] = gpu
        started[jid].set()
        release.wait(5)
        store.update_job(jid, status="completed")
    with accounts.db() as db:
        db.execute("UPDATE users SET active_limit=1,pending_limit=1 WHERE id=?", (alice,))
    try:
        with as_owner(alice):
            store.create_job_once("a1", "alice_jobs", "generate", {}, 4)
            workers.submit("a1", 0, execute)
        assert started["a1"].wait(2)
        with as_owner(alice):
            store.create_job_once("a2", "alice_jobs", "generate", {}, 4)
            workers.submit("a2", 0, execute)
            with pytest.raises(ResourceLimit):
                store.create_job_once("a3", "alice_jobs", "generate", {}, 4)
        with as_owner(bob):
            store.create_job_once("b1", "bob_jobs", "generate", {}, 4)
            workers.submit("b1", 0, execute)
        assert started["b1"].wait(2)
        assert not started["a2"].is_set()
        assert assigned["a1"] != assigned["b1"]
        release.set()
        assert started["a2"].wait(2)
    finally:
        release.set()
        workers.shutdown()



def test_static_cache_headers_only_for_real_files(tmp_path, monkeypatch):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "art" / "v2").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (web / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (web / "art" / "v2" / "plate.webp").write_bytes(b"RIFF0000WEBP")
    monkeypatch.setenv("WEB_ROOT", str(web))
    key = tmp_path / "external-master.key"
    key.write_bytes(secrets.token_bytes(32))
    app = create_app(state_root=tmp_path / "state", key_path=key, origin=ORIGIN, attach_runtime=False)
    client = TestClient(app, base_url=ORIGIN)
    hashed = client.get("/assets/index-abc123.js")
    assert hashed.status_code == 200 and hashed.headers["cache-control"] == "public, max-age=31536000, immutable"
    art = client.get("/art/v2/plate.webp")
    assert art.status_code == 200 and art.headers["cache-control"].startswith("public, max-age=86400")
    assert art.headers["content-type"] == "image/webp"
    assert "content-security-policy" in art.headers
    # Missing static paths fall back to the SPA shell, which must never be cached.
    for path in ("/assets/missing.js", "/", "/create", "/brand/none.png"):
        response = client.get(path)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store", path
    assert client.get("/v1/auth/session").headers["cache-control"] == "no-store"
