"""Gráficos generados localmente con Pillow: fondos, rótulos, logotipos.

Todo se genera en el equipo, sin servicios externos. Las animaciones (entrada
de textos, zooms, desplazamientos) las aplica FFmpeg en editor.py.
"""
from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ----------------------------------------------------------------- fuentes


@dataclass(frozen=True)
class FontRef:
    file: str
    family: str      # nombre completo para libass (p. ej. "Inter Black")
    pattern: str


@lru_cache(maxsize=None)
def _fc_match(pattern: str) -> tuple[str, str, str] | None:
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}|%{family[0]}|%{fullname[0]}", pattern],
                             capture_output=True, text=True, timeout=10).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    parts = out.split("|")
    if len(parts) < 3 or not Path(parts[0]).exists():
        return None
    return parts[0], parts[1], parts[2]


@lru_cache(maxsize=None)
def resolve_font(patterns: tuple[str, ...]) -> FontRef | None:
    """Primer patrón fontconfig cuya familia existe realmente en el sistema."""
    for pat in patterns:
        if Path(pat).is_file():
            return FontRef(pat, Path(pat).stem, pat)
        m = _fc_match(pat)
        if not m:
            continue
        wanted = pat.split(":")[0].strip().lower()
        if m[1].lower() == wanted or m[2].lower().startswith(wanted):
            return FontRef(m[0], m[2] or m[1], pat)
    return None


def font_for(role: str, settings: dict) -> FontRef | None:
    fonts = settings.get("fonts", {})
    key = {"hook": "title", "title": "title", "cta": "title", "subtitle": "subtitle"}.get(role, "body")
    return resolve_font(tuple(fonts.get(key, []))) or resolve_font(tuple(fonts.get("body", [])))


def load_font(ref: FontRef | None, size: int) -> ImageFont.FreeTypeFont:
    if ref:
        return ImageFont.truetype(ref.file, size)
    return ImageFont.load_default(size=size)


# ----------------------------------------------------------------- colores

def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(rgb: tuple[int, int, int]) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@dataclass
class Palette:
    bg: tuple[int, int, int]
    bg2: tuple[int, int, int]
    accent: tuple[int, int, int]
    accent2: tuple[int, int, int]
    text: tuple[int, int, int]

    @classmethod
    def from_list(cls, colors: list[str]) -> "Palette":
        c = [hex_rgb(x) for x in (colors or [])] + [hex_rgb(x) for x in ["#0A0E1A", "#12182B", "#00E5FF", "#7C4DFF", "#FFFFFF"]]
        return cls(c[0], c[1], c[2], c[3], c[4])

    @property
    def dark_bg(self) -> bool:
        return luminance(self.bg) < 0.25


# ------------------------------------------------------------------ fondos

def _vgradient(w, h, c1, c2):
    t = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(c1)[None, None, :] * (1 - t) + np.array(c2)[None, None, :] * t)
    return np.repeat(arr, w, axis=1)


def _radial(w, h, cx, cy, radius):
    y, x = np.ogrid[:h, :w]
    d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / radius
    return np.clip(1 - d, 0, 1) ** 2


BACKGROUNDS = ("tech_grid", "gradient", "spotlight", "speed_lines", "minimal", "bokeh")


def generate_particles(width: int, height: int, palette: Palette, out: Path, seed: int = 0, density: float = 1.0) -> Path:
    """Capa transparente (doble de alta) con partículas y destellos para animar en paralaje sobre el fondo."""
    rng = np.random.default_rng(seed + 101)
    w, h = width, height * 2
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(int(90 * density)):
        x, y = rng.random() * w, rng.random() * height
        r = max(1.2, rng.random() * w / 260)
        col = palette.accent if rng.random() > 0.3 else palette.text
        a = int(60 + 150 * rng.random())
        for yy in (y, y + height):  # mosaico vertical sin costuras
            d.ellipse([x - r, yy - r, x + r, yy + r], fill=(*col, a))
    glow = layer.filter(ImageFilter.GaussianBlur(w / 220))
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(glow, layer).save(out)
    return out


def generate_background(kind: str, width: int, height: int, palette: Palette, out: Path, seed: int = 0) -> Path:
    """Genera un fondo de alta calidad en PNG. Tipos: tech_grid, gradient, spotlight, speed_lines, minimal, bokeh."""
    rng = np.random.default_rng(seed + 7)
    w, h = width, height
    base = _vgradient(w, h, palette.bg2, palette.bg)

    if kind == "tech_grid":
        glow = _radial(w, h, w * (0.2 + 0.6 * rng.random()), h * (0.2 + 0.25 * rng.random()), max(w, h) * (0.45 + 0.3 * rng.random()))[..., None]
        base = base * (1 - glow * 0.5) + np.array(palette.accent2) * glow * 0.5
        img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        horizon = int(h * (0.5 + 0.15 * rng.random()))
        cx = w / 2
        lw = max(1, w // 540)
        for i in range(-14, 15):  # líneas de fuga
            d.line([(cx + i * w * 0.04, horizon), (cx + i * w * 0.32, h)], fill=(*palette.accent, 70), width=lw)
        for k in range(1, 14):  # horizontales en perspectiva
            y = horizon + (h - horizon) * (k / 13) ** 2.2
            d.line([(0, y), (w, y)], fill=(*palette.accent, int(30 + 50 * k / 13)), width=lw)
        for _ in range(60):  # nodos luminosos
            x, y = rng.random() * w, rng.random() * horizon
            r = max(1.5, rng.random() * w / 300)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(*palette.accent, int(80 + 120 * rng.random())))
        for _ in range(10):  # trazos de circuito
            x, y = rng.random() * w, rng.random() * horizon * 0.9
            pts = [(x, y)]
            for _ in range(4):
                if rng.random() > 0.5:
                    x += (rng.random() - 0.5) * w * 0.3
                else:
                    y += (rng.random() - 0.5) * h * 0.12
                pts.append((x, y))
            d.line(pts, fill=(*palette.accent, 55), width=lw)
        img = Image.alpha_composite(img.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(0.6)))
        bloom = layer.filter(ImageFilter.GaussianBlur(w / 120))
        img = Image.alpha_composite(img, bloom)
    elif kind == "gradient":
        t = (np.linspace(0, 1, w)[None, :] * 0.6 + np.linspace(0, 1, h)[:, None] * 0.4)[..., None]
        base = np.array(palette.bg)[None, None] * (1 - t) + np.array(palette.accent2)[None, None] * t * 0.55 + np.array(palette.bg2)[None, None] * t * 0.45
        for _ in range(3):
            g = _radial(w, h, rng.random() * w, rng.random() * h, max(w, h) * (0.35 + rng.random() * 0.3))[..., None]
            base = base * (1 - g * 0.35) + np.array(palette.accent) * g * 0.35
        base += rng.normal(0, 3, base.shape)
        img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    elif kind == "spotlight":
        g = _radial(w, h, w * 0.5, h * 0.3, max(w, h) * 0.75)[..., None]
        base = np.array(palette.bg)[None, None] * (1 - g) + np.array(palette.bg2)[None, None] * (1 - g) * 0.5 + np.array(palette.accent) * g * 0.28 + 30 * g
        base += rng.normal(0, 2.5, base.shape)
        img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    elif kind == "speed_lines":
        img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for _ in range(70):
            col = palette.accent if rng.random() > 0.5 else palette.accent2
            x, y = rng.random() * w * 1.4 - w * 0.2, rng.random() * h
            L = w * (0.2 + rng.random() * 0.6)
            d.line([(x, y), (x + L, y - L * 0.35)], fill=(*col, int(40 + 120 * rng.random())), width=max(1, int(rng.random() * w / 180)))
        img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(1.2)))
    elif kind == "bokeh":
        img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for _ in range(26):
            col = palette.accent if rng.random() > 0.45 else palette.accent2
            x, y, r = rng.random() * w, rng.random() * h, w * (0.015 + rng.random() * 0.06)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(*col, int(18 + 40 * rng.random())))
        img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(w / 60)))
    else:  # minimal
        g = _radial(w, h, w * 0.5, h * 0.45, max(w, h) * 0.9)[..., None]
        base = np.array(palette.bg)[None, None] * (0.94 + 0.06 * g) + np.array(palette.bg2)[None, None] * 0
        img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out)
    return out


# ------------------------------------------------------------------ textos

ROLE_SIZE = {"hook": 0.112, "title": 0.096, "body": 0.074, "cta": 0.07, "label": 0.046}


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def wrap_words(words: list[str], font, max_width: float) -> list[list[str]]:
    lines, cur = [], []
    for w in words:
        trial = " ".join(cur + [w])
        if cur and font.getlength(trial) > max_width:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


@dataclass
class TextLayout:
    path: Path
    width: int
    height: int
    font_size: int
    lines: int
    overflow: bool


def render_text(text: str, role: str, frame_w: int, frame_h: int, max_width: int, palette: Palette,
                font: FontRef | None, out: Path, highlight: list[str] | None = None, scale: float = 1.0,
                max_lines: int = 4) -> TextLayout:
    """Renderiza un rótulo a PNG con transparencia, ajustando tamaño y saltos de línea."""
    short = min(frame_w, frame_h)
    size = max(18, int(short * ROLE_SIZE.get(role, 0.06) * scale))
    hl = {_norm(x) for x in (highlight or []) for x in x.split()}
    words = text.split()
    overflow = False
    while True:
        f = load_font(font, size)
        lines = wrap_words(words, f, max_width)
        widest = max((f.getlength(" ".join(l)) for l in lines), default=0)
        if (len(lines) <= max_lines and widest <= max_width) or size <= 18:
            overflow = widest > max_width or len(lines) > max_lines
            break
        size = int(size * 0.92)

    asc, desc = f.getmetrics()
    line_h = int((asc + desc) * 1.08)
    pad = int(size * 0.45)
    is_cta = role == "cta"
    text_w = int(max((f.getlength(" ".join(l)) for l in lines), default=0))
    W = text_w + pad * 2 + (int(size * 1.2) if is_cta else 0)
    H = line_h * len(lines) + pad * 2 + (int(size * 0.5) if is_cta else 0)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    text_col = palette.text
    accent = palette.accent
    if is_cta:  # botón tipo píldora con el color de acento
        r = (H - pad) // 2
        d.rounded_rectangle([pad // 2, pad // 2, W - pad // 2, H - pad // 2], radius=r, fill=(*accent, 255))
        text_col = (10, 10, 14) if luminance(accent) > 0.35 else (255, 255, 255)
    elif role == "label":
        d.rectangle([pad // 2, pad, pad // 2 + max(4, size // 6), H - pad], fill=(*accent, 255))

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    y = pad + (int(size * 0.25) if is_cta else 0)
    # contorno y sombra oscuros solo para texto claro (fondos oscuros o vídeo);
    # el texto oscuro sobre fondo claro queda limpio, con una sombra muy suave
    light_text = luminance(text_col) > 0.3
    stroke = 0 if (is_cta or not light_text) else max(2, size // 22)
    shadow_alpha = 170 if light_text else 45
    for line in lines:
        lw = f.getlength(" ".join(line))
        x = (W - lw) / 2
        for word in line:
            col = accent if (_norm(word) in hl and not is_cta) else text_col
            if not is_cta:
                sd.text((x + size * 0.04, y + size * 0.06), word, font=f, fill=(0, 0, 0, shadow_alpha))
            d.text((x, y), word, font=f, fill=(*col, 255), stroke_width=stroke, stroke_fill=(0, 0, 0, 200) if stroke else None)
            x += f.getlength(word + " ")
        y += line_h
    if not is_cta:
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(1, size // 16)))
        img = Image.alpha_composite(shadow, img)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return TextLayout(out, W, H, size, len(lines), overflow)


def render_wordmark(name: str, palette: Palette, font: FontRef | None, out: Path, width: int = 1200) -> Path:
    """Logotipo tipográfico provisional a partir del nombre de la marca (cuando no se aporta logo)."""
    words = name.upper().split() or ["LOGO"]
    size = 160
    f = load_font(font, size)
    while max(f.getlength(w) for w in words) > width * 0.9 and size > 30:
        size -= 8
        f = load_font(font, size)
    asc, desc = f.getmetrics()
    lh = int((asc + desc) * 1.05)
    H = lh * len(words) + size
    img = Image.new("RGBA", (width, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = size // 2
    for i, w in enumerate(words):
        col = palette.accent if i == 0 and len(words) > 1 else palette.text
        d.text(((width - f.getlength(w)) / 2, y), w, font=f, fill=(*col, 255))
        y += lh
    bar_w = int(width * 0.18)
    d.rectangle([(width - bar_w) // 2, H - size // 3, (width + bar_w) // 2, H - size // 3 + max(4, size // 14)], fill=(*palette.accent, 255))
    glow = img.filter(ImageFilter.GaussianBlur(size / 10))
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(glow, img).save(out)
    return out


def text_position(position: str, frame_w: int, frame_h: int, box_w: int, box_h: int, safe: dict) -> tuple[int, int]:
    """Coordenadas (x, y) de un rótulo respetando las zonas seguras de la plataforma."""
    left, right = safe.get("left", 0.05) * frame_w, safe.get("right", 0.05) * frame_w
    top, bottom = safe.get("top", 0.05) * frame_h, safe.get("bottom", 0.1) * frame_h
    x = int(left + (frame_w - left - right - box_w) / 2)
    if position == "top":
        y = top
    elif position == "lower_third":
        y = frame_h * (0.66 if frame_h > frame_w else 0.72) - box_h / 2
    elif position == "bottom":
        y = frame_h - bottom - box_h
    else:
        y = (frame_h - box_h) / 2
    y = min(max(y, top), frame_h - bottom - box_h)
    return max(0, x), int(max(0, y))


def ease_out_expr(t0: float, dur: float) -> str:
    """Expresión FFmpeg 0→1 con easing (cúbica) entre t0 y t0+dur."""
    p = f"min(1,max(0,(t-{t0:.3f})/{dur:.3f}))"
    return f"(1-pow(1-{p},3))"


def contact_sheet(frames: list[Path], out: Path, cols: int = 3, thumb_w: int = 360, labels: list[str] | None = None) -> Path:
    imgs = [Image.open(p).convert("RGB") for p in frames]
    if not imgs:
        raise ValueError("No hay fotogramas para la hoja de contactos")
    th = int(thumb_w * imgs[0].height / imgs[0].width)
    rows = math.ceil(len(imgs) / cols)
    sheet = Image.new("RGB", (cols * thumb_w + (cols + 1) * 8, rows * (th + 30) + 8), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        x, y = 8 + c * (thumb_w + 8), 8 + r * (th + 30)
        sheet.paste(im.resize((thumb_w, th)), (x, y))
        if labels:
            d.text((x + 4, y + th + 6), labels[i], fill=(230, 230, 230))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
