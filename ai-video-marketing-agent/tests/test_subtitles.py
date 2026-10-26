"""Subtítulos y prueba de aceptación C (transcripción real)."""
import shutil
import subprocess

import pytest

from video_agent import ff, subtitles as subs
from video_agent.motion_graphics import Palette, font_for

from conftest import requires_ffmpeg, whisper_model_available


def test_group_and_srt_roundtrip(tmp_path):
    words = subs.words_from_lines([("Hola a todos, esto es Nexus Development.", 0.0, 2.0),
                                   ("Creamos software a medida", 2.5, 4.0)])
    cues = subs.group_words(words, max_words=3)
    assert all(len(c.text.split()) <= 3 for c in cues)
    assert all(a.end <= b.start for a, b in zip(cues, cues[1:]))
    srt = subs.write_srt(cues, tmp_path / "a.srt")
    back = subs.parse_srt(srt)
    assert [c.text for c in back] == [c.text for c in cues]
    assert abs(back[-1].end - cues[-1].end) < 0.002


@pytest.mark.parametrize("style", ["minimal", "corporate", "cinematic", "gaming", "dynamic"])
def test_ass_styles(tmp_path, style, settings):
    words = subs.words_from_lines([("Más clientes con Nexus", 0.0, 1.6)])
    cues = subs.group_words(words)
    out = subs.write_ass(cues, tmp_path / "s.ass", 1080, 1920, Palette.from_list([]), font_for("subtitle", settings),
                         style, {"bottom": 0.22, "left": 0.06, "right": 0.15}, ["Nexus"])
    txt = out.read_text()
    assert "PlayResY: 1920" in txt and "Dialogue:" in txt
    margin_v = int(txt.split("Style: Default,")[1].split(",")[20])
    assert margin_v >= int(1920 * 0.22)  # por encima de la interfaz de TikTok
    if style in ("dynamic", "gaming"):
        assert txt.count("Dialogue:") == len(words) and "\\fscx112" in txt


def test_check_fit_flags_long_lines(settings):
    cues = [subs.Cue(0, 1, "palabra " * 30)]
    probs = subs.check_fit(cues, 1080, 1920, font_for("subtitle", settings), "dynamic", {"left": .06, "right": .15})
    assert probs


@requires_ffmpeg
@pytest.mark.transcription
@pytest.mark.skipif(not shutil.which("espeak-ng"), reason="espeak-ng no instalado (genera la voz de prueba)")
@pytest.mark.skipif(not whisper_model_available(), reason="faster-whisper o modelo Whisper no disponible")
def test_C_subtitles_from_real_transcription(agent, tmp_path):
    """Prueba C: vídeo con voz → transcripción real (Whisper) → subtítulos quemados."""
    voice = tmp_path / "voz.wav"
    subprocess.run(["espeak-ng", "-v", "es", "-s", "150", "-w", str(voice),
                    "Hola, bienvenidos a Nexus Development. Creamos software a medida para tu empresa."], check=True)
    video = tmp_path / "entrevista.mp4"
    ff.ffmpeg("-f", "lavfi", "-i", "testsrc2=s=480x270:r=25", "-i", voice, "-shortest", "-c:v", "libx264",
              "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", video)
    r = agent.edit([video], platform="landscape", subtitles=True, duration=None)
    assert r.plan.subtitles.enabled and r.plan.subtitles.source == "transcribe"
    srt = (r.project.root / "subtitles" / "captions.srt").read_text().lower()
    assert "nexus" in srt and "software" in srt
    assert r.qc.passed, r.qc.to_markdown()
    assert r.project.data["transcriptions"][0]["language"] == "es"
