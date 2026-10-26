import pytest

from video_agent import exporter, ff

from conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


def test_presets():
    assert exporter.resolution_for("tiktok") == (1080, 1920, 30.0)
    assert exporter.resolution_for("youtube")[:2] == (1920, 1080)
    assert exporter.resolution_for("square")[:2] == (1080, 1080)
    with pytest.raises(ValueError):
        exporter.resolution_for("tiktok", 1081, 1920)
    with pytest.raises(ValueError):
        exporter.preset("myspace")


def test_preview_thumbnail_and_formats(media, tmp_path):
    pv = exporter.make_preview(media["clip_a"], tmp_path / "p.mp4", max_side=320)
    assert ff.probe(pv).width == 320
    th = exporter.make_thumbnail(media["clip_a"], tmp_path / "t.jpg", 1.0)
    assert th.stat().st_size > 0
    webm = exporter.convert(media["clip_a"], tmp_path / "v.webm", "webm")
    info = ff.probe(webm)
    assert info.video_codec == "vp9" and info.audio_codec == "opus"
