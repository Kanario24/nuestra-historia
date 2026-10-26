"""Prueba de aceptación D: detectar exportaciones defectuosas e informar con claridad."""
from video_agent import ff
from video_agent.quality_control import Expectations, inspect

from conftest import requires_ffmpeg

pytestmark = requires_ffmpeg


def _status(rep, name_start):
    return next(c.status for c in rep.checks if c.name.startswith(name_start))


def test_good_file_passes(media, tmp_path, settings):
    rep = inspect(media["clip_a"], Expectations(duration=6, width=640, height=360, audio=True), settings, tmp_path / "f")
    assert rep.passed, rep.to_markdown()
    assert rep.contact_sheet and len(rep.frames) == 4


def test_D_truncated_export_fails(media, tmp_path, settings):
    rep = inspect(media["corrupt"], Expectations(duration=6), settings)
    assert not rep.passed
    assert any(c.status == "fail" for c in rep.checks)
    assert "NO APROBADO" in rep.to_markdown()


def test_D_missing_file(tmp_path, settings):
    rep = inspect(tmp_path / "nada.mp4", Expectations(), settings)
    assert not rep.passed and rep.checks[0].fix == "rerender"


def test_D_black_frames_no_audio_wrong_size(tmp_path, settings):
    bad = tmp_path / "bad.mp4"
    ff.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=2", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=2",
              "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=2",
              "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264",
              "-preset", "ultrafast", "-pix_fmt", "yuv420p", bad)
    rep = inspect(bad, Expectations(duration=10, width=1080, height=1920, audio=True), settings, tmp_path / "q")
    assert not rep.passed
    assert _status(rep, "Duración") == "fail"
    assert _status(rep, "Resolución") == "fail"
    assert _status(rep, "Pista de audio") == "fail"
    assert _status(rep, "Fotogramas negros") == "fail"
    js, md = rep.save(tmp_path / "rep")
    text = md.read_text()
    assert "❌" in text and "00:02" in text
    assert set(rep.fixes) >= {"retime", "rerender", "audio", "black"}


def test_expected_black_is_allowed(tmp_path, settings):
    f = tmp_path / "fade.mp4"
    ff.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=2", "-f", "lavfi", "-i", "color=c=black:s=320x240:r=25:d=1",
              "-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=2",
              "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264",
              "-preset", "ultrafast", "-pix_fmt", "yuv420p", f)
    rep = inspect(f, Expectations(duration=5, audio=False, allowed_black=[(1.9, 3.1)]), settings)
    assert _status(rep, "Fotogramas negros") == "pass"


def test_silence_detected(tmp_path, settings):
    f = tmp_path / "sil.mp4"
    ff.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=320x240:r=25:d=6", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=6",
              "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", f)
    rep = inspect(f, Expectations(duration=6, audio=True), settings)
    assert _status(rep, "Silencios") == "fail"
