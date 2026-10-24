import asyncio
import json
import socket
import time

import pytest
from fastapi.testclient import TestClient

from media_lab.providers import Providers, Endpoint, ProviderCredential, ProviderSelection, ProviderSettings
from media_lab.security import as_owner
from test_web_security import lab, sign_in, ORIGIN
from test_web_redesign import endpoints, admin_client, seed_erasure


def member(app, name):
    client = TestClient(app, base_url=ORIGIN)
    signed = sign_in(client, name)
    return client, {'Origin': ORIGIN, 'X-CSRF-Token': signed.json()['csrf']}


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))])


def test_member_can_add_save_discover_and_select_private_provider(lab, public_dns, monkeypatch):
    app, accounts, _, _, _, alice, _ = lab
    endpoints(accounts)
    client, headers = member(app, 'alice')
    assert not client.get('/v1/account/provider').json()['configured']
    body = {'label': 'Mi IA', 'base_url': 'https://first.example/v1/'}
    response = client.post('/v1/account/endpoints', headers=headers, json=body)
    assert response.status_code == 201
    endpoint = response.json()
    assert endpoint['personal'] and endpoint['base_url'] == 'https://first.example/v1'
    assert endpoint['id'] != 'one'  # Same host as a shared provider, independent identity.
    assert client.post('/v1/account/endpoints', headers=headers, json=body).json()['id'] == endpoint['id']
    assert not client.get('/v1/account/provider').json()['configured']
    eid = endpoint['id']
    assert client.put(f'/v1/account/providers/{eid}', headers=headers, json={'api_key': 'alice-private-key'}).status_code == 200
    def discovery(base, key, method, suffix, **kwargs):
        assert (base, key, method, suffix) == ('https://first.example/v1', 'alice-private-key', 'GET', '/models')
        return {'data': [{'id': 'my-model'}]}
    monkeypatch.setattr(app.state.providers, '_request', discovery)
    assert client.get(f'/v1/account/providers/{eid}/models').json() == {'items': [{'id': 'my-model'}]}
    selected = client.post('/v1/account/providers/activate', headers=headers, json={'endpoint_id': eid, 'model': 'my-model'})
    assert selected.status_code == 200 and selected.json()['model'] == 'my-model'
    assert selected.json()['capabilities'] is None
    data = client.get('/v1/account/providers').json()
    assert data['items'][0]['personal'] and 'alice-private-key' not in json.dumps(data)
    with accounts.db() as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert 'alice-private-key' not in db.execute('SELECT encrypted_key FROM saved_providers WHERE owner_id=?', (alice,)).fetchone()[0]


def test_private_endpoint_is_invisible_and_inaccessible_to_other_accounts_and_admin(lab, public_dns):
    app, accounts, _, _, _, alice, bob = lab
    with as_owner(alice):
        first = app.state.providers.register(Endpoint(label='Privado Alice', base_url='https://private.example/v1'))
    client, headers = member(app, 'bob')
    assert client.get('/v1/account/endpoints').json()['items'] == []
    eid = first['id']
    assert client.put(f'/v1/account/providers/{eid}', headers=headers, json={'api_key': 'bob-key'}).status_code == 404
    assert client.put('/v1/account/provider', headers=headers, json={'endpoint_id': eid, 'api_key': 'bob-key', 'model': 'other'}).status_code == 404
    assert client.delete(f'/v1/account/providers/{eid}', headers=headers).status_code == 404
    assert client.get(f'/v1/account/providers/{eid}/models').status_code == 422
    assert client.post('/v1/account/providers/activate', headers=headers, json={'endpoint_id': eid, 'model': 'other'}).status_code == 422
    second = client.post('/v1/account/endpoints', headers=headers, json={'label': 'Privado Bob', 'base_url': first['base_url']}).json()
    assert second['id'] != eid
    assert client.get('/v1/account/endpoints').json()['items'][0]['label'] == 'Privado Bob'
    admin, admin_headers = admin_client(app, accounts)
    assert admin.get('/v1/admin/providers').json()['items'] == []
    assert admin.delete('/v1/admin/providers/' + eid, headers=admin_headers).status_code == 404
    assert admin.put('/v1/admin/providers/' + eid + '/enabled', headers=admin_headers, json={'enabled': True}).status_code == 404
    with as_owner(alice):
        assert app.state.providers.endpoints()[0]['id'] == eid


@pytest.mark.parametrize('url,address', [
    ('http://api.example/v1', '8.8.8.8'), ('https://localhost/v1', '8.8.8.8'),
    ('https://api.example:444/v1', '8.8.8.8'), ('https://api.example/v1', '127.0.0.1'),
    ('https://api.example/v1', '169.254.169.254'), ('https://api.example/v1', '10.0.0.1'),
    ('https://user:secret@api.example/v1', '8.8.8.8'),
])
def test_member_registration_keeps_destination_restrictions(lab, monkeypatch, url, address):
    app, *_ = lab
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (address, 443))])
    client, headers = member(app, 'alice')
    response = client.post('/v1/account/endpoints', headers=headers, json={'label': 'No permitido', 'base_url': url})
    assert response.status_code == 422
    assert client.get('/v1/account/endpoints').json()['items'] == []
    assert 'secret' not in response.text


def test_personal_provider_limit_and_active_agent_lock(lab, public_dns):
    app, accounts, store, _, _, alice, _ = lab
    client, headers = member(app, 'alice')
    for i in range(20):
        assert client.post('/v1/account/endpoints', headers=headers, json={'label': str(i), 'base_url': f'https://api.example/{i}'}).status_code == 201
    assert client.post('/v1/account/endpoints', headers=headers, json={'label': 'extra', 'base_url': 'https://api.example/extra'}).status_code == 422
    with as_owner(alice):
        store.ensure_session('private_active')
    with accounts.db() as db:
        db.execute("INSERT INTO agent_runs VALUES(?,?,?,'running',?)", ('run_' + '4' * 24, alice, 'private_active', time.time()))
    assert client.post('/v1/account/endpoints', headers=headers, json={'label': 'blocked', 'base_url': 'https://api.example/blocked'}).status_code == 409


def test_legacy_endpoint_migration_preserves_ids_keys_selections_and_foreign_keys(lab):
    app, accounts, _, _, _, alice, _ = lab
    endpoints(accounts)
    p = app.state.providers
    with as_owner(alice):
        p.save(ProviderSettings(endpoint_id='one', model='alpha', api_key='old-private-key'))
        p.save_configuration('two', ProviderCredential(api_key='other-private-key', model='beta'))
    with accounts.db() as db:
        before = [tuple(r) for r in db.execute('SELECT * FROM saved_providers ORDER BY endpoint_id')]
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE legacy_endpoints(id TEXT PRIMARY KEY,label TEXT NOT NULL,base_url TEXT UNIQUE NOT NULL,enabled INTEGER NOT NULL DEFAULT 1)')
        db.execute('INSERT INTO legacy_endpoints SELECT id,label,base_url,enabled FROM provider_endpoints')
        db.execute('DROP TABLE provider_endpoints')
        db.execute('ALTER TABLE legacy_endpoints RENAME TO provider_endpoints')
    Providers(accounts)
    Providers(accounts)
    with accounts.db() as db:
        assert before == [tuple(r) for r in db.execute('SELECT * FROM saved_providers ORDER BY endpoint_id')]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT COUNT(*) FROM provider_endpoints WHERE owner_id IS NULL').fetchone()[0] == 2
    with as_owner(alice):
        assert p.get()['endpoint_id'] == 'one' and p.get()['model'] == 'alpha'
        assert all(not e['personal'] for e in p.endpoints())


def test_removal_and_account_erasure_purge_only_owned_endpoints(lab, public_dns):
    app, accounts, *_ = lab
    alice, bob = lab[-2:]
    with as_owner(alice):
        removed = app.state.providers.register(Endpoint(label='Retirar', base_url='https://api.example/remove'))
        app.state.providers.save_configuration(removed['id'], ProviderCredential(api_key='key'))
        app.state.providers.activate(ProviderSelection(endpoint_id=removed['id'], model='model'))
        app.state.providers.remove_configuration(removed['id'])
        assert not app.state.providers.get()['configured'] and app.state.providers.endpoints() == []
        app.state.providers.register(Endpoint(label='Purgar', base_url='https://api.example/v1'))
    with as_owner(bob):
        other = app.state.providers.register(Endpoint(label='Conservar', base_url='https://api.example/v1'))
    seed_erasure(lab)
    asyncio.run(app.state.admin_ops.tick())
    with accounts.db() as db:
        assert not db.execute('SELECT 1 FROM provider_endpoints WHERE owner_id=?', (alice,)).fetchone()
        assert db.execute('SELECT id FROM provider_endpoints WHERE owner_id=?', (bob,)).fetchone()[0] == other['id']
        assert not db.execute('SELECT 1 FROM users WHERE id=?', (alice,)).fetchone()
