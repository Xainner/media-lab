"""Static pre-flight checks for model prompts; structure only, never a quality verdict."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .creative_workflows import h3_length, h3_model_prompt

BASE_FIELDS = ('integrated_multimodal_description', 'overall_soundscape', 'non_diegetic_music')
REF_FIELDS = ('subject_definitions', 'summary', 'retention_analysis', 'detailed_description',
              'overall_soundscape', 'non_diegetic_music')
VISUAL_RETENTION = {'fully_preserved', 'partially_preserved', 'attribute_transfer', 'weak_reference'}
AUDIO_RETENTION = {'fully_copy', 'partially_copy', 'reference', 'weak_reference'}
TASK_TYPES = {'reference generation', 'keyframe completion', 'video editing', 'video continuation',
              'audio reuse', 'audio reference'}
SECTIONS = {'intro', 'verse', 'pre-chorus', 'chorus', 'post-chorus', 'interlude', 'bridge', 'outro',
            'hook', 'break', 'instrumental', 'solo', 'refrain', 'drop', 'build-up'}
BOOSTERS = re.compile(r'\b(masterpiece|best quality|8k|4k|ultra[- ]?hd|highly detailed|award[- ]winning|trending on)\b', re.I)
CANVAS = re.compile(r'\b(\d{3,5}\s*[x×]\s*\d{3,5}|\d{1,2}:\d{1,2}\s*(aspect|ratio)|aspect ratio)\b', re.I)


class PromptCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    model: Literal['image', 'edit', 'video', 'music'] = Field(description='image/edit = Qwen-Image-2.1, video = MiniMax H3, music = YuE2.')
    prompt: str = Field(default='', max_length=20000, description='Image/edit/video prompt. For music, the style tags.')
    lyrics: str = Field(default='', max_length=20000, description='Music only: YuE2 lyrics.')
    mode: Literal['t2v', 'i2v', 'r2v'] = Field(default='t2v', description='Video only.')
    seconds: float = Field(default=5, ge=5, le=15, description='Video only: requested duration.')
    first_frame: bool = Field(default=False, description='Video only: a first frame will be supplied.')
    last_frame: bool = Field(default=False, description='Video only: a last frame will be supplied.')
    images: int = Field(default=0, ge=0, le=16, description='Edit: number of references. Video r2v: number of `references`.')
    videos: int = Field(default=0, ge=0, le=3, description='Video r2v: number of `reference_videos`.')
    videos_with_audio: int = Field(default=0, ge=0, le=3, description='Video r2v: how many reference videos contain an audio stream.')
    audios: int = Field(default=0, ge=0, le=3, description='Video r2v: number of `reference_audios`.')


def _fields(text: str, names: tuple[str, ...]):
    found = [(m.group(1), m.start()) for m in re.finditer(r'^\s*(' + '|'.join(names) + r')\s*:', text, re.M)]
    return [name for name, _ in found]


def _labels(text: str, kind: str) -> set[int]:
    return {int(n) for n in re.findall(r'<' + kind + r' (\d+)>', text)}


def _check_video(body: PromptCheck, errors: list, warnings: list) -> dict:
    text = body.prompt
    ref2va = body.mode == 'r2v'
    expected = REF_FIELDS if ref2va else BASE_FIELDS
    present = _fields(text, REF_FIELDS + BASE_FIELDS[:1])
    if ref2va and 'integrated_multimodal_description' in present:
        errors.append('r2v uses the six Ref2VA sections; integrated_multimodal_description belongs to t2v/i2v.')
    if not ref2va and set(present) & {'subject_definitions', 'summary', 'retention_analysis', 'detailed_description'}:
        errors.append('t2v/i2v use the three Base fields; Ref2VA sections belong to r2v.')
    ordered = [name for name in present if name in expected]
    for name in expected:
        count = ordered.count(name)
        if count == 0:
            errors.append(f'Missing field `{name}:`.')
        elif count > 1:
            errors.append(f'Field `{name}:` appears {count} times.')
    if len(set(ordered)) == len(expected) and list(dict.fromkeys(ordered)) != list(expected):
        errors.append('Fields are out of order; expected ' + ' → '.join(expected) + '.')
    extra = re.findall(r'^\s*(negative_prompt|hard_constraints|camera|audio_timing|reference_manifest)\s*:', text, re.M)
    if extra:
        errors.append('Unsupported top-level section(s): ' + ', '.join(sorted(set(extra))) + '.')

    if body.mode == 'i2v' and not body.first_frame:
        errors.append('i2v requires a first_frame.')
    if ref2va and not (body.images or body.videos):
        warnings.append('r2v without an image or video reference is not an officially documented setup.')
    available = {
        'Picture': body.images if ref2va else int(body.first_frame) + int(body.last_frame),
        'Video': body.videos if ref2va else 0,
        'Audio': (body.videos_with_audio + body.audios) if ref2va else 0,
    }
    for kind, count in available.items():
        missing = sorted(n for n in _labels(text, kind) if n > count)
        if missing:
            errors.append(f'<{kind} {missing[0]}> has no matching input ({count} available).')
    if ref2va:
        defined = {m for m in re.findall(r'^\s*(<Subject \d+>)', text, re.M)}
        used = set(re.findall(r'<Subject \d+>', text))
        if used - defined:
            errors.append('Subjects used but not defined in subject_definitions: ' + ', '.join(sorted(used - defined)) + '.')
        summary = re.search(r'summary:\s*\n?\s*\[([^\]]+)\]', text)
        if not summary:
            errors.append('summary must start with a bracketed task type, e.g. [reference generation].')
        else:
            unknown = [t.strip() for t in summary.group(1).split('+') if t.strip() not in TASK_TYPES]
            if unknown:
                errors.append('Unknown task type(s): ' + ', '.join(unknown) + '.')
        block = re.search(r'retention_analysis:(.*?)(?:^\s*detailed_description\s*:|\Z)', text, re.S | re.M)
        for line in (block.group(1).splitlines() if block else []):
            m = re.match(r'\s*<(Subject|Picture|Video|Audio) \d+>[^:]*:\s*([a-z_]+)', line)
            if not m:
                continue
            allowed = AUDIO_RETENTION if m.group(1) == 'Audio' else VISUAL_RETENTION
            if m.group(2) not in allowed:
                errors.append(f'Retention value `{m.group(2)}` is not valid for {m.group(1)}.')
            if re.search(r'\(S\d', line):
                warnings.append('Speaker IDs belong in definitions and vocal events, not retention_analysis.')

    frames = h3_length(body.seconds)
    duration = frames / 24
    shots = [int(n) for n in re.findall(r'\[Shot (\d+)\]', text)]
    if not shots:
        errors.append('The description must start with [Shot 1].')
    else:
        unique = list(dict.fromkeys(shots))
        if unique != list(range(1, len(unique) + 1)):
            errors.append('Shots must be numbered 1, 2, 3… in order.')
    if re.search(r'\[Shot 1\]\s*At \d', text):
        errors.append('[Shot 1] takes no timestamp.')
    times = [int(m) * 60 + float(s) for m, s in re.findall(r'\[Shot \d+\]\s*At (\d{2}):(\d{2}(?:\.\d+)?)', text)]
    if any(b <= a for a, b in zip(times, times[1:])):
        errors.append('Cut timestamps must strictly increase.')
    if any(t >= duration for t in times):
        errors.append(f'A cut falls at or after the effective duration ({duration:.3f} s).')

    opens, closes = text.count('<d>'), text.count('</d>')
    if opens != closes:
        errors.append(f'Unbalanced dialogue tags: {opens} <d> and {closes} </d>.')
    spoken = re.findall(r'<d>(.*?)</d>', text, re.S)
    for line in spoken:
        if not re.match(r'\s*\[[A-Za-z][A-Za-z \-]*\]', line):
            warnings.append('Each <d> block should start with a language tag such as [Spanish].')
            break
    words = sum(len(re.sub(r'^\s*\[[^\]]*\]', '', line).split()) for line in spoken)
    if words and words / duration > 3:
        warnings.append(f'{words} spoken words in {duration:.1f} s exceeds ~3 words/s; extend the clip or shorten with the user\'s approval.')
    if spoken and re.search(r'overall_soundscape:\s*N/A', text) and re.search(r'non_diegetic_music:\s*N/A', text):
        warnings.append('Both audio fields are N/A (complete silence) but the clip contains speech.')
    if BOOSTERS.search(text):
        warnings.append('Quality boosters ("8K", "masterpiece") do not help H3; describe visible results instead.')
    effective = h3_model_prompt(text, body.mode, body.seconds, body.first_frame, body.last_frame)
    return {'frames': frames, 'effective_duration': round(duration, 3), 'effective_prompt': effective,
            'alignment_added': effective != text.strip()}


def _check_image(body: PromptCheck, errors: list, warnings: list) -> dict:
    text = body.prompt
    if not text.strip():
        errors.append('The prompt is empty.')
    if BOOSTERS.search(text):
        warnings.append('Remove quality boosters ("8K", "masterpiece"); describe materials, light and composition instead.')
    if CANVAS.search(text):
        warnings.append('Aspect ratio and resolution are request fields; keep them out of the prompt.')
    if text.count('"') % 2:
        warnings.append('Odd number of straight double quotes; visible text must be fully quoted.')
    if body.model == 'image':
        words = len(text.split())
        if words < 60:
            warnings.append(f'Only {words} words; Qwen-Image-2.1 responds best to a full 150–500 word observer description.')
        if re.search(r'\b(create|generate|make sure|you should|please)\b', text, re.I):
            warnings.append('Describe the finished image declaratively instead of giving instructions.')
    else:
        tags = sorted({int(n) for n in re.findall(r'<image(\d+)>', text)})
        if body.images <= 1 and tags:
            warnings.append('With a single reference, refer to "the image" naturally instead of <image1>.')
        if body.images >= 2 and not tags:
            errors.append('With several references, name each one as <image1>, <image2>… and state its role.')
        if tags and tags[-1] > max(body.images, 1):
            errors.append(f'<image{tags[-1]}> has no matching reference ({body.images} supplied).')
        if body.images > 10:
            errors.append('Qwen-Image-2.1 accepts at most 10 reference images.')
        if body.images >= 2 and len(tags) < body.images:
            warnings.append('Not every reference image is mentioned; describe the role of each one.')
    return {}


def _check_music(body: PromptCheck, errors: list, warnings: list) -> dict:
    style, lyrics = body.prompt, body.lyrics
    if not style.strip():
        errors.append('The style tags are empty.')
    elif ',' not in style:
        warnings.append('YuE2 style works best as comma-separated tags (genre, mood, instruments, vocal, tempo feel).')
    if not lyrics.strip():
        errors.append('Lyrics are required; use section tags only (or [Instrumental]) for an instrumental piece.')
        return {}
    tags = [t.strip().lower() for t in re.findall(r'^\s*\[([^\]]+)\]\s*$', lyrics, re.M)]
    if not tags:
        warnings.append('Add section tags such as [Verse] and [Chorus] on their own lines.')
    unknown = sorted({t for t in tags if re.sub(r'\s*\d+$', '', t) not in SECTIONS})
    if unknown:
        warnings.append('Unusual section tag(s): ' + ', '.join(unknown) + '.')
    if re.search(r'\b(x\s?\d|\(repeat\)|repeat chorus|bis)\b', lyrics, re.I):
        warnings.append('Write repeated sections out in full instead of "x2" or "(repeat)".')
    sung = [line for line in lyrics.splitlines() if line.strip() and not re.match(r'^\s*\[[^\]]+\]\s*$', line)]
    if not sung and 'instrumental' not in style.lower():
        warnings.append('No sung lines: add "instrumental, no vocals" to the style for an instrumental piece.')
    return {'sections': len(tags), 'sung_lines': len(sung)}


def check_prompt(body: PromptCheck) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    if body.model == 'video':
        extra = _check_video(body, errors, warnings)
    elif body.model == 'music':
        extra = _check_music(body, errors, warnings)
    else:
        extra = _check_image(body, errors, warnings)
    return {'ok': not errors, 'errors': errors, 'warnings': list(dict.fromkeys(warnings)),
            'note': 'Structural check only; it does not predict output quality.', **extra}
