"""Inspección y análisis del material aportado, y selección de fragmentos.

El análisis es de señal (cortes de escena, negro, congelados, nitidez,
movimiento, brillo, audio), no semántico. Para entender el contenido de las
imágenes, el agente debe mirar los fotogramas de referencia que se extraen aquí.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import ff

log = logging.getLogger("video_agent")

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts", ".3gp", ".mpg", ".mpeg", ".wmv", ".flv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2"}
SUB_EXT = {".srt", ".vtt", ".ass"}


def classify(path: Path) -> str:
    ext = path.suffix.lower()
    name = path.stem.lower()
    if ext in FONT_EXT:
        return "font"
    if ext in SUB_EXT:
        return "subtitle"
    if ext in AUDIO_EXT:
        return "voice" if re.search(r"voz|voice|locuci|narra|vo[_-]", name) else "music"
    if ext in IMAGE_EXT:
        return "logo" if re.search(r"logo|isotipo|brand|marca", name) else "image"
    if ext in VIDEO_EXT:
        return "video"
    return "other"


@dataclass
class ClipAnalysis:
    path: str
    kind: str
    ok: bool = True
    error: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = False
    scene_cuts: list[float] = field(default_factory=list)
    black: list[tuple[float, float]] = field(default_factory=list)
    frozen: list[tuple[float, float]] = field(default_factory=list)
    per_second: list[dict] = field(default_factory=list)   # luma, sharpness, motion, loudness
    ahash: str = ""
    duplicate_of: str | None = None
    speech_ratio: float = 0.0
    reference_frames: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _frames_gray(path: Path, fps: float = 2.0, size: int = 64, max_seconds: float = 600) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(max_seconds), "-i", str(path), "-vf",
                          f"fps={fps},scale={size}:{size},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (size * size)
    return np.frombuffer(raw[: n * size * size], np.uint8).reshape(n, size, size).astype(np.float32)


def _audio_rms_per_second(path: Path, max_seconds: float = 600) -> np.ndarray:
    sr = 8000
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(max_seconds), "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if x.size < sr:
        return np.zeros(0)
    x = x[: x.size // sr * sr].reshape(-1, sr)
    return 20 * np.log10(np.sqrt((x ** 2).mean(axis=1)) + 1e-6)


def ahash(img: Image.Image) -> str:
    g = np.asarray(img.convert("L").resize((8, 8)), dtype=np.float32)
    bits = (g > g.mean()).flatten()
    return "".join("1" if b else "0" for b in bits)


def hamming(a: str, b: str) -> int:
    return sum(x != y for x, y in zip(a, b)) if a and b else 64


def detect_scene_cuts(path: Path, threshold: float = 0.3, max_seconds: float = 600) -> list[float]:
    proc = ff.ffmpeg("-t", str(max_seconds), "-i", path, "-an", "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo",
                     "-f", "null", "-", check=False)
    return [round(float(m), 3) for m in re.findall(r"pts_time:([\d.]+)", proc.stderr)]


def detect_black(path: Path, min_d: float = 0.4, pix_th: float = 0.10) -> list[tuple[float, float]]:
    proc = ff.ffmpeg("-i", path, "-an", "-vf", f"blackdetect=d={min_d}:pix_th={pix_th}", "-f", "null", "-", check=False)
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", proc.stderr)]


def detect_freeze(path: Path, min_d: float = 2.0) -> list[tuple[float, float]]:
    proc = ff.ffmpeg("-i", path, "-an", "-vf", f"freezedetect=n=0.003:d={min_d}", "-f", "null", "-", check=False)
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", proc.stderr)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", proc.stderr)]
    return list(zip(starts, ends + [float("inf")] * (len(starts) - len(ends))))


def extract_frame(path: Path, t: float, out: Path, width: int = 480) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    ff.ffmpeg("-ss", f"{max(0, t):.3f}", "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "3", out)
    return out


def analyze_clip(path: Path, frames_dir: Path | None = None, deep: bool = True) -> ClipAnalysis:
    kind = classify(path)
    a = ClipAnalysis(path=str(path), kind=kind)
    try:
        info = ff.probe(path)
    except Exception as e:  # archivo corrupto / no multimedia
        a.ok, a.error = False, f"ffprobe no puede leerlo: {str(e).splitlines()[-1][:200]}"
        return a
    a.duration, a.width, a.height, a.fps, a.has_audio = info.duration, info.width, info.height, info.fps, info.has_audio
    if kind in ("image", "logo"):
        if not info.has_video:
            a.ok, a.error = False, "imagen no decodificable"
            return a
        try:
            with Image.open(path) as im:
                a.ahash = ahash(im)
        except Exception as e:
            a.ok, a.error = False, f"imagen no válida: {e}"
        return a
    if kind != "video":
        return a
    if not info.has_video or info.duration <= 0:
        a.ok, a.error = False, "sin pista de vídeo o duración nula"
        return a
    # decodificación completa para detectar archivos dañados
    chk = ff.ffmpeg("-v", "error", "-i", path, "-f", "null", "-", check=False)
    errors = [l for l in chk.stderr.splitlines() if l.strip()]
    if chk.returncode != 0 or len(errors) > 5:
        a.ok, a.error = False, f"errores de decodificación: {errors[-1][:200] if errors else chk.returncode}"
        return a
    if not deep:
        return a
    a.scene_cuts = detect_scene_cuts(path)
    a.black = detect_black(path)
    a.frozen = detect_freeze(path)
    g = _frames_gray(path, fps=2.0)
    rms = _audio_rms_per_second(path) if info.has_audio else np.zeros(0)
    secs = int(np.ceil(info.duration))
    for s in range(secs):
        fr = g[s * 2: s * 2 + 2]
        if fr.size == 0:
            break
        lap = np.abs(np.diff(fr, axis=1)).mean() + np.abs(np.diff(fr, axis=2)).mean()
        mot = float(np.abs(np.diff(g[max(0, s * 2 - 1): s * 2 + 2], axis=0)).mean()) if fr.shape[0] > 0 and s > 0 else 0.0
        a.per_second.append({"t": s, "luma": round(float(fr.mean()), 1), "sharpness": round(float(lap), 2),
                             "motion": round(mot, 2), "loudness_db": round(float(rms[s]), 1) if s < rms.size else None})
    if rms.size:
        a.speech_ratio = round(float((rms > -35).mean()), 2)
    mid = info.duration / 2
    with Image.fromarray(g[min(len(g) - 1, int(mid * 2))].astype(np.uint8)) as im:
        a.ahash = ahash(im)
    if frames_dir is not None:
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", path.stem)
        for i, t in enumerate(np.linspace(0.1, max(0.1, info.duration - 0.2), 4)):
            a.reference_frames.append(str(extract_frame(path, float(t), frames_dir / f"{stem}_{i}.jpg")))
    return a


def mark_duplicates(analyses: list[ClipAnalysis], max_distance: int = 4) -> None:
    for i, a in enumerate(analyses):
        if not a.ok or not a.ahash:
            continue
        for b in analyses[:i]:
            if b.ok and b.kind == a.kind and b.duplicate_of is None and hamming(a.ahash, b.ahash) <= max_distance \
                    and abs(a.duration - b.duration) < 0.5:
                a.duplicate_of = b.path
                break


# ----------------------------------------------------------- selección

@dataclass
class Segment:
    path: str
    start: float
    duration: float
    score: float


def _window_score(a: ClipAnalysis, start: float, dur: float) -> float:
    rows = [r for r in a.per_second if start - 0.5 <= r["t"] < start + dur]
    if not rows:
        return 0.0
    sharp = np.mean([r["sharpness"] for r in rows])
    motion = np.mean([r["motion"] for r in rows])
    luma = np.mean([r["luma"] for r in rows])
    luma_ok = 1.0 - min(1.0, abs(luma - 120) / 120)
    score = 0.45 * min(1.0, sharp / 25) + 0.25 * min(1.0, motion / 12) + 0.30 * luma_ok
    # penaliza negro, congelados y cortes de escena dentro de la ventana
    for s, e in a.black + a.frozen:
        if s < start + dur and e > start:
            score -= 0.6
    if any(start + 0.15 < c < start + dur - 0.15 for c in a.scene_cuts):
        score -= 0.15
    return float(score)


def choose_segments(analyses: list[ClipAnalysis], durations: list[float], step: float = 0.5) -> list[Segment | None]:
    """Asigna a cada escena el mejor fragmento disponible sin repetir material.

    Reparte las escenas entre clips distintos (rotación) y elige dentro de cada
    clip la ventana con mejor puntuación de señal que no se solape con otra ya usada.
    """
    clips = [a for a in analyses if a.ok and a.kind == "video" and a.duplicate_of is None and a.duration > 0.5]
    used: dict[str, list[tuple[float, float]]] = {c.path: [] for c in clips}
    result: list[Segment | None] = []
    if not clips:
        return [None] * len(durations)
    for i, dur in enumerate(durations):
        best: Segment | None = None
        order = clips[i % len(clips):] + clips[: i % len(clips)]
        for rank, c in enumerate(order):
            need = dur
            if c.duration < need:
                continue
            for s in np.arange(0, c.duration - need + 1e-6, step):
                if any(s < ue and s + need > us for us, ue in used[c.path]):
                    continue
                sc = _window_score(c, float(s), need) - 0.05 * rank - 0.02 * (len(used[c.path]))
                if best is None or sc > best.score:
                    best = Segment(c.path, round(float(s), 3), need, sc)
        if best is None:  # el material es más corto que la escena: usa el clip más largo (se ralentiza/congela al final)
            c = max(clips, key=lambda x: x.duration)
            best = Segment(c.path, 0.0, min(dur, c.duration), -1.0)
        used.setdefault(best.path, []).append((best.start, best.start + best.duration))
        result.append(best)
    return result
