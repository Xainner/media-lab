import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from test_web_security import lab, sign_in, image, PASSWORD, ORIGIN
from media_lab.providers import Providers, ProviderCredential, ProviderSelection, ProviderSettings, ProviderBusy
from media_lab.security import as_owner
from media_lab.tenancy import NotOwned


def endpoints(accounts):
    with accounts.db() as db:
        db.executemany('INSERT INTO provider_endpoints(id,label,base_url,enabled) VALUES(?,?,?,1)', [('one', 'First', 'https://first.example/v1'), ('two', 'Second', 'https://second.example/v1')])


def admin_client(app, accounts):
    client = TestClient(app, base_url=ORIGIN)
    signed = sign_in(client, 'admin')
    with accounts.db() as db:
        db.execute('UPDATE auth_sessions SET mfa=1')
        uid = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()[0]
        db.execute("UPDATE users SET totp_secret=? WHERE id=?", (accounts.vault.seal('FIXTURE-ONLY', f'totp:{uid}'), uid))
    return client, {'Origin': ORIGIN, 'X-CSRF-Token': signed.json()['csrf']}


def test_saved_providers_are_private_and_legacy_migration_is_idempotent(lab):
    app, accounts, _, _, _, alice, bob = lab
    endpoints(accounts)
    p = app.state.providers
    with as_owner(alice):
        p.save(ProviderSettings(endpoint_id='one', model='alpha', api_key='private-fixture-key'))
        p.save_configuration('two', ProviderCredential(api_key='second-fixture-key'))
        assert len(p.configurations()) == 2
        assert 'fixture-key' not in json.dumps(p.configurations())
        Providers(accounts); Providers(accounts)
        assert len(p.configurations()) == 2
        assert p.get()['model'] == 'alpha'
    with as_owner(bob):
        assert p.configurations() == []
        with pytest.raises(ValueError):
            p.models('one')


def test_discovery_uses_saved_key_and_normalizes_catalog(lab, monkeypatch):
    app, accounts, _, _, _, alice, _ = lab
    endpoints(accounts)
    p = app.state.providers
    def send(base, key, method, suffix, **kwargs):
        assert (base, key, method, suffix) == ('https://first.example/v1', 'discovery-key', 'GET', '/models')
        return {'data': [{'id':'zeta'}, {'id':'alpha'}, {'id':'alpha'}, {'id':23}, {'id':''}]}
    monkeypatch.setattr(p, '_request', send)
    with as_owner(alice):
        p.save_configuration('one', ProviderCredential(api_key='discovery-key'))
        assert p.models('one') == {'items':[{'id':'alpha'},{'id':'zeta'}]}
        monkeypatch.setattr(p, '_request', lambda *a, **k: {'data':[]})
        assert p.models('one')['items'] == []
        monkeypatch.setattr(p, '_request', lambda *a, **k: {'invalid':'catalog'})
        with pytest.raises(ValueError, match='catálogo'):
            p.models('one')


def test_model_switch_clears_capabilities_and_active_run_locks_settings(lab):
    app, accounts, store, _, _, alice, _ = lab
    endpoints(accounts)
    p = app.state.providers
    with as_owner(alice):
        p.save(ProviderSettings(endpoint_id='one', model='alpha', api_key='key'))
        with accounts.db() as db:
            caps=json.dumps({'chat':True,'tools':True,'vision':False})
            db.execute('UPDATE saved_providers SET capabilities=? WHERE owner_id=?', (caps, alice))
        assert p.activate(ProviderSelection(endpoint_id='one', model='alpha'))['capabilities']['tools']
        assert p.activate(ProviderSelection(endpoint_id='one', model='beta'))['capabilities'] is None
        store.ensure_session('active_run')
        with accounts.db() as db:
            db.execute("INSERT INTO agent_runs VALUES(?,?,?,'running',?)", ('run_'+'1'*24, alice, 'active_run', time.time()))
        for action in [lambda:p.activate(ProviderSelection(endpoint_id='one',model='gamma')),lambda:p.save_configuration('one',ProviderCredential(api_key='new')),lambda:p.remove_configuration('one')]:
            with pytest.raises(ProviderBusy): action()


def test_discovery_rejects_disabled_endpoint_and_remove_clears_active(lab):
    app, accounts, _, _, _, alice, _=lab
    endpoints(accounts)
    p=app.state.providers
    with as_owner(alice):
        p.save(ProviderSettings(endpoint_id='one',model='alpha',api_key='key'))
        with accounts.db() as db: db.execute("UPDATE provider_endpoints SET enabled=0 WHERE id='one'")
        with pytest.raises(ValueError):p.models('one')
        p.remove_configuration('one')
        assert not p.get()['configured'] and p.configurations()==[]


def test_user_rename_updates_login_identity_and_duplicate_rolls_back(lab):
    app,accounts,_,_,_,alice,_=lab
    client,headers=admin_client(app,accounts)
    assert client.put(f'/v1/admin/users/{alice}',headers=headers,json={'username':'alice-new','role':'member'}).status_code==200
    assert accounts.login('alice-new',PASSWORD,False,'test','test')[1]['user_id']==alice
    with pytest.raises(ValueError):accounts.login('alice',PASSWORD,False,'test','test')
    assert client.put(f'/v1/admin/users/{alice}',headers=headers,json={'username':'bob','role':'member'}).status_code==409
    assert accounts.login('alice-new',PASSWORD,False,'test','test')[1]['user_id']==alice


def test_role_change_revokes_sessions_and_last_admin_is_protected(lab):
    app,accounts,_,_,admin,alice,_=lab
    client,headers=admin_client(app,accounts)
    accounts.login('alice',PASSWORD,False,'test','test')
    assert client.put(f'/v1/admin/users/{alice}',headers=headers,json={'username':'alice','role':'admin'}).status_code==200
    assert accounts.sessions(alice)==[]
    assert client.put(f'/v1/admin/users/{alice}',headers=headers,json={'username':'alice','role':'member'}).status_code==200
    assert client.put(f'/v1/admin/users/{admin}',headers=headers,json={'username':'admin','role':'member'}).status_code==409


def test_members_cannot_manage_users_and_revocation_is_scoped(lab):
    app,accounts,_,_,_,alice,bob=lab
    client,headers=admin_client(app,accounts)
    accounts.login('alice',PASSWORD,False,'test','test');accounts.login('bob',PASSWORD,False,'test','test')
    assert client.delete(f'/v1/admin/users/{alice}/sessions/all',headers=headers).status_code==200
    assert accounts.sessions(alice)==[] and accounts.sessions(bob)
    member=TestClient(app,base_url=ORIGIN);r=sign_in(member,'bob');h={'Origin':ORIGIN,'X-CSRF-Token':r.json()['csrf']}
    assert member.put(f'/v1/admin/users/{alice}',headers=h,json={'username':'alice','role':'admin'}).status_code==403
    assert member.get('/v1/admin/invitations').status_code==403


def test_invitation_management_never_returns_tokens(lab):
    app,accounts,_,_,admin,_,_=lab
    client,headers=admin_client(app,accounts)
    mail=app.state.mail
    from media_lab.mailbox import SMTPConfig
    mail.configure(SMTPConfig(host='smtp.example.org',username='test',password='test',sender='admin@example.org'),admin)
    with accounts.db() as db:db.execute('UPDATE smtp_config SET verified=1')
    assert client.post('/v1/admin/invitations',headers=headers,json={'email':'invite@example.org'}).status_code==200
    items=client.get('/v1/admin/invitations').json()['items']
    assert len(items)==1 and items[0]['status']=='pending' and 'token' not in json.dumps(items)
    assert client.post('/v1/admin/invitations/'+items[0]['id']+'/resend',headers=headers,json={}).status_code==200
    assert len(client.get('/v1/admin/invitations').json()['items'])==2
    pending=next(i for i in client.get('/v1/admin/invitations').json()['items'] if i['status']=='pending')
    assert client.delete('/v1/admin/invitations/'+pending['id'],headers=headers).status_code==200
    assert not any(i['status']=='pending' for i in client.get('/v1/admin/invitations').json()['items'])


def seed_erasure(lab):
    app,accounts,store,artifacts,_,alice,bob=lab
    with as_owner(alice):
        ref=artifacts.put_upload('alice_media',image(),'image/png')
        store.create_job_once('alice_job','alice_media','generate',{},4,'key')
        store.add_message('alice_media','user','private',[ref])
    with as_owner(bob):
        other=artifacts.put_upload('bob_media',image(),'image/png')
    with accounts.db() as db:
        db.execute('UPDATE users SET enabled=0 WHERE id=?',(alice,))
        db.execute("INSERT INTO account_deletions VALUES(?,'fixture','pending',?,?)",(alice,time.time(),time.time()))
    return app,accounts,artifacts,alice,bob,other


def test_erasure_purges_only_target_and_is_idempotent(lab):
    app,accounts,artifacts,alice,bob,other=seed_erasure(lab)
    asyncio.run(app.state.admin_ops.tick())
    with accounts.db() as db:
        assert not db.execute('SELECT 1 FROM users WHERE id=?',(alice,)).fetchone()
        assert db.execute('SELECT status FROM account_deletions WHERE user_id=?',(alice,)).fetchone()[0]=='completed'
        assert db.execute('SELECT 1 FROM users WHERE id=?',(bob,)).fetchone()
    assert not (artifacts.root/'alice_media').exists()
    with as_owner(bob):assert artifacts.resolve(other['uri'],other['sha256']).exists()
    asyncio.run(app.state.admin_ops.tick())


def test_erasure_drains_admitted_requests_and_blocks_new_sessions(lab):
    app,accounts,artifacts,alice,_,_=seed_erasure(lab)
    accounts.inflight_requests[alice]=1
    asyncio.run(app.state.admin_ops.tick())
    assert (artifacts.root/'alice_media').exists()
    with as_owner(alice), pytest.raises(NotOwned):
        app.state.store.ensure_session('late_upload')
    accounts.inflight_requests.clear()
    asyncio.run(app.state.admin_ops.tick())
    assert not (artifacts.root/'alice_media').exists()


def test_erasure_waits_for_worker_and_recovers_after_failure(lab):
    app,accounts,artifacts,alice,_,_=seed_erasure(lab)
    import threading
    workers=SimpleNamespace(lock=threading.Lock(),assigned={'alice_job':0},executing={'alice_job'},cancel=lambda jid:None)
    ops=app.state.admin_ops;ops.runtime=SimpleNamespace(workers=workers);ops.agent_request=AsyncMock(side_effect=HTTPException(503,'offline'))
    asyncio.run(ops.tick())
    assert (artifacts.root/'alice_media').exists()
    workers.assigned.clear();workers.executing.clear()
    asyncio.run(ops.tick())
    with accounts.db() as db:assert db.execute('SELECT status FROM account_deletions WHERE user_id=?',(alice,)).fetchone()[0]=='failed'
    ops.agent_request=AsyncMock(return_value={'ok':True});ops.state(alice,'pending')
    asyncio.run(ops.tick())
    assert not (artifacts.root/'alice_media').exists()


def test_erasure_requires_admin_confirmation_password_and_factor(lab):
    app,accounts,_,_,admin,alice,_=lab
    client,headers=admin_client(app,accounts)
    payload={'confirmation':'alice','password':'wrong','code':'invalid'}
    assert client.post(f'/v1/admin/users/{alice}/delete',headers=headers,json=payload).status_code==403
    assert client.post(f'/v1/admin/users/{admin}/delete',headers=headers,json=payload).status_code==409
    payload['password']=PASSWORD
    assert client.post(f'/v1/admin/users/{alice}/delete',headers=headers,json=payload).status_code == 400


def test_endpoint_disable_waits_for_active_provider_and_can_be_restored(lab, monkeypatch):
    app,accounts,_,_,admin,alice,_=lab
    endpoints(accounts);client,headers=admin_client(app,accounts)
    with as_owner(alice):app.state.providers.save(ProviderSettings(endpoint_id='one',model='first',api_key='fixture-key'))
    with accounts.db() as db:db.execute("INSERT INTO agent_admissions VALUES(?,?)",(alice,time.time()+100))
    assert client.delete('/v1/admin/providers/one',headers=headers).status_code==409
    with accounts.db() as db:db.execute('DELETE FROM agent_admissions')
    assert client.delete('/v1/admin/providers/one',headers=headers).status_code==200
    assert any(e['id']=='one' and not e['enabled'] for e in client.get('/v1/admin/providers').json()['items'])
    monkeypatch.setattr('media_lab.providers.public_destination',lambda url:(None,None))
    assert client.put('/v1/admin/providers/one/enabled',headers=headers,json={'enabled':True}).status_code==200
    with as_owner(alice):assert app.state.providers.get()['configured']


def test_confirmed_erasure_revokes_access_and_records_persistent_operation(lab):
    import pyotp
    app,accounts,_,_,admin,alice,_=lab
    member=TestClient(app,base_url=ORIGIN);sign_in(member,'alice')
    client,headers=admin_client(app,accounts)
    secret=pyotp.random_base32()
    with accounts.db() as db:db.execute('UPDATE users SET totp_secret=?,totp_step=-1 WHERE id=?',(accounts.vault.seal(secret,f'totp:{admin}'),admin))
    response=client.post(f'/v1/admin/users/{alice}/delete',headers=headers,json={'confirmation':'alice','password':PASSWORD,'code':pyotp.TOTP(secret).now()})
    assert response.status_code==202
    assert not member.get('/v1/auth/session').json()['authenticated']
    with accounts.db() as db:
        assert db.execute('SELECT enabled FROM users WHERE id=?',(alice,)).fetchone()[0]==0
        assert db.execute('SELECT status FROM account_deletions WHERE user_id=?',(alice,)).fetchone()[0]=='pending'
    asyncio.run(app.state.admin_ops.tick())
    with accounts.db() as db:assert not db.execute('SELECT 1 FROM users WHERE id=?',(alice,)).fetchone()


def test_erasure_rejects_foreign_symlink_and_retains_other_account(lab):
    app,accounts,artifacts,alice,bob,other=seed_erasure(lab)
    import shutil
    shutil.rmtree(artifacts.root/'alice_media')
    try:(artifacts.root/'alice_media').symlink_to(artifacts.root/'bob_media',target_is_directory=True)
    except OSError:pytest.skip('Symlinks require Windows Developer Mode')
    asyncio.run(app.state.admin_ops.tick())
    with accounts.db() as db:assert db.execute('SELECT status FROM account_deletions WHERE user_id=?',(alice,)).fetchone()[0]=='failed'
    with as_owner(bob):assert artifacts.resolve(other['uri'],other['sha256']).exists()
