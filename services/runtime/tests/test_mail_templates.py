"""Capture SMTP locally: never send test messages to a real mailbox."""
import json
import re
from email import policy
from email.parser import BytesParser

import pytest

from media_lab.mail_templates import render_email
from media_lab.mailbox import SMTPConfig
from media_lab.security import digest
from test_web_security import lab, ORIGIN, PASSWORD


@pytest.mark.parametrize('kind,expiry', [('invite', '72 horas'), ('reset', '30 minutos')])
def test_legacy_link_preserved_in_both_versions(kind, expiry):
    url = ORIGIN + '/#' + kind + '=' + 'original_token-_' * 3
    subject, text, html = render_email(kind, 'Enlace anterior: ' + url + '\n2FA seguirá activo.', ORIGIN)
    assert 'Media Lab' in subject
    assert expiry in text and expiry in html
    assert url in text and html.count('href="' + url + '"') == 2
    assert ORIGIN + '/brand/mail-logo.png' in html
    assert 'role="presentation"' in html and '#ff5a1f' in html
    if kind == 'reset':
        assert 'dos pasos seguirá activa' in text


@pytest.mark.parametrize('content', [
    '<script>alert(1)</script> https://evil.example/#invite=' + 'x' * 43,
    'https://evil.example/' + ORIGIN + '/#invite=' + 'x' * 43,
    ORIGIN + '/#invite=' + 'x' * 43 + '&redirect=https://evil.example/',
])
def test_unexpected_links_cannot_become_actions(content):
    _, text, html = render_email('invite', content, ORIGIN)
    assert content in text
    assert '<script>' not in html
    assert 'Aceptar mi invitación' not in html
    assert 'href="https://evil.example' not in html


def test_unknown_content_is_escaped():
    _, text, html = render_email('future', '<img src=x onerror="alert(1)"> & privado', ORIGIN)
    assert '<img src=x' in text
    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; privado' in html
    assert '<img src=x' not in html


@pytest.mark.parametrize('tls', ['starttls', 'implicit'])
def test_smtp_delivers_branded_multipart_and_functional_links(lab, monkeypatch, tls):
    app, accounts, _, _, admin, alice, _ = lab
    mail = app.state.mail
    calls, messages = [], []

    class CapturedSMTP:
        def __init__(self, host, port, **options):
            calls.append(('connect', host, port, 'context' in options))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def starttls(self, **options):
            calls.append(('starttls', bool(options['context'])))
        def login(self, username, password):
            assert (username, password) == ('mailer', 'private-test-password')
            calls.append(('login',))
        def send_message(self, message):
            messages.append(BytesParser(policy=policy.default).parsebytes(message.as_bytes()))

    monkeypatch.setattr('media_lab.mailbox.smtplib.SMTP', CapturedSMTP)
    monkeypatch.setattr('media_lab.mailbox.smtplib.SMTP_SSL', CapturedSMTP)
    mail.configure(SMTPConfig(host='smtp.example.org', port=465 if tls == 'implicit' else 587,
                             tls=tls, username='mailer', password='private-test-password',
                             sender='rinari@example.org'), admin)
    mail.test('admin@example.org', admin)
    assert mail.deliver_one() and mail.state()['verified']
    invite_id = mail.invite('new@example.org', admin)
    mail.request_reset('alice@example.org', admin)
    # Persisted pre-redesign payloads remain plaintext inside encryption, and
    # rendering at delivery adds HTML without altering their stored tokens.
    with accounts.db() as db:
        pending = list(db.execute("SELECT * FROM mail_outbox WHERE status='pending' ORDER BY created_at"))
        original_urls = [re.search(r'https://\S+', json.loads(accounts.vault.open(
            row['payload'], f"mail:{row['id']}"))['content']).group(0) for row in pending]
        assert all('<html' not in accounts.vault.open(row['payload'], f"mail:{row['id']}") for row in pending)
    assert mail.deliver_one() and mail.deliver_one()
    assert len(messages) == 3
    for message in messages:
        assert message.get_content_type() == 'multipart/alternative'
        assert [part.get_content_type() for part in message.iter_parts()] == ['text/plain', 'text/html']
        assert str(message['From']) == 'Media Lab <rinari@example.org>'
        assert '· Media Lab' in str(message['Subject'])
        assert 'private-test-password' not in message.as_string()
        assert ORIGIN + '/brand/mail-logo.png' in message.get_body(('html',)).get_content()
    for message, url in zip(messages[1:], original_urls):
        assert url in message.get_body(('plain',)).get_content()
        assert 'href="' + url + '"' in message.get_body(('html',)).get_content()
    assert str(messages[1]['Message-ID']) == f'<{invite_id}@media.example.com>'
    invite_token, reset_token = [url.split('=', 1)[1] for url in original_urls]
    accepted = accounts.accept(invite_token, 'new@example.org', 'newuser', PASSWORD)
    assert accepted
    with accounts.db() as db:
        assert db.execute("SELECT user_id FROM account_links WHERE kind='reset' AND token_hash=? AND consumed=0",
                          (digest(reset_token),)).fetchone()[0] == alice
        assert db.execute("SELECT COUNT(*) FROM mail_outbox WHERE status='delivered' AND payload='' AND attempts=1").fetchone()[0] == 3
    assert any(call[0] == 'starttls' for call in calls) == (tls == 'starttls')
    assert calls[0][3] == (tls == 'implicit')
