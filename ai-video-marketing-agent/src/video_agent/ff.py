"""Envoltorio mínimo y verificable sobre ffmpeg/ffprobe."""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("video_agent")


class FFmpegError(RuntimeError):
    def __init__(self, cmd: list[str], stderr: str):
        self.cmd = cmd
        self.stderr = stderr
        tail = "\n".join(stderr.strip().splitlines()[-15:])
        super().__init__(f"FFmpeg falló ({cmd[0]}):\n{tail}")


def require(binary: str = "ffmpeg") -> str:
    path = shutil.which(binary)
    if not path:
        raise FFmpegError([binary], f"'{binary}' no está instalado o no está en el PATH. Consulta README → Instalación de FFmpeg.")
    return path


def run(args: list[str], *, capture: bool = True, check: bool = True, timeout: float | None = None,
        cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    cmd = [require(args[0])] + [str(a) for a in args[1:]]
    log.debug("$ (cwd=%s) %s", cwd or ".", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout, errors="replace", cwd=cwd)
    if check and proc.returncode != 0:
        raise FFmpegError(cmd, proc.stderr or "")
    return proc


def ffmpeg(*args: str | Path, check: bool = True, timeout: float | None = None,
           cwd: str | Path | None = None) -> subprocess.CompletedProcess:
    return run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *map(str, args)], check=check, timeout=timeout, cwd=cwd)


@lru_cache(maxsize=None)
def available_filters() -> frozenset[str]:
    out = run(["ffmpeg", "-hide_banner", "-filters"]).stdout
    names = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3 and re.fullmatch(r"[TSC.|]{3}", parts[0]):
            names.add(parts[1])
    return frozenset(names)


@lru_cache(maxsize=None)
def available_encoders() -> frozenset[str]:
    out = run(["ffmpeg", "-hide_banner", "-encoders"]).stdout
    return frozenset(p.split()[1] for p in out.splitlines() if len(p.split()) > 1 and re.fullmatch(r"[VAS.][F.][S.][X.][B.][D.]", p.split()[0]))


@dataclass
class MediaInfo:
    path: Path
    format_name: str = ""
    duration: float = 0.0
    size_bytes: int = 0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str | None = None
    pix_fmt: str | None = None
    sar: str | None = None
    video_duration: float | None = None
    audio_codec: str | None = None
    audio_channels: int = 0
    sample_rate: int = 0
    audio_duration: float | None = None
    video_start: float = 0.0
    audio_start: float = 0.0
    is_image: bool = False
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def has_video(self) -> bool:
        return self.video_codec is not None

    @property
    def has_audio(self) -> bool:
        return self.audio_codec is not None

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 0.0

    def summary(self) -> dict:
        return {
            "path": str(self.path), "format": self.format_name, "duration": round(self.duration, 3),
            "size_mb": round(self.size_bytes / 1e6, 2), "width": self.width, "height": self.height,
            "fps": round(self.fps, 3), "video_codec": self.video_codec, "pix_fmt": self.pix_fmt,
            "audio_codec": self.audio_codec, "audio_channels": self.audio_channels,
            "sample_rate": self.sample_rate, "is_image": self.is_image,
        }


IMAGE_CODECS = {"png", "mjpeg", "webp", "bmp", "tiff", "gif", "jpegls"}


def _rate(s: str | None) -> float:
    if not s or s in ("0/0",):
        return 0.0
    if "/" in s:
        n, d = s.split("/")
        return float(n) / float(d) if float(d) else 0.0
    return float(s)


def probe(path: str | Path) -> MediaInfo:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]).stdout
    data = json.loads(out or "{}")
    fmt = data.get("format", {})
    info = MediaInfo(path=path, format_name=fmt.get("format_name", ""), raw=data,
                     duration=float(fmt.get("duration") or 0), size_bytes=int(fmt.get("size") or 0))
    for st in data.get("streams", []):
        if st.get("codec_type") == "video" and info.video_codec is None:
            if st.get("disposition", {}).get("attached_pic"):
                continue
            info.video_codec = st.get("codec_name")
            info.width, info.height = int(st.get("width", 0)), int(st.get("height", 0))
            info.fps = _rate(st.get("avg_frame_rate")) or _rate(st.get("r_frame_rate"))
            info.pix_fmt = st.get("pix_fmt")
            info.sar = st.get("sample_aspect_ratio")
            info.video_duration = float(st["duration"]) if st.get("duration") else None
            info.video_start = float(st.get("start_time") or 0)
            info.is_image = info.video_codec in IMAGE_CODECS and (fmt.get("format_name", "").endswith("_pipe") or info.duration < 0.1 or "image2" in fmt.get("format_name", ""))
            # rotación en vídeos de móvil
            rot = 0
            for sd in st.get("side_data_list", []) or []:
                if "rotation" in sd:
                    rot = int(sd["rotation"])
            if abs(rot) in (90, 270):
                info.width, info.height = info.height, info.width
        elif st.get("codec_type") == "audio" and info.audio_codec is None:
            info.audio_codec = st.get("codec_name")
            info.audio_channels = int(st.get("channels", 0))
            info.sample_rate = int(st.get("sample_rate", 0))
            info.audio_duration = float(st["duration"]) if st.get("duration") else None
            info.audio_start = float(st.get("start_time") or 0)
    if info.is_image:
        info.duration = 0.0
    return info


SAFE_FILTER_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")


def filter_path(path: str | Path, cwd: Path) -> str:
    """Ruta relativa a `cwd` apta para usarse dentro de un filtro de FFmpeg.

    Las rutas que se pasan a filtros (subtítulos ASS, etc.) se generan siempre
    dentro del proyecto con nombres seguros y FFmpeg se ejecuta con cwd=proyecto,
    así se evitan los problemas de escape de ':' '\\' o comillas.
    """
    rel = Path(path).resolve().relative_to(cwd.resolve()).as_posix()
    if not SAFE_FILTER_PATH.match(rel):
        raise ValueError(f"Ruta no segura para un filtro FFmpeg: {rel}")
    return rel


def db_to_gain(db: float) -> float:
    return 10 ** (db / 20.0)
