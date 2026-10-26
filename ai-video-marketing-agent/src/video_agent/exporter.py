"""Exportación: presets por plataforma, vista previa, miniatura y formatos adicionales."""
from __future__ import annotations

from pathlib import Path

from . import config, ff


def preset(name: str) -> dict:
    plats = config.platforms()
    if name not in plats:
        raise ValueError(f"Preset desconocido '{name}'. Opciones: {', '.join(plats)}")
    return plats[name]


def resolution_for(platform: str, width: int | None = None, height: int | None = None) -> tuple[int, int, float]:
    p = preset(platform)
    w, h = width or p["width"], height or p["height"]
    if w % 2 or h % 2:
        raise ValueError("La resolución debe tener ancho y alto pares (requisito de H.264 yuv420p)")
    return w, h, float(p["fps"])


def make_preview(src: Path, out: Path, max_side: int = 640) -> Path:
    """Vista previa ligera para revisar o compartir rápidamente."""
    out.parent.mkdir(parents=True, exist_ok=True)
    ff.ffmpeg("-i", src, "-vf", f"scale='if(gt(iw,ih),{max_side},-2)':'if(gt(iw,ih),-2,{max_side})'",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", out)
    return out


def make_thumbnail(src: Path, out: Path, t: float = 1.0) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    ff.ffmpeg("-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-q:v", "2", out)
    return out


def convert(src: Path, out: Path, fmt: str) -> Path:
    """Copia del vídeo final en otro formato (webm VP9/Opus o mov H.264/AAC)."""
    if fmt == "webm":
        args = ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1", "-c:a", "libopus", "-b:a", "160k"]
    elif fmt == "mov":
        args = ["-c", "copy"]
    elif fmt == "mp4":
        args = ["-c", "copy", "-movflags", "+faststart"]
    else:
        raise ValueError(f"Formato no soportado: {fmt}")
    ff.ffmpeg("-i", src, *args, out)
    return out
