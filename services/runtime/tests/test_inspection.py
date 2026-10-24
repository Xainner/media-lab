import io
import pytest
from PIL import Image
from media_lab.artifacts import ArtifactStore
from media_lab.inspection import inspect_media


def test_inspection_is_reduced_checked_and_ephemeral(tmp_path):
    artifacts = ArtifactStore(tmp_path / "artifacts", 20 * 1024**2, 20_000_000)
    buf = io.BytesIO()
    Image.new("RGBA", (1024, 1024), (255, 0, 0, 0)).save(buf, "PNG")
    ref = artifacts.import_image("session", buf.getvalue(), {"prompt": "dragon"})
    before = sorted(str(p) for p in artifacts.root.rglob("*"))
    result = inspect_media(artifacts, ref["uri"], ref["sha256"])
    assert result["kind"] == "image" and result["width"] == 1024
    assert result["preview"]["mime"] == "image/png"
    assert sorted(str(p) for p in artifacts.root.rglob("*")) == before
    with pytest.raises(ValueError):
        inspect_media(artifacts, ref["uri"], "a" * 64)
    with pytest.raises(ValueError):
        inspect_media(artifacts, ref["uri"], "")
    assert len(artifacts.search_library("dragon", "images")) == 1
    assert not artifacts.search_library("absent")
    assert not artifacts.search_library("dragon", "songs")


def test_video_sheet_uses_video_stream_not_longer_audio(tmp_path, monkeypatch):
    from media_lab import inspection
    artifacts = ArtifactStore(tmp_path / "artifacts", 20 * 1024**2, 20_000_000)
    ref = artifacts.put_media("session", b"checked-video", "video/mp4", "productions", {})
    monkeypatch.setattr(inspection, "media_probe", lambda _: {"duration": 10, "video_duration": 5})
    def frame(command, **kwargs):
        assert float(command[command.index("-ss") + 1]) < 5
        Image.new("RGB", (384, 216), "red").save(command[-1], "JPEG")
    monkeypatch.setattr(inspection.subprocess, "run", frame)
    before = sorted(str(p) for p in artifacts.root.rglob("*"))
    result = inspect_media(artifacts, ref["uri"], ref["sha256"])
    assert len(result["timestamps"]) == 6
    assert max(result["timestamps"]) < 5
    assert sorted(str(p) for p in artifacts.root.rglob("*")) == before


def test_probe_reads_matroska_video_duration(monkeypatch, tmp_path):
    from media_lab import creative
    from types import SimpleNamespace
    monkeypatch.setattr(creative.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=
        '{"format":{"duration":"10"},"streams":[{"codec_type":"video","tags":{"DURATION":"00:00:05.125"}}]}'))
    assert creative.media_probe(tmp_path / "test.mkv")["video_duration"] == 5.125
