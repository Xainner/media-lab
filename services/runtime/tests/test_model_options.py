import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from media_lab.contracts import GenerateRequest, EditRequest, VideoRequest, SongRequest, ProductionRequest
from media_lab.model_options import CanvasOptions, ImageOptions, VideoOptions, SongOptions, video_size, image_canvas
from media_lab.workflows import t2i_workflow, edit_workflow
from media_lab.creative_workflows import h3_workflow, yue2_workflow
from media_lab.creative import CreativeJobs
from media_lab.store import Store, IdempotencyConflict

REF = {'uri': 'artifact://s/images/ref.png', 'sha256': 'a' * 64}


def test_old_requests_keep_exact_fingerprints(tmp_path):
    requests = [('generate', GenerateRequest(prompt='x')), ('edit', EditRequest(prompt='x', references=[REF])),
                ('video', VideoRequest(prompt='x')), ('song', SongRequest(style='x', lyrics='x')),
                ('production', ProductionRequest(title='x', song=REF, brief='x', scenes=[{}]))]
    store = Store(tmp_path / 'state.db')
    for operation, body in requests:
        legacy = body.model_dump()
        assert not {'options', 'keyframe_options', 'video_options', 'reference_videos', 'reference_audios'} & legacy.keys()
        store.create_job_once(operation, 's', operation, legacy, key='k')
        assert store.create_job_once('replay', 's', operation, body.model_dump(), key='k') == (operation, False)
        options_key = 'video_options' if operation == 'production' else 'options'
        with pytest.raises(IdempotencyConflict):
            store.create_job_once('changed', 's', operation, {**legacy, options_key: {'sampler': 'heun'}}, key='k')


@pytest.mark.parametrize('profile,steps', [('base', 20), ('fused_turbo', 4)])
def test_h3_resolution_sampling_shifts_and_encoding_reach_native_nodes(profile, steps):
    options = VideoOptions(resolution='720p', sampler='heun', scheduler='karras', denoise=.8,
                           shift_video=9, shift_audio=2, ref_image_size='max', container='webm', codec='av1', crf=17)
    width, height = video_size('16:9', options)
    graph = h3_workflow('x', 'r2v', width, height, 5, steps, 31, references=['ref.png'], profile=profile,
                        options=options, reference_videos=['silent.mp4', 'music.mp4'],
                        video_soundtracks=[False, True], reference_audios=['ref.wav'])
    condition = graph['condition']['inputs']
    assert (condition['width'], condition['height'], condition['ref_image_size']) == (1280, 704, 'max')
    assert graph['sampler']['inputs']['sampler_name'] == 'heun'
    assert graph['scheduler']['inputs']['scheduler'] == 'karras'
    assert graph['scheduler']['inputs']['denoise'] == .8
    assert graph['shift']['inputs']['shift_video'] == 9
    assert condition['ref_videos.ref_video_0'] == ['ref_video_parts_0', 0]
    assert 'ref_video_audios.ref_video_audio_0' not in condition
    assert condition['ref_video_audios.ref_video_audio_1'] == ['ref_video_parts_1', 1]
    assert condition['ref_audios.ref_audio_0'] == ['ref_audio_0', 0]
    assert graph['save']['inputs']['format.codec.encoding.crf'] == 17
    assert graph['save']['inputs']['format'] == 'webm'
    assert graph['video']['inputs']['fps'] == 24


def test_qwen_controls_and_sixteen_references():
    options = ImageOptions(steps=53, cfg=2.5, sampler='dpmpp_2m', scheduler='karras', denoise=.9, negative_prompt='blur')
    for graph, text_node in [(t2i_workflow('x', 1024, 1024, 0, 40, options=options), '4'),
                             (edit_workflow('x', ['ref.png'] * 16, 0, 40, options=options), '5')]:
        assert graph['6']['inputs']['steps'] == 53
        assert graph['6']['inputs']['cfg'] == 2.5
        assert graph['6']['inputs']['sampler_name'] == 'dpmpp_2m'
        assert graph[text_node]['inputs']['negative_prompt'] == 'blur'
    assert 'images.image_16' in graph['5']['inputs']


def test_music_and_score_settings_target_different_nodes_and_preserve_supplied_abc():
    options = SongOptions(composition={'temperature': 1.4, 'top_k': 64, 'cfg_scale': 2},
                          score={'temperature': .6, 'max_abc_tokens': 1234, 'penalty_window': 50},
                          sampler='euler', cfg=1.5, format='mp3', audio_quality='320k')
    graph = yue2_workflow('pop', 'hi', 'full', '', 90, 48, 7, options=options)
    assert graph['music']['inputs']['temperature'] == 1.4
    assert graph['music']['inputs']['cfg_scale'] == 2
    assert graph['abc']['inputs']['temperature'] == .6
    assert graph['abc']['inputs']['max_abc_tokens'] == 1234
    assert graph['sample']['inputs']['cfg'] == 1.5
    assert graph['save']['inputs']['format.quality'] == '320k'
    supplied = yue2_workflow('pop', 'hi', 'full', 'X:1\nK:C\nC', 90, 48, 7, options=options)
    assert 'abc' not in supplied and supplied['music']['inputs']['abc'] == 'X:1\nK:C\nC'
    cover = yue2_workflow('pop', 'hi', 'melody', '', 90, 48, 7, 'ref.wav', options=options)
    assert 'temperature' not in cover['abc']['inputs']


@pytest.mark.parametrize('model,values', [
    (VideoOptions, {'cfg': 2}), (VideoOptions, {'resolution': 'custom', 'width': 1024}),
    (VideoOptions, {'container': 'webm'}), (VideoOptions, {'crf': 52}),
    (VideoOptions, {'width': 1000, 'height': 1000}), (ImageOptions, {'sampler': 'invented'}),
    (ImageOptions, {'denoise': float('nan')}), (ImageOptions, {'steps': 201}),
    (SongOptions, {'format': 'flac', 'audio_quality': '320k'}),
    (SongOptions, {'format': 'opus', 'audio_quality': 'V0'}),
    (SongOptions, {'composition': {'temperature': 6}}),
])
def test_invalid_or_unsupported_controls_fail_before_workflow(model, values):
    with pytest.raises(ValueError):
        model(**values)


def test_host_memory_limits_are_independent_of_node_dimension_ranges():
    with pytest.raises(ValueError, match='1,1 MP'):
        VideoRequest(prompt='x', options={'resolution': 'custom', 'width': 2048, 'height': 2048})
    body = GenerateRequest(prompt='x', options={'width': 2048, 'height': 2048})
    with pytest.raises(ValueError, match='límite'):
        image_canvas(body, False, (1024, 1024))
    assert image_canvas(body, True, (1024, 1024)) == (2048, 2048)
    body.model_precision = 'bf16'
    with pytest.raises(ValueError):
        image_canvas(body, True, (1024, 1024))


def test_director_inherits_options_and_scene_seed(monkeypatch):
    monkeypatch.setattr('media_lab.creative.audio_analysis', lambda path: {'duration': 5})
    creative = object.__new__(CreativeJobs)
    creative.artifacts = SimpleNamespace(resolve=lambda *args: Path('ref.png'))
    creative.store = SimpleNamespace(cancel_requested=lambda job: False)
    creative.h3_locks = [threading.Lock(), threading.Lock()]
    captured = []
    def video(job, session, gpu, body):
        captured.append(body)
        raise RuntimeError('captured before generation')
    creative._video_locked = video
    body = ProductionRequest(title='x', brief='x', song=REF, seed=0, video_options={'resolution': '480p', 'crf': 18},
                             scenes=[{'start': 0, 'end': 5, 'image': REF, 'image_prompt': 'x', 'video_prompt': 'x'}])
    with pytest.raises(RuntimeError, match='captured'):
        creative._production('job', {'session_id': 's', 'request': body.model_dump()}, 0)
    assert captured[0].options.resolution == '480p'
    assert captured[0].options.crf == 18
    assert captured[0].seed == 0
