import pytest
from pydantic import ValidationError

from media_lab.contracts import SongRequest
from media_lab.creative_workflows import ACE_CLIPS, ACE_DIT, ace_caption, ace_language, ace_step_workflow, ace_tempo
from media_lab.mcp_server import GUIDES


def test_graph_follows_the_official_xl_turbo_template():
    graph = ace_step_workflow("cumbia, accordion", "[verse]\nhola", 95.0, 7, 100, "A minor", "es", "mp3")
    assert graph["unet"]["inputs"]["unet_name"] == ACE_DIT
    assert (graph["clip"]["inputs"]["clip_name1"], graph["clip"]["inputs"]["clip_name2"]) == ACE_CLIPS
    assert graph["clip"]["inputs"]["type"] == "ace" and graph["shift"]["inputs"]["shift"] == 3.0
    music = graph["music"]["inputs"]
    assert music["duration"] == 95.0 and graph["latent"]["inputs"]["seconds"] == 95.0
    assert (music["bpm"], music["keyscale"], music["language"], music["generate_audio_codes"]) == (100, "A minor", "es", True)
    sample = graph["sample"]["inputs"]
    assert (sample["steps"], sample["cfg"], sample["sampler_name"], sample["scheduler"]) == (8, 1.0, "euler", "simple")
    assert sample["negative"] == ["negative", 0] and graph["negative"]["class_type"] == "ConditioningZeroOut"
    assert graph["save"]["inputs"]["format"] == "mp3" and graph["save"]["inputs"]["format.quality"] == "V0"
    assert "format.quality" not in ace_step_workflow("pop", "x", 30, 1, 110, "C major", "en")["save"]["inputs"]


def test_tempo_key_and_language_come_from_the_brief():
    assert ace_tempo("reggaeton, 95 BPM, E minor, female vocals") == (95, "E minor")
    assert ace_tempo("balada, 72 bpm, Do menor") == (72, "C major")  # solfège is not parsed
    assert ace_tempo("rock, F# Mayor") == (110, "F# major")
    assert ace_tempo("ambient, 20 bpm") == (40, "C major")
    assert ace_language("[verse]\nEsta noche quiero bailar contigo\nque la luna nos vea") == "es"
    assert ace_language("[verse]\nTonight we dance under neon lights\nhold me close") == "en"
    assert ace_language("[Instrumental]") == "en"


def test_ace_requests_refuse_covers_scores_and_overlong_songs():
    ok = SongRequest(style="pop", lyrics="[verse] hi", model="ace_step", max_duration=240, bpm=128, key="E minor")
    assert ok.model == "ace_step" and SongRequest(style="pop", lyrics="x").model == "yue2"
    ref = {"uri": "artifact://s/sources/a.wav", "sha256": "a" * 64}
    for bad in ({"source_audio": ref}, {"abc": "X:1"}, {"max_duration": 700}, {"bpm": 300}, {"language": "spa"}):
        with pytest.raises(ValidationError):
            SongRequest(style="pop", lyrics="x", model="ace_step", **bad)


def test_music_guide_explains_both_engines():
    guide = "".join(str(v) for v in GUIDES.values())
    assert "`ace_step` is ACE-Step 1.5 XL" in guide and "YuE2: `mode=direct`" in guide


def test_tempo_and_key_leave_the_caption_and_the_meter_is_configurable():
    assert ace_caption("reggaeton, 95 BPM, E minor, female vocals") == "reggaeton, female vocals"
    assert ace_caption("dreamy pop, warm synths") == "dreamy pop, warm synths"
    assert ace_caption("120 bpm") == "120 bpm"  # never send an empty caption
    assert ace_step_workflow("waltz", "[Instrumental]", 60, 1, 90, "D major", "en", time_signature="3")["music"]["inputs"]["timesignature"] == "3"
    assert ace_step_workflow("pop", "x", 30, 1, 110, "C major", "en")["music"]["inputs"]["timesignature"] == "4"


def test_ace_requests_follow_the_documented_input_limits():
    assert SongRequest(style="waltz", lyrics="x", model="ace_step", time_signature="3").time_signature == "3"
    for bad in ({"style": "x" * 513}, {"lyrics": "x" * 4097}, {"time_signature": "5"}):
        with pytest.raises(ValidationError):
            SongRequest(**{"style": "pop", "lyrics": "x", "model": "ace_step", **bad})
    assert SongRequest(style="x" * 600, lyrics="x").model == "yue2"
