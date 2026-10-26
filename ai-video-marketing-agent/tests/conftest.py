"""Material de prueba generado localmente con FFmpeg/Pillow (sin derechos de terceros)."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from video_agent import config
from video_agent.agent import VideoAgent

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(not FFMPEG, reason="FFmpeg no instalado")


def ffgen(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("media")
    m = {
        "clip_a": d / "clip_a.mp4",       # horizontal con tono de audio
        "clip_b": d / "clip_b.mp4",       # horizontal sin audio
        "clip_c": d / "clip_c.mov",       # vertical
        "clip_dup": d / "clip_a_copia.mp4",      # copia exacta (mismo SHA-256)
        "clip_reenc": d / "clip_a_reencoded.mp4",  # mismo contenido, otros bytes
        "image": d / "foto_producto.png",
        "logo": d / "logo_acme.png",
        "corrupt": d / "roto.mp4",
    }
    ffgen("-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=6", "-f", "lavfi", "-i", "sine=f=440:d=6",
          "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(m["clip_a"]))
    ffgen("-f", "lavfi", "-i", "mandelbrot=s=640x360:r=25", "-t", "5", "-c:v", "libx264", "-preset", "ultrafast",
          "-pix_fmt", "yuv420p", str(m["clip_b"]))
    ffgen("-f", "lavfi", "-i", "life=s=360x640:mold=10:r=25:ratio=0.1:death_color=#C83232:life_color=#00ff00", "-t", "5",
          "-vf", "scale=360:640", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(m["clip_c"]))
    shutil.copy2(m["clip_a"], m["clip_dup"])
    ffgen("-i", str(m["clip_a"]), "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35", "-c:a", "copy", str(m["clip_reenc"]))
    img = Image.new("RGB", (800, 600), (30, 60, 120))
    ImageDraw.Draw(img).ellipse([250, 150, 550, 450], fill=(240, 180, 40))
    img.save(m["image"])
    logo = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(logo).rectangle([20, 20, 580, 180], outline=(255, 255, 255, 255), width=10)
    logo.save(m["logo"])
    m["corrupt"].write_bytes(m["clip_a"].read_bytes()[:3000])
    return m


FAST = {"render": {"preset": "ultrafast", "intermediate_preset": "ultrafast", "crf": 28}, "qc": {"preview_frames": 4}}


@pytest.fixture
def settings():
    return config.load_settings(overrides=FAST)


@pytest.fixture
def agent(tmp_path, settings) -> VideoAgent:
    return VideoAgent(settings, tmp_path / "projects")


def small(plan, w: int = 270, h: int = 480, fps: int = 15):
    """Reduce la resolución de un plan para que las pruebas sean rápidas."""
    plan.export.width, plan.export.height, plan.export.fps = w, h, fps
    return plan


def whisper_model_available() -> bool:
    if importlib.util.find_spec("faster_whisper") is None:
        return False
    m = os.environ.get("VIDEO_AGENT_WHISPER_MODEL")
    if m and Path(m).is_dir():
        return True
    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    return cache.exists() and any(cache.glob("models--*faster-whisper*"))
