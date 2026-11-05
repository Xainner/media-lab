import json
import time

import pytest
from fastapi.testclient import TestClient

from test_web_security import lab, sign_in, image, ORIGIN
from media_lab.security import as_owner
from media_lab.tenancy import NotOwned, ResourceLimit


def finished_job(store, job_id, session, outputs, request=None, key=None):
    store.create_job_once(job_id, session, 'generate', request or {'prompt': f'secret prompt {job_id}'}, 4, key)
    store.update_job(job_id, status='completed', completed_at=time.time(),
                     result_json={'media': [{'uri': o['uri'], 'sha256': o['sha256'], 'prompt': 'secret'} for o in outputs]})


def rows(store, sql, *args):
    with store._db() as db:
        return db.execute(sql, args).fetchall()


def test_deleting_the_last_output_deletes_its_job_prompt_and_every_mention(lab):
    _, _, store, artifacts, _, alice, _ = lab
    with as_owner(alice):
        out = artifacts.put_upload('s1', image(), 'image/png')
        keep = artifacts.put_upload('s1', image(), 'image/png')
        finished_job(store, 'job_aaaaaaaaaaaa', 's1', [out], key='k1')
        store.add_message('s1', 'assistant', 'here', [out, keep])
        with store._db() as db:
            db.execute("INSERT INTO characters(id,owner_id,handle,name,references_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                       ('c1', alice, 'cat', 'Cat', json.dumps([out, keep]), time.time(), time.time()))
        path = artifacts.resolve(out['uri'], out['sha256'])
        removed = artifacts.delete_media(out['uri'], out['sha256'])
    assert removed == {'uris': [out['uri']], 'jobs': ['job_aaaaaaaaaaaa']}
    assert not path.exists() and not path.with_name(path.name + '.json').exists()
    assert not rows(store, 'SELECT 1 FROM jobs WHERE id=?', 'job_aaaaaaaaaaaa')
    assert not rows(store, 'SELECT 1 FROM idempotency WHERE job_id=?', 'job_aaaaaaaaaaaa')
    media = json.loads(rows(store, 'SELECT media_json FROM messages WHERE session_id=?', 's1')[0][0])
    assert [m['uri'] for m in media] == [keep['uri']]
    refs = json.loads(rows(store, "SELECT references_json FROM characters WHERE id='c1'")[0][0])
    assert [r['uri'] for r in refs] == [keep['uri']]


def test_a_job_with_other_outputs_keeps_its_prompt_until_the_last_one(lab):
    _, _, store, artifacts, _, alice, _ = lab
    with as_owner(alice):
        a = artifacts.put_upload('s1', image(), 'image/png')
        b = artifacts.put_upload('s1', image(), 'image/png')
        finished_job(store, 'job_bbbbbbbbbbbb', 's1', [a, b])
        assert artifacts.delete_media(a['uri'], a['sha256'])['jobs'] == []
        result = json.loads(rows(store, 'SELECT result_json FROM jobs WHERE id=?', 'job_bbbbbbbbbbbb')[0][0])
        assert [m['uri'] for m in result['media']] == [b['uri']]
        assert artifacts.delete_media(b['uri'], b['sha256'])['jobs'] == ['job_bbbbbbbbbbbb']


def test_erasing_a_job_deletes_its_outputs_but_not_its_inputs(lab):
    _, _, store, artifacts, _, alice, bob = lab
    with as_owner(alice):
        source = artifacts.put_upload('s1', image(), 'image/png')
        out = artifacts.put_upload('s1', image(), 'image/png')
        finished_job(store, 'job_cccccccccccc', 's1', [out], request={'prompt': 'x', 'references': [source]})
        store.create_job_once('job_dddddddddddd', 's1', 'generate', {'prompt': 'running'}, 4)
        with pytest.raises(ResourceLimit):
            artifacts.delete_job('job_dddddddddddd')
    with as_owner(bob), pytest.raises(NotOwned):
        artifacts.delete_job('job_cccccccccccc')
    with as_owner(alice):
        assert artifacts.delete_job('job_cccccccccccc') == {'uris': [out['uri']], 'jobs': ['job_cccccccccccc']}
        assert artifacts.resolve(source['uri'], source['sha256']).exists()
        with pytest.raises(NotOwned):
            artifacts.resolve(out['uri'], out['sha256'])
        # A failed job without outputs is still erased.
        store.create_job_once('job_eeeeeeeeeeee', 's1', 'generate', {'prompt': 'failed'}, 4)
        store.update_job('job_eeeeeeeeeeee', status='failed')
        assert artifacts.delete_job('job_eeeeeeeeeeee')['jobs'] == ['job_eeeeeeeeeeee']


def test_deleting_a_session_removes_everything_in_it_and_nothing_else(lab):
    _, _, store, artifacts, _, alice, _ = lab
    with as_owner(alice):
        mine = artifacts.put_upload('gone', image(), 'image/png')
        other = artifacts.put_upload('kept', image(), 'image/png')
        finished_job(store, 'job_ffffffffffff', 'gone', [mine], key='k2')
        store.add_message('gone', 'user', 'private words', [mine])
        store.add_message('kept', 'user', 'uses it', [mine, other])
        with store._db() as db:
            db.execute("INSERT INTO agent_runs VALUES('run_' || ?, ?, 'gone', 'completed', ?)", ('a' * 24, alice, time.time()))
        folder = artifacts.root / 'gone'
        removed = artifacts.delete_session('gone')
    assert removed['uris'] == [mine['uri']] and removed['jobs'] == ['job_ffffffffffff']
    assert not folder.exists()
    for table, column in (('sessions', 'id'), ('jobs', 'session_id'), ('messages', 'session_id'),
                          ('artifacts', 'session_id'), ('agent_runs', 'session_id')):
        assert not rows(store, f'SELECT 1 FROM {table} WHERE {column}=?', 'gone'), table
    kept = json.loads(rows(store, 'SELECT media_json FROM messages WHERE session_id=?', 'kept')[0][0])
    assert [m['uri'] for m in kept] == [other['uri']]
    with as_owner(alice):
        assert artifacts.resolve(other['uri'], other['sha256']).exists()


def test_a_session_with_active_work_is_not_deleted(lab):
    _, _, store, artifacts, _, alice, _ = lab
    with as_owner(alice):
        artifacts.put_upload('busy', image(), 'image/png')
        store.create_job_once('job_000000000001', 'busy', 'generate', {'prompt': 'x'}, 4)
        with pytest.raises(ResourceLimit):
            artifacts.delete_session('busy')
    assert (artifacts.root / 'busy').exists()


def test_forgetting_a_run_deletes_its_record_and_mirrored_messages(lab):
    _, _, store, _, _, alice, _ = lab
    rid = 'run_' + 'b' * 24
    with as_owner(alice):
        store.add_message('chat', 'user', 'mine, tagged', [], rid)
        store.add_message('chat', 'assistant', 'mine, legacy', [])
        store.add_message('chat', 'user', 'written by hand', [])
        with store._db() as db:
            db.execute("INSERT INTO agent_runs VALUES(?,?,'chat','completed',?)", (rid, alice, time.time()))
        store.forget_run(rid, [{'role': 'assistant', 'content': 'mine, legacy'}])
    assert [r[0] for r in rows(store, 'SELECT content FROM messages WHERE session_id=?', 'chat')] == ['written by hand']
    assert not rows(store, 'SELECT 1 FROM agent_runs WHERE id=?', rid)


def test_session_delete_endpoint_is_owner_scoped_and_storage_overwrites_deleted_rows(lab):
    app, _, store, artifacts, _, alice, _ = lab
    with as_owner(alice):
        artifacts.put_upload('alice_session', image(), 'image/png')
    other = TestClient(app, base_url=ORIGIN)
    csrf = sign_in(other, 'bob').json()['csrf']
    assert other.delete('/v1/sessions/alice_session', headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf}).status_code == 404
    owner = TestClient(app, base_url=ORIGIN)
    csrf = sign_in(owner, 'alice').json()['csrf']
    reply = owner.delete('/v1/sessions/alice_session', headers={'Origin': ORIGIN, 'X-CSRF-Token': csrf})
    assert reply.status_code == 200 and reply.json()['media'] == 1
    assert not (artifacts.root / 'alice_session').exists()
    with store._db() as db:
        assert db.execute('PRAGMA secure_delete').fetchone()[0] == 1


def test_erasing_the_only_job_of_a_session_removes_the_session_and_its_prompt_title(lab):
    _, _, store, artifacts, _, alice, _ = lab
    with as_owner(alice):
        store.create_job_once('job_111111111111', 'solo', 'generate', {'prompt': 'a private apple'}, 4)
        out = artifacts.put_upload('solo', image(), 'image/png')
        store.update_job('job_111111111111', status='completed', completed_at=time.time(),
                         result_json={'media': [{'uri': out['uri'], 'sha256': out['sha256']}]})
        store.create_job_once('job_222222222222', 'pair', 'generate', {'prompt': 'first prompt'}, 4)
        store.create_job_once('job_333333333333', 'pair', 'generate', {'prompt': 'second prompt'}, 4)
        for job_id in ('job_111111111111', 'job_222222222222', 'job_333333333333'):
            store.update_job(job_id, status='completed', completed_at=time.time())
        assert rows(store, "SELECT title FROM sessions WHERE id='solo'")[0][0] == 'a private apple'
        artifacts.delete_job('job_111111111111')
        artifacts.delete_job('job_222222222222')
    assert not rows(store, "SELECT 1 FROM sessions WHERE id='solo'")
    assert not (artifacts.root / 'solo').exists()
    # The other session still has work; it keeps existing without the deleted prompt as its title.
    assert rows(store, "SELECT title FROM sessions WHERE id='pair'")[0][0] == 'Nueva sesión'
