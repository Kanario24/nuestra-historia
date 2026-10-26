"""Director creativo automático: convierte una petición en un plan de edición ejecutable."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from . import config, marketing
from .media_manager import ClipAnalysis, choose_segments
from .models import (Brand, EditPlan, ExportSpec, MusicSpec, Scene, Source, SubtitleSpec, TextOverlay,
                     VoiceSpec, fmt_ts)


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


@dataclass
class BriefInfo:
    duration: float | None = None
    platform: str | None = None
    style: str | None = None
    goal: str | None = None
    brand: str = ""
    language: str = "es"
    voiceover: bool | None = None
    music: bool | None = None
    music_mood: str | None = None
    subtitles: bool | None = None
    audience: str = ""
    cta: str = ""
    website: str = ""
    notes: list[str] = field(default_factory=list)


PLATFORM_WORDS = {"tiktok", "youtube", "instagram", "reels", "shorts", "reel", "short", "facebook", "linkedin"}


def parse_brief(brief: str) -> BriefInfo:
    """Extrae los parámetros explícitos de una petición en lenguaje natural (es/en)."""
    info = BriefInfo()
    t = _fold(brief)
    info.language = marketing.detect_language(brief)

    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:s|seg|segs|segundos?|secs?|seconds?)\b", t)
    if m:
        info.duration = float(m.group(1).replace(",", "."))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:min|minutos?|minutes?)\b", t)
    if m:
        info.duration = (info.duration or 0) + float(m.group(1).replace(",", ".")) * 60

    if "tiktok" in t:
        info.platform = "tiktok"
    elif "reel" in t or "instagram" in t:
        info.platform = "instagram_reels"
    elif "short" in t:
        info.platform = "youtube_shorts"
    elif re.search(r"anuncio|\bads?\b|publicidad", t) and not re.search(r"horizontal|16:9", t):
        info.platform = "ad_vertical"
    elif "youtube" in t:
        info.platform = "youtube"
    elif re.search(r"cuadrad|square|1:1", t):
        info.platform = "square"
    elif re.search(r"horizontal|16:9|landscape", t):
        info.platform = "landscape"
    elif re.search(r"vertical|9:16", t):
        info.platform = "tiktok"

    scores = {k: marketing.keyword_hits(brief, kws) for k, kws in config.style_keywords().items()}
    if scores and max(scores.values()) > 0:
        info.style = max(scores, key=scores.get)

    info.goal = marketing.detect_goal(brief, default="brand")

    if re.search(r"sin voz|no voice|without voice", t):
        info.voiceover = False
    elif re.search(r"voz en off|locuci|narraci|narrad|voice ?over|narrat", t):
        info.voiceover = True
    if re.search(r"sin musica|no music|without music", t):
        info.music = False
    elif re.search(r"musica|music", t):
        info.music = True
        for mood, kws in {"electronic": ["electronic", "techno", "synth"], "cinematic": ["epic", "cinemat", "orquest"],
                          "corporate": ["corporat", "inspirad"], "chill": ["chill", "relaj", "lofi", "tranquil"],
                          "gaming": ["gaming", "8 bit", "8-bit", "arcade"]}.items():
            if any(k in t for k in kws):
                info.music_mood = mood
                break
    if re.search(r"sin subtitul|no subtitles|no captions", t):
        info.subtitles = False
    elif re.search(r"subtitul|captions|subtitles|rotulad", t):
        info.subtitles = True

    m = re.search(r"(https?://\S+|www\.\S+|\b[\w-]+\.(?:com|es|io|dev|net|org|app|ai)\b)", brief)
    if m:
        info.website = m.group(1).rstrip(".,)")
    m = re.search(r"[\"“«]([^\"”»]{2,40})[\"”»]", brief)
    if m:
        info.brand = m.group(1).strip()
    if not info.brand:
        pat = r"(?:promocionar|promociona|presentar|presenta|anunciar|lanzar|para|de|sobre|promote|for|about|launch)\s+" \
              r"(?:a |la marca |la empresa |mi empresa |el producto |la app |the brand |our |my )?" \
              r"((?:[A-Z0-9][\w&'.+-]*)(?:\s+(?:[A-Z0-9][\w&'.+-]*))*)"
        for m in re.finditer(pat, brief):
            words = []
            for w in m.group(1).split():  # la marca termina en el primer signo de puntuación
                end = bool(re.search(r"[.,;:!?]$", w)) and not re.fullmatch(r"(?:[A-Z]\.)+", w)
                w = w.rstrip(".,;:!?")
                if _fold(w) not in PLATFORM_WORDS:
                    words.append(w)
                if end:
                    break
            cand = " ".join(words).strip()
            if cand and not re.fullmatch(r"[\d.,]+", cand):
                info.brand = cand
                break
    m = re.search(r"(?:dirigido a|para un publico de|publico objetivo:?|publico:?|audience:?|target:?)\s+([^.;\n]+)", t)
    if m:
        info.audience = m.group(1).strip()[:120]
    return info


# ------------------------------------------------------------------ timing

def allocate(beats: list[dict], total: float) -> list[float]:
    raw = [b["weight"] * total for b in beats]
    for _ in range(4):
        clamped = [min(max(r, b.get("min", 0.5)), b.get("max", 999)) for r, b in zip(raw, beats)]
        scale = total / sum(clamped)
        raw = [c * scale for c in clamped]
    return raw


def snap_to_beats(durations: list[float], bpm: float | None, min_len: float = 0.8) -> list[float]:
    """Ajusta los cortes al pulso de la música (cortes a ritmo)."""
    if not bpm or bpm <= 0:
        return durations
    beat = 60.0 / bpm
    total = sum(durations)
    bounds, acc = [], 0.0
    for d in durations[:-1]:
        acc += d
        snapped = round(acc / beat) * beat
        prev = bounds[-1] if bounds else 0.0
        if snapped - prev < min_len:
            snapped = prev + max(min_len, round(min_len / beat + 0.5) * beat)
        bounds.append(snapped)
    if bounds and total - bounds[-1] < min_len:
        return durations
    out, prev = [], 0.0
    for b in bounds + [total]:
        out.append(round(b - prev, 3))
        prev = b
    return out


# ------------------------------------------------------------------- plan

@dataclass
class AssetSet:
    clips: list[ClipAnalysis] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    logo: str | None = None
    music: str | None = None
    voice: str | None = None
    fonts: list[str] = field(default_factory=list)
    subtitles: str | None = None


def build_plan(brief: str, project_name: str, assets: AssetSet | None = None, *, platform: str | None = None,
               duration: float | None = None, style: str | None = None, goal: str | None = None,
               brand: str | None = None, language: str | None = None, voiceover: bool | None = None,
               subtitles: bool | None = None, subtitle_style: str | None = None, music_mood: str | None = None,
               keep_clip_audio: bool | None = None, fit: str | None = None, cta: str | None = None) -> EditPlan:
    assets = assets or AssetSet()
    info = parse_brief(brief)
    platform = platform or info.platform or "tiktok"
    plats = config.platforms()
    if platform not in plats:
        raise ValueError(f"Plataforma desconocida '{platform}'. Opciones: {', '.join(plats)}")
    pf = plats[platform]
    styles = config.styles()
    style = style or info.style or "tech_dark"
    if style not in styles:
        raise ValueError(f"Estilo desconocido '{style}'. Opciones: {', '.join(styles)}")
    st = styles[style]
    goal = goal or info.goal or "brand"
    lang = language or info.language
    brand_name = brand if brand is not None else info.brand
    notes = list(info.notes)

    clips = [c for c in assets.clips if c.ok and c.kind == "video" and c.duplicate_of is None]
    total_media = sum(c.duration for c in clips)
    # con voz original hay que respetar el orden y no trocear frases: montaje "de diálogo"
    dialogue = bool(keep_clip_audio) and any(c.speech_ratio > 0.5 for c in clips)
    if duration is None:
        duration = info.duration
    if duration is None and dialogue:
        duration = round(total_media, 2)
    if duration is None:
        duration = float(pf["default_duration"])
        if clips and total_media < duration and not assets.images:
            duration = max(6.0, round(total_media, 1))
        notes.append(f"Duración no indicada: se usa {duration:.0f}s (valor por defecto de {pf['label']}).")
    duration = float(min(duration, pf.get("max_duration", duration)))

    copy = marketing.copy_for(goal, brand_name, lang)
    cta_text = cta or info.cta or copy["cta"]
    music_spec = MusicSpec(mood=music_mood or info.music_mood or st["music"]["mood"], bpm=st["music"]["bpm"])
    if assets.music:
        music_spec.path = assets.music
        music_spec.generate = False
        music_spec.license_note = "Aportada por el usuario"
    if info.music is False:
        music_spec.generate = False
        music_spec.path = None

    bpm = music_spec.bpm if (music_spec.path is None and music_spec.generate) else None

    tmpl_path = "advertisements/ad.yaml" if goal == "ad" and pf["height"] > pf["width"] else pf["template"]
    beats = config.template(tmpl_path)["beats"]
    durs = allocate(beats, duration)

    # división en planos según el ritmo del estilo
    shots: list[tuple[dict, float, str | None]] = []
    for b, d in ([] if dialogue else zip(beats, durs)):
        if b.get("split") and b["copy"] == "benefits":
            items = copy["benefits"]
            n = max(1, min(len(items), int(d / max(1.0, st["shot_length"] * 0.6))))
            for k in range(n):
                shots.append((b, d / n, items[k]))
        else:
            n = 1
            if b["copy"] in ("problem", "solution") and (assets.clips or assets.images):  # más planos solo si hay material
                n = max(1, int(round(d / (st["shot_length"] * 1.6))))
            n = min(n, 2)
            for k in range(n):
                shots.append((b, d / n, None if k else "__main__"))
    shot_durs = snap_to_beats([s[1] for s in shots], bpm)

    # recursos de imagen para cada plano "media"
    media_idx = [i for i, (b, _, _) in enumerate(shots) if b["source"] == "media"]
    segs = choose_segments(clips, [shot_durs[i] for i in media_idx]) if clips else [None] * len(media_idx)
    has_speech = any(c.speech_ratio > 0.5 for c in clips)
    keep_audio = keep_clip_audio if keep_clip_audio is not None else False
    images = list(assets.images)

    scenes: list[Scene] = []
    motions, transitions = st["motion"], st["transitions"]
    img_i = 0
    vo_lines: list[str] = []
    for i, ((beat, _, item), d) in enumerate(zip(shots, shot_durs)):
        purpose = beat["purpose"]
        motion = motions[i % len(motions)]
        if beat["source"] == "logo":
            src = Source(type="logo", path=assets.logo, seed=i)
            motion = "zoom_in"
        else:
            seg = segs[media_idx.index(i)] if i in media_idx else None
            if seg is not None:
                src = Source(type="clip", path=seg.path, start=seg.start, keep_audio=keep_audio, fit=fit or "cover")
            elif images:
                src = Source(type="image", path=images[img_i % len(images)], fit=fit or "cover")
                img_i += 1
            else:
                src = Source(type="generated", seed=i)
        texts: list[TextOverlay] = []
        anim = st["text_animation"]
        pos = beat.get("text_position", "center")
        line = None
        if beat["copy"] == "hook":
            line = copy["hooks"][0]
            texts.append(TextOverlay(text=line, role="hook", position=pos, start=0.1, animation=anim))
        elif beat["copy"] == "problem" and item == "__main__":
            line = copy["problem"]
            texts.append(TextOverlay(text=line, role="body", position=pos, start=0.2, animation=anim))
        elif beat["copy"] == "solution" and item == "__main__":
            line = copy["solution"]
            texts.append(TextOverlay(text=line, role="title", position=pos, start=0.2, animation=anim,
                                     highlight=brand_name.split() if brand_name else []))
        elif beat["copy"] == "benefits" and item:
            line = item
            texts.append(TextOverlay(text=item, role="title", position=pos, start=0.15, animation=anim))
        elif beat["copy"] == "cta":
            line = cta_text
            texts.append(TextOverlay(text=cta_text, role="cta", position="bottom", start=0.5, animation="pop"))
            if info.website:
                texts.append(TextOverlay(text=info.website, role="label", position="top", start=0.8, animation="fade"))
        if line:
            vo_lines.append(line)
        scenes.append(Scene(
            id=f"s{i + 1:02d}", purpose=purpose, duration=d, source=src, texts=texts, motion=motion,
            motion_strength=0.06 if src.type == "clip" else 0.1,
            transition=transitions[i % len(transitions)], transition_duration=st["transition_duration"],
            voiceover=line if line else None,
            sfx="whoosh" if (i > 0 and purpose in ("solution", "cta") and scenes and scenes[-1].purpose != purpose) else None,
        ))
    if dialogue:
        scenes = dialogue_scenes(clips, duration, copy["hooks"][0], cta_text, st, fit)
        music_spec.volume_db = -14
        notes.append("Material con voz: se conserva el orden original y se corta solo en cambios de plano.")
    elif scenes:
        scenes[0].sfx = "hit" if style in ("gaming", "energetic", "tech_dark", "automotive") else None

    use_vo = voiceover if voiceover is not None else (info.voiceover or False)
    if assets.voice:
        use_vo = True
    if not use_vo:
        for sc in scenes:
            sc.voiceover = None
    sub_enabled = subtitles if subtitles is not None else (info.subtitles if info.subtitles is not None else bool(use_vo))
    sub_source = "voiceover"
    if assets.subtitles:
        sub_source = "file"
    elif assets.voice or (keep_audio and has_speech) or (sub_enabled and not use_vo):
        sub_source = "transcribe"
    if sub_enabled and sub_source == "transcribe" and not (assets.voice or (keep_audio and has_speech)):
        notes.append("Se pidieron subtítulos pero no hay voz: se desactivan (los textos en pantalla ya transmiten el mensaje).")
        sub_enabled = False

    palette = st["palette"]
    letterbox = bool(st.get("letterbox")) and pf["width"] > pf["height"]
    plan = EditPlan(
        project=project_name, brief=brief, objective=copy["label"], goal=goal, platform=platform,
        audience=info.audience or ("Clientes potenciales de la marca" if lang == "es" else "Brand prospects"),
        language=lang, duration=duration, aspect=pf["aspect"], style=style,
        pacing="rápido" if st["shot_length"] < 1.8 else ("pausado" if st["shot_length"] > 3 else "medio"),
        palette=palette, brand=Brand(name=brand_name, logo=assets.logo, palette=palette, website=info.website),
        script=vo_lines, hook_variants=marketing.hook_variants(copy["hooks"], brand_name, lang, 5), cta=cta_text,
        scenes=scenes, music=music_spec,
        voiceover=VoiceSpec(enabled=bool(use_vo), language=lang, path=assets.voice),
        subtitles=SubtitleSpec(enabled=bool(sub_enabled), source=sub_source, file=assets.subtitles,
                               style=subtitle_style or st["subtitle_style"], language=lang,
                               highlight_words=marketing.extract_keywords(vo_lines, brand_name)),
        export=ExportSpec(width=pf["width"], height=pf["height"], fps=pf["fps"], letterbox=letterbox),
        notes=notes,
    )
    if not brand_name:
        plan.notes.append("No se detectó el nombre de la marca: el cierre usa textos genéricos.")
    if not assets.logo:
        plan.notes.append("No se aportó logotipo: el cierre usa un logotipo tipográfico provisional con el nombre de la marca.")
    return plan


def dialogue_scenes(clips: list[ClipAnalysis], duration: float, hook: str, cta: str, st: dict,
                    fit: str | None = None) -> list[Scene]:
    """Escenas para material hablado: ventanas continuas en orden cronológico, cortes solo en cambios de plano."""
    from .media_manager import _window_score
    total = sum(c.duration for c in clips)
    take = min(duration, total)
    scenes: list[Scene] = []
    remaining = take
    for c in clips:
        share = min(take * c.duration / total if total > take else c.duration, remaining, c.duration)
        if share < 0.5:
            continue
        best = 0.0
        if c.duration > share + 0.5:
            cands = [k * 0.5 for k in range(int((c.duration - share) / 0.5) + 1)]
            best = max(cands, key=lambda s: _window_score(c, s, share))
        cuts = [x - best for x in c.scene_cuts if best + 1.0 < x < best + share - 1.0]
        bounds = [0.0] + cuts + [share]
        for a, b in zip(bounds, bounds[1:]):
            n = len(scenes)
            scenes.append(Scene(id=f"s{n + 1:02d}", purpose="body", duration=round(b - a, 3),
                                source=Source(type="clip", path=c.path, start=round(best + a, 3), keep_audio=True, fit=fit or "cover"),
                                motion="zoom_in" if n % 2 == 0 else "zoom_out", motion_strength=0.03, transition="cut",
                                transition_duration=0))
        remaining -= share
    if not scenes:
        raise ValueError("El material con voz es demasiado corto")
    first, last = scenes[0], scenes[-1]
    first.purpose = "hook"
    first.texts.append(TextOverlay(text=hook, role="hook", position="top", start=0.1, end=min(3.0, first.duration),
                                   animation=st["text_animation"]))
    last.purpose = "cta" if len(scenes) > 1 else last.purpose
    last.texts.append(TextOverlay(text=cta, role="cta", position="top", start=max(0.0, last.duration - 3.0), animation="pop"))
    return scenes


def storyboard_markdown(plan: EditPlan) -> str:
    lines = [f"# Storyboard — {plan.project}", "",
             f"- **Objetivo:** {plan.objective} · **Plataforma:** {plan.platform} ({plan.export.width}×{plan.export.height}, {plan.aspect})",
             f"- **Duración:** {plan.duration:.2f}s · **Estilo:** {plan.style} · **Ritmo:** {plan.pacing}",
             f"- **Público:** {plan.audience}", f"- **Paleta:** {', '.join(plan.palette)}",
             f"- **Música:** {plan.music.path or ('sintética local ' + plan.music.mood + f' {plan.music.bpm:.0f} BPM' if plan.music.generate else 'sin música')}",
             f"- **Voz en off:** {'sí' if plan.voiceover.enabled else 'no'} · **Subtítulos:** {plan.subtitles.style if plan.subtitles.enabled else 'no'}",
             f"- **CTA:** {plan.cta}", "", "| Tiempo | Escena | Propósito | Imagen | Texto en pantalla | Voz | Movimiento | Transición |",
             "|---|---|---|---|---|---|---|---|"]
    for r in plan.storyboard_rows():
        lines.append(f"| {fmt_ts(r['start'])}–{fmt_ts(r['end'])} | {r['id']} | {r['purpose']} | {r['source']} | {r['text']} | "
                     f"{r['voiceover']} | {r['motion']} | {r['transition']} |")
    if plan.hook_variants:
        lines += ["", "## Ganchos alternativos", *[f"- {h}" for h in plan.hook_variants]]
    if plan.notes:
        lines += ["", "## Notas", *[f"- {n}" for n in plan.notes]]
    return "\n".join(lines) + "\n"


def script_markdown(plan: EditPlan) -> str:
    out = [f"# Guion — {plan.project}", ""]
    for sc in plan.scenes:
        txt = " / ".join(t.text for t in sc.texts)
        out.append(f"**{fmt_ts(sc.start)}–{fmt_ts(sc.start + sc.duration)} · {sc.purpose}**  ")
        if txt:
            out.append(f"Pantalla: {txt}  ")
        if sc.voiceover:
            out.append(f"Voz: {sc.voiceover}  ")
        out.append("")
    return "\n".join(out)
