"""Detección real de capacidades del entorno y control de permisos.

`doctor()` comprueba qué herramientas y proveedores están disponibles de verdad
(no presupone acceso a ninguna API). `require_permission()` es la única puerta
de salida para cualquier acción con coste o que envíe datos fuera del equipo.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path

from . import ff
from .motion_graphics import font_for

REQUIRED_FILTERS = ["xfade", "acrossfade", "zoompan", "overlay", "ass", "loudnorm", "sidechaincompress",
                    "blackdetect", "silencedetect", "freezedetect", "ebur128", "amix", "adelay"]

PROVIDERS = {
    "openai_tts": {"env": "OPENAI_API_KEY", "paid": True, "uploads": False,
                   "docs": "https://platform.openai.com/api-keys", "use": "Voz en off natural (tts.provider: openai)"},
    "pexels": {"env": "PEXELS_API_KEY", "paid": False, "uploads": False,
               "docs": "https://www.pexels.com/api/", "use": "Búsqueda de vídeos/fotos de stock con licencia Pexels"},
}


class PermissionDenied(RuntimeError):
    pass


def require_permission(settings: dict, action: str, *, paid: bool = False, upload: bool = False, network: bool = False,
                       est_cost: float = 0.0) -> None:
    perms, limits = settings["permissions"], settings["limits"]
    if paid and not perms.get("allow_paid_apis"):
        raise PermissionDenied(f"'{action}' tiene coste. Pide autorización al usuario y activa permissions.allow_paid_apis.")
    if est_cost > float(limits.get("max_estimated_cost_usd", 0)):
        raise PermissionDenied(f"'{action}' costaría ~{est_cost:.3f} USD, por encima de limits.max_estimated_cost_usd.")
    if upload and not perms.get("allow_external_uploads"):
        raise PermissionDenied(f"'{action}' enviaría material a un servicio externo. Requiere permissions.allow_external_uploads.")
    if network and not perms.get("allow_network_asset_search"):
        raise PermissionDenied(f"'{action}' usa Internet. Requiere permissions.allow_network_asset_search.")


def _whisper_status(settings: dict) -> tuple[bool, str]:
    if not importlib.util.find_spec("faster_whisper"):
        return False, "faster-whisper no instalado (pip install -e '.[transcribe]')"
    model = settings["transcription"]["model"]
    if Path(model).is_dir():
        return True, f"modelo local {model}"
    cache = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    cached = any(cache.glob(f"models--*faster-whisper-{model}*")) if cache.exists() else False
    return True, f"modelo '{model}' {'en caché' if cached else 'se descargará de huggingface.co en el primer uso'}"


def doctor(settings: dict) -> dict:
    report: dict = {"tools": {}, "providers": {}, "permissions": settings["permissions"], "missing": []}
    for b in ["ffmpeg", "ffprobe", "fc-match", "espeak-ng"]:
        report["tools"][b] = bool(shutil.which(b))
    if report["tools"]["ffmpeg"]:
        filters = ff.available_filters()
        missing = [f for f in REQUIRED_FILTERS if f not in filters]
        report["tools"]["ffmpeg_filters_missing"] = missing
        report["tools"]["libx264"] = "libx264" in ff.available_encoders()
        report["tools"]["ffmpeg_version"] = ff.run(["ffmpeg", "-version"]).stdout.splitlines()[0]
        if missing:
            report["missing"].append(f"FFmpeg sin filtros: {', '.join(missing)} (instala una compilación completa)")
        if not report["tools"]["libx264"]:
            report["missing"].append("FFmpeg sin libx264")
    else:
        report["missing"].append("FFmpeg (obligatorio)")
    ok, msg = _whisper_status(settings)
    report["providers"]["transcription"] = {"available": ok, "detail": msg}
    if not ok:
        report["missing"].append("Transcripción: " + msg)
    report["providers"]["tts_espeak"] = {"available": report["tools"]["espeak-ng"], "detail": "voz local gratuita"}
    if not report["tools"]["espeak-ng"]:
        report["missing"].append("espeak-ng (voz en off local)")
    for name, p in PROVIDERS.items():
        has_key = bool(os.environ.get(p["env"]))
        report["providers"][name] = {"configured": has_key, "env": p["env"], "paid": p["paid"], "docs": p["docs"], "use": p["use"]}
    report["providers"]["moviepy"] = {"installed": bool(importlib.util.find_spec("moviepy")),
                                      "detail": "opcional; el motor implementado es FFmpeg"}
    f = font_for("title", settings)
    report["tools"]["title_font"] = f.file if f else None
    return report
