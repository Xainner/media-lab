import pytest
from pydantic import ValidationError

from media_lab.comfy import ComfyClient, ComfyError
from media_lab.contracts import StemsRequest
from media_lab.creative import check_stems_input
from media_lab.creative_workflows import STEMS_MODEL, stems_ready, stems_workflow

REF = {"uri": "artifact://s/songs/a.flac", "sha256": "a" * 64}


def test_two_stems_save_vocals_and_instrumental():
    graph = stems_workflow("song.flac", "two")
    assert graph["split"] == {"class_type": "MediaLabStems", "inputs": {"audio": ["load", 0]}}
    assert sorted(k for k in graph if k.startswith("save_")) == ["save_instrumental", "save_vocals"]
    assert graph["save_vocals"]["inputs"]["audio"] == ["split", 0]
    assert graph["save_instrumental"]["inputs"]["audio"] == ["split", 1]
    assert "format.quality" not in graph["save_vocals"]["inputs"]


def test_four_stems_map_to_the_node_outputs_and_mp3_quality():
    graph = stems_workflow("song.mp3", "four", "mp3")
    assert {k: v["inputs"]["audio"][1] for k, v in graph.items() if k.startswith("save_")} == {
        "save_vocals": 0, "save_drums": 2, "save_bass": 3, "save_other": 4}
    assert graph["save_drums"]["inputs"]["format.quality"] == "V0"


def test_ready_limits_and_request(tmp_path):
    assert not stems_ready(tmp_path)
    (tmp_path / "stems").mkdir()
    (tmp_path / "stems" / STEMS_MODEL).touch()
    assert stems_ready(tmp_path)
    check_stems_input({"duration": 180.0, "streams": [{"codec_type": "audio"}]})
    with pytest.raises(ValueError):
        check_stems_input({"duration": 180.0, "streams": [{"codec_type": "video"}]})
    with pytest.raises(ValueError):
        check_stems_input({"duration": 901.0, "streams": [{"codec_type": "audio"}]})
    assert StemsRequest(audio=REF).stems == "two"
    with pytest.raises(ValidationError):
        StemsRequest(audio=REF, stems="six")


def test_run_outputs_fetches_each_save_node(monkeypatch):
    client = ComfyClient("http://comfy", 5)
    history = {"p": {"outputs": {"save_vocals": {"audio": [{"filename": "v.flac", "subfolder": "media_lab"}]},
                                 "save_instrumental": {"audio": [{"filename": "i.flac", "subfolder": "media_lab"}]}}}}
    monkeypatch.setattr(client, "_execute", lambda *a: (history, "p"))
    fetched = []

    class Response:
        def __init__(self, name): self.content = name.encode()
        def raise_for_status(self): pass

    class Http:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def get(self, url, params):
            fetched.append(params["filename"])
            return Response(params["filename"])

    monkeypatch.setattr("media_lab.comfy.httpx.Client", Http)
    files, backend = client.run_outputs({}, ["save_vocals", "save_instrumental"], "audio", lambda p: None, lambda: False)
    assert files == {"save_vocals": b"v.flac", "save_instrumental": b"i.flac"} and backend == {"prompt_id": "p"}
    with pytest.raises(ComfyError):
        client.run_outputs({}, ["save_drums"], "audio", lambda p: None, lambda: False)
