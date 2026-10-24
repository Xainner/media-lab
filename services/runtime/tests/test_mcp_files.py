import io
import json
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from test_mcp import call, complete_lab, decoded, token_for  # noqa: F401  (fixture)
from test_web_security import ORIGIN, image, lab  # noqa: F401  (fixture)
from media_lab import mcp_files
from media_lab.security import as_owner

FFMPEG = bool(shutil.which('ffmpeg') and shutil.which('ffprobe'))


def links(client, token, *names, **extra):
    return decoded(call(client, token, 'create_uploads', {'files': [{'name': name} for name in names], **extra}))


def encoded(fmt, **kwargs):
    data = io.BytesIO()
    Image.new('RGB', (64, 48), 'red').save(data, fmt, **kwargs)
    return data.getvalue()


def test_upload_links_store_images_once_without_bearer_and_feed_jobs(complete_lab):
    app, _, _, _, _, alice, bob = complete_lab
    a, b = token_for(app, alice), token_for(app, bob)
    with TestClient(app, base_url=ORIGIN) as client:
        made = links(client, a, 'one.png', 'two.jpg', 'three.gif', session_id='mcp_files')
        assert 'rvl_mcp_' not in json.dumps(made) and made['expires_in_seconds'] == mcp_files.UPLOAD_TTL
        urls = [slot['url'] for slot in made['uploads']]
        assert all(url.startswith(ORIGIN + '/mcp/files/rvl_up_') for url in urls)

        first = client.put(urls[0], content=image())
        assert first.status_code == 200, first.text
        body = first.json()
        assert body['kind'] == 'image' and body['name'] == 'one.png' and body['reference']['uri'].startswith('artifact://mcp_files/references/')
        assert client.put(urls[0], content=image()).status_code == 409
        second = client.post(urls[1], files={'file': ('two.jpg', encoded('JPEG'), 'image/jpeg')})
        assert second.status_code == 200, second.text
        third = client.put(urls[2], content=encoded('GIF'))
        assert third.status_code == 200 and third.json()['converted_from'] == 'GIF'
        assert third.json()['content_type'] == 'image/png'

        status = decoded(call(client, a, 'get_uploads', {'ids': [slot['id'] for slot in made['uploads']]}))['uploads']
        assert [item['status'] for item in status] == ['completed'] * 3
        assert status[0]['reference'] == body['reference']
        assert decoded(call(client, b, 'get_uploads', {'ids': [made['uploads'][0]['id']]}))['uploads'][0]['status'] == 'unknown'

        refs = [body['reference'], second.json()['reference']]
        assert call(client, b, 'get_media', {'reference': refs[0]})['isError']
        job = decoded(call(client, a, 'edit_image', {'body': {'prompt': 'Place <image1> in front of <image2>.', 'references': refs}}))
        assert job['job_id']


def test_failed_uploads_keep_the_link_and_links_honor_scope_and_revocation(complete_lab, monkeypatch):
    app, _, _, _, _, alice, _ = complete_lab
    token, reader = token_for(app, alice), token_for(app, alice, ['read'])
    with TestClient(app, base_url=ORIGIN) as client:
        assert call(client, reader, 'create_uploads', {'files': [{'name': 'x.png'}]})['isError']
        assert call(client, token, 'create_uploads', {'files': [{'name': 'x'}] * 51})['isError']
        assert call(client, token, 'create_uploads', {'files': [{'name': 'x'}], 'session_id': '../escape'})['isError']
        slot = links(client, token, 'photo.png')['uploads'][0]
        url = slot['url']
        assert client.get(url).status_code == 405
        assert client.put(url, content=b'').status_code == 400
        rejected = client.put(url, content=b'definitely not media')
        assert rejected.status_code == 415 and 'Unsupported' in rejected.json()['detail']
        monkeypatch.setattr(mcp_files, 'MEDIA_MAX_BYTES', 16)
        assert client.put(url, content=image()).status_code == 413
        monkeypatch.undo()
        pending = decoded(call(client, token, 'get_uploads', {'ids': [slot['id']]}))['uploads'][0]
        assert pending['status'] == 'pending' and 'last_error' in pending
        assert client.put(url, content=image()).status_code == 200

        assert client.put(ORIGIN + '/mcp/files/rvl_up_' + 'x' * 43, content=image()).status_code == 404
        later = links(client, token, 'later.png')['uploads'][0]['url']
        with app.state.mcp_access.accounts.db() as db:
            db.execute('UPDATE mcp_transfers SET expires_at=? WHERE direction=? AND state=?', (time.time() - 1, 'upload', 'pending'))
        assert client.put(later, content=image()).status_code == 404

        fresh = links(client, token, 'fresh.png')['uploads'][0]['url']
        with as_owner(alice):
            app.state.mcp_access.toggle(False)
            app.state.mcp_access.toggle(True)
        assert client.put(fresh, content=image()).status_code == 404


def test_download_links_serve_owned_files_without_headers(complete_lab):
    app, _, _, artifacts, _, alice, bob = complete_lab
    token, other = token_for(app, alice), token_for(app, bob)
    with as_owner(alice):
        media = artifacts.put_upload('downloads', image(), 'image/png')
    ref = {'uri': media['uri'], 'sha256': media['sha256']}
    with TestClient(app, base_url=ORIGIN) as client:
        assert call(client, other, 'get_download_links', {'references': [ref]})['isError']
        result = decoded(call(client, token, 'get_download_links', {'references': [ref, ref]}))
        assert len(result['links']) == 2 and result['links'][0]['content_type'] == 'image/png'
        url = result['links'][0]['url']
        assert 'rvl_mcp_' not in url and url.startswith(ORIGIN + '/mcp/files/rvl_dl_')
        stored = artifacts.root.joinpath(*media['uri'].removeprefix('artifact://').split('/')).read_bytes()
        whole = client.get(url)
        assert whole.status_code == 200 and whole.content == stored and whole.headers['cache-control'] == 'no-store'
        assert client.get(url).status_code == 200  # reusable until it expires
        part = client.get(url, headers={'Range': 'bytes=0-7'})
        assert part.status_code == 206 and part.content == stored[:8]
        assert client.put(url, content=b'x').status_code == 405
        single = decoded(call(client, token, 'get_media', {'reference': ref}))
        assert client.get(single['temporary_url']).content == stored
        with as_owner(alice):
            app.state.mcp_access.toggle(False)
            app.state.mcp_access.toggle(True)
        assert client.get(url).status_code == 404


def ffmpeg(tmp_path, name, *args):
    target = tmp_path / name
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *args, str(target)], check=True, capture_output=True, timeout=120)
    return target.read_bytes()


@pytest.mark.skipif(not FFMPEG, reason='ffmpeg/ffprobe not installed')
def test_audio_and_video_are_detected_and_normalized(complete_lab, tmp_path):
    app, _, _, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    tone = ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=2']
    clip = ['-f', 'lavfi', '-i', 'testsrc=size=64x64:rate=24:duration=3']
    files = {
        'voice.wav': (ffmpeg(tmp_path, 'voice.wav', *tone), 'audio', 'audio/wav', None),
        'voice.m4a': (ffmpeg(tmp_path, 'voice.m4a', *tone, '-c:a', 'aac'), 'audio', 'audio/flac', 'mov'),
        'clip.mp4': (ffmpeg(tmp_path, 'clip.mp4', *clip, '-c:v', 'libx264', '-pix_fmt', 'yuv420p'), 'video', 'video/mp4', None),
        'clip.avi': (ffmpeg(tmp_path, 'clip.avi', *clip, '-c:v', 'mpeg4'), 'video', 'video/x-matroska', 'avi'),
    }
    with TestClient(app, base_url=ORIGIN) as client:
        slots = links(client, token, *files)['uploads']
        for slot in slots:
            data, kind, mime, converted = files[slot['name']]
            # Declared names and MIME types are ignored: the bytes decide.
            reply = client.put(slot['url'], content=data, headers={'Content-Type': 'application/octet-stream'})
            assert reply.status_code == 200, (slot['name'], reply.text)
            body = reply.json()
            assert (body['kind'], body['content_type']) == (kind, mime), slot['name']
            assert body.get('converted_from') == converted, slot['name']
            assert 1.5 < body['seconds'] < 3.5
            assert body['reference']['uri'].startswith('artifact://') and '/sources/' in body['reference']['uri']


def test_guides_explain_the_remote_server_and_reference_limits(complete_lab):
    from media_lab.mcp_server import GUIDES
    app, _, _, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    for marker in ('remote MCP server', 'install nothing', 'create_uploads', 'curl -sS -T', 'get_download_links',
                   'capabilities.inputs.references', 'same local network'):
        assert marker in GUIDES['overview'], marker
    assert 'converted to FLAC' in GUIDES['formats'] and 'remuxed to MKV' in GUIDES['formats']
    with TestClient(app, base_url=ORIGIN) as client:
        caps = decoded(call(client, token, 'capabilities'))
    refs = caps['inputs']['references']
    assert refs['edit_image']['references']['images'] == [1, 10]
    assert refs['generate_video']['reference_videos']['videos'] == [0, 3]
    assert caps['inputs']['video']['seconds'] == [1, 600]


def test_agents_see_why_a_call_was_rejected_without_server_paths(complete_lab):
    from media_lab.mcp_server import reason
    app, _, _, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    with TestClient(app, base_url=ORIGIN) as client:
        result = call(client, token, 'generate_video', {'body': {'prompt': 'A cat jumps.', 'mode': 'i2v'}})
        assert result['isError'] and 'i2v requires first_frame' in str(result), result
        turbo = call(client, token, 'generate_image', {'body': {'prompt': 'A cat.', 'model_variant': 'turbo', 'options': {'steps': 20}}})
        assert turbo['isError'] and 'steps' in str(turbo)
    assert reason('failed reading /data/artifacts/u/images/a.png for artifact://u/images/a.png') == \
        'failed reading <path> for artifact://u/images/a.png'


def test_wait_for_job_returns_outputs_and_schemas_describe_every_creation_field(complete_lab):
    app, _, store, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    image_ref = {'uri': 'artifact://waits/images/a.png', 'sha256': 'a' * 64}
    with as_owner(alice):
        store.create_job_once('done_job', 'waits', 'production', {'title': 'x'})
        store.update_job('done_job', status='completed', result_json={'preview': {**image_ref, 'width': 1},
                         'scenes': [{'image': image_ref, 'video': {'uri': 'artifact://waits/videos/b.mp4', 'sha256': 'b' * 64}}]})
        store.create_job_once('busy_job', 'waits', 'video', {'prompt': 'x'})
    with TestClient(app, base_url=ORIGIN) as client:
        done = decoded(call(client, token, 'wait_for_job', {'job_id': 'done_job'}))
        assert [o['kind'] for o in done['outputs']] == ['images', 'videos']
        assert decoded(call(client, token, 'get_job', {'job_id': 'done_job'}))['outputs'] == done['outputs']
        started = time.monotonic()
        busy = decoded(call(client, token, 'wait_for_job', {'job_id': 'busy_job', 'max_seconds': 1}))
        assert busy['still_running'] and 'outputs' not in busy and time.monotonic() - started < 10
        assert call(client, token, 'wait_for_job', {'job_id': 'nope'})['isError']
        tools = {t['name']: t['inputSchema'] for t in decoded_tools(client, token)}
    image = json.dumps(tools['generate_image'])
    assert '"enum": ["1:1"' in image and 'observer paragraph' in image and 'one per creative intent' in image
    video = json.dumps(tools['generate_video'])
    for text in ('needs first_frame', '<Picture 1>', 'check_prompt'):
        assert text in video, text
    assert 'verbatim' in json.dumps(tools['generate_music']).lower()


def decoded_tools(client, token):
    from test_mcp import rpc
    return rpc(client, token, 'tools/list').json()['result']['tools']


def test_guide_is_plain_text_and_finished_jobs_come_with_verified_download_links(complete_lab):
    import hashlib
    app, _, store, artifacts, _, alice, _ = complete_lab
    token = token_for(app, alice)
    with as_owner(alice):
        media = artifacts.put_upload('linked', image(), 'image/png')
        ref = {'uri': media['uri'], 'sha256': media['sha256']}
        store.create_job_once('linked_job', 'linked', 'edit', {'prompt': 'x'})
        store.update_job('linked_job', status='completed', result_json={'image': ref})
    with TestClient(app, base_url=ORIGIN) as client:
        tools = {t['name']: t for t in decoded_tools(client, token)}
        # Clients that validate text against an output schema rejected the Markdown guide.
        assert 'outputSchema' not in tools['prompt_guide']
        guide = call(client, token, 'prompt_guide', {'topic': 'overview'})
        assert not guide.get('isError') and guide['content'][0]['text'].startswith('# Media Lab')
        assert 'not files on your side' in guide['content'][0]['text']
        assert 'not a local file' in json.dumps(tools['get_download_links']['inputSchema'])
        done = decoded(call(client, token, 'wait_for_job', {'job_id': 'linked_job'}))
        output = done['outputs'][0]
        assert output['uri'] == ref['uri'] and output['url'].startswith(ORIGIN + '/mcp/files/rvl_dl_')
        response = client.get(output['url'])
        assert response.status_code == 200
        assert response.headers['x-content-sha256'] == ref['sha256'] == hashlib.sha256(response.content).hexdigest()


def test_read_only_tools_are_annotated_so_clients_do_not_ask_for_approval(complete_lab):
    app, _, _, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    with TestClient(app, base_url=ORIGIN) as client:
        hints = {t['name']: t.get('annotations') or {} for t in decoded_tools(client, token)}
    for name in ('prompt_guide', 'capabilities', 'studio_status', 'provider_status', 'list_providers', 'discover_models',
                 'get_job', 'get_job_preview', 'find_job', 'list_jobs', 'get_media', 'inspect_media', 'list_library',
                 'list_gallery', 'get_session', 'list_sessions', 'get_uploads', 'get_agent_run', 'list_agent_runs',
                 'check_prompt', 'get_download_links', 'wait_for_job', 'export_image'):
        if name in hints:  # get_job_preview's route is not mounted in this test app
            assert hints[name].get('readOnlyHint') is True, name
    assert len(set(hints) & {'prompt_guide', 'check_prompt', 'get_job', 'wait_for_job', 'get_download_links'}) == 5
    for name in ('generate_image', 'create_uploads', 'upload_reference', 'add_message', 'cancel_job'):
        assert hints[name].get('readOnlyHint') is False and hints[name].get('destructiveHint') is False, name
    assert hints['delete_media']['destructiveHint'] is True


def test_wait_for_job_without_progress_token_is_capped_and_compact(complete_lab, monkeypatch):
    from media_lab import mcp_server
    app, _, store, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    with as_owner(alice):
        store.create_job_once('slow_job', 'waits', 'video', {'prompt': 'x'})
        store.update_job('slow_job', status='running', progress_json={'pct': 40, 'node': 'sampling'})
    # Without a progressToken the wait is capped (nothing would reset the client's timeout).
    monkeypatch.setattr(mcp_server, 'WAIT_WITHOUT_PROGRESS', 1)
    with TestClient(app, base_url=ORIGIN) as client:
        started = time.monotonic()
        running = decoded(call(client, token, 'wait_for_job', {'job_id': 'slow_job', 'max_seconds': 600}))
        assert time.monotonic() - started < 15
        assert (running['still_running'], running['progress_pct'], running['stage']) == (True, 40, 'sampling')
        assert 'request' not in running


def test_wait_for_job_with_progress_token_streams_notifications_until_done(complete_lab):
    import anyio
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    app, _, store, _, _, alice, _ = complete_lab
    token = token_for(app, alice)
    with as_owner(alice):
        store.create_job_once('slow_job', 'waits', 'video', {'prompt': 'x'})
        store.update_job('slow_job', status='running', progress_json={'pct': 40, 'node': 'sampling'})
    events = []

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers={'Authorization': 'Bearer ' + token}) as http:
                async with Client(streamable_http_client(ORIGIN + '/mcp', http_client=http), cache=None) as external:
                    async def finish():
                        await anyio.sleep(2)
                        with as_owner(alice):
                            store.update_job('slow_job', status='completed', result_json={'video': {'uri': 'artifact://waits/videos/c.mp4', 'sha256': 'c' * 64}})

                    async def progress(value, total, message):
                        events.append((value, total, message))
                    async with anyio.create_task_group() as group:
                        group.start_soon(finish)
                        result = await external.call_tool('wait_for_job', {'job_id': 'slow_job', 'max_seconds': 120}, progress_callback=progress)
                    return result
    result = anyio.run(scenario)
    assert not result.is_error, result
    body = json.loads(result.content[0].text)
    assert body['status'] == 'completed' and body['progress_pct'] == 100 and body['outputs'][0]['kind'] == 'videos'
    assert events and events[0][0] == 40 and 'sampling' in events[0][2] and events[-1][0] == 100
