"""Control de calidad automático de un vídeo exportado.

Todas las comprobaciones se ejecutan de verdad con FFmpeg/ffprobe sobre el
archivo. La revisión visual es por muestreo de fotogramas: se generan una hoja
de contactos y métricas por fotograma; la interpretación semántica de esas
imágenes la hace el agente mirándolas (no este módulo).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import audio as audio_mod
from . import ff
from .media_manager import ahash, extract_frame, hamming
from .motion_graphics import contact_sheet
from .models import fmt_ts

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""
    fix: str | None = None          # código de corrección automática sugerida
    data: dict = field(default_factory=dict)


@dataclass
class Expectations:
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    audio: bool = True
    allowed_black: list[tuple[float, float]] = field(default_factory=list)
    allowed_silence: list[tuple[float, float]] = field(default_factory=list)
    loudness_lufs: float | None = None
    text_layout: dict = field(default_factory=dict)
    subtitle_problems: list[str] = field(default_factory=list)
    sample_times: list[float] = field(default_factory=list)
    sample_labels: list[str] = field(default_factory=list)


@dataclass
class QCReport:
    file: str
    checks: list[Check] = field(default_factory=list)
    frames: list[str] = field(default_factory=list)
    contact_sheet: str | None = None
    info: dict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(c.status == FAIL for c in self.checks)

    @property
    def fixes(self) -> list[str]:
        return sorted({c.fix for c in self.checks if c.fix and c.status in (FAIL, WARN)})

    def add(self, *a, **kw) -> Check:
        c = Check(*a, **kw)
        self.checks.append(c)
        return c

    def to_dict(self) -> dict:
        return {"file": self.file, "passed": self.passed, "checks": [asdict(c) for c in self.checks], "frames": self.frames,
                "contact_sheet": self.contact_sheet, "info": self.info, "limitations": self.limitations, "fixes": self.fixes}

    def to_markdown(self) -> str:
        icon = {PASS: "✅", WARN: "⚠️", FAIL: "❌", SKIP: "⏭️"}
        verdict = "APROBADO (sin fallos detectados en las comprobaciones realizadas)" if self.passed else "NO APROBADO"
        out = ["# Informe de control de calidad", "", f"- **Archivo:** `{self.file}`", f"- **Resultado:** {verdict}"]
        if self.info:
            i = self.info
            out.append(f"- **Formato:** {i.get('width')}×{i.get('height')} · {i.get('fps')} fps · {i.get('duration')} s · "
                       f"vídeo {i.get('video_codec')} / audio {i.get('audio_codec')} · {i.get('size_mb')} MB")
        out += ["", "| Estado | Comprobación | Detalle |", "|---|---|---|"]
        for c in self.checks:
            out.append(f"| {icon.get(c.status, c.status)} | {c.name} | {c.detail.replace('|', '/')} |")
        if self.contact_sheet:
            out += ["", f"Hoja de contactos: `{self.contact_sheet}`"]
        if self.limitations:
            out += ["", "## Limitaciones de esta revisión", *[f"- {l}" for l in self.limitations]]
        return "\n".join(out) + "\n"

    def save(self, reports_dir: Path, stem: str = "qc_report") -> tuple[Path, Path]:
        reports_dir.mkdir(parents=True, exist_ok=True)
        j = reports_dir / f"{stem}.json"
        m = reports_dir / f"{stem}.md"
        j.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        m.write_text(self.to_markdown(), encoding="utf-8")
        return j, m


def _overlaps(a: tuple[float, float], allowed: list[tuple[float, float]], margin: float = 0.15) -> bool:
    return any(a[0] >= s - margin and a[1] <= e + margin for s, e in allowed)


def inspect(path: str | Path, exp: Expectations | None = None, settings: dict | None = None,
            frames_dir: Path | None = None, sample_count: int | None = None) -> QCReport:
    path = Path(path)
    exp = exp or Expectations(audio=False)
    qs = (settings or {}).get("qc", {})
    rep = QCReport(file=str(path))
    rep.limitations.append("La revisión visual es por muestras de fotogramas (hoja de contactos), no fotograma a fotograma; "
                           "el análisis de contenido lo realiza el agente al mirar las imágenes.")
    rep.limitations.append("La sincronía audio/vídeo se comprueba por duración y arranque de las pistas; no se mide la sincronía labial.")

    # 1. existencia
    if not path.exists() or path.stat().st_size == 0:
        rep.add("Archivo exportado", FAIL, "No existe o está vacío", fix="rerender")
        return rep
    rep.add("Archivo exportado", PASS, f"{path.stat().st_size / 1e6:.2f} MB")
    if path.with_name(path.stem + ".partial" + path.suffix).exists():
        rep.add("Exportación finalizada", FAIL, "Existe un archivo .partial: la exportación se interrumpió", fix="rerender")

    # 2. contenedor
    try:
        info = ff.probe(path)
    except Exception as e:
        rep.add("Contenedor legible (ffprobe)", FAIL, str(e).splitlines()[-1][:300], fix="rerender")
        return rep
    rep.info = info.summary()
    if not info.has_video:
        rep.add("Pista de vídeo", FAIL, "El archivo no contiene vídeo", fix="rerender")
        return rep
    rep.add("Contenedor legible (ffprobe)", PASS, info.format_name)

    # 3. decodificación completa
    proc = ff.ffmpeg("-v", "error", "-xerror", "-i", path, "-f", "null", "-", check=False)
    errs = [l for l in proc.stderr.splitlines() if l.strip()]
    if proc.returncode != 0 or errs:
        rep.add("Decodificación completa", FAIL, f"{len(errs)} errores: {errs[-1][:200] if errs else proc.returncode}", fix="rerender")
    else:
        rep.add("Decodificación completa", PASS, "Todo el archivo se decodifica sin errores")

    # 4. duración
    if exp.duration:
        tol = qs.get("duration_tolerance_s", 0.5)
        diff = info.duration - exp.duration
        rep.add("Duración", PASS if abs(diff) <= tol else FAIL,
                f"{info.duration:.2f}s (esperado {exp.duration:.2f}s, tolerancia ±{tol}s)", fix=None if abs(diff) <= tol else "retime")
    # 5. resolución / aspecto
    if exp.width and exp.height:
        ok = (info.width, info.height) == (exp.width, exp.height)
        rep.add("Resolución", PASS if ok else FAIL, f"{info.width}×{info.height} (esperado {exp.width}×{exp.height})",
                fix=None if ok else "rerender")
    sar_ok = info.sar in (None, "1:1", "0:1", "N/A")
    rep.add("Relación de aspecto / píxel cuadrado", PASS if sar_ok else FAIL,
            f"DAR {info.width}:{info.height} ({info.aspect:.4f}), SAR {info.sar}", fix=None if sar_ok else "rerender")
    if exp.fps:
        ok = abs(info.fps - exp.fps) < 0.05
        rep.add("Fotogramas por segundo", PASS if ok else WARN, f"{info.fps:.3f} (esperado {exp.fps})")
    # 6. compatibilidad
    if path.suffix.lower() in (".mp4", ".mov"):
        ok = info.video_codec == "h264" and info.pix_fmt == "yuv420p" and info.audio_codec in (None, "aac")
        rep.add("Compatibilidad (H.264 yuv420p + AAC)", PASS if ok else WARN, f"{info.video_codec} {info.pix_fmt} / {info.audio_codec}")

    # 7. audio
    if exp.audio:
        rep.add("Pista de audio", PASS if info.has_audio else FAIL,
                f"{info.audio_codec} {info.sample_rate} Hz {info.audio_channels} canales" if info.has_audio else "Falta la pista de audio",
                fix=None if info.has_audio else "audio")
    # 8. A/V
    if info.has_audio and info.video_duration and info.audio_duration:
        tol = qs.get("av_sync_tolerance_s", 0.15)
        dd = abs(info.video_duration - info.audio_duration)
        ds = abs(info.video_start - info.audio_start)
        ok = dd <= max(tol, 0.1) and ds <= tol
        rep.add("Sincronía A/V (duración y arranque de pistas)", PASS if ok else WARN,
                f"vídeo {info.video_duration:.3f}s / audio {info.audio_duration:.3f}s, desfase de inicio {ds * 1000:.0f} ms",
                fix=None if ok else "rerender")

    # 9. fotogramas negros
    blacks = []
    out = ff.ffmpeg("-i", path, "-an", "-vf", f"blackdetect=d={qs.get('black_min_duration_s', 0.4)}:pix_th={qs.get('black_pixel_threshold', 0.1)}",
                    "-f", "null", "-", check=False).stderr
    for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", out):
        blacks.append((float(a), float(b)))
    unexpected = [b for b in blacks if not _overlaps(b, exp.allowed_black)]
    if unexpected:
        total = sum(e - s for s, e in unexpected)
        rep.add("Fotogramas negros inesperados", FAIL if total > 1.0 else WARN,
                ", ".join(f"{fmt_ts(s)}–{fmt_ts(e)}" for s, e in unexpected), fix="black", data={"ranges": unexpected})
    else:
        rep.add("Fotogramas negros inesperados", PASS, f"Ninguno ({len(blacks)} tramos negros previstos por transiciones)" if blacks else "Ninguno")

    # 10. silencios
    if info.has_audio and exp.audio:
        out = ff.ffmpeg("-i", path, "-vn", "-af", f"silencedetect=n={qs.get('silence_noise_db', -50)}dB:d={qs.get('silence_min_duration_s', 1.5)}",
                        "-f", "null", "-", check=False).stderr
        starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", out)]
        ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", out)]
        sil = list(zip(starts, ends + [info.duration] * (len(starts) - len(ends))))
        bad = [s for s in sil if not _overlaps(s, exp.allowed_silence, 0.3)]
        if bad:
            rep.add("Silencios inesperados", WARN if sum(e - s for s, e in bad) < 3 else FAIL,
                    ", ".join(f"{fmt_ts(s)}–{fmt_ts(e)}" for s, e in bad), fix="audio", data={"ranges": bad})
        else:
            rep.add("Silencios inesperados", PASS, "Ninguno")
        # 11. sonoridad
        loud = audio_mod.measure_loudness(path)
        if loud and exp.loudness_lufs is not None:
            tol = qs.get("loudness_tolerance_lu", 2.5)
            i, tp = loud["integrated_lufs"], loud["true_peak_db"]
            ok = abs(i - exp.loudness_lufs) <= tol and (tp is None or tp <= -0.5)
            rep.add("Sonoridad y picos", PASS if ok else WARN,
                    f"{i:.1f} LUFS (objetivo {exp.loudness_lufs}), pico verdadero {tp} dBTP", fix=None if ok else "loudness", data=loud)

    # 12. congelados
    out = ff.ffmpeg("-i", path, "-an", "-vf", f"freezedetect=n=0.001:d={qs.get('freeze_min_duration_s', 2.5)}", "-f", "null", "-",
                    check=False).stderr
    fr = re.findall(r"freeze_start: ([\d.]+)", out)
    rep.add("Imagen congelada", WARN if fr else PASS, f"Congelado desde {', '.join(fmt_ts(float(x)) for x in fr)}" if fr else "No detectada")

    # 13. textos y subtítulos
    if exp.text_layout:
        over = [v["text"] for v in exp.text_layout.values() if v.get("overflow")]
        rep.add("Textos dentro de la zona segura", FAIL if over else PASS,
                ("Desbordan: " + "; ".join(over)) if over else f"{len(exp.text_layout)} rótulos dentro de los márgenes de la plataforma",
                fix="text_overflow" if over else None)
    if exp.subtitle_problems:
        rep.add("Subtítulos sin cortes", FAIL, "; ".join(exp.subtitle_problems[:5]), fix="subtitle_size")

    # 14. revisión visual por muestras
    if frames_dir is not None:
        n = sample_count or qs.get("preview_frames", 9)
        times = exp.sample_times or list(np.linspace(0.3, max(0.31, info.duration - 0.3), n))
        labels = exp.sample_labels or [fmt_ts(t) for t in times]
        frames, stats = [], []
        for k, t in enumerate(times):
            fp = extract_frame(path, float(t), frames_dir / f"qc_{k:02d}.jpg", 360)
            frames.append(fp)
            with Image.open(fp) as im:
                g = np.asarray(im.convert("L"), dtype=np.float32)
                stats.append({"t": round(float(t), 2), "luma": round(float(g.mean()), 1), "std": round(float(g.std()), 1), "hash": ahash(im)})
        rep.frames = [str(f) for f in frames]
        rep.contact_sheet = str(contact_sheet(frames, frames_dir / "contact_sheet.jpg", cols=min(5, len(frames)), thumb_w=240, labels=labels))
        flat = [s for s in stats if s["std"] < 4]
        rep.add("Muestras sin contenido (planos uniformes)", WARN if flat else PASS,
                ", ".join(fmt_ts(s["t"]) for s in flat) if flat else f"{len(stats)} muestras con contenido",
                data={"stats": stats})
        rep_pairs = [(a["t"], b["t"]) for a, b in zip(stats, stats[1:]) if hamming(a["hash"], b["hash"]) <= 2 and exp.sample_labels]
        rep.add("Escenas repetidas (muestras consecutivas casi idénticas)", WARN if rep_pairs else PASS,
                ", ".join(f"{fmt_ts(a)}≈{fmt_ts(b)}" for a, b in rep_pairs) if rep_pairs else "No detectadas")
    return rep
