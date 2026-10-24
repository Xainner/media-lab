from media_lab.creative_workflows import h3_length, h3_model_prompt, h3_workflow
from media_lab.model_guides import H3, MODEL_GUIDE
from media_lab.prompt_check import PromptCheck, check_prompt

BASE = ('integrated_multimodal_description: [Shot 1] Live-action, a woman waves. [Shot 2] At 00:04.000, the camera cuts to her hand.'
        '\n\noverall_soundscape: Wind.\n\nnon_diegetic_music: N/A')
REF = """subject_definitions:
<Subject 1> is the woman from <Picture 1>, preserving her face and hair.
<Audio 1> is the voice-timbre reference for <Subject 1> (S1).

summary:
[reference generation + audio reference] The woman greets the viewer.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - identity kept.
<Audio 1>: reference - voice guided.

detailed_description:
[Shot 1] <Subject 1> (S1) says in the voice referenced from <Audio 1>, <d>[Spanish] Hola, ¿cómo estás?</d>

overall_soundscape:
Quiet room tone.

non_diegetic_music:
N/A"""


def check(**kwargs):
    return check_prompt(PromptCheck(**kwargs))


def test_alignment_line_follows_official_formats_and_effective_duration():
    assert h3_length(8) == 192 and h3_length(15) == 362 and h3_length(5) == 124
    assert h3_model_prompt(BASE, 't2v', 8, False, False) == BASE
    assert h3_model_prompt(BASE, 'r2v', 8, True, False) == BASE
    first = h3_model_prompt(BASE, 'i2v', 8, True, False)
    assert first == 'For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n' + BASE
    both = h3_model_prompt(BASE, 'i2v', 8, True, True)
    assert both.startswith('How the reference pictures align with the target video — Picture 1 (from Shot 1)')
    assert 'Picture 2 (from Shot 2) aligns with the 8.00-second mark' in both
    last = h3_model_prompt(BASE, 't2v', 10, False, True)
    assert '<Picture 1> (from [Shot 2]) aligns with the 10.12-second mark' in last
    assert h3_model_prompt(first, 'i2v', 8, True, False) == first  # never doubled


def test_workflow_sends_aligned_prompt_only_for_keyframes():
    graph = h3_workflow(BASE, 'i2v', 640, 352, 8, 20, 1, first='f.png')
    assert graph['condition']['inputs']['prompt'].startswith('For the target video')
    assert graph['condition']['inputs']['prompt'].endswith(BASE)
    assert h3_workflow(BASE, 't2v', 640, 352, 8, 20, 1)['condition']['inputs']['prompt'] == BASE


def test_h3_checks_structure_labels_and_timing():
    assert check(model='video', prompt=BASE, seconds=8)['ok']
    ref = check(model='video', mode='r2v', prompt=REF, images=1, audios=1)
    assert ref['ok'], ref
    missing_audio = check(model='video', mode='r2v', prompt=REF, images=1)
    assert not missing_audio['ok'] and any('<Audio 1>' in e for e in missing_audio['errors'])
    soundtrack = check(model='video', mode='r2v', prompt=REF.replace('<Picture 1>', '<Video 1>'), videos=1, videos_with_audio=1)
    assert soundtrack['ok'], soundtrack
    wrong_schema = check(model='video', mode='r2v', prompt=BASE, images=1)
    assert any('six Ref2VA' in e for e in wrong_schema['errors'])
    late = check(model='video', prompt=BASE.replace('00:04.000', '00:09.000'), seconds=8)
    assert any('effective duration' in e for e in late['errors'])
    bad = check(model='video', mode='r2v', prompt=REF.replace('fully_preserved', 'kept'), images=1, audios=1)
    assert any('`kept`' in e for e in bad['errors'])
    chatty = check(model='video', seconds=5, prompt=BASE.replace('a woman waves.', 'she says <d>[English] ' + 'word ' * 30 + '</d>'))
    assert any('words/s' in w for w in chatty['warnings'])
    assert any('first_frame' in e for e in check(model='video', mode='i2v', prompt=BASE)['errors'])


def test_image_edit_and_music_checks():
    single = check(model='edit', images=1, prompt='In <image1>, replace the sky.')
    assert single['ok'] and any('single reference' in w for w in single['warnings'])
    multi = check(model='edit', images=2, prompt='Place the dog into the park.')
    assert not multi['ok']
    assert check(model='edit', images=2, prompt='Place the dog from <image1> into the park of <image2>.')['ok']
    image = check(model='image', prompt='masterpiece, 8k, a cat, 16:9 aspect ratio')
    assert len(image['warnings']) >= 3
    song = check(model='music', prompt='City pop, groovy bass, female vocal', lyrics='[Verse]\nHola luna\n\n[Chorus]\nBaila x2')
    assert song['ok'] and any('x2' in w for w in song['warnings'])
    assert not check(model='music', prompt='rock', lyrics='')['ok']


def test_guides_document_studio_numbering_and_official_formats():
    for marker in ('`<Audio j>` counts first the soundtrack', 'is fully referenced', '| 15 | 362 |', 'subject_definitions'):
        assert marker in H3
    for marker in ('[Pre-Chorus]', 'mode=melody', 'observer', '<image1>'):
        assert marker in MODEL_GUIDE
