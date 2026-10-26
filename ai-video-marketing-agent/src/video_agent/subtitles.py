"""Subtítulos: transcripción real (faster-whisper), SRT y ASS con estilos animados."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .motion_graphics import FontRef, Palette, load_font, luminance


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Cue:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


# --------------------------------------------------------------- transcripción

class TranscriptionUnavailable(RuntimeError):
    pass


def _decode_16k(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0


_MODEL_CACHE: dict = {}


def transcribe(path: Path, settings: dict, language: str | None = None) -> tuple[list[Word], str]:
    """Transcribe la voz de un archivo con faster-whisper (local). Devuelve palabras con tiempos e idioma."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover - depende del entorno
        raise TranscriptionUnavailable("faster-whisper no está instalado: pip install 'ai-video-marketing-agent[transcribe]'") from e
    cfg = settings["transcription"]
    key = (cfg["model"], cfg.get("device", "cpu"), cfg.get("compute_type", "int8"))
    if key not in _MODEL_CACHE:
        try:
            _MODEL_CACHE[key] = WhisperModel(cfg["model"], device=key[1], compute_type=key[2])
        except Exception as e:  # descarga bloqueada, modelo inexistente...
            raise TranscriptionUnavailable(
                f"No se pudo cargar el modelo Whisper '{cfg['model']}': {e}. Si no hay acceso a huggingface.co, "
                "descarga un modelo CTranslate2 y define VIDEO_AGENT_WHISPER_MODEL=/ruta/al/modelo") from e
    model = _MODEL_CACHE[key]
    audio = _decode_16k(path)
    if audio.size == 0:
        return [], language or ""
    segments, info = model.transcribe(audio, language=language, word_timestamps=True, vad_filter=False)
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if t:
                words.append(Word(t, float(w.start), float(w.end)))
    return words, info.language


# ------------------------------------------------------------ construcción

def words_from_lines(lines: list[tuple[str, float, float]]) -> list[Word]:
    """Tiempos por palabra estimados (proporcionales a la longitud) para textos con tiempo conocido."""
    out: list[Word] = []
    for text, start, end in lines:
        toks = text.split()
        if not toks:
            continue
        weights = np.array([len(t) + 2 for t in toks], dtype=float)
        bounds = start + np.concatenate([[0], np.cumsum(weights)]) / weights.sum() * (end - start)
        out += [Word(t, float(bounds[i]), float(bounds[i + 1])) for i, t in enumerate(toks)]
    return out


def group_words(words: list[Word], max_words: int = 4, max_chars: int = 28, max_gap: float = 0.6) -> list[Cue]:
    cues: list[Cue] = []
    cur: list[Word] = []

    def flush():
        if cur:
            cues.append(Cue(cur[0].start, cur[-1].end, " ".join(w.text for w in cur), list(cur)))
            cur.clear()

    for w in words:
        if cur and (len(cur) >= max_words or len(" ".join(x.text for x in cur + [w])) > max_chars
                    or w.start - cur[-1].end > max_gap or re.search(r"[.!?…]$", cur[-1].text)):
            flush()
        cur.append(w)
    flush()
    for a, b in zip(cues, cues[1:]):  # sin solapes y con un mínimo de lectura
        a.end = min(max(a.end, a.start + 0.5), b.start)
    return cues


def _srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues: list[Cue], out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(f"{i}\n{_srt_ts(c.start)} --> {_srt_ts(c.end)}\n{c.text}\n" for i, c in enumerate(cues, 1)), encoding="utf-8")
    return out


def parse_srt(path: Path) -> list[Cue]:
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*\n(.+)", block, re.S)
        if m:
            g = list(map(int, m.groups()[:8]))
            st = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            en = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            text = " ".join(m.group(9).split())
            cues.append(Cue(st, en, text, words_from_lines([(text, st, en)])))
    return cues


# --------------------------------------------------------------------- ASS

def _ass_color(rgb: tuple[int, int, int], alpha: int = 0) -> str:
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def _ass_ts(t: float) -> str:
    cs = int(round(max(0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


SUB_STYLES = {
    #            size(frac short side), upper, outline, shadow, box, highlight mode
    "minimal":   dict(size=0.050, upper=False, outline=2, shadow=0, box=False, mode="static"),
    "corporate": dict(size=0.048, upper=False, outline=0, shadow=0, box=True, mode="static"),
    "cinematic": dict(size=0.046, upper=False, outline=1, shadow=2, box=False, mode="fade"),
    "gaming":    dict(size=0.066, upper=True, outline=5, shadow=3, box=False, mode="word"),
    "dynamic":   dict(size=0.064, upper=True, outline=5, shadow=2, box=False, mode="word"),
}


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def ass_layout(style: str, width: int, height: int, font_scale: float = 1.0) -> dict:
    st = SUB_STYLES.get(style, SUB_STYLES["dynamic"])
    return {**st, "font_size": int(min(width, height) * st["size"] * font_scale)}


def write_ass(cues: list[Cue], out: Path, width: int, height: int, palette: Palette, font: FontRef | None,
              style: str = "dynamic", safe: dict | None = None, highlight: list[str] | None = None,
              font_scale: float = 1.0) -> Path:
    """Genera subtítulos ASS. En los estilos dynamic/gaming la palabra activa se resalta y crece."""
    safe = safe or {"bottom": 0.12, "left": 0.06, "right": 0.06}
    lay = ass_layout(style, width, height, font_scale)
    size = lay["font_size"]
    margin_v = int(height * safe.get("bottom", 0.12) + size * 0.6)
    margin_l = int(width * safe.get("left", 0.06))
    margin_r = int(width * safe.get("right", 0.06))
    family = font.family if font else "Sans"
    primary = _ass_color(palette.text)
    accent = _ass_color(palette.accent)
    back = _ass_color((0, 0, 0), 0x60 if lay["box"] else 0x80)
    # contorno oscuro para texto claro y claro para texto oscuro (paletas claras)
    outline = _ass_color((0, 0, 0)) if luminance(palette.text) > 0.3 else _ass_color((255, 255, 255))
    border_style = 3 if lay["box"] else 1
    hl = {_norm(h) for h in (highlight or []) for h in h.split()}
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},{size},{primary},{accent},{outline},{back},0,0,0,0,100,100,0,0,{border_style},{lay['outline']},{lay['shadow']},2,{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for c in cues:
        words = c.words or [Word(t, c.start, c.end) for t in c.text.split()]
        disp = [(w.text.upper() if lay["upper"] else w.text) for w in words]
        if lay["mode"] == "word" and len(words) > 0:
            for i, w in enumerate(words):
                st = w.start if i else c.start
                en = words[i + 1].start if i + 1 < len(words) else c.end
                if en - st < 0.02:
                    continue
                parts = []
                for j, (ww, d) in enumerate(zip(words, disp)):
                    d = _escape_ass(d)
                    if j == i:
                        parts.append(f"{{\\c{accent}\\fscx112\\fscy112}}{d}{{\\c{primary}\\fscx100\\fscy100}}")
                    elif _norm(ww.text) in hl:
                        parts.append(f"{{\\c{accent}}}{d}{{\\c{primary}}}")
                    else:
                        parts.append(d)
                pop = "{\\fad(60,0)}" if i == 0 else ""
                events.append(f"Dialogue: 0,{_ass_ts(st)},{_ass_ts(en)},Default,,0,0,0,,{pop}{' '.join(parts)}")
        else:
            parts = [f"{{\\c{accent}}}{_escape_ass(d)}{{\\c{primary}}}" if _norm(w.text) in hl else _escape_ass(d)
                     for w, d in zip(words, disp)]
            fx = "{\\fad(150,150)}" if lay["mode"] == "fade" else ""
            events.append(f"Dialogue: 0,{_ass_ts(c.start)},{_ass_ts(c.end)},Default,,0,0,0,,{fx}{' '.join(parts)}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out


def check_fit(cues: list[Cue], width: int, height: int, font: FontRef | None, style: str, safe: dict,
              font_scale: float = 1.0) -> list[str]:
    """Comprueba que cada subtítulo cabe en la zona segura (como mucho 2 líneas con el ancho disponible)."""
    lay = ass_layout(style, width, height, font_scale)
    f = load_font(font, lay["font_size"])
    avail = width * (1 - safe.get("left", 0.06) - safe.get("right", 0.06))
    problems = []
    for c in cues:
        text = c.text.upper() if lay["upper"] else c.text
        w = f.getlength(text) * (1.12 if lay["mode"] == "word" else 1.0)
        if w > avail * 2:
            problems.append(f"{_ass_ts(c.start)} '{c.text}' ocupa {w:.0f}px (> 2 líneas de {avail:.0f}px)")
    return problems
