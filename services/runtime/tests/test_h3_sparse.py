import pytest

from media_lab import main
from media_lab.contracts import VideoRequest
from media_lab.creative_workflows import h3_workflow
from media_lab.model_options import VideoOptions


def graph(profile='base', mode='t2v', steps=None, **options):
    steps = steps or {'base': 20, 'fused_turbo': 4, 'turbo': 8, 'omni': 8, 'flex': 6}[profile]
    refs = ['ref.png'] if mode == 'r2v' else None
    return h3_workflow('x', mode, 640, 352, 5, steps, 7, references=refs, profile=profile,
                       options=VideoOptions(**options) if options else None)


def test_dense_default_leaves_the_graph_and_fingerprint_unchanged():
    assert graph(attention='dense') == graph()
    assert 'sparse_attention' not in graph()
    # Requests stored before this option keep their idempotency fingerprint.
    for body in (VideoRequest(prompt='x', options=VideoOptions(resolution='720p')),
                 VideoRequest(prompt='x', options=VideoOptions(resolution='720p', attention='dense'))):
        assert 'attention' not in body.model_dump()['options']
    assert VideoRequest(prompt='x', options=VideoOptions(attention='sparse')).model_dump()['options']['attention'] == 'sparse'


@pytest.mark.parametrize('profile,mode,model', [
    ('base', 't2v', ['unet', 0]), ('turbo', 'i2v', ['shift', 0]), ('fused_turbo', 't2v', ['shift', 0]),
    ('flex', 't2v', ['flex_lora', 0]), ('omni', 'r2v', ['shift', 0])])
def test_sparse_attention_wraps_the_whole_model_chain(profile, mode, model):
    plain = graph(profile, mode) if mode != 'i2v' else None
    sparse = (graph(profile, mode, attention='sparse') if mode != 'i2v' else
              h3_workflow('x', 'i2v', 640, 352, 5, 8, 7, first='a.png', profile=profile,
                          options=VideoOptions(attention='sparse')))
    node = sparse['sparse_attention']
    assert node['class_type'] == 'BlockSparseAttention'
    assert node['inputs']['model'] == model
    assert sparse['guider']['inputs']['model'] == ['sparse_attention', 0]
    if profile == 'omni':
        assert (node['inputs']['selection'], node['inputs']['selection.keep_percent']) == ('vsa', 10.0)
    else:
        assert (node['inputs']['selection'], node['inputs']['selection.tau']) == ('sol-attn', 1.3)
    assert node['inputs']['start_percent'] == 0.2 and node['inputs']['verbose'] is True
    if plain is not None:
        # Sigmas still come from the unpatched chain, and nothing else changes.
        assert sparse['scheduler'] == plain['scheduler']
        assert sparse['decode_video'] == plain['decode_video']


def test_sparse_attention_goes_after_video_control():
    sparse = h3_workflow('x', 'r2v', 640, 352, 5, 20, 7, profile='base', control=('clip.mp4', 'pose', 1.0),
                         options=VideoOptions(attention='sparse'))
    assert sparse['sparse_attention']['inputs']['model'] == ['control', 0]
    assert sparse['guider']['inputs']['model'] == ['sparse_attention', 0]


def test_sparse_attention_is_refused_on_kandinsky():
    # The contract already refuses every option on Kandinsky 6.
    with pytest.raises(ValueError, match='Kandinsky'):
        VideoRequest(prompt='x', model='kandinsky6', options=VideoOptions(attention='sparse'))


def test_capabilities_report_the_attention_choices():
    video = main.capabilities()['video']
    assert video['attention'] == ['dense', 'sparse'] and 'vae_x2' not in video
    assert all(p['attention'] == ['dense', 'sparse'] for p in video['profiles'].values())
    catalog = {f['path']: f for f in main.capabilities()['generation_options']['video']}
    assert catalog['attention']['default'] == 'dense' and 'vae_x2' not in catalog
