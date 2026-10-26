import json

import pytest
from pydantic import ValidationError

from video_agent import marketing
from video_agent.models import EditPlan, Scene, Source
from video_agent.planner import AssetSet, build_plan, parse_brief, snap_to_beats, storyboard_markdown

NEXUS = ("Quiero un vídeo de 25 segundos para promocionar Nexus Development. Quiero una estética tecnológica, oscura y "
         "elegante, con transiciones dinámicas, música electrónica, textos impactantes y un final con el logotipo. "
         "Formato vertical para TikTok")


def test_parse_brief_example():
    info = parse_brief(NEXUS)
    assert info.duration == 25
    assert info.platform == "tiktok"
    assert info.style == "tech_dark"
    assert info.brand == "Nexus Development"
    assert info.music is True and info.music_mood == "electronic"
    assert info.language == "es"


@pytest.mark.parametrize("brief,field,value", [
    ("Hazme un vídeo de 30 segundos para TikTok", "duration", 30),
    ("Crea un vídeo cinematográfico épico", "style", "cinematic"),
    ("Haz un vídeo de gaming con cortes rápidos", "style", "gaming"),
    ("Convierte esto en un Short de YouTube", "platform", "youtube_shorts"),
    ("Vídeo horizontal para YouTube de 2 minutos", "duration", 120),
    ("Make a 20 second Instagram reel for Acme Cloud with voiceover", "voiceover", True),
    ("Crea una campaña para conseguir clientes para \"Panadería Sol\"", "brand", "Panadería Sol"),
    ("Anuncio vertical sin música", "music", False),
])
def test_parse_brief_cases(brief, field, value):
    assert getattr(parse_brief(brief), field) == value


def test_goal_detection_word_boundaries():
    assert marketing.detect_goal("Crea una campaña para conseguir clientes") == "leads"
    # "panadería" no debe activar el estilo tecnológico por contener "ia"
    assert parse_brief("Vídeo para la panadería del barrio").style != "tech_dark"


def test_plan_timing_matches_duration():
    plan = build_plan(NEXUS, "nexus")
    assert abs(sum(s.duration for s in plan.scenes) - 25) < 1e-6
    assert plan.duration == 25
    t = 0
    for sc in plan.scenes:  # escenas contiguas
        assert abs(sc.start - t) < 1e-6
        t += sc.duration
    assert plan.scenes[0].purpose == "hook" and plan.scenes[-1].purpose == "cta"
    assert plan.scenes[-1].source.type == "logo"
    assert (plan.export.width, plan.export.height) == (1080, 1920)


def test_cuts_snapped_to_beat():
    plan = build_plan(NEXUS, "nexus")
    beat = 60 / plan.music.bpm
    for sc in plan.scenes[1:]:
        assert abs(sc.start / beat - round(sc.start / beat)) < 1e-6


def test_snap_to_beats_keeps_total():
    d = snap_to_beats([2.7, 4.1, 5.3, 3.9], 120)
    assert abs(sum(d) - 16.0) < 1e-6


def test_plan_uses_user_assets(media):
    from video_agent.media_manager import analyze_clip
    assets = AssetSet(clips=[analyze_clip(media["clip_a"]), analyze_clip(media["clip_b"])], logo="logo.png")
    plan = build_plan("Anuncio de 12 segundos para Acme", "acme", assets)
    used = {sc.source.path for sc in plan.scenes if sc.source.type == "clip"}
    assert used == {str(media["clip_a"]), str(media["clip_b"])}
    assert plan.scenes[-1].source.path == "logo.png"


def test_plan_json_roundtrip_and_storyboard():
    plan = build_plan(NEXUS, "nexus")
    again = EditPlan.model_validate(json.loads(plan.model_dump_json()))
    assert again == plan
    md = storyboard_markdown(plan)
    assert "00:00.00–" in md and "| s01 |" in md


def test_invalid_transition_rejected():
    with pytest.raises(ValidationError):
        Scene(id="x", duration=2, source=Source(type="generated"), transition="explosion")


def test_hook_variants_unique():
    v = marketing.hook_variants(["A", "B"], "Acme", "es", 5)
    assert len(v) == 5 and len(set(v)) == 5
