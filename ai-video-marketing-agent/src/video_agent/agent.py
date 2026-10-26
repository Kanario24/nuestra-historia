"""Orquestador: petición → plan → render → control de calidad → corrección → entrega."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import audio as audio_mod
from . import config, exporter, planner, subtitles as subs
from .editor import FFmpegEditor, get_editor
from .media_manager import ClipAnalysis, analyze_clip, classify, mark_duplicates, _window_score
from .models import EditPlan, Scene, Source, SubtitleSpec, TextOverlay, fmt_ts
from .motion_graphics import Palette, font_for
from .project_manager import Project
from .quality_control import Expectations, QCReport, inspect

log = logging.getLogger("video_agent")


@dataclass
class ProduceResult:
    project: Project
    plan: EditPlan
    final: Path
    qc: QCReport
    attempts: int
    deliverables: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    summary_path: Path | None = None


class VideoAgent:
    def __init__(self, settings: dict | None = None, projects_dir: str | Path | None = None):
        self.settings = settings or config.load_settings()
        self.projects_dir = Path(projects_dir or self.settings["workspace"]["projects_dir"])
        self._layout: dict = {}

    # ------------------------------------------------------------- material
    def ingest(self, project: Project, paths: list[str | Path], analyze: bool = True) -> tuple[planner.AssetSet, list[ClipAnalysis]]:
        """Importa el material del usuario (copia, nunca modifica originales) y lo analiza."""
        assets = planner.AssetSet()
        analyses: list[ClipAnalysis] = []
        max_mb = self.settings["limits"]["max_input_file_mb"]
        ref_dir = project.dir("previews") / "reference"
        for p in paths:
            p = Path(p)
            kind = classify(p)
            rel = project.import_file(p, "input" if kind in ("video", "image", "voice", "music") else "asset",
                                      copy=self.settings["workspace"].get("copy_inputs", True), max_mb=max_mb)
            absp = project.abs(rel)
            if kind == "font":
                assets.fonts.append(rel)
                continue
            if kind == "subtitle":
                assets.subtitles = rel
                continue
            if kind == "music":
                assets.music = rel
                project.add_provenance(rel, "usuario", "el usuario declara tener derechos de uso")
                continue
            if kind == "voice":
                assets.voice = rel
                continue
            a = analyze_clip(absp, ref_dir if analyze else None, deep=analyze)
            a.path = rel
            analyses.append(a)
            if not a.ok:
                log.warning("Archivo descartado %s: %s", rel, a.error)
                continue
            if kind == "logo":
                assets.logo = rel
            elif kind == "image":
                assets.images.append(rel)
        mark_duplicates(analyses)
        assets.clips = [a for a in analyses if a.kind == "video"]
        dupe_imgs = {a.path for a in analyses if a.kind == "image" and a.duplicate_of}
        assets.images = [i for i in assets.images if i not in dupe_imgs]
        (project.dir("reports") / "media_analysis.json").write_text(
            json.dumps([a.to_dict() for a in analyses], indent=2, ensure_ascii=False), encoding="utf-8")
        return assets, analyses

    # ----------------------------------------------------------------- plan
    def plan(self, brief: str, inputs: list[str | Path] | None = None, name: str | None = None, **opts) -> tuple[Project, EditPlan]:
        info = planner.parse_brief(brief)
        name = name or info.brand or " ".join(brief.split()[:6])
        project = Project.create(name, self.projects_dir)
        project.data["brief"] = brief
        project.save()
        assets, _ = self.ingest(project, inputs or [])
        plan = planner.build_plan(brief, project.name, assets, **opts)
        self._check_limits(plan)
        self.write_plan_docs(project, plan)
        return project, plan

    def _check_limits(self, plan: EditPlan) -> None:
        lim = self.settings["limits"]
        if plan.duration > lim["max_duration_s"]:
            raise ValueError(f"Duración {plan.duration}s supera limits.max_duration_s ({lim['max_duration_s']}s)")

    def write_plan_docs(self, project: Project, plan: EditPlan) -> None:
        project.save_plan(plan)
        sb = project.dir("storyboard")
        (sb / "plan.json").write_text(json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8")
        (sb / "storyboard.md").write_text(planner.storyboard_markdown(plan), encoding="utf-8")
        (sb / "script.md").write_text(planner.script_markdown(plan), encoding="utf-8")

    # --------------------------------------------------------------- render
    def _audio_assets(self, project: Project, plan: EditPlan, editor: FFmpegEditor, assembled: Path, warnings: list[str]):
        music = voice = None
        voice_lines = []
        adir = project.dir("audio")
        if plan.music.path:
            src = project.abs(plan.music.path)
            music = audio_mod.prepare_music(src, adir / "music_prepared.wav", plan.duration, plan.music.fade_in, plan.music.fade_out)
        elif plan.music.generate:
            music = adir / f"music_{plan.music.mood}_{int(plan.music.bpm)}_{plan.duration:.2f}.wav"
            if not music.exists():
                audio_mod.synth_music(music, plan.duration, plan.music.mood, plan.music.bpm)
                project.add_provenance(project.rel(music), "sintetizada localmente (FFmpeg aevalsrc)", "propia, libre de derechos")
        if plan.voiceover.path:
            src = project.abs(plan.voiceover.path)
            voice = adir / "voiceover_prepared.wav"
            audio_mod.ff.ffmpeg("-i", src, "-af", f"aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=0:{plan.duration:.3f}",
                                "-c:a", "pcm_s16le", voice)
        elif plan.voiceover.enabled:
            lines = [(sc.id, sc.voiceover, sc.start, sc.duration) for sc in plan.scenes if sc.voiceover]
            if lines:
                try:
                    voice, voice_lines, w = audio_mod.build_voiceover_track(
                        lines, adir / "voice", plan.duration, self.settings, plan.voiceover.language,
                        plan.voiceover.provider, plan.voiceover.voice)
                    warnings += w
                    project.add_provenance(project.rel(voice), f"TTS {plan.voiceover.provider or self.settings['tts']['provider']}",
                                           "generada para este proyecto")
                except (audio_mod.ProviderUnavailable, audio_mod.PermissionDenied) as e:
                    warnings.append(f"Voz en off no generada: {e}")
        return music, voice, voice_lines

    def _subtitles(self, project: Project, plan: EditPlan, editor: FFmpegEditor, assembled: Path, voice: Path | None,
                   voice_lines: list, warnings: list[str]) -> tuple[Path | None, list[str]]:
        sp = plan.subtitles
        if not sp.enabled:
            return None, []
        words: list[subs.Word] = []
        if sp.source == "file" and sp.file:
            cues = subs.parse_srt(project.abs(sp.file))
        else:
            if sp.source == "voiceover" and voice_lines:
                # no se subtitula lo que ya aparece literalmente como rótulo en esa escena
                shown = {(sc.id, _norm_text(t.text)) for sc in plan.scenes for t in sc.texts}
                lines = [vl for vl in voice_lines if (vl.scene_id, _norm_text(vl.text)) not in shown]
                if not lines:
                    warnings.append("Subtítulos omitidos: toda la locución ya aparece como texto en pantalla.")
                    return None, []
                words = subs.words_from_lines([(vl.text, vl.start, vl.end) for vl in lines])
            else:  # transcripción real del audio
                target = voice if (plan.voiceover.path and voice) else assembled
                try:
                    words, lang = subs.transcribe(target, self.settings, sp.language or None)
                    project.data.setdefault("transcriptions", []).append({"file": project.rel(target), "language": lang, "words": len(words)})
                    project.save()
                except subs.TranscriptionUnavailable as e:
                    warnings.append(f"Subtítulos no generados: {e}")
                    return None, []
            if not words:
                warnings.append("Subtítulos activados pero no se detectó voz que transcribir.")
                return None, []
            cues = subs.group_words(words, sp.max_words)
        W, H = plan.export.width, plan.export.height
        safe = config.platforms().get(plan.platform, {}).get("safe_zone", {})
        palette = Palette.from_list(plan.brand.palette or plan.palette)
        font = font_for("subtitle", self.settings)
        editor.install_font(font)
        sdir = project.dir("subtitles")
        subs.write_srt(cues, sdir / "captions.srt")
        ass = subs.write_ass(cues, sdir / "captions.ass", W, H, palette, font, sp.style, safe, sp.highlight_words, sp.font_scale)
        problems = subs.check_fit(cues, W, H, font, sp.style, safe, sp.font_scale)
        return ass, problems

    def _expectations(self, plan: EditPlan, editor: FFmpegEditor, has_audio: bool, sub_problems: list[str],
                      music: Path | None, voice: Path | None) -> Expectations:
        allowed_black = []
        for i, sc in enumerate(plan.scenes[:-1]):
            if sc.transition in ("fadeblack",):
                t = plan.scenes[i + 1].start
                allowed_black.append((t - 0.2, t + sc.transition_duration + 0.2))
        allowed_black += [(sc.start, sc.start + sc.duration) for sc in plan.scenes if sc.source.type == "color"]
        allowed_silence = [(0, 0.6), (max(0, plan.duration - 2.0), plan.duration + 1)]
        if not music:  # sin música, las pausas entre frases son normales
            allowed_silence = [(0, plan.duration + 1)]
        sample_times = [sc.start + min(sc.duration * 0.6, max(0.5, sc.duration - 0.5)) for sc in plan.scenes]
        labels = [f"{sc.id} {sc.purpose} {fmt_ts(t)}" for sc, t in zip(plan.scenes, sample_times)]
        return Expectations(duration=plan.duration, width=plan.export.width, height=plan.export.height, fps=plan.export.fps,
                            audio=has_audio, allowed_black=allowed_black, allowed_silence=allowed_silence,
                            loudness_lufs=self.settings["audio"]["loudness_lufs"] if has_audio else None,
                            text_layout=editor.layout, subtitle_problems=sub_problems,
                            sample_times=sample_times, sample_labels=labels)

    def render_once(self, project: Project, plan: EditPlan) -> tuple[Path, QCReport, list[str], dict]:
        warnings: list[str] = []
        editor = get_editor(project, self.settings)
        t0 = time.time()
        segments = editor.render_segments(plan)
        assembled = editor.assemble(plan, segments)
        music, voice, voice_lines = self._audio_assets(project, plan, editor, assembled, warnings)
        ass, sub_problems = self._subtitles(project, plan, editor, assembled, voice, voice_lines, warnings)
        sfx = []
        for i, sc in enumerate(plan.scenes):
            if sc.sfx:
                f = project.dir("audio") / f"sfx_{sc.sfx}.wav"
                if not f.exists():
                    audio_mod.synth_sfx(sc.sfx, f)
                at = sc.start - (0.2 if sc.sfx == "whoosh" else 0.0)
                sfx.append((f, max(0.0, at)))
        out = project.dir("exports") / plan.export.filename
        final = editor.finalize(plan, assembled, music, voice, ass, out, sfx)
        warnings += editor.warnings
        self._layout = dict(editor.layout)
        has_audio = bool(music or voice or sfx or editor.scene_audio(plan))
        exp = self._expectations(plan, editor, has_audio, sub_problems, music, voice)
        stem = Path(plan.export.filename).stem
        qc = inspect(final, exp, self.settings, project.dir("previews") / f"qc_{stem}")
        if plan.subtitles.enabled and ass and not sub_problems:
            qc.add("Subtítulos sin cortes", "pass", "Todas las líneas caben en la zona segura (≤2 líneas)")
        elif plan.subtitles.enabled and not ass:
            qc.add("Subtítulos", "warn", "Se pidieron subtítulos pero no se generaron (ver avisos)")
        timeline = {"segments": [project.rel(s) for s in segments], "assembled": project.rel(assembled),
                    "music": project.rel(music) if music else None, "voice": project.rel(voice) if voice else None,
                    "subtitles": project.rel(ass) if ass else None, "sfx": [(project.rel(p), t) for p, t in sfx],
                    "text_layout": editor.layout, "render_seconds": round(time.time() - t0, 1),
                    "voice_lines": [{"scene": v.scene_id, "start": round(v.start, 2), "end": round(v.end, 2), "text": v.text, "tempo": v.tempo}
                                    for v in voice_lines]}
        (project.dir("timeline") / f"timeline_{stem}.json").write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
        return final, qc, warnings, timeline

    # ---------------------------------------------------------- corrección
    def apply_fixes(self, project: Project, plan: EditPlan, qc: QCReport) -> list[str]:
        applied: list[str] = []
        fixes = qc.fixes
        if "text_overflow" in fixes:
            for sc in plan.scenes:
                for j, t in enumerate(sc.texts):
                    lay = self._layout.get(f"{sc.id}.{j}")
                    if lay and lay.get("overflow"):
                        t.scale = round(t.scale * 0.85, 3)
                        applied.append(f"Texto '{t.text}' reducido al {t.scale:.0%}")
        if "subtitle_size" in fixes:
            plan.subtitles.font_scale = round(plan.subtitles.font_scale * 0.85, 3)
            plan.subtitles.max_words = max(2, plan.subtitles.max_words - 1)
            applied.append(f"Subtítulos más pequeños (x{plan.subtitles.font_scale}) y con menos palabras por línea")
        if "black" in fixes:
            ranges = next((c.data.get("ranges", []) for c in qc.checks if c.fix == "black"), [])
            for s, e in ranges:
                for sc in plan.scenes:
                    if sc.start < e and sc.start + sc.duration > s and sc.source.type in ("clip", "image"):
                        old = sc.source.path
                        sc.source = Source(type="generated", seed=hash(sc.id) % 97)
                        applied.append(f"Escena {sc.id}: el material ({old}) era negro en {fmt_ts(s)}–{fmt_ts(e)}; se sustituye por un fondo generado")
        if "audio" in fixes:
            if plan.music.path is None and not plan.music.generate and not plan.voiceover.enabled:
                pass  # el usuario pidió sin música/voz: no se inventa audio
            elif plan.music.generate or plan.music.path:
                cur = plan.music.volume_db if plan.music.volume_db is not None else self.settings["audio"]["music_volume_db"]
                if cur < -2:
                    plan.music.volume_db = cur + 4
                    applied.append(f"Volumen de música aumentado a {plan.music.volume_db} dB para cubrir silencios")
        if {"rerender", "retime"} & set(fixes):
            plan.retime()
            for f in project.dir("cache").glob("seg_*.mkv"):
                f.unlink()
            applied.append("Caché de escenas eliminada y nuevo render completo")
        return applied

    # -------------------------------------------------------------- producir
    def produce(self, project: Project, plan: EditPlan | None = None, previews: bool = True) -> ProduceResult:
        plan = plan or project.load_plan()
        self._check_limits(plan)
        self.write_plan_docs(project, plan)
        max_attempts = int(self.settings["limits"]["max_render_attempts"])
        warnings: list[str] = []
        final = qc = None
        attempt = 0
        for attempt in range(1, max_attempts + 1):
            final, qc, warnings, timeline = self.render_once(project, plan)
            entry = {"attempt": attempt, "output": project.rel(final), "passed": qc.passed,
                     "failed_checks": [c.name for c in qc.checks if c.status == "fail"],
                     "warnings": warnings, "render_seconds": timeline["render_seconds"]}
            if qc.passed:
                project.log_attempt(entry)
                break
            applied = self.apply_fixes(project, plan, qc)
            entry["fixes_applied"] = applied
            project.log_attempt(entry)
            if not applied:
                break
            self.write_plan_docs(project, plan)
        stem = Path(plan.export.filename).stem
        qc.save(project.dir("reports"), "qc_report" if stem == "final" else f"qc_{stem}")
        deliverables = {"video": project.rel(final), "plan": "storyboard/plan.json", "storyboard": "storyboard/storyboard.md",
                        "script": "storyboard/script.md", "qc_report": f"reports/{'qc_report' if stem == 'final' else 'qc_' + stem}.md",
                        "contact_sheet": project.rel(qc.contact_sheet) if qc.contact_sheet else None}
        if (project.root / "subtitles" / "captions.srt").exists() and plan.subtitles.enabled:
            deliverables["subtitles"] = ["subtitles/captions.srt", "subtitles/captions.ass"]
        if previews and plan.export.preview:
            pv = exporter.make_preview(final, project.dir("previews") / f"{stem}_preview.mp4")
            th_t = plan.scenes[0].start + min(1.2, plan.scenes[0].duration * 0.7)
            th = exporter.make_thumbnail(final, project.dir("previews") / f"{stem}_thumbnail.jpg", th_t)
            deliverables["preview"] = project.rel(pv)
            deliverables["thumbnail"] = project.rel(th)
        res = ProduceResult(project, plan, final, qc, attempt, deliverables, warnings)
        res.summary_path = self.write_summary(res)
        deliverables["summary"] = project.rel(res.summary_path)
        if stem == "final":
            project.set_deliverables(deliverables)
        else:
            project.data.setdefault("variants", {})[stem] = deliverables
            project.save()
        return res

    def write_summary(self, r: ProduceResult) -> Path:
        p = r.plan
        lines = [f"# Resumen — {p.project}", "",
                 f"**Vídeo:** `{r.deliverables['video']}` · {p.export.width}×{p.export.height} · {p.duration:.2f}s · {p.platform}",
                 f"**Control de calidad:** {'aprobado' if r.qc.passed else 'NO aprobado'} tras {r.attempts} intento(s) "
                 f"(ver `{r.deliverables['qc_report']}`)", "",
                 "## Qué se ha hecho",
                 f"- Objetivo: {p.objective}. Estilo `{p.style}`, ritmo {p.pacing}, {len(p.scenes)} escenas.",
                 "- Imagen: " + ", ".join(sorted({sc.source.type for sc in p.scenes})) + " (generado = fondos creados localmente).",
                 f"- Música: {p.music.path or ('base sintética local ' + p.music.mood if p.music.generate else 'sin música')}.",
                 f"- Voz en off: {'sí (' + (p.voiceover.path or (p.voiceover.provider or self.settings['tts']['provider'])) + ')' if p.voiceover.enabled else 'no'}.",
                 f"- Subtítulos: {('estilo ' + p.subtitles.style + ', fuente ' + p.subtitles.source) if p.subtitles.enabled else 'no'}.",
                 f"- CTA: {p.cta}", "", "## Entregables"]
        lines += [f"- {k}: `{v}`" for k, v in r.deliverables.items() if v]
        issues = [c for c in r.qc.checks if c.status in ("fail", "warn")]
        if issues or r.warnings or p.notes:
            lines += ["", "## Avisos"]
            lines += [f"- [{c.status}] {c.name}: {c.detail}" for c in issues]
            lines += [f"- {w}" for w in r.warnings] + [f"- {n}" for n in p.notes]
        lines += ["", "## Limitaciones", *[f"- {l}" for l in r.qc.limitations],
                  "- No se garantiza alcance, viralidad ni resultados comerciales."]
        stem = Path(p.export.filename).stem
        out = r.project.dir("reports") / ("summary.md" if stem == "final" else f"summary_{stem}.md")
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out

    # ------------------------------------------------------------ comandos
    def create(self, brief: str, inputs: list[str | Path] | None = None, name: str | None = None, **opts) -> ProduceResult:
        project, plan = self.plan(brief, inputs, name, **opts)
        return self.produce(project, plan)

    def edit(self, inputs: list[str | Path], brief: str = "", style: str | None = None, platform: str | None = None,
             duration: float | None = None, subtitles: bool | None = None, name: str | None = None, **opts) -> ProduceResult:
        """Edita el material aportado. Si los clips tienen voz, se conserva su audio y se subtitula."""
        name = name or Path(inputs[0]).stem
        project = Project.create(name, self.projects_dir)
        assets, analyses = self.ingest(project, inputs)
        speech = any(a.speech_ratio > 0.5 for a in analyses if a.ok and a.kind == "video")
        keep = opts.pop("keep_clip_audio", None)
        keep = speech if keep is None else keep
        brief = brief or f"Edición profesional de {name}"
        plan = planner.build_plan(brief, project.name, assets, style=style, platform=platform, duration=duration,
                                  subtitles=subtitles if subtitles is not None else (True if keep and speech else None),
                                  keep_clip_audio=keep, **opts)
        if keep and speech:
            plan.music.duck_under_voice = True
            plan.notes.append("El material tiene voz: se conserva el audio original y la música se atenúa bajo la voz.")
        self.write_plan_docs(project, plan)
        return self.produce(project, plan)

    def variants(self, project: Project, count: int = 3) -> list[ProduceResult]:
        """Versiones con ganchos distintos; las escenas no modificadas se reutilizan de la caché."""
        count = min(count, int(self.settings["limits"]["max_variants"]))
        base = project.load_plan()
        hooks = base.hook_variants or [t.text for t in base.scenes[0].texts]
        results = []
        for k in range(count):
            plan = base.model_copy(deep=True)
            hook = hooks[k % len(hooks)]
            first = plan.scenes[0]
            if first.texts:
                first.texts[0].text = hook
            else:
                first.texts.append(TextOverlay(text=hook, role="hook"))
            if first.voiceover:
                first.voiceover = hook
            plan.export.filename = f"variants/variant_{k + 1:02d}.mp4"
            plan.notes = plan.notes + [f"Variante {k + 1}: gancho «{hook}»"]
            results.append(self.produce(project, plan))
        project.save_plan(base)  # el plan principal no cambia
        self.write_plan_docs(project, base)
        return results

    def shorts(self, source: str | Path, count: int = 3, duration: float = 30, platform: str = "youtube_shorts",
               style: str | None = None, fit: str = "blur_fill", subtitles: bool | None = None,
               name: str | None = None) -> list[ProduceResult]:
        """Convierte un vídeo (p. ej. horizontal) en varios cortos verticales eligiendo los mejores fragmentos."""
        name = name or f"{Path(source).stem}-shorts"
        parent = Project.create(name, self.projects_dir)
        _, analyses = self.ingest(parent, [source])
        clip = next((a for a in analyses if a.kind == "video" and a.ok), None)
        if not clip:
            raise ValueError(f"No se pudo analizar el vídeo {source}")
        duration = min(duration, clip.duration)
        windows = []
        step = 1.0
        t = 0.0
        while t + duration <= clip.duration + 1e-6:
            score = _window_score(clip, t, duration)
            loud = [r["loudness_db"] for r in clip.per_second if t <= r["t"] < t + duration and r["loudness_db"] is not None]
            if loud:
                score += 0.2 * min(1.0, max(0.0, (sum(loud) / len(loud) + 45) / 30))
            windows.append((score, t))
            t += step
        chosen: list[float] = []
        for score, t in sorted(windows, reverse=True):
            if all(abs(t - c) >= duration for c in chosen):
                chosen.append(t)
            if len(chosen) >= count:
                break
        chosen.sort()
        if len(chosen) < count:
            parent.data.setdefault("notes", []).append(f"El vídeo solo permite {len(chosen)} cortos de {duration:.0f}s sin solaparse.")
        speech = clip.speech_ratio > 0.5
        results = []
        styles = config.styles()
        st_name = style or "energetic"
        for k, start in enumerate(chosen):
            sub = Project.create(f"short-{k + 1:02d}", parent.root)
            rel = sub.import_file(parent.abs(clip.path), "input")
            cuts = [c - start for c in clip.scene_cuts if start + 0.8 < c < start + duration - 0.8]
            bounds = [0.0] + cuts + [duration]
            scenes = []
            for j, (a, b) in enumerate(zip(bounds, bounds[1:])):
                scenes.append(Scene(id=f"s{j + 1:02d}", purpose="hook" if j == 0 else "body", duration=b - a,
                                    source=Source(type="clip", path=rel, start=start + a, keep_audio=True, fit=fit),
                                    motion="zoom_in" if j % 2 == 0 else "zoom_out", motion_strength=0.04,
                                    transition="cut", transition_duration=0))
            pf = config.platforms()[platform]
            plan = EditPlan(project=sub.name, brief=f"Short {k + 1} de {Path(source).name} ({fmt_ts(start)}–{fmt_ts(start + duration)})",
                            objective="Reutilizar contenido largo en formato corto", goal="followers", platform=platform,
                            duration=duration, aspect=pf["aspect"], style=st_name, palette=styles[st_name]["palette"], scenes=scenes,
                            export={"width": pf["width"], "height": pf["height"], "fps": pf["fps"]},
                            subtitles=SubtitleSpec(enabled=speech if subtitles is None else subtitles, source="transcribe",
                                                   style=styles[st_name]["subtitle_style"]))
            plan.music.generate = False
            plan.notes.append(f"Fragmento original {fmt_ts(start)}–{fmt_ts(start + duration)}; encuadre '{fit}'.")
            self.write_plan_docs(sub, plan)
            results.append(self.produce(sub, plan))
        return results


def _norm_text(t: str) -> str:
    return " ".join("".join(ch for ch in t.lower() if ch.isalnum() or ch.isspace()).split())
