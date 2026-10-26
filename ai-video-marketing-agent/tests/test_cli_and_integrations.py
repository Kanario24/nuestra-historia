import io
import json
import os
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from video_agent import asset_search, audio, config
from video_agent.cli import main
from video_agent.integrations import PermissionDenied, doctor, require_permission
from video_agent.project_manager import Project

from conftest import requires_ffmpeg

ROOT = Path(__file__).resolve().parents[1]


def test_cli_help_lists_commands():
    res = CliRunner().invoke(main, ["--help"], obj={})
    assert res.exit_code == 0
    for cmd in ["create", "edit", "inspect", "variants", "render", "shorts", "subtitle", "doctor"]:
        assert cmd in res.output


def test_cli_validates_parameters():
    r = CliRunner().invoke(main, ["create", "x", "--platform", "myspace"], obj={})
    assert r.exit_code == 2 and "myspace" in r.output
    r = CliRunner().invoke(main, ["inspect", "/no/existe.mp4"], obj={})
    assert r.exit_code == 2


@requires_ffmpeg
def test_cli_inspect_exit_codes(media, tmp_path):
    ok = CliRunner().invoke(main, ["inspect", str(media["clip_a"]), "--duration", "6", "--frames-dir", str(tmp_path / "a")], obj={})
    assert ok.exit_code == 0, ok.output
    bad = CliRunner().invoke(main, ["inspect", str(media["corrupt"]), "--frames-dir", str(tmp_path / "b"), "--json"], obj={})
    assert bad.exit_code == 1 and json.loads(bad.output)["passed"] is False


def test_cli_plan_only(tmp_path):
    r = CliRunner().invoke(main, ["--projects-dir", str(tmp_path), "create", "Vídeo de 15 s para Reels de Acme", "--plan-only"], obj={})
    assert r.exit_code == 0, r.output
    pj = next(tmp_path.glob("*/project.json"))
    plan = json.loads(pj.read_text())["plan"]
    assert plan["platform"] == "instagram_reels" and plan["duration"] == 15
    assert (pj.parent / "storyboard" / "storyboard.md").exists()


@requires_ffmpeg
def test_doctor(settings):
    rep = doctor(settings)
    assert rep["tools"]["ffmpeg"] and rep["tools"]["ffmpeg_filters_missing"] == []


def test_permissions_default_deny(settings):
    with pytest.raises(PermissionDenied):
        require_permission(settings, "tts", paid=True)
    with pytest.raises(PermissionDenied):
        require_permission(settings, "subida", upload=True)
    with pytest.raises(PermissionDenied):
        require_permission(settings, "stock", network=True)
    require_permission(settings, "local")  # sin coste ni red: permitido


def test_openai_tts_refuses_without_permission(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with pytest.raises(audio.PermissionDenied):
        audio.tts_openai("hola", tmp_path / "x.wav", settings)
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(audio.ProviderUnavailable):
        audio.tts_openai("hola", tmp_path / "x.wav", settings)


def test_pexels_search_and_download_with_mock(settings, tmp_path, monkeypatch):
    """Integración Pexels probada con respuestas simuladas (la API real requiere clave y red)."""
    monkeypatch.setenv("PEXELS_API_KEY", "test")
    settings["permissions"]["allow_network_asset_search"] = True
    payload = {"videos": [{"id": 1, "url": "https://www.pexels.com/video/1", "duration": 9, "user": {"name": "Ana"},
                           "video_files": [{"file_type": "video/mp4", "link": "https://cdn/x.mp4", "width": 1080, "height": 1920}]}]}
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=0):
        calls.append(req.full_url)
        return Resp(json.dumps(payload).encode() if "api.pexels.com" in req.full_url else b"\x00" * 100)

    hits = asset_search.search_pexels("coche deportivo", settings, opener=opener)
    assert hits[0].author == "Ana" and "Pexels" in hits[0].license
    proj = Project.create("stock", tmp_path)
    rel = asset_search.download(hits[0], proj, settings, opener=opener)
    assert (proj.root / rel).exists()
    assert proj.data["provenance"][0]["license"].startswith("Pexels")
    assert "orientation=portrait" in calls[0]


def test_pexels_blocked_by_default(settings, monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "test")
    with pytest.raises(PermissionDenied):
        asset_search.search_pexels("x", settings)


def test_local_asset_search(tmp_path):
    (tmp_path / "coche_rojo.mp4").write_bytes(b"x")
    (tmp_path / "playa.jpg").write_bytes(b"x")
    hits = asset_search.search_local("coche deportivo", [tmp_path])
    assert hits[0].title == "coche_rojo"


def test_import_never_modifies_originals(media, tmp_path):
    before = media["clip_a"].read_bytes()
    p = Project.create("orig", tmp_path)
    rel = p.import_file(media["clip_a"])
    assert (p.root / rel).read_bytes() == before and media["clip_a"].read_bytes() == before
    assert p.import_file(media["clip_dup"]) == rel  # duplicado exacto: no se copia dos veces


# ------------------------------------------------------------------ skill (prueba F, parte automatizable)

def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n")[1])


def test_F_skill_structure():
    skill = ROOT / "skills" / "video-marketing-agent" / "SKILL.md"
    fm = _frontmatter(skill)
    assert fm["name"] == "video-marketing-agent"
    desc = fm["description"] + " " + fm.get("when_to_use", "")
    assert 50 < len(desc) <= 1536
    assert len(skill.read_text(encoding="utf-8").splitlines()) < 500
    runner = ROOT / "skills" / "video-marketing-agent" / "scripts" / "video-agent"
    assert runner.exists() and os.access(runner, os.X_OK)
    for ref in ["reference/workflow.md", "reference/plan-schema.md"]:
        assert (skill.parent / ref).exists(), ref
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "ai-video-marketing-agent"
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert market["plugins"][0]["name"] == plugin["name"]


def test_config_files_are_consistent():
    styles, plats = config.styles(), config.platforms()
    for name, st in styles.items():
        for tr in st["transitions"]:
            from video_agent.models import TRANSITIONS
            assert tr in TRANSITIONS, (name, tr)
    for name, p in plats.items():
        assert p["width"] % 2 == 0 and p["height"] % 2 == 0
        assert config.template(p["template"])["beats"]
