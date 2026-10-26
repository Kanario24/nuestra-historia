"""Interfaz de línea de comandos: video-agent <comando>."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from . import __version__, config
from .agent import ProduceResult, VideoAgent
from .ff import FFmpegError
from .integrations import doctor as run_doctor
from .models import EditPlan, Scene, Source, SubtitleSpec
from .project_manager import Project
from .quality_control import Expectations, inspect as qc_inspect

STYLES = list(config.styles())
PLATFORMS = list(config.platforms())
GOALS = list(config.goals())


def _agent(ctx) -> VideoAgent:
    obj = ctx.obj
    return VideoAgent(config.load_settings(obj.get("settings")), obj.get("projects_dir"))


def _print_result(r: ProduceResult, as_json: bool) -> None:
    data = {"project": str(r.project.root), "final": str(r.final), "passed": r.qc.passed, "attempts": r.attempts,
            "deliverables": {k: (str(r.project.root / v) if isinstance(v, str) else v) for k, v in r.deliverables.items()},
            "warnings": r.warnings, "failed_checks": [c.name for c in r.qc.checks if c.status == "fail"],
            "warn_checks": [c.name for c in r.qc.checks if c.status == "warn"]}
    if as_json:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return
    mark = click.style("APROBADO", fg="green") if r.qc.passed else click.style("NO APROBADO", fg="red")
    click.echo(f"\n🎬 {r.final}")
    click.echo(f"   {r.plan.export.width}×{r.plan.export.height} · {r.plan.duration:.2f}s · QC {mark} ({r.attempts} intento/s)")
    for k, v in data["deliverables"].items():
        if v:
            click.echo(f"   - {k}: {v}")
    for w in r.warnings:
        click.echo(click.style(f"   ⚠ {w}", fg="yellow"))
    for c in r.qc.checks:
        if c.status in ("fail", "warn"):
            click.echo(click.style(f"   [{c.status}] {c.name}: {c.detail}", fg="red" if c.status == "fail" else "yellow"))


def _bool_opt(v: str | None) -> bool | None:
    return None if v is None else v == "on"


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="video-agent")
@click.option("--settings", type=click.Path(exists=True, dir_okay=False), help="YAML de configuración adicional.")
@click.option("--projects-dir", type=click.Path(file_okay=False), help="Carpeta de proyectos (por defecto ./projects).")
@click.option("-v", "--verbose", is_flag=True, help="Muestra los comandos FFmpeg ejecutados.")
@click.pass_context
def main(ctx, settings, projects_dir, verbose):
    """AI Video Marketing Agent: planifica, edita, renderiza y revisa vídeos de marketing con FFmpeg."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING, format="%(levelname)s %(message)s")
    ctx.ensure_object(dict)
    ctx.obj.update(settings=settings, projects_dir=projects_dir)


common_plan_opts = [
    click.option("--platform", "-p", type=click.Choice(PLATFORMS), help="Plataforma de destino (define formato y zonas seguras)."),
    click.option("--duration", "-d", type=click.FloatRange(1, 3600), help="Duración en segundos."),
    click.option("--style", "-s", type=click.Choice(STYLES), help="Estilo de edición."),
    click.option("--goal", "-g", type=click.Choice(GOALS), help="Objetivo de marketing."),
    click.option("--brand", "-b", help="Nombre de la marca/producto."),
    click.option("--language", type=click.Choice(["es", "en"]), help="Idioma de textos y voz."),
    click.option("--voiceover", type=click.Choice(["on", "off"]), help="Voz en off (TTS local por defecto)."),
    click.option("--subtitles", type=click.Choice(["on", "off"]), help="Subtítulos quemados."),
    click.option("--subtitle-style", type=click.Choice(["minimal", "corporate", "cinematic", "gaming", "dynamic"])),
    click.option("--cta", help="Texto de la llamada a la acción."),
    click.option("--name", help="Nombre del proyecto."),
]


def plan_options(f):
    for opt in reversed(common_plan_opts):
        f = opt(f)
    return f


def _opts(platform, duration, style, goal, brand, language, voiceover, subtitles, subtitle_style, cta) -> dict:
    return {k: v for k, v in dict(platform=platform, duration=duration, style=style, goal=goal, brand=brand, language=language,
                                  voiceover=_bool_opt(voiceover), subtitles=_bool_opt(subtitles), subtitle_style=subtitle_style,
                                  cta=cta).items() if v is not None}


@main.command()
@click.argument("brief")
@click.option("--input", "-i", "inputs", multiple=True, type=click.Path(exists=True, dir_okay=False),
              help="Material: vídeos, imágenes, logo (nombre con 'logo'), música, voz (nombre con 'voz'/'voice'), fuentes, .srt.")
@plan_options
@click.option("--plan-only", is_flag=True, help="Solo crea el plan y el storyboard (para revisarlo antes de renderizar).")
@click.option("--json", "as_json", is_flag=True, help="Salida en JSON.")
@click.pass_context
def create(ctx, brief, inputs, platform, duration, style, goal, brand, language, voiceover, subtitles, subtitle_style, cta,
           name, plan_only, as_json):
    """Crea un vídeo a partir de una petición en lenguaje natural.

    Ejemplo: video-agent create "Vídeo de 25 s para TikTok de Nexus Development, estética tecnológica oscura"
    """
    agent = _agent(ctx)
    project, plan = agent.plan(brief, list(inputs), name, **_opts(platform, duration, style, goal, brand, language, voiceover,
                                                                 subtitles, subtitle_style, cta))
    if plan_only:
        click.echo(f"Plan creado: {project.file}\nStoryboard: {project.root / 'storyboard' / 'storyboard.md'}\n"
                   f"Renderiza con: video-agent render {project.root}")
        return
    _print_result(agent.produce(project, plan), as_json)


@main.command()
@click.argument("project_dir", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def render(ctx, project_dir, as_json):
    """(Re)renderiza un proyecto a partir de su project.json (reproducible)."""
    agent = _agent(ctx)
    project = Project.open(project_dir)
    _print_result(agent.produce(project), as_json)


@main.command()
@click.argument("inputs", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--brief", default="", help="Descripción de lo que se quiere conseguir.")
@plan_options
@click.option("--keep-audio/--no-keep-audio", default=None, help="Conservar el audio original (por defecto: sí si hay voz).")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def edit(ctx, inputs, brief, platform, duration, style, goal, brand, language, voiceover, subtitles, subtitle_style, cta,
         name, keep_audio, as_json):
    """Edita clips aportados como un vídeo profesional (cortes, textos, color, música, transiciones)."""
    agent = _agent(ctx)
    opts = _opts(platform, duration, style, goal, brand, language, voiceover, subtitles, subtitle_style, cta)
    subs_opt = opts.pop("subtitles", None)
    r = agent.edit(list(inputs), brief=brief, subtitles=subs_opt, name=name, keep_clip_audio=keep_audio, **opts)
    _print_result(r, as_json)


@main.command()
@click.argument("video", type=click.Path(exists=True, dir_okay=False))
@click.option("--duration", type=float, help="Duración esperada (s).")
@click.option("--platform", type=click.Choice(PLATFORMS), help="Comprueba resolución y FPS de la plataforma.")
@click.option("--no-audio-expected", is_flag=True, help="No marcar como error la ausencia de audio.")
@click.option("--frames-dir", type=click.Path(file_okay=False), help="Dónde guardar fotogramas y hoja de contactos.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def inspect(ctx, video, duration, platform, no_audio_expected, frames_dir, as_json):
    """Analiza técnicamente un vídeo y genera un informe de calidad (código de salida 1 si falla)."""
    settings = config.load_settings(ctx.obj.get("settings"))
    exp = Expectations(duration=duration, audio=not no_audio_expected,
                       loudness_lufs=None)
    if platform:
        pf = config.platforms()[platform]
        exp.width, exp.height, exp.fps = pf["width"], pf["height"], pf["fps"]
    fd = Path(frames_dir) if frames_dir else Path(video).with_suffix("").parent / f"{Path(video).stem}_qc"
    rep = qc_inspect(video, exp, settings, fd)
    rep.save(fd, "qc_report")
    if as_json:
        click.echo(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False))
    else:
        click.echo(rep.to_markdown())
        click.echo(f"Informe guardado en {fd / 'qc_report.md'}")
    sys.exit(0 if rep.passed else 1)


@main.command()
@click.argument("project_dir", type=click.Path(exists=True))
@click.option("--count", "-n", type=click.IntRange(1, 20), default=3, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def variants(ctx, project_dir, count, as_json):
    """Genera N variantes de un proyecto con ganchos distintos (para pruebas A/B)."""
    agent = _agent(ctx)
    project = Project.open(project_dir)
    for r in agent.variants(project, count):
        _print_result(r, as_json)


@main.command()
@click.argument("video", type=click.Path(exists=True, dir_okay=False))
@click.option("--count", "-n", type=click.IntRange(1, 20), default=3, show_default=True)
@click.option("--duration", "-d", type=float, default=30, show_default=True)
@click.option("--platform", "-p", type=click.Choice(PLATFORMS), default="youtube_shorts", show_default=True)
@click.option("--fit", type=click.Choice(["blur_fill", "cover", "contain"]), default="blur_fill", show_default=True,
              help="blur_fill: plano completo sobre fondo desenfocado; cover: recorte centrado.")
@click.option("--subtitles", type=click.Choice(["on", "off"]))
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def shorts(ctx, video, count, duration, platform, fit, subtitles, as_json):
    """Convierte un vídeo largo/horizontal en varios cortos verticales."""
    agent = _agent(ctx)
    for r in agent.shorts(video, count, duration, platform, fit=fit, subtitles=_bool_opt(subtitles)):
        _print_result(r, as_json)


@main.command()
@click.argument("video", type=click.Path(exists=True, dir_okay=False))
@click.option("--style", type=click.Choice(["minimal", "corporate", "cinematic", "gaming", "dynamic"]), default="dynamic", show_default=True)
@click.option("--language", help="Idioma de la voz (es, en...). Por defecto se detecta.")
@click.option("--music", "music", type=click.Path(exists=True, dir_okay=False), help="Música a mezclar bajo la voz.")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def subtitle(ctx, video, style, language, music, as_json):
    """Transcribe la voz de un vídeo y le añade subtítulos animados (y música opcional)."""
    agent = _agent(ctx)
    project = Project.create(f"{Path(video).stem}-subtitulado", agent.projects_dir)
    assets, analyses = agent.ingest(project, [video] + ([music] if music else []))
    clip = next((a for a in analyses if a.kind == "video" and a.ok), None)
    if not clip:
        raise click.ClickException("El vídeo no se puede leer")
    W, H = clip.width - clip.width % 2, clip.height - clip.height % 2
    plat = "tiktok" if H > W else ("square" if H == W else "landscape")
    plan = EditPlan(project=project.name, brief="Añadir subtítulos", objective="Subtitulado", platform=plat, duration=clip.duration,
                    style="minimal", scenes=[Scene(id="s01", duration=clip.duration, motion="none", motion_strength=0, transition="cut",
                                                   source=Source(type="clip", path=clip.path, keep_audio=True))],
                    subtitles=SubtitleSpec(enabled=True, source="transcribe", style=style, language=language or ""),
                    export={"width": W, "height": H, "fps": round(clip.fps or 30, 3)})
    plan.music.generate = False
    plan.music.path = assets.music
    agent.write_plan_docs(project, plan)
    _print_result(agent.produce(project, plan), as_json)


@main.command()
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def doctor(ctx, as_json):
    """Comprueba herramientas, proveedores y permisos disponibles en este equipo."""
    rep = run_doctor(config.load_settings(ctx.obj.get("settings")))
    if as_json:
        click.echo(json.dumps(rep, indent=2, ensure_ascii=False))
        return
    for k, v in rep["tools"].items():
        click.echo(f"{'✔' if v not in (False, None, []) or k == 'ffmpeg_filters_missing' and not v else '✘'} {k}: {v}")
    for k, v in rep["providers"].items():
        click.echo(f"• {k}: {v}")
    click.echo(f"• permisos: {rep['permissions']}")
    if rep["missing"]:
        click.echo(click.style("Falta: " + "; ".join(rep["missing"]), fg="yellow"))
    else:
        click.echo(click.style("Todo lo necesario para el modo local está disponible.", fg="green"))


def run() -> None:
    try:
        main(obj={})
    except FFmpegError as e:
        click.echo(click.style(f"Error de FFmpeg: {e}", fg="red"), err=True)
        sys.exit(2)
    except (FileNotFoundError, ValueError, PermissionError) as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(2)


if __name__ == "__main__":
    run()
