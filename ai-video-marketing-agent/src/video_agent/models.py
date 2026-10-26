"""Modelo de datos del plan de edición (se guarda en project.json).

El plan es la fuente de verdad: el editor lo ejecuta literalmente, por lo que
modificar el JSON y volver a renderizar reproduce el vídeo con los cambios.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

Motion = Literal["none", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"]
Animation = Literal["none", "fade", "slide_up", "slide_left", "pop"]
Position = Literal["top", "center", "bottom", "lower_third"]
Fit = Literal["cover", "contain", "blur_fill"]

# Transiciones xfade de FFmpeg admitidas + "cut" (corte seco).
TRANSITIONS = {
    "cut", "fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circleopen", "circleclose", "zoomin", "pixelize", "radial", "hblur", "distance",
}


class TextOverlay(BaseModel):
    text: str
    role: Literal["hook", "title", "body", "cta", "label"] = "title"
    position: Position = "center"
    start: float = Field(0.0, ge=0, description="segundos desde el inicio de la escena")
    end: Optional[float] = Field(None, description="segundos desde el inicio de la escena (None = hasta el final)")
    animation: Animation = "slide_up"
    highlight: list[str] = Field(default_factory=list, description="palabras resaltadas con el color de acento")
    scale: float = Field(1.0, gt=0.2, le=3.0, description="multiplicador del tamaño de fuente")


class Source(BaseModel):
    type: Literal["clip", "image", "generated", "color", "logo"]
    path: Optional[str] = Field(None, description="ruta relativa al proyecto (clip, image, logo)")
    start: float = Field(0.0, ge=0, description="punto de entrada en el clip (s)")
    generator: Optional[str] = Field(None, description="fondo local: tech_grid, gradient, spotlight, speed_lines, minimal, bokeh")
    color: Optional[str] = None
    fit: Fit = "cover"
    keep_audio: bool = False
    seed: int = 0


class Scene(BaseModel):
    id: str
    purpose: str = "body"
    start: float = Field(0.0, ge=0)
    duration: float = Field(..., gt=0.2)
    source: Source
    texts: list[TextOverlay] = Field(default_factory=list)
    motion: Motion = "zoom_in"
    motion_strength: float = Field(0.08, ge=0, le=0.5)
    speed: float = Field(1.0, gt=0.25, le=4.0)
    transition: str = Field("fade", description="transición HACIA la escena siguiente")
    transition_duration: float = Field(0.4, ge=0, le=2.0)
    voiceover: Optional[str] = None
    sfx: Optional[Literal["whoosh", "hit", "rise", "click"]] = None
    notes: str = ""

    @model_validator(mode="after")
    def _check_transition(self):
        if self.transition not in TRANSITIONS:
            raise ValueError(f"Transición no soportada '{self.transition}'. Opciones: {sorted(TRANSITIONS)}")
        if self.transition == "cut":
            self.transition_duration = 0.0
        return self


class MusicSpec(BaseModel):
    path: Optional[str] = Field(None, description="música aportada por el usuario (relativa al proyecto)")
    generate: bool = Field(True, description="si no hay archivo, sintetiza una base musical local sencilla")
    mood: str = "electronic"
    bpm: float = 120
    volume_db: Optional[float] = None
    fade_in: float = 0.4
    fade_out: float = 1.5
    duck_under_voice: bool = True
    license_note: str = ""


class VoiceSpec(BaseModel):
    enabled: bool = False
    provider: Optional[str] = None  # None = settings.tts.provider
    voice: Optional[str] = None
    language: str = "es"
    path: Optional[str] = Field(None, description="locución grabada por el usuario (sustituye a TTS)")


class SubtitleSpec(BaseModel):
    enabled: bool = False
    source: Literal["voiceover", "transcribe", "file"] = "voiceover"
    file: Optional[str] = None
    style: Literal["minimal", "corporate", "cinematic", "gaming", "dynamic"] = "dynamic"
    language: str = "es"
    highlight_words: list[str] = Field(default_factory=list)
    max_words: int = Field(4, ge=1, le=12)
    font_scale: float = 1.0


class Brand(BaseModel):
    name: str = ""
    logo: Optional[str] = None
    palette: list[str] = Field(default_factory=list)
    website: str = ""
    tagline: str = ""


class ExportSpec(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: float = 30
    format: Literal["mp4", "mov", "webm"] = "mp4"
    crf: Optional[int] = None
    filename: str = "final.mp4"
    preview: bool = True
    letterbox: bool = False


class EditPlan(BaseModel):
    version: int = 1
    project: str
    brief: str = ""
    objective: str = ""
    goal: str = "brand"
    platform: str = "tiktok"
    audience: str = ""
    language: str = "es"
    duration: float = Field(..., gt=0.5)
    aspect: str = "9:16"
    style: str = "tech_dark"
    pacing: str = "medium"
    palette: list[str] = Field(default_factory=list)
    brand: Brand = Field(default_factory=Brand)
    script: list[str] = Field(default_factory=list)
    hook_variants: list[str] = Field(default_factory=list)
    cta: str = ""
    scenes: list[Scene]
    music: MusicSpec = Field(default_factory=MusicSpec)
    voiceover: VoiceSpec = Field(default_factory=VoiceSpec)
    subtitles: SubtitleSpec = Field(default_factory=SubtitleSpec)
    export: ExportSpec = Field(default_factory=ExportSpec)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize(self):
        if not self.scenes:
            raise ValueError("El plan necesita al menos una escena")
        self.retime()
        return self

    def retime(self) -> None:
        """Recalcula los inicios para que las escenas sean contiguas y ajusta la duración total."""
        t = 0.0
        for i, sc in enumerate(self.scenes):
            sc.start = round(t, 3)
            t += sc.duration
            last = i == len(self.scenes) - 1
            if last:
                sc.transition_duration = 0.0 if sc.transition == "cut" else sc.transition_duration
            # una transición no puede durar más que la mitad de las escenas que une
            nxt = self.scenes[i + 1].duration if not last else sc.duration
            sc.transition_duration = round(min(sc.transition_duration, sc.duration / 2, nxt / 2), 3)
        self.duration = round(t, 3)

    def storyboard_rows(self) -> list[dict]:
        rows = []
        for sc in self.scenes:
            rows.append({
                "id": sc.id, "start": sc.start, "end": round(sc.start + sc.duration, 3), "purpose": sc.purpose,
                "source": sc.source.path or sc.source.generator or sc.source.type,
                "text": " / ".join(t.text for t in sc.texts), "voiceover": sc.voiceover or "",
                "motion": sc.motion, "transition": sc.transition if sc is not self.scenes[-1] else "—",
            })
        return rows


def fmt_ts(t: float) -> str:
    m, s = divmod(max(0.0, t), 60)
    return f"{int(m):02d}:{s:05.2f}"
