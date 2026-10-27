from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from media_lab import main
from media_lab.contracts import EditRequest

REF = {"uri": "artifact://s/images/a.png", "sha256": "a" * 64}


@pytest.fixture
def admit(monkeypatch):
    """Run the edit admission checks with the GPU job queue stubbed out."""
    monkeypatch.setattr(main, "require_image_model", lambda *_: None)
    monkeypatch.setattr(main, "camera_ready", lambda *_: True)
    monkeypatch.setattr(main, "resolve_loras", lambda *_: [])
    monkeypatch.setattr(main, "artifacts", SimpleNamespace(resolve=lambda *_: None))
    monkeypatch.setattr(main, "jobs", SimpleNamespace(submit_edit=lambda *_: {"job_id": "j", "status": "queued"}))

    def run(enable_2k: bool, **fields):
        monkeypatch.setattr(main, "SETTINGS", replace(main.SETTINGS, enable_2k=enable_2k))
        body = EditRequest(**{"prompt": "relight", "references": [REF], "resolution": 2048, **fields})
        try:
            return main.edit(body, None)
        except HTTPException as exc:
            return exc.detail
    return run


def test_2k_edit_runs_on_int8_qwen_with_up_to_four_references(admit):
    assert admit(True)["job_id"] == "j"
    assert admit(True, references=[REF] * 4, model_variant="turbo")["job_id"] == "j"


def test_2k_edit_is_refused_outside_its_tested_envelope(admit):
    assert "not enabled" in admit(False)
    assert "INT8" in admit(True, model_precision="bf16")
    assert "up to 4 references" in admit(True, references=[REF] * 5)
    assert "camera" in admit(True, camera={"azimuth": "back view", "elevation": "eye-level shot", "distance": "medium shot"}, prompt="")
    assert "camera" in admit(True, remove_background=True, prompt="")


def test_capabilities_report_the_2k_edit_envelope():
    caps = main.capabilities()
    caps = caps.get("data", caps)
    assert caps["two_k_create_only"] is False
    assert caps["two_k_edit"] == {"max_resolution": 2048, "max_references": 4, "precisions": ["int8"], "models": ["qwen"]}
