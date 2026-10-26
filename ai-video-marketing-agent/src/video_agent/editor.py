"""Motor de edición. Ejecuta un EditPlan con FFmpeg y produce el vídeo final.

Flujo: escenas → segmentos normalizados (con movimiento, color y rótulos) →
montaje con transiciones (xfade/acrossfade) → mezcla de audio (música con
ducking, voz, efectos, normalización) + subtítulos quemados → exportación.

`EditorBackend` define la interfaz común; FFmpegEditor es la implementación
completa. Un motor alternativo (p. ej. MoviePy) debe implementar los mismos
métodos para que el agente pueda intercambiarlos.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from PIL import Image

from . import config, ff
from .models import EditPlan, Scene
from .motion_graphics import (FontRef, Palette, ease_out_expr, font_for, generate_background, generate_particles,
                              render_text, render_wordmark, text_position)
from .project_manager import Project

log = logging.getLogger("video_agent")
RENDERER_VERSION = "2"


@dataclass
class RenderResult:
    final: Path
    assembled: Path
    segments: list[Path]
    warnings: list[str] = field(default_factory=list)
    layout: dict = field(default_factory=dict)       # rótulos generados (tamaño, desbordes)
    voice_lines: list = field(default_factory=list)
    subtitle_file: Path | None = None
    music_file: Path | None = None
    voice_file: Path | None = None


class EditorBackend(Protocol):
    name: str

    def render_segments(self, plan: EditPlan) -> list[Path]: ...

    def assemble(self, plan: EditPlan, segments: list[Path]) -> Path: ...

    def finalize(self, plan: EditPlan, assembled: Path, music: Path | None, voice: Path | None,
                 subtitles: Path | None, out: Path) -> Path: ...


def _gain(db: float) -> str:
    return f"{ff.db_to_gain(db):.4f}"


class FFmpegEditor:
    name = "ffmpeg"

    def __init__(self, project: Project, settings: dict):
        self.project = project
        self.settings = settings
        self.rs = settings["render"]
        self.warnings: list[str] = []
        self.layout: dict[str, dict] = {}

    # ------------------------------------------------------------ utilidades
    def _ctx(self, plan: EditPlan):
        W, H, fps = plan.export.width, plan.export.height, plan.export.fps
        safe = config.platforms().get(plan.platform, {}).get("safe_zone", {"top": .06, "bottom": .1, "left": .05, "right": .05})
        palette = Palette.from_list(plan.brand.palette or plan.palette)
        return W, H, fps, safe, palette

    def scene_audio(self, plan: EditPlan) -> bool:
        """True si alguna escena conserva audio original que existe de verdad."""
        for sc in plan.scenes:
            if sc.source.type == "clip" and sc.source.keep_audio and sc.source.path:
                p = self.project.abs(sc.source.path)
                if p.exists() and ff.probe(p).has_audio:
                    return True
        return False

    def _seg_len(self, plan: EditPlan, i: int) -> float:
        sc = plan.scenes[i]
        last = i == len(plan.scenes) - 1
        return sc.duration + (0 if last or sc.transition == "cut" else sc.transition_duration)

    def _cache_key(self, plan: EditPlan, i: int, extra: dict) -> str:
        sc = plan.scenes[i]
        payload = {"v": RENDERER_VERSION, "scene": sc.model_dump(mode="json"), "len": self._seg_len(plan, i),
                   "export": plan.export.model_dump(mode="json"), "style": plan.style, "palette": plan.brand.palette or plan.palette,
                   "brand": plan.brand.model_dump(mode="json"), "platform": plan.platform, **extra}
        if sc.source.path:
            p = self.project.abs(sc.source.path)
            if p.exists():
                payload["src_stat"] = [p.stat().st_size, int(p.stat().st_mtime)]
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]

    # ---------------------------------------------------------- recursos
    def _background(self, plan: EditPlan, sc: Scene) -> Path:
        W, H, _, _, palette = self._ctx(plan)
        kind = sc.source.generator or config.styles()[plan.style]["background"]
        if isinstance(kind, list):
            kind = kind[sc.source.seed % len(kind)]
        key = hashlib.sha1(f"{kind}{W}{H}{plan.brand.palette or plan.palette}{sc.source.seed}".encode()).hexdigest()[:10]
        out = self.project.dir("assets") / "generated" / f"bg_{kind}_{key}.png"
        if not out.exists():
            generate_background(kind, W, H, palette, out, seed=sc.source.seed)
            self.project.add_provenance(self.project.rel(out), "generado localmente (Pillow)", "propio del proyecto")
        return out

    def _logo(self, plan: EditPlan) -> Path:
        W, H, _, _, palette = self._ctx(plan)
        if plan.brand.logo and self.project.abs(plan.brand.logo).exists():
            src = self.project.abs(plan.brand.logo)
        else:
            font = font_for("title", self.settings)
            src = self.project.dir("assets") / "generated" / "wordmark.png"
            render_wordmark(plan.brand.name or plan.project, palette, font, src)
        # escala el logo para que ocupe ~55% del lado corto
        target_w = int(min(W, H) * 0.62)
        out = self.project.dir("cache") / f"logo_{target_w}.png"
        with Image.open(src) as im:
            im = im.convert("RGBA")
            bbox = im.getbbox()  # recorta márgenes transparentes
            if bbox:
                im = im.crop(bbox)
            ratio = target_w / im.width
            if im.height * ratio > H * 0.35:
                ratio = H * 0.35 / im.height
            im.resize((max(2, int(im.width * ratio)), max(2, int(im.height * ratio))), Image.LANCZOS).save(out)
        return out

    def _text_pngs(self, plan: EditPlan, i: int) -> list[tuple[Path, int, int, object]]:
        W, H, _, safe, palette = self._ctx(plan)
        sc = plan.scenes[i]
        max_w = int(W * (1 - safe.get("left", .05) - safe.get("right", .05)))
        out = []
        for j, t in enumerate(sc.texts):
            font: FontRef | None = font_for(t.role, self.settings)
            lay = render_text(t.text, t.role, W, H, max_w, palette, font,
                              self.project.dir("cache") / f"text_{sc.id}_{j}.png", t.highlight, t.scale)
            x, y = text_position(t.position, W, H, lay.width, lay.height, safe)
            self.layout[f"{sc.id}.{j}"] = {"text": t.text, "font_size": lay.font_size, "lines": lay.lines,
                                           "box": [x, y, lay.width, lay.height], "overflow": lay.overflow}
            if lay.overflow:
                self.warnings.append(f"El texto '{t.text}' ({sc.id}) no cabe completo en la zona segura")
            out.append((lay.path, x, y, t))
        return out

    # ------------------------------------------------------- segmentos
    def _video_chain(self, plan: EditPlan, sc: Scene, L: float, src_label: str, has_src_frames: bool) -> list[str]:
        W, H, fps, _, palette = self._ctx(plan)
        st = config.styles().get(plan.style, {})
        bg_hex = "#%02x%02x%02x" % palette.bg
        fit = sc.source.fit
        chain: list[str] = []
        if fit == "contain":
            chain.append(f"[{src_label}]scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={bg_hex},setsar=1[fit]")
        elif fit == "blur_fill":
            chain.append(f"[{src_label}]split=2[bgsrc][fgsrc];"
                         f"[bgsrc]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=40,eq=brightness=-0.12:saturation=0.8[bgb];"
                         f"[fgsrc]scale={W}:{H}:force_original_aspect_ratio=decrease,setsar=1[fg];"
                         f"[bgb][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[fit]")
        else:
            chain.append(f"[{src_label}]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[fit]")
        cur = "fit"
        pre = f"fps={fps}"
        if sc.speed != 1.0 and has_src_frames:
            pre = f"setpts=PTS/{sc.speed},fps={fps}"
        if has_src_frames:  # si el clip es más corto que la escena, congela el último fotograma
            pre += f",tpad=stop_mode=clone:stop_duration={L:.3f}"
        chain.append(f"[{cur}]{pre},trim=duration={L:.3f},setpts=PTS-STARTPTS[pre]")
        cur = "pre"
        N = max(1, int(round(L * fps)))
        S = sc.motion_strength
        z, x, y = None, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        if sc.motion == "zoom_in":
            z = f"1+{S}*on/{N}"
        elif sc.motion == "zoom_out":
            z = f"1+{S}-{S}*on/{N}"
        elif sc.motion in ("pan_left", "pan_right", "pan_up", "pan_down"):
            z = f"{1 + S}"
            if sc.motion == "pan_right":
                x = f"(iw-iw/zoom)*on/{N}"
            elif sc.motion == "pan_left":
                x = f"(iw-iw/zoom)*(1-on/{N})"
            elif sc.motion == "pan_down":
                y = f"(ih-ih/zoom)*on/{N}"
            else:
                y = f"(ih-ih/zoom)*(1-on/{N})"
        if z and S > 0:
            chain.append(f"[{cur}]zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={fps}[mot]")
            cur = "mot"
        grade = st.get("grade", "")
        if grade and sc.source.type in ("clip", "image"):
            chain.append(f"[{cur}]{grade}[grd]")
            cur = "grd"
        return chain + [f"[{cur}]null[base]"]

    def render_segment(self, plan: EditPlan, i: int) -> Path:
        W, H, fps, safe, palette = self._ctx(plan)
        sc = plan.scenes[i]
        L = self._seg_len(plan, i)
        texts = self._text_pngs(plan, i)
        key = self._cache_key(plan, i, {"fonts": [str(font_for(t.role, self.settings)) for t in sc.texts]})
        out = self.project.dir("cache") / f"seg_{i:02d}_{sc.id}_{key}.mkv"
        if self.rs.get("cache_segments", True) and out.exists() and out.stat().st_size > 0:
            return out

        args: list[str] = []
        src = sc.source
        has_src_frames = False
        audio_from_clip = False
        if src.type == "clip":
            p = self.project.abs(src.path or "")
            if not p.exists():
                raise FileNotFoundError(f"Escena {sc.id}: no existe el clip {src.path}")
            info = ff.probe(p)
            need = L * sc.speed
            args += ["-ss", f"{src.start:.3f}", "-t", f"{need + 0.1:.3f}", "-i", str(p)]
            has_src_frames = True
            audio_from_clip = src.keep_audio and info.has_audio
        elif src.type == "image":
            p = self.project.abs(src.path or "")
            if not p.exists():
                raise FileNotFoundError(f"Escena {sc.id}: no existe la imagen {src.path}")
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{L:.3f}", "-i", str(p)]
        elif src.type == "color":
            col = (src.color or "#%02x%02x%02x" % palette.bg).lstrip("#")
            args += ["-f", "lavfi", "-i", f"color=c=0x{col}:s={W}x{H}:r={fps}:d={L:.3f}"]
        else:  # generated / logo → fondo generado
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{L:.3f}", "-i", str(self._background(plan, sc))]
        n_in = 1

        fc = self._video_chain(plan, sc, L, "0:v", has_src_frames)
        cur = "base"
        if src.type in ("generated", "logo", "color"):  # paralaje de partículas: da vida a los fondos estáticos
            ptc = self.project.dir("assets") / "generated" / f"particles_{W}x{H}_{sc.source.seed % 3}.png"
            if not ptc.exists():
                generate_particles(W, H, palette, ptc, seed=sc.source.seed % 3)
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{L:.3f}", "-i", str(ptc)]
            speed = H * 0.04 * (1 + (sc.source.seed % 3) * 0.4)
            fc.append(f"[{n_in}:v]format=rgba[ptc]")
            fc.append(f"[{cur}][ptc]overlay=x=0:y='-mod(t*{speed:.1f}+{(sc.source.seed * 211) % H},{H})':eval=frame[bgp]")
            cur = "bgp"
            n_in += 1
        # logotipo
        if src.type == "logo":
            logo = self._logo(plan)
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{L:.3f}", "-i", str(logo)]
            with Image.open(logo) as im:
                lw, lh = im.size
            lx, ly = (W - lw) // 2, int(H * 0.42 - lh / 2)
            e = ease_out_expr(0.15, 0.6)
            fc.append(f"[{n_in}:v]format=rgba,fade=t=in:st=0.15:d=0.5:alpha=1[lg]")
            fc.append(f"[{cur}][lg]overlay=x={lx}:y='{ly}+{int(H * 0.03)}*(1-{e})':eval=frame:shortest=0[wlogo]")
            cur = "wlogo"
            n_in += 1
        # rótulos
        for j, (png, x, y, t) in enumerate(texts):
            args += ["-loop", "1", "-framerate", str(fps), "-t", f"{L:.3f}", "-i", str(png)]
            t0 = t.start
            t1 = min(t.end if t.end is not None else sc.duration - 0.05, sc.duration)
            fade_out = "" if i == len(plan.scenes) - 1 and t.end is None else f",fade=t=out:st={max(t0, t1 - 0.25):.3f}:d=0.25:alpha=1"
            fade_in = f"fade=t=in:st={t0:.3f}:d={0.35 if t.animation != 'none' else 0.01}:alpha=1"
            fc.append(f"[{n_in}:v]format=rgba,{fade_in}{fade_out}[tx{j}]")
            e = ease_out_expr(t0, 0.45)
            xe, ye = f"{x}", f"{y}"
            if t.animation == "slide_up":
                ye = f"{y}+{int(H * 0.035)}*(1-{e})"
            elif t.animation == "slide_left":
                xe = f"{x}+{int(W * 0.08)}*(1-{e})"
            elif t.animation == "pop":
                ye = f"{y}+{int(H * 0.015)}*(1-{e})"
            fc.append(f"[{cur}][tx{j}]overlay=x='{xe}':y='{ye}':eval=frame:enable='between(t,{t0:.3f},{t1 + 0.01:.3f})'[o{j}]")
            cur = f"o{j}"
            n_in += 1
        if plan.export.letterbox:
            bar = int(H * 0.09)
            fc.append(f"[{cur}]drawbox=x=0:y=0:w=iw:h={bar}:color=black:t=fill,drawbox=x=0:y=ih-{bar}:w=iw:h={bar}:color=black:t=fill[lb]")
            cur = "lb"
        fc.append(f"[{cur}]format=yuv420p,setsar=1[vout]")

        # audio de la escena
        if audio_from_clip:
            tempo = []
            sp = sc.speed
            while sp > 2.0:
                tempo.append("atempo=2.0"); sp /= 2.0
            while sp < 0.5:
                tempo.append("atempo=0.5"); sp /= 0.5
            if abs(sp - 1) > 1e-3:
                tempo.append(f"atempo={sp:.4f}")
            chain = ",".join(tempo + [f"volume={_gain(self.settings['audio']['clip_audio_volume_db'])}",
                                      "aformat=sample_rates=48000:channel_layouts=stereo", "apad",
                                      f"atrim=duration={L:.3f}", "afade=t=in:d=0.03",
                                      f"afade=t=out:st={max(0, L - 0.05):.3f}:d=0.05"])
            fc.append(f"[0:a]{chain}[aout]")
        else:
            args += ["-f", "lavfi", "-t", f"{L:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            fc.append(f"[{n_in}:a]atrim=duration={L:.3f}[aout]")
            n_in += 1

        script = self.project.dir("cache") / f"seg_{i:02d}.fc"
        script.write_text(";\n".join(fc), encoding="utf-8")
        ff.ffmpeg(*args, "-filter_complex_script", script, "-map", "[vout]", "-map", "[aout]",
                  "-t", f"{L:.3f}", "-r", str(fps), "-c:v", "libx264", "-preset", self.rs["intermediate_preset"],
                  "-crf", str(self.rs["intermediate_crf"]), "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", "-ar", "48000",
                  "-threads", str(self.rs.get("threads", 0)), out)
        return out

    def render_segments(self, plan: EditPlan) -> list[Path]:
        self.layout = {}
        return [self.render_segment(plan, i) for i in range(len(plan.scenes))]

    # ---------------------------------------------------------- montaje
    def assemble(self, plan: EditPlan, segments: list[Path]) -> Path:
        out = self.project.dir("timeline") / "assembled.mkv"
        if len(segments) == 1:
            shutil.copy2(segments[0], out)
            return out
        args: list[str] = []
        for s in segments:
            args += ["-i", str(s)]
        fc = []
        v, a = "0:v", "0:a"
        for i in range(1, len(segments)):
            prev = plan.scenes[i - 1]
            offset = plan.scenes[i].start
            td = prev.transition_duration
            if prev.transition == "cut" or td <= 0:
                fc.append(f"[{v}][{i}:v]concat=n=2:v=1:a=0[v{i}]")
                fc.append(f"[{a}][{i}:a]concat=n=2:v=0:a=1[a{i}]")
            else:
                fc.append(f"[{v}][{i}:v]xfade=transition={prev.transition}:duration={td:.3f}:offset={offset:.3f}[v{i}]")
                fc.append(f"[{a}][{i}:a]acrossfade=d={td:.3f}:c1=tri:c2=tri[a{i}]")
            v, a = f"v{i}", f"a{i}"
        script = self.project.dir("cache") / "assemble.fc"
        script.write_text(";\n".join(fc), encoding="utf-8")
        ff.ffmpeg(*args, "-filter_complex_script", script, "-map", f"[{v}]", "-map", f"[{a}]",
                  "-t", f"{plan.duration:.3f}", "-c:v", "libx264", "-preset", self.rs["intermediate_preset"],
                  "-crf", str(self.rs["intermediate_crf"]), "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", out)
        return out

    # ------------------------------------------------------- final
    def finalize(self, plan: EditPlan, assembled: Path, music: Path | None, voice: Path | None,
                 subtitles: Path | None, out: Path, sfx: list[tuple[Path, float]] | None = None) -> Path:
        aud = self.settings["audio"]
        args = ["-i", str(assembled)]
        fc: list[str] = []
        mix: list[str] = []
        idx = 1
        has_scene_audio = self.scene_audio(plan)
        fc.append("[0:a]aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[scn][scnkey]")
        mix.append("[scn]")
        key_labels = ["[scnkey]"] if has_scene_audio else []
        if not has_scene_audio:
            fc.append("[scnkey]anullsink")
        if voice:
            args += ["-i", str(voice)]
            fc.append(f"[{idx}:a]volume={_gain(aud['voice_volume_db'])},aformat=sample_rates=48000:channel_layouts=stereo,asplit=2[vo][vokey]")
            mix.append("[vo]")
            key_labels.append("[vokey]")
            idx += 1
        if music:
            args += ["-i", str(music)]
            mdb = plan.music.volume_db if plan.music.volume_db is not None else aud["music_volume_db"]
            fc.append(f"[{idx}:a]volume={_gain(mdb)},aformat=sample_rates=48000:channel_layouts=stereo[mus]")
            idx += 1
            if key_labels and plan.music.duck_under_voice:
                if len(key_labels) > 1:
                    fc.append(f"{''.join(key_labels)}amix=inputs={len(key_labels)}:normalize=0[key]")
                else:
                    fc.append(f"{key_labels[0]}anull[key]")
                ratio = max(2, min(20, abs(aud["music_under_voice_db"]) / 1.5))
                fc.append(f"[mus][key]sidechaincompress=threshold=0.02:ratio={ratio:.1f}:attack=15:release=350:makeup=1[musd]")
                mix.append("[musd]")
            else:
                for k in key_labels:
                    fc.append(f"{k}anullsink")
                mix.append("[mus]")
        else:
            for k in key_labels:
                fc.append(f"{k}anullsink")
        for path, at in sfx or []:
            args += ["-i", str(path)]
            fc.append(f"[{idx}:a]volume={_gain(-8)},adelay={int(at * 1000)}:all=1,aformat=sample_rates=48000:channel_layouts=stereo[fx{idx}]")
            mix.append(f"[fx{idx}]")
            idx += 1
        lufs, tp = aud["loudness_lufs"], aud["true_peak_db"]
        # loudnorm devuelve NaN con silencio digital puro: solo se normaliza si hay audio real
        norm = f"loudnorm=I={lufs}:TP={tp}:LRA=11," if (has_scene_audio or voice or music or sfx) else ""
        fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:dropout_transition=0,"
                  f"{norm}aresample=48000,apad,atrim=0:{plan.duration:.3f}[aout]")
        vchain = "[0:v]null"
        if subtitles:
            fonts_dir = self.project.dir("cache") / "fonts"
            vchain = f"[0:v]ass=filename={ff.filter_path(subtitles, self.project.root)}:fontsdir={ff.filter_path(fonts_dir, self.project.root)}"
        fc.append(f"{vchain},format=yuv420p[vout]")
        script = self.project.dir("cache") / "final.fc"
        script.write_text(";\n".join(fc), encoding="utf-8")
        enc = self._encoder_args(plan)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.stem + ".partial" + out.suffix)
        # cwd=proyecto: el filtro ass recibe rutas relativas sin caracteres que escapar
        ff.ffmpeg(*args, "-filter_complex_script", str(script), "-map", "[vout]", "-map", "[aout]",
                  "-t", f"{plan.duration:.3f}", *enc, str(tmp), cwd=self.project.root)
        tmp.replace(out)
        return out

    def _encoder_args(self, plan: EditPlan) -> list[str]:
        fmt = plan.export.format
        crf = str(plan.export.crf or self.rs["crf"])
        common = ["-r", str(plan.export.fps), "-ar", str(self.rs["audio_sample_rate"])]
        if fmt == "webm":
            return ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-pix_fmt", "yuv420p", "-c:a", "libopus", "-b:a", "160k", *common]
        args = ["-c:v", self.rs["video_codec"], "-preset", self.rs["preset"], "-crf", crf, "-pix_fmt", self.rs["pix_fmt"],
                "-profile:v", "high", "-c:a", self.rs["audio_codec"], "-b:a", self.rs["audio_bitrate"], *common]
        if fmt == "mp4":
            args += ["-movflags", "+faststart"]
        return args

    def install_font(self, font: FontRef | None) -> None:
        """Copia la fuente de subtítulos al proyecto (reproducible y apta para libass)."""
        if not font:
            return
        d = self.project.dir("cache") / "fonts"
        d.mkdir(parents=True, exist_ok=True)
        dest = d / Path(font.file).name
        if not dest.exists():
            shutil.copy2(font.file, dest)


def get_editor(project: Project, settings: dict) -> FFmpegEditor:
    engine = settings["render"].get("engine", "ffmpeg")
    if engine != "ffmpeg":
        raise ValueError(f"Motor de edición '{engine}' no implementado. Motores disponibles: ffmpeg")
    return FFmpegEditor(project, settings)
