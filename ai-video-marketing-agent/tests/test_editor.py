"""Pruebas de aceptación A, B y E: render real con FFmpeg."""
import json
import time

import pytest
from click.testing import CliRunner

from video_agent import ff
from video_agent.cli import main
from video_agent.project_manager import Project

from conftest import FAST, requires_ffmpeg, small

pytestmark = requires_ffmpeg


def _produce_small(agent, brief, inputs, **opts):
    project, plan = agent.plan(brief, inputs, **opts)
    return agent.produce(project, small(plan))


def test_A_edit_input_video_with_cuts_and_text(agent, media):
    """Prueba A: vídeo de entrada → versión editada con cortes, textos y MP4."""
    r = _produce_small(agent, "Vídeo de 8 segundos para presentar Acme", [media["clip_a"]], platform="landscape")
    info = ff.probe(r.final)
    assert r.final.suffix == ".mp4" and r.final.name == "final.mp4"
    assert info.video_codec == "h264" and info.audio_codec == "aac"
    assert abs(info.duration - 8) < 0.3
    assert len(r.plan.scenes) >= 3                       # cortes
    assert sum(len(s.texts) for s in r.plan.scenes) >= 3  # textos
    assert any(s.source.type == "clip" for s in r.plan.scenes)
    assert r.qc.passed, r.qc.to_markdown()
    assert (r.project.root / "reports" / "qc_report.md").exists()


@pytest.mark.slow
def test_B_tiktok_vertical_from_clips(agent, media):
    """Prueba B: TikTok vertical 1080×1920 a partir de clips horizontales y verticales."""
    project, plan = agent.plan("Vídeo de 12 segundos para TikTok de la marca Acme, estilo dinámico",
                               [media["clip_a"], media["clip_b"], media["clip_c"], media["logo"]])
    plan.export.fps = 24  # más rápido sin cambiar la resolución
    r = agent.produce(project, plan)
    info = ff.probe(r.final)
    assert (info.width, info.height) == (1080, 1920)
    assert abs(info.duration - 12) < 0.3
    assert r.qc.passed, r.qc.to_markdown()
    srcs = {s.source.path for s in plan.scenes if s.source.type == "clip"}
    assert len(srcs) == 3                                 # usa los tres clips
    assert plan.scenes[-1].source.type == "logo" and plan.brand.logo.endswith(".png")


def test_duplicates_and_corrupt_files_are_excluded(agent, media):
    project, plan = agent.plan("Vídeo de 6 segundos",
                               [media["clip_a"], media["clip_dup"], media["clip_reenc"], media["corrupt"]])
    report = json.loads((project.root / "reports" / "media_analysis.json").read_text())
    by_name = {r["path"].split("/")[-1]: r for r in report}
    assert "clip-a-copia.mp4" not in by_name                       # copia exacta: no se importa dos veces
    assert by_name["roto.mp4"]["ok"] is False and by_name["roto.mp4"]["error"]
    assert by_name["clip-a-reencoded.mp4"]["duplicate_of"] == "input/clip-a.mp4"  # duplicado visual
    used = {s.source.path for s in plan.scenes if s.source.type == "clip"}
    assert len(used) == 1


def test_E_rerender_from_project_json(agent, media, tmp_path):
    """Prueba E: volver a ejecutar un proyecto desde project.json, también tras editarlo a mano."""
    r1 = _produce_small(agent, "Vídeo de 6 segundos para Acme", [media["clip_b"]])
    pj = r1.project.file
    data = json.loads(pj.read_text())
    data["plan"]["scenes"][0]["texts"][0]["text"] = "Texto cambiado"
    pj.write_text(json.dumps(data, ensure_ascii=False))
    settings_file = tmp_path / "fast.yaml"
    import yaml
    settings_file.write_text(yaml.safe_dump(FAST))
    t0 = time.time()
    res = CliRunner().invoke(main, ["--settings", str(settings_file), "render", str(r1.project.root), "--json"], obj={})
    assert res.exit_code == 0, res.output
    out = json.loads(res.output)
    assert out["passed"]
    info = ff.probe(out["final"])
    assert abs(info.duration - r1.plan.duration) < 0.1
    reopened = Project.open(r1.project.root)
    assert reopened.load_plan().scenes[0].texts[0].text == "Texto cambiado"
    assert len(reopened.data["attempts"]) >= 2
    # solo la escena modificada se vuelve a renderizar (caché)
    segs = sorted((r1.project.root / "cache").glob("seg_*.mkv"))
    assert len(segs) == len(r1.plan.scenes) + 1
    assert time.time() - t0 < 120


def test_variants_reuse_cache(agent, media):
    r = _produce_small(agent, "Vídeo de 6 segundos para Acme", [media["clip_b"]])
    results = agent.variants(r.project, 2)
    assert len(results) == 2
    hooks = [x.plan.scenes[0].texts[0].text for x in results]
    assert hooks[0] != hooks[1]
    for x in results:
        assert x.final.exists() and "variants" in str(x.final)
        assert x.qc.passed, x.qc.to_markdown()


def test_shorts_from_horizontal(agent, media):
    out = agent.shorts(media["clip_b"], count=2, duration=2, platform="youtube_shorts", subtitles=False)
    assert len(out) == 2
    for r in out:
        info = ff.probe(r.final)
        assert info.height > info.width
        assert abs(info.duration - 2) < 0.2


def test_text_overflow_is_detected_and_fixed(agent, media):
    project, plan = agent.plan("Vídeo de 5 segundos", [media["clip_b"]])
    plan = small(plan)
    plan.scenes[0].texts[0].text = "Supercalifragilisticoespialidoso " * 2
    plan.scenes[0].texts[0].scale = 3.0
    r = agent.produce(project, plan)
    attempts = r.project.data["attempts"]
    assert any(a.get("fixes_applied") for a in attempts), attempts
    assert r.plan.scenes[0].texts[0].scale < 3.0


def test_unknown_engine_is_reported(tmp_path, settings):
    from video_agent.editor import get_editor
    settings["render"]["engine"] = "moviepy"
    with pytest.raises(ValueError, match="no implementado"):
        get_editor(Project.create("x", tmp_path), settings)
