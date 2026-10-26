"""Búsqueda de recursos: biblioteca local y, opcionalmente, Pexels (licencia Pexels).

Antes de descargar se exige permiso de red y se guarda la procedencia (autor,
URL, licencia) en project.json. No se usa ninguna fuente sin integración real.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .integrations import PermissionDenied, require_permission
from .media_manager import AUDIO_EXT, IMAGE_EXT, VIDEO_EXT
from .project_manager import Project, slugify


@dataclass
class AssetHit:
    title: str
    kind: str
    path: str | None = None       # local
    url: str | None = None        # remoto (descarga directa)
    page_url: str = ""
    author: str = ""
    license: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    score: float = 0.0


def search_local(query: str, dirs: list[str | Path], kind: str | None = None) -> list[AssetHit]:
    """Busca por nombre de archivo y por un `tags.json` opcional ({"archivo": ["etiqueta", ...]}) en cada carpeta."""
    terms = [t for t in re.split(r"\W+", query.lower()) if len(t) > 2]
    exts = {"video": VIDEO_EXT, "image": IMAGE_EXT, "audio": AUDIO_EXT}.get(kind or "", VIDEO_EXT | IMAGE_EXT | AUDIO_EXT)
    hits = []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        tags = {}
        tf = d / "tags.json"
        if tf.exists():
            tags = json.loads(tf.read_text(encoding="utf-8"))
        for p in d.rglob("*"):
            if p.suffix.lower() not in exts:
                continue
            hay = (p.stem.lower().replace("-", " ").replace("_", " ") + " " + " ".join(tags.get(p.name, []))).lower()
            score = sum(1 for t in terms if t in hay)
            if score or not terms:
                k = "video" if p.suffix.lower() in VIDEO_EXT else "image" if p.suffix.lower() in IMAGE_EXT else "audio"
                hits.append(AssetHit(p.stem, k, path=str(p), license="aportado por el usuario", score=score))
    return sorted(hits, key=lambda h: -h.score)


def search_pexels(query: str, settings: dict, kind: str = "video", orientation: str = "portrait", per_page: int = 8,
                  opener=urllib.request.urlopen) -> list[AssetHit]:
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise PermissionDenied("Falta PEXELS_API_KEY (gratuita en https://www.pexels.com/api/)")
    require_permission(settings, "búsqueda en Pexels", network=True)
    base = "https://api.pexels.com/videos/search" if kind == "video" else "https://api.pexels.com/v1/search"
    url = f"{base}?{urllib.parse.urlencode({'query': query, 'orientation': orientation, 'per_page': per_page})}"
    req = urllib.request.Request(url, headers={"Authorization": key, "User-Agent": "ai-video-marketing-agent"})
    with opener(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    hits = []
    if kind == "video":
        for v in data.get("videos", []):
            files = sorted([f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"],
                           key=lambda f: abs((f.get("height") or 0) - 1920))
            if not files:
                continue
            f = files[0]
            hits.append(AssetHit(f"pexels-{v['id']}", "video", url=f["link"], page_url=v.get("url", ""),
                                 author=v.get("user", {}).get("name", ""), license="Pexels License (https://www.pexels.com/license/)",
                                 width=f.get("width") or 0, height=f.get("height") or 0, duration=float(v.get("duration") or 0)))
    else:
        for ph in data.get("photos", []):
            hits.append(AssetHit(f"pexels-{ph['id']}", "image", url=ph["src"]["original"], page_url=ph.get("url", ""),
                                 author=ph.get("photographer", ""), license="Pexels License (https://www.pexels.com/license/)",
                                 width=ph.get("width", 0), height=ph.get("height", 0)))
    return hits


def download(hit: AssetHit, project: Project, settings: dict, opener=urllib.request.urlopen) -> str:
    """Descarga un recurso remoto al proyecto y registra su licencia y procedencia."""
    if not hit.url:
        raise ValueError("El recurso no tiene URL de descarga")
    require_permission(settings, f"descarga de {hit.title}", network=True)
    ext = ".mp4" if hit.kind == "video" else Path(urllib.parse.urlparse(hit.url).path).suffix or ".jpg"
    dest = project.dir("assets") / "stock" / f"{slugify(hit.title)}{ext}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    max_mb = settings["limits"].get("max_input_file_mb", 4096)
    with opener(urllib.request.Request(hit.url, headers={"User-Agent": "ai-video-marketing-agent"}), timeout=120) as resp:
        data = resp.read(int(max_mb * 1e6) + 1)
    if len(data) > max_mb * 1e6:
        raise ValueError("El recurso supera limits.max_input_file_mb")
    dest.write_bytes(data)
    rel = project.rel(dest)
    project.add_provenance(rel, "pexels", hit.license, url=hit.page_url, author=hit.author)
    return rel
