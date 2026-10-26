"""Carga de configuración (YAML) y localización de recursos del paquete."""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent


def resource_dir(name: str) -> Path:
    """Devuelve el directorio `config` o `templates`.

    Orden de búsqueda: $VIDEO_AGENT_HOME/<name>, el repositorio clonado
    (instalación editable o ejecución desde el código fuente) y la copia
    empaquetada dentro de la rueda (`video_agent/_resources/<name>`).
    """
    candidates = []
    if os.environ.get("VIDEO_AGENT_HOME"):
        candidates.append(Path(os.environ["VIDEO_AGENT_HOME"]) / name)
    candidates.append(PACKAGE_DIR.parents[1] / name)
    candidates.append(PACKAGE_DIR / "_resources" / name)
    for c in candidates:
        if c.is_dir():
            return c
    raise FileNotFoundError(f"No se encuentra el directorio de recursos '{name}' (buscado en {candidates})")


@lru_cache(maxsize=None)
def load_yaml(relpath: str, base: str = "config") -> dict[str, Any]:
    path = resource_dir(base) / relpath
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_dotenv(path: str | Path = ".env") -> None:
    """Carga variables de un archivo .env local sin sobrescribir las ya definidas."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def load_settings(override_path: str | Path | None = None, overrides: dict | None = None) -> dict[str, Any]:
    """Configuración efectiva: settings.yaml + video-agent.yaml local + overrides (+ variables de .env)."""
    load_dotenv(Path.cwd() / ".env")
    settings = copy.deepcopy(load_yaml("settings.yaml"))
    paths = [override_path, os.environ.get("VIDEO_AGENT_SETTINGS"), Path.cwd() / "video-agent.yaml"]
    for p in paths:
        if p and Path(p).is_file():
            with open(p, encoding="utf-8") as fh:
                settings = deep_merge(settings, yaml.safe_load(fh) or {})
            break
    if os.environ.get("VIDEO_AGENT_WHISPER_MODEL"):
        settings["transcription"]["model"] = os.environ["VIDEO_AGENT_WHISPER_MODEL"]
    if overrides:
        settings = deep_merge(settings, overrides)
    return settings


def platforms() -> dict[str, Any]:
    return load_yaml("platforms.yaml")


def styles() -> dict[str, Any]:
    return load_yaml("editing_presets.yaml")["styles"]


def style_keywords() -> dict[str, list[str]]:
    return load_yaml("editing_presets.yaml").get("style_keywords", {})


def goals() -> dict[str, Any]:
    return load_yaml("marketing.yaml")["goals"]


def template(relpath: str) -> dict[str, Any]:
    return load_yaml(relpath, base="templates")
