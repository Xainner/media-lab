import pytest
from pydantic import ValidationError

from media_lab.contracts import SpeechRequest
from media_lab.creative_workflows import speech_workflow

REF = {"uri": "artifact://a", "sha256": "a" * 64}


def test_preset_and_design_need_no_reference():
    graph = speech_workflow("Hola", "preset", "spanish", "ryan", "susurrando", 3, fmt="mp3")
    assert graph["speak"]["class_type"] == "MediaLabSpeech" and "reference" not in graph
    assert graph["speak"]["inputs"]["speaker"] == "ryan" and graph["save"]["inputs"]["format.quality"] == "V0"
    assert SpeechRequest(text="Hola").voice == "preset"
    with pytest.raises(ValidationError):
        SpeechRequest(text="Hola", voice="design")
    assert SpeechRequest(text="Hola", voice="design", instruct="a warm old man").voice == "design"


def test_cloning_needs_a_reference_and_consent():
    graph = speech_workflow("Hola", "clone", "auto", "serena", "", 3, "voice.wav", "lo que dice")
    assert graph["speak"]["inputs"]["reference"] == ["reference", 0]
    assert graph["reference"]["inputs"]["audio"] == "voice.wav"
    with pytest.raises(ValidationError):
        SpeechRequest(text="Hola", voice="clone", reference=REF)
    with pytest.raises(ValidationError):
        SpeechRequest(text="Hola", voice="clone", consent=True)
    assert SpeechRequest(text="Hola", voice="clone", reference=REF, consent=True).consent
    for bad in ({"reference": REF}, {"consent": True}, {"reference_text": "x"}):
        with pytest.raises(ValidationError):
            SpeechRequest(text="Hola", **bad)
