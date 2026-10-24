import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pyotp
import pytest
import anyio
import httpx2
from fastapi.testclient import TestClient

from test_web_security import lab, sign_in, image, PASSWORD, ORIGIN
from media_lab.accounts import AccessDenied
from media_lab.mcp_access import Credential, McpAccess
from media_lab.security import as_owner, digest
from media_lab.tenancy import NotOwned


def token_for(app, uid, scopes=None):
    with as_owner(uid):
        access = app.state.mcp_access
        access.toggle(True)
        return access.mint(Credential(label='Test client', scopes=scopes or ['read', 'create', 'agent'], password=PASSWORD), {'ip': 'test'})['token']


def rpc(client, token, method, params=None, **kwargs):
    return client.post('/mcp', headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json, text/event-stream', **kwargs.pop('headers', {})},
                       json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}, **kwargs)


def call(client, token, name, arguments=None):
    response = rpc(client, token, 'tools/call', {'name': name, 'arguments': arguments or {}})
    assert response.status_code == 200, response.text
    return response.json()['result']


def test_protocol_discovery_guides_and_account_identity(lab):
    app, accounts, store, artifacts, _, alice, bob = lab
    a, b = token_for(app, alice), token_for(app, bob)
    with as_owner(alice):
        store.create_job_once('alice_job', 'alice_session', 'generate', {'prompt': 'private'})
    with TestClient(app, base_url=ORIGIN) as client:
        init = rpc(client, a, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'external-agent', 'version': '1'}})
        assert init.status_code == 200, init.text
        assert init.json()['result']['serverInfo']['name'] == 'Media Lab'
        tools = rpc(client, a, 'tools/list').json()['result']['tools']
        names = {t['name'] for t in tools}
        assert {'start_agent', 'list_jobs', 'prompt_guide', 'upload_reference', 'get_media', 'export_image'} <= names
        assert not any(name.startswith(('admin', 'private')) for name in names)
        assert 'ctx' not in json.dumps([t['inputSchema'] for t in tools])
        assert 'style' not in json.dumps(next(t for t in tools if t['name'] == 'start_agent')['inputSchema'])
        guide = call(client, a, 'prompt_guide')
        assert not guide.get('isError')
        assert 'image_prompt' in str(guide) and 'fused_turbo' in str(guide)
        resources = rpc(client, a, 'resources/list').json()['result']['resources']
        assert resources[0]['uri'] == 'rinari://guides/prompts'
        assert 'YuE2' in str(rpc(client, a, 'resources/read', {'uri': 'rinari://guides/prompts'}).json())
        prompt = rpc(client, a, 'prompts/get', {'name': 'creative_brief', 'arguments': {'goal': 'Una gata bajo la lluvia'}})
        assert 'Una gata' in str(prompt.json()), prompt.text
        assert 'alice_job' in str(call(client, a, 'list_jobs'))
        assert 'alice_job' not in str(call(client, b, 'list_jobs'))
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda i: call(client, a if i % 2 else b, 'list_jobs'), range(12)))
        assert all(('alice_job' in str(value)) == bool(i % 2) for i, value in enumerate(results))
    assert accounts.inflight_requests == {}


def test_bearer_is_mcp_only_origin_host_and_scope_checks(lab):
    app, accounts, _, _, _, alice, _ = lab
    token = token_for(app, alice, ['read'])
    with TestClient(app, base_url=ORIGIN) as client:
        assert client.post('/mcp', json={}).status_code == 401
        assert rpc(client, 'bad-token', 'tools/list').status_code == 401
        assert rpc(client, token, 'tools/list', headers={'Origin': 'https://evil.example'}).status_code == 403
        assert rpc(client, token, 'tools/list', headers={'Host': 'evil.example'}).status_code == 400
        assert client.get('/v1/account/mcp', headers={'Authorization': 'Bearer ' + token}).status_code == 401
        assert client.get('/v1/admin/users', headers={'Authorization': 'Bearer ' + token}).status_code == 401
        result = call(client, token, 'delete_media', {'uri': 'artifact://a/images/a.png', 'sha256': 'a' * 64})
        assert result['isError'] and 'delete' in str(result)
        assert client.get('/mcp/unknown', headers={'Authorization': 'Bearer ' + token}).status_code == 404


def test_private_media_download_range_export_and_revocation(lab):
    app, accounts, _, artifacts, _, alice, bob = lab
    a, b = token_for(app, alice), token_for(app, bob)
    with as_owner(alice):
        media = artifacts.put_upload('private_image', image(), 'image/png')
    with TestClient(app, base_url=ORIGIN) as client:
        result = call(client, a, 'get_media', {'reference': {'uri': media['uri'], 'sha256': media['sha256']}})
        assert not result.get('isError'), result
        value = result.get('structuredContent') or json.loads(result['content'][0]['text'])
        url = value['download_url']
        assert 'rvl_mcp_' not in url
        response = client.get(url, headers={'Authorization': 'Bearer ' + a, 'Range': 'bytes=0-15'})
        assert response.status_code == 206 and response.content == image()[:16]
        assert response.headers['cache-control'] == 'no-store'
        assert client.get(url).status_code == 401
        assert client.get(url, headers={'Authorization': 'Bearer ' + b}).status_code == 404
        assert call(client, b, 'get_media', {'reference': {'uri': media['uri'], 'sha256': media['sha256']}})['isError']
        export = call(client, a, 'export_image', {'request': {'uri': media['uri'], 'sha256': media['sha256'], 'format': 'webp'}})
        assert not export.get('isError'), export
        with as_owner(alice):
            app.state.mcp_access.toggle(False)
            app.state.mcp_access.toggle(True)
        assert rpc(client, a, 'tools/list').status_code == 401
        assert client.get(url, headers={'Authorization': 'Bearer ' + a}).status_code == 401


def test_management_csrf_owner_password_rotation_expiration_and_no_plaintext(lab):
    app, accounts, _, _, _, alice, bob = lab
    with TestClient(app, base_url=ORIGIN) as client:
        signed = sign_in(client, 'alice').json()
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': signed['csrf']}
        assert client.put('/v1/account/mcp', json={'enabled': True}).status_code == 403
        assert not client.get('/v1/account/mcp').json()['enabled']
        assert client.put('/v1/account/mcp', json={'enabled': True}, headers=headers).status_code == 200
        body = {'label': 'Agent', 'password': 'invalid', 'scopes': ['read']}
        assert client.post('/v1/account/mcp/tokens', json=body, headers=headers).status_code == 400
        body['password'] = PASSWORD
        first = client.post('/v1/account/mcp/tokens', json=body, headers=headers).json()
        assert first['token'].startswith('rvl_mcp_')
        assert first['token'] not in client.get('/v1/account/mcp').text
        with accounts.db() as db:
            row = db.execute('SELECT * FROM mcp_tokens WHERE id=?', (first['id'],)).fetchone()
            assert row['token_hash'] == digest(first['token']) and first['token'] not in str(dict(row))
        second = client.post(f"/v1/account/mcp/tokens/{first['id']}/rotate", json=body, headers=headers).json()
        assert rpc(client, first['token'], 'tools/list').status_code == 401
        assert rpc(client, second['token'], 'tools/list').status_code == 200
        with accounts.db() as db:
            db.execute('UPDATE mcp_tokens SET expires_at=? WHERE id=?', (time.time() - 1, second['id']))
        assert rpc(client, second['token'], 'tools/list').status_code == 401
        with as_owner(bob):
            with pytest.raises(NotOwned):
                app.state.mcp_access.revoke(first['id'])
            assert app.state.mcp_access.status()['items'] == []


def test_password_reset_and_disabled_user_revoke_external_access(lab):
    app, accounts, _, _, _, alice, _ = lab
    token = token_for(app, alice)
    with accounts.db() as db:
        db.execute('UPDATE users SET enabled=0 WHERE id=?', (alice,))
    with pytest.raises(AccessDenied):
        app.state.mcp_access.authenticate(token)
    with accounts.db() as db:
        db.execute('UPDATE users SET enabled=1 WHERE id=?', (alice,))
    accounts.reset_password(accounts.reset_link('alice@example.org'), PASSWORD + ' nueva')
    with pytest.raises(AccessDenied):
        app.state.mcp_access.authenticate(token)
    McpAccess(accounts, ORIGIN)  # additive and idempotent startup
    with accounts.db() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 3


def test_token_creation_requires_second_factor(lab):
    app, accounts, _, _, _, alice, _ = lab
    secret = pyotp.random_base32()
    with accounts.db() as db:
        db.execute('UPDATE users SET totp_secret=? WHERE id=?', (accounts.vault.seal(secret, 'totp:' + alice), alice))
    with as_owner(alice):
        access = app.state.mcp_access
        access.toggle(True)
        with pytest.raises(AccessDenied):
            access.mint(Credential(label='Agent', password=PASSWORD), {'ip': 'test'})
        minted = access.mint(Credential(label='Agent', password=PASSWORD, code=pyotp.TOTP(secret).now()), {'ip': 'test'})
        assert access.authenticate(minted['token'])['owner_id'] == alice


@pytest.fixture
def complete_lab(lab, monkeypatch, tmp_path):
    """Real API contracts and job admission; mock only physical GPU execution."""
    app, accounts, store, artifacts, _, alice, bob = lab
    from media_lab import config
    settings = replace(config.SETTINGS, db_path=accounts.path, artifacts_root=tmp_path / 'artifacts', model_root=tmp_path / 'models')
    monkeypatch.setattr(config, 'SETTINGS', settings)
    from media_lab import main
    from media_lab.jobs import JobManager
    from media_lab.creative import CreativeJobs
    from media_lab.mcp_server import build_mcp
    monkeypatch.setattr(main, 'SETTINGS', settings)
    monkeypatch.setattr(main, 'store', store)
    monkeypatch.setattr(main, 'artifacts', artifacts)
    def cancel(jid):
        store.request_cancel(jid)
        store.update_job(jid, status='cancelled')
        return True
    workers = SimpleNamespace(submit=lambda *_: 0, cancel=cancel, clients=[])
    monkeypatch.setattr(main, 'jobs', JobManager(settings, store, artifacts, workers))
    monkeypatch.setattr(main, 'creative', CreativeJobs(settings, store, artifacts, workers))
    existing = {(m, r.path) for r in app.routes if hasattr(r, 'methods') for m in r.methods}
    app.router.routes.extend(r for r in main.app.routes if getattr(r, 'path', '').startswith('/v1/') and not any((m, r.path) in existing for m in r.methods))
    app.state.mcp, transport = build_mcp(app, app.state.mcp_access)
    app.user_middleware[0].kwargs['mcp_app'] = transport
    return lab


def decoded(result):
    assert not result.get('isError'), result
    return result.get('structuredContent') or json.loads(result['content'][0]['text'])


def test_full_creative_catalog_contracts_quota_idempotency_and_owned_references(complete_lab):
    app, accounts, store, artifacts, _, alice, bob = complete_lab
    a, b = token_for(app, alice), token_for(app, bob)
    with TestClient(app, base_url=ORIGIN) as client:
        tools = rpc(client, a, 'tools/list').json()['result']['tools']
        names = {t['name'] for t in tools}
        assert {'generate_image', 'edit_image', 'generate_video', 'generate_music', 'create_production', 'list_library', 'find_job', 'resume_job'} <= names
        assert len(names) >= 35
        video = next(t['inputSchema'] for t in tools if t['name'] == 'generate_video')
        assert 'fused_turbo' in json.dumps(video) and 'first_frame' in json.dumps(video)
        assert decoded(call(client, a, 'capabilities'))['model'] == 'Qwen-Image-2.1'
        assert call(client, a, 'generate_video', {'body': {'prompt': 'x', 'seconds': 2}})['isError']
        assert call(client, a, 'generate_music', {'body': {'style': 'pop', 'lyrics': ''}})['isError']
        assert call(client, a, 'list_library', {'limit': 501})['isError']
        upload = decoded(call(client, a, 'upload_reference', {'data_base64': base64.b64encode(image()).decode(), 'content_type': 'image/png', 'session_id': 'mcp_upload'}))['data']
        ref = {'uri': upload['uri'], 'sha256': upload['sha256']}
        inspected = call(client, a, 'inspect_media', ref)
        assert not inspected.get('isError') and inspected['content'][1]['type'] == 'image'
        assert 'base64' not in inspected['content'][0]['text']
        reviewed = call(client, a, 'review_image', ref)
        assert not reviewed.get('isError') and reviewed['content'][1]['type'] == 'image'
        assert 'alpha' in reviewed['content'][0]['text']
        assert call(client, b, 'edit_image', {'body': {'prompt': 'Cambiar fondo', 'references': [ref]}})['isError']
        assert len(decoded(call(client, a, 'list_library'))['items']) == 1
        assert decoded(call(client, b, 'list_library'))['items'] == []
        request = {'body': {'prompt': 'Una gata entre estrellas', 'session_id': 'mcp_generation'}, 'idempotency_key': 'one-intention'}
        first = decoded(call(client, a, 'generate_image', request))
        second = decoded(call(client, a, 'generate_image', request))
        assert first['job_id'] == second['job_id']
        assert decoded(call(client, a, 'find_job', {'scope': 'generate', 'key': 'one-intention'}))['job_id'] == first['job_id']
        assert call(client, b, 'get_job', {'job_id': first['job_id']})['isError']
        assert decoded(call(client, a, 'get_job', {'job_id': first['job_id']}))['request']['prompt'] == request['body']['prompt']
        assert call(client, a, 'generate_image', {**request, 'body': {'prompt': 'otro'}})['isError']
        with accounts.db() as db:
            db.execute('UPDATE users SET daily_limit=1 WHERE id=?', (alice,))
        exceeded = call(client, a, 'generate_image', {'body': {'prompt': 'segundo'}, 'idempotency_key': 'another-intention'})
        assert exceeded['isError'] and 'quota' in str(exceeded)
        assert decoded(call(client, a, 'cancel_job', {'job_id': first['job_id']}))['status'] == 'cancelled'


def test_role_change_and_user_erasure_remove_mcp_credentials(lab, monkeypatch):
    from test_web_redesign import admin_client
    app, accounts, _, _, _, alice, bob = lab
    a, b = token_for(app, alice), token_for(app, bob)
    client, headers = admin_client(app, accounts)
    assert client.put(f'/v1/admin/users/{alice}', headers=headers, json={'username': 'alice', 'role': 'admin'}).status_code == 200
    with pytest.raises(AccessDenied):
        app.state.mcp_access.authenticate(a)
    # Cascading private credentials are removed with the account, preserving other tokens.
    with accounts.db() as db:
        db.execute('DELETE FROM identities WHERE user_id=?', (bob,))
        db.execute('DELETE FROM users WHERE id=?', (bob,))
        assert not db.execute('SELECT 1 FROM mcp_tokens WHERE owner_id=?', (bob,)).fetchone()
        assert not db.execute('SELECT 1 FROM mcp_accounts WHERE owner_id=?', (bob,)).fetchone()
        assert db.execute('SELECT 1 FROM mcp_tokens WHERE owner_id=?', (alice,)).fetchone()


def test_official_external_client_modern_and_legacy_transport(lab):
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    app, _, _, _, _, alice, _ = lab
    token = token_for(app, alice)
    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers={'Authorization': 'Bearer ' + token}) as http:
                for mode in ('auto', 'legacy'):
                    async with Client(streamable_http_client(ORIGIN + '/mcp', http_client=http), mode=mode, cache=None) as external:
                        tools = await external.list_tools()
                        assert 'list_jobs' in {tool.name for tool in tools.tools}
                        result = await external.call_tool('prompt_guide')
                        assert not result.is_error and 'YuE2' in str(result)
                        resource = await external.read_resource('rinari://guides/prompts')
                        assert 'fused_turbo' in str(resource)
    anyio.run(scenario)


def test_english_guides_cover_all_tools_formats_and_live_controls(complete_lab):
    from media_lab.mcp_server import GUIDE, GUIDES
    from media_lab.model_options import option_catalog
    from media_lab.artifacts import ALLOWED_TYPES, MEDIA_TYPES
    app, _, _, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    with TestClient(app, base_url=ORIGIN) as client:
        initialized = rpc(client, token, 'initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'guide-check', 'version': '1'}}).json()['result']
        # Compact instructions; the complete guide is served on demand.
        assert initialized['instructions'] == GUIDES['overview']
        assert len(GUIDES['overview']) < len(GUIDE) / 3
        tools = rpc(client, token, 'tools/list').json()['result']['tools']
        for tool in tools:
            assert f"`{tool['name']}`" in GUIDE, tool['name']
            assert f"`{tool['name']}`" in GUIDES['overview'], tool['name']
            assert not re.search(r'\b(Guía|Generar|Subir|propia|Permiso|español|Duración)\b', json.dumps(tool, ensure_ascii=False))
        assert {'check_prompt', 'account_preferences'} <= {tool['name'] for tool in tools}
        for topic in ('all', 'overview', 'prompts', 'formats', 'controls', 'workflows', 'image', 'edit', 'video', 'music', 'director'):
            result = call(client, token, 'prompt_guide', {'topic': topic})
            assert result['content'][0]['text'] == GUIDES[topic]
        for path, topic in [('prompts', 'all'), ('formats', 'formats'), ('controls', 'controls'), ('qwen-image', 'image'),
                            ('qwen-edit', 'edit'), ('h3', 'video'), ('yue2', 'music'), ('director', 'director')]:
            result = rpc(client, token, 'resources/read', {'uri': 'rinari://guides/' + path}).json()['result']
            assert result['contents'][0]['text'] == GUIDES[topic]
        for marker in ('integrated_multimodal_description', 'retention_analysis', '<d>[', 'is fully referenced', '[Pre-Chorus]', '<image2>'):
            assert marker in GUIDES['prompts'], marker
        names = {p['name'] for p in rpc(client, token, 'prompts/list').json()['result']['prompts']}
        assert {'creative_brief', 'image_prompt', 'video_prompt', 'music_prompt', 'music_video'} <= names
        video = rpc(client, token, 'prompts/get', {'name': 'video_prompt', 'arguments': {'goal': 'Un gato salta', 'inputs': 'one first frame'}}).json()['result']
        assert 'subject_definitions' in str(video) and 'Un gato salta' in str(video)
        checked = decoded(call(client, token, 'check_prompt', {'body': {'model': 'video', 'mode': 'i2v', 'first_frame': True, 'seconds': 8,
            'prompt': 'integrated_multimodal_description: [Shot 1] A cat jumps.\n\noverall_soundscape: Paws thump.\n\nnon_diegetic_music: N/A'}}))
        assert checked['ok'] and checked['alignment_added'] and checked['frames'] == 192
        assert checked['effective_prompt'].startswith('For the target video, at 0.00 seconds')
        caps = decoded(call(client, token, 'capabilities'))
        for group in ('image', 'edit', 'video', 'song'):
            for field in option_catalog()[group]:
                assert '`' + field['path'] + '`' in GUIDES['controls']
            fields = caps['generation_options'][group]
            assert not re.search(r'\b(Muestreo|Condicionamiento|Pasos|Generación|Guía|Tamaño|Calidad)\b', json.dumps(fields, ensure_ascii=False))
        assert caps['generation_options']['limits'] == option_catalog()['limits']
        for mime in ALLOWED_TYPES | set(MEDIA_TYPES):
            assert f'`{mime}`' in GUIDES['formats']
        for value in ('bit_depth', 'audio_quality', 'reference_videos', 'reference_audios', 'keyframe_options', 'video_options', 'blocked_gpu', 'mode=cover', '1280×704'):
            assert value in GUIDE
        assert 'English' in GUIDE and 'Keep literal content in its own language' in GUIDE
        prompt = rpc(client, token, 'prompts/get', {'name': 'creative_brief', 'arguments': {'goal': 'Un retrato con el texto "Buenas noches"'}}).json()['result']
        assert 'Original user goal (image)' in str(prompt)
        assert 'Buenas noches' in str(prompt)


def test_mcp_video_upload_modes_types_and_ownership(complete_lab, monkeypatch):
    from media_lab import main
    app, _, _, _, _, alice, bob = complete_lab
    token, other = token_for(app, alice), token_for(app, bob)
    monkeypatch.setattr(main, 'media_probe', lambda _: {'duration': 5, 'streams': [{'codec_type': 'video'}]})
    with TestClient(app, base_url=ORIGIN) as client:
        data = base64.b64encode(b'fixture video; only physical decoding mocked').decode()
        for mime in ('video/mp4', 'video/x-matroska', 'video/webm'):
            media = decoded(call(client, token, 'upload_video', {'data_base64': data, 'content_type': mime, 'session_id': 'mcp_video'}))['data']
            ref = {'uri': media['uri'], 'sha256': media['sha256']}
            assert decoded(call(client, token, 'get_media', {'reference': ref}))['bytes'] > 0
            assert call(client, other, 'get_media', {'reference': ref})['isError']
        for tool, mime in [('upload_video', 'audio/wav'), ('upload_audio', 'audio/madeup'), ('upload_reference', 'video/mp4')]:
            assert call(client, token, tool, {'data_base64': data, 'content_type': mime})['isError']
        assert call(client, token, 'upload_video', {'data_base64': 'not-base64', 'content_type': 'video/mp4'})['isError']
        # Longer sources are valid uploads (upscaling); H3 enforces 2–15 s per job.
        monkeypatch.setattr(main, 'media_probe', lambda _: {'duration': 16, 'streams': [{'codec_type': 'video'}]})
        assert not call(client, token, 'upload_video', {'data_base64': data, 'content_type': 'video/mp4'}).get('isError')
        monkeypatch.setattr(main, 'media_probe', lambda _: {'duration': 601, 'streams': [{'codec_type': 'video'}]})
        assert call(client, token, 'upload_video', {'data_base64': data, 'content_type': 'video/mp4'})['isError']
        monkeypatch.setattr(main, 'media_probe', lambda _: {'duration': 5, 'streams': [{'codec_type': 'audio'}]})
        assert call(client, token, 'upload_video', {'data_base64': data, 'content_type': 'video/mp4'})['isError']


def test_mcp_all_advanced_creation_schemas_and_idempotency_key(complete_lab):
    app, _, _, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    with TestClient(app, base_url=ORIGIN) as client:
        tools = {t['name']: t['inputSchema'] for t in rpc(client, token, 'tools/list').json()['result']['tools']}
        assert 'bit_depth' in json.dumps(tools['generate_video'])
        assert 'reference_videos' in json.dumps(tools['generate_video'])
        assert 'max_abc_tokens' in json.dumps(tools['generate_music'])
        assert 'video_options' in json.dumps(tools['create_production'])
        assert 'MKV or WebM' in json.dumps(tools['create_production'])
        assert call(client, token, 'generate_image', {'body': {'prompt': 'test'}, 'idempotency_key': 'intención'})['isError']


@pytest.mark.parametrize("operation", ["generate", "edit", "video", "song", "production"])
@pytest.mark.parametrize("explicit_session", [True, False])
def test_resume_preserves_operation_settings_session_and_owner(complete_lab, operation, explicit_session):
    from media_lab.contracts import GenerateRequest, EditRequest, VideoRequest, SongRequest, ProductionRequest
    app, _, store, artifacts, _, alice, bob = complete_lab
    with as_owner(alice):
        media = artifacts.put_upload('resume_source', image(), 'image/png')
        reference = {"uri": media["uri"], "sha256": media["sha256"]}
        bodies = {
            "generate": GenerateRequest(prompt="A moonlit garden", quality="quality", session_id="resume_source"),
            "edit": EditRequest(prompt="Add violet flowers", references=[reference], session_id="resume_source"),
            "video": VideoRequest(prompt="A gentle camera orbit", seconds=12, profile="fused_turbo", session_id="resume_source"),
            "song": SongRequest(style="dream pop", lyrics="Stars above the garden", session_id="resume_source"),
            "production": ProductionRequest(title="Moonlit garden", video_profile="fused_turbo", song=reference, brief="An orbit around the garden", scenes=[{"prompt": "A garden", "seconds": 5}], session_id="resume_source"),
        }
        request = bodies[operation].model_dump()
        if not explicit_session:
            request["session_id"] = None
        store.create_job_once('resume_original', 'resume_source', operation, request)
        partial = {"scenes": []}
        store.update_job('resume_original', status='interrupted', result_json=partial)
    with TestClient(app, base_url=ORIGIN) as client:
        signed = sign_in(client, 'bob').json()
        headers = {'Origin': ORIGIN, 'X-CSRF-Token': signed['csrf'], 'Idempotency-Key': 'resume-intention'}
        assert client.post('/v1/jobs/resume_original/resume', headers=headers).status_code == 404
        signed = sign_in(client, 'alice').json()
        headers['X-CSRF-Token'] = signed['csrf']
        resumed = client.post('/v1/jobs/resume_original/resume', headers=headers)
        assert resumed.status_code == 202, resumed.text
        jid = resumed.json()['job_id']
        assert client.post('/v1/jobs/resume_original/resume', headers=headers).json()['job_id'] == jid
        with as_owner(alice):
            new = store.get_job(jid)
            assert new['operation'] == operation
            assert new['request'] == {**request, 'session_id': 'resume_source'}
            assert new['session_id'] == 'resume_source'
            if operation == 'production':
                assert new['result'] == partial
            assert store.get_job('resume_original')['status'] == 'interrupted'
        with as_owner(bob):
            assert store.get_job(jid) is None
