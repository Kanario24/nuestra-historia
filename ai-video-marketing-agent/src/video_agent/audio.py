"""Audio: música (aportada o sintetizada localmente), voz en off (TTS), efectos y análisis.

- La música sintetizada es una base sencilla generada con FFmpeg (aevalsrc),
  libre de derechos, pensada como recurso local cuando no se aporta música.
- La voz local usa espeak-ng (gratuita, sonido robótico). Para voces naturales
  se puede configurar un proveedor de pago (OpenAI) que requiere permiso explícito.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import ff

log = logging.getLogger("video_agent")

# ----------------------------------------------------------------- música

PROGRESSIONS = {  # raíces (Hz) de una progresión de 4 compases
    "electronic": [110.0, 87.31, 130.81, 98.0],     # Am F C G
    "gaming": [110.0, 130.81, 98.0, 87.31],
    "corporate": [130.81, 98.0, 110.0, 87.31],      # C G Am F
    "cinematic": [73.42, 58.27, 87.31, 65.41],      # Dm Bb F C (graves)
    "chill": [87.31, 110.0, 73.42, 98.0],
}


def _music_expr(mood: str, bpm: float) -> str:
    B = 60.0 / bpm
    roots = PROGRESSIONS.get(mood, PROGRESSIONS["electronic"])
    bar = 4 * B
    root = (f"if(lt(mod(t,{4*bar:.5f}),{bar:.5f}),{roots[0]},if(lt(mod(t,{4*bar:.5f}),{2*bar:.5f}),{roots[1]},"
            f"if(lt(mod(t,{4*bar:.5f}),{3*bar:.5f}),{roots[2]},{roots[3]})))")
    beat = f"mod(t,{B:.5f})"
    kick = "0.85*sin(2*PI*(45+110*exp(-28*ld(1)))*ld(1))*exp(-8*ld(1))"
    hat = f"0.10*(random(0)*2-1)*exp(-70*mod(t+{B/2:.5f},{B:.5f}))"
    duck = "(1-0.55*exp(-9*ld(1)))"
    bass = f"0.24*sin(2*PI*ld(0)*t)*(0.55+0.45*exp(-7*mod(t,{B/2:.5f})))*{duck}"
    pad = "0.07*(sin(2*PI*ld(0)*2*t)+sin(2*PI*ld(0)*2.378*t)+sin(2*PI*ld(0)*3*t))*(0.75+0.25*sin(2*PI*0.21*t))"
    arp_note = f"if(lt(mod(t,{B:.5f}),{B/4:.5f}),2,if(lt(mod(t,{B:.5f}),{B/2:.5f}),3,if(lt(mod(t,{B:.5f}),{3*B/4:.5f}),2.378,4)))"
    pluck = f"0.09*sin(2*PI*ld(0)*2*{arp_note}*t)*exp(-14*mod(t,{B/4:.5f}))"
    boom = f"0.6*sin(2*PI*42*mod(t,{2*bar:.5f}))*exp(-2.2*mod(t,{2*bar:.5f}))"
    if mood == "cinematic":
        body = f"{pad}*1.8+{boom}+0.05*sin(2*PI*ld(0)*4*t)*(0.5+0.5*sin(2*PI*t/{B:.5f}))"
    elif mood == "corporate":
        body = f"0.5*{kick}+{pluck}+{pad}+0.6*{bass}"
    elif mood == "chill":
        body = f"0.45*{kick}+{pluck}*0.8+{pad}*1.3"
    elif mood == "gaming":
        body = f"{kick}+{hat}*1.3+{bass}+{pluck}*1.2+{pad}*0.8"
    else:
        body = f"{kick}+{hat}+{bass}+{pad}+{pluck}*0.6"
    return f"st(0,{root});st(1,{beat});{body}"


def synth_music(out: Path, duration: float, mood: str = "electronic", bpm: float = 120, sample_rate: int = 48000) -> Path:
    """Sintetiza una base musical simple y libre de derechos con FFmpeg."""
    expr = _music_expr(mood, bpm)
    fade_out = min(2.0, duration / 4)
    out.parent.mkdir(parents=True, exist_ok=True)
    ff.ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':s={sample_rate}:d={duration + 0.5:.3f}",
              "-af", f"highpass=f=30,lowpass=f=11000,aecho=0.8:0.5:45|90:0.18|0.10,"
                     f"afade=t=in:d=0.3,afade=t=out:st={max(0, duration - fade_out):.3f}:d={fade_out:.3f},"
                     f"alimiter=limit=0.8,aformat=channel_layouts=stereo",
              "-t", f"{duration:.3f}", "-ar", str(sample_rate), "-c:a", "pcm_s16le", out)
    return out


def synth_sfx(kind: str, out: Path, sample_rate: int = 48000) -> Path:
    """Efectos de sonido sintéticos sencillos: whoosh, hit, rise, click."""
    specs = {
        "whoosh": ("(random(0)*2-1)*pow(sin(PI*t/0.45),2)", 0.45, "highpass=f=600,lowpass=f=6000,volume=0.6"),
        "hit": ("0.9*sin(2*PI*55*t)*exp(-7*t)+0.3*(random(0)*2-1)*exp(-40*t)", 0.6, "lowpass=f=4000"),
        "rise": ("(random(0)*2-1)*pow(t/1.0,2)", 1.0, "highpass=f=1200,lowpass=f=9000,volume=0.5"),
        "click": ("0.8*sin(2*PI*2000*t)*exp(-300*t)", 0.05, "anull"),
    }
    expr, dur, af = specs[kind]
    out.parent.mkdir(parents=True, exist_ok=True)
    ff.ffmpeg("-f", "lavfi", "-i", f"aevalsrc='{expr}':s={sample_rate}:d={dur}", "-af", f"{af},aformat=channel_layouts=stereo",
              "-c:a", "pcm_s16le", out)
    return out


def estimate_bpm(path: Path, max_seconds: float = 60) -> float | None:
    """Estimación aproximada del tempo (autocorrelación de la envolvente de energía)."""
    sr = 11025
    raw = subprocess.run(["ffmpeg", "-v", "error", "-t", str(max_seconds), "-i", str(path), "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32)
    if x.size < sr * 4:
        return None
    hop = 256
    frames = x[: x.size // hop * hop].reshape(-1, hop)
    env = np.sqrt((frames ** 2).mean(axis=1))
    onset = np.maximum(0, np.diff(env))
    onset -= onset.mean()
    ac = np.correlate(onset, onset, mode="full")[onset.size - 1:]
    fps = sr / hop
    lags = np.arange(int(fps * 60 / 180), int(fps * 60 / 70))
    if lags.size == 0 or lags[-1] >= ac.size:
        return None
    best = lags[np.argmax(ac[lags])]
    return round(60 * fps / best, 1)


def measure_loudness(path: Path) -> dict | None:
    """Sonoridad integrada (LUFS) y pico verdadero mediante el filtro ebur128."""
    proc = ff.ffmpeg("-i", path, "-vn", "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-", check=False)
    txt = proc.stderr
    m_i = re.findall(r"I:\s+(-?[\d.]+|-inf) LUFS", txt)
    m_p = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", txt)
    if not m_i:
        return None
    to_f = lambda s: float("-inf") if s == "-inf" else float(s)
    return {"integrated_lufs": to_f(m_i[-1]), "true_peak_db": to_f(m_p[-1]) if m_p else None}


def audio_duration(path: Path) -> float:
    info = ff.probe(path)
    return info.audio_duration or info.duration


# --------------------------------------------------------------------- TTS

class ProviderUnavailable(RuntimeError):
    pass


class PermissionDenied(RuntimeError):
    pass


ESPEAK_LANG = {"es": "es", "en": "en-us", "pt": "pt", "fr": "fr", "it": "it", "de": "de"}


def tts_espeak(text: str, out: Path, language: str = "es", voice: str | None = None, speed: int = 165, pitch: int = 45) -> Path:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise ProviderUnavailable("espeak-ng no está instalado (apt install espeak-ng / brew install espeak-ng)")
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".raw.wav")
    v = voice or ESPEAK_LANG.get(language, language)
    subprocess.run([exe, "-v", v, "-s", str(speed), "-p", str(pitch), "-w", str(raw), text], check=True, capture_output=True)
    # limpieza: recorte de silencios, ecualización suave y 48 kHz estéreo
    ff.ffmpeg("-i", raw, "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
              "silenceremove=start_periods=1:start_threshold=-50dB,areverse,highpass=f=80,"
              "equalizer=f=3000:t=q:w=1:g=3,aformat=sample_rates=48000:channel_layouts=stereo", "-c:a", "pcm_s16le", out)
    raw.unlink(missing_ok=True)
    return out


def tts_openai(text: str, out: Path, settings: dict, voice: str | None = None) -> Path:
    """Voz con la API de OpenAI (de pago). Requiere OPENAI_API_KEY y permiso allow_paid_apis."""
    perms, limits = settings["permissions"], settings["limits"]
    cfg = settings["tts"]["openai"]
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ProviderUnavailable("Falta la variable de entorno OPENAI_API_KEY")
    if not perms.get("allow_paid_apis"):
        raise PermissionDenied("El TTS de OpenAI tiene coste: activa permissions.allow_paid_apis tras la autorización del usuario")
    cost = len(text) / 1000 * float(cfg.get("usd_per_1k_chars", 0.015))
    if cost > float(limits.get("max_estimated_cost_usd", 0)):
        raise PermissionDenied(f"Coste estimado {cost:.4f} USD supera limits.max_estimated_cost_usd")
    body = json.dumps({"model": cfg["model"], "voice": voice or cfg["voice"], "input": text, "response_format": "wav"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".api.wav")
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw.write_bytes(resp.read())
    ff.ffmpeg("-i", raw, "-af", "aformat=sample_rates=48000:channel_layouts=stereo", "-c:a", "pcm_s16le", out)
    raw.unlink(missing_ok=True)
    return out


def synthesize_speech(text: str, out: Path, settings: dict, language: str = "es", provider: str | None = None,
                      voice: str | None = None) -> Path:
    provider = provider or settings["tts"]["provider"]
    if provider == "espeak":
        cfg = settings["tts"].get("espeak", {})
        return tts_espeak(text, out, language, voice, cfg.get("speed_wpm", 165), cfg.get("pitch", 45))
    if provider == "openai":
        return tts_openai(text, out, settings, voice)
    raise ProviderUnavailable(f"Proveedor TTS desconocido: {provider}")


@dataclass
class VoiceLine:
    scene_id: str
    text: str
    start: float
    end: float
    path: Path
    tempo: float = 1.0


def build_voiceover_track(lines: list[tuple[str, str, float, float]], out_dir: Path, total: float, settings: dict,
                          language: str = "es", provider: str | None = None, voice: str | None = None,
                          lead_in: float = 0.15) -> tuple[Path, list[VoiceLine], list[str]]:
    """Genera una pista de voz con cada frase colocada al inicio de su escena.

    lines: (scene_id, texto, inicio_escena, duración_escena). Si una frase no
    cabe en su escena se acelera hasta x1.3; si aun así no cabe, se avisa.
    """
    warnings: list[str] = []
    placed: list[VoiceLine] = []
    for i, (sid, text, start, dur) in enumerate(lines):
        if not text.strip():
            continue
        p = synthesize_speech(text, out_dir / f"vo_{i:02d}_{sid}.wav", settings, language, provider, voice)
        d = audio_duration(p)
        avail = max(0.5, dur - lead_in - 0.1)
        tempo = 1.0
        if d > avail:
            tempo = min(1.3, d / avail)
            if d / tempo > avail + 0.05:
                warnings.append(f"La locución de la escena {sid} dura {d:.1f}s y no cabe en {dur:.1f}s; acorta el texto o alarga la escena")
            if tempo > 1.01:
                fast = p.with_name(p.stem + "_fast.wav")
                ff.ffmpeg("-i", p, "-af", f"atempo={tempo:.3f}", "-c:a", "pcm_s16le", fast)
                p = fast
                d = d / tempo
        placed.append(VoiceLine(sid, text, start + lead_in, start + lead_in + d, p, tempo))
    track = out_dir / "voiceover.wav"
    if not placed:
        raise ValueError("No hay textos de locución")
    args: list[str] = []
    for vl in placed:
        args += ["-i", str(vl.path)]
    chains = [f"[{i}:a]adelay={int(vl.start * 1000)}:all=1[v{i}]" for i, vl in enumerate(placed)]
    mix = "".join(f"[v{i}]" for i in range(len(placed)))
    fc = ";".join(chains) + f";{mix}amix=inputs={len(placed)}:normalize=0:dropout_transition=0,apad,atrim=0:{total:.3f}[out]"
    ff.ffmpeg(*args, "-filter_complex", fc, "-map", "[out]", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", track)
    return track, placed, warnings


def prepare_music(src: Path, out: Path, duration: float, fade_in: float = 0.4, fade_out: float = 1.5) -> Path:
    """Ajusta la música del usuario: bucle si es corta, recorte y fundidos."""
    fo = min(fade_out, duration / 3)
    ff.ffmpeg("-stream_loop", "-1", "-i", src, "-t", f"{duration:.3f}", "-vn",
              "-af", f"afade=t=in:d={fade_in:.3f},afade=t=out:st={max(0, duration - fo):.3f}:d={fo:.3f},"
                     "aformat=sample_rates=48000:channel_layouts=stereo", "-c:a", "pcm_s16le", out)
    return out
