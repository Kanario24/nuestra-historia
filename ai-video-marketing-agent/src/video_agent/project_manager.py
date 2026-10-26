"""Estructura de carpetas de cada proyecto y persistencia en project.json."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from .models import EditPlan

SUBDIRS = ["input", "assets", "audio", "subtitles", "storyboard", "timeline", "previews", "exports", "reports", "cache"]


def slugify(text: str, max_len: int = 48) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:max_len].strip("-")) or "proyecto"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while b := fh.read(chunk):
            h.update(b)
    return h.hexdigest()


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


class Project:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.data: dict[str, Any] = {}
        if self.file.exists():
            self.data = json.loads(self.file.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ rutas
    @property
    def file(self) -> Path:
        return self.root / "project.json"

    def dir(self, name: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def rel(self, path: str | Path) -> str:
        p = Path(path).resolve()
        try:
            return p.relative_to(self.root).as_posix()
        except ValueError:
            return str(p)

    def abs(self, rel: str | Path) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    @property
    def name(self) -> str:
        return self.data.get("name", self.root.name)

    # ------------------------------------------------------------ creación
    @classmethod
    def create(cls, name: str, projects_dir: str | Path = "projects", unique: bool = True) -> "Project":
        base = Path(projects_dir)
        slug = slugify(name)
        root = base / slug
        if unique:
            i = 2
            while (root / "project.json").exists():
                root = base / f"{slug}-{i}"
                i += 1
        for sd in SUBDIRS:
            (root / sd).mkdir(parents=True, exist_ok=True)
        p = cls(root)
        p.data = {"name": root.name, "created": now(), "updated": now(), "inputs": [], "provenance": [],
                  "attempts": [], "deliverables": {}, "plan": None}
        p.save()
        return p

    @classmethod
    def open(cls, path: str | Path) -> "Project":
        path = Path(path)
        if path.is_file() and path.name == "project.json":
            path = path.parent
        if not (path / "project.json").exists():
            raise FileNotFoundError(f"No hay project.json en {path}")
        p = cls(path)
        for sd in SUBDIRS:
            (p.root / sd).mkdir(exist_ok=True)
        return p

    def save(self) -> None:
        self.data["updated"] = now()
        tmp = self.file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.file)

    # --------------------------------------------------------------- material
    def import_file(self, src: str | Path, kind: str = "input", copy: bool = True, max_mb: float | None = None) -> str:
        """Copia un archivo del usuario al proyecto (nunca modifica el original)."""
        src = Path(src).expanduser().resolve()
        if not src.is_file():
            raise FileNotFoundError(f"No existe el archivo: {src}")
        size_mb = src.stat().st_size / 1e6
        if max_mb and size_mb > max_mb:
            raise ValueError(f"{src.name} ocupa {size_mb:.0f} MB, por encima del límite configurado ({max_mb} MB)")
        digest = sha256_file(src)
        for item in self.data.get("inputs", []):
            if item["sha256"] == digest:
                return item["path"]  # ya importado (o duplicado exacto)
        dest_dir = self.dir("input" if kind == "input" else "assets")
        stem = slugify(src.stem, 40)
        dest = dest_dir / f"{stem}{src.suffix.lower()}"
        i = 2
        while dest.exists():
            dest = dest_dir / f"{stem}-{i}{src.suffix.lower()}"
            i += 1
        if copy:
            shutil.copy2(src, dest)
        else:
            dest.symlink_to(src)
        rel = self.rel(dest)
        self.data.setdefault("inputs", []).append({
            "path": rel, "original": str(src), "sha256": digest, "kind": kind, "imported": now()})
        self.save()
        return rel

    def add_provenance(self, path: str, source: str, license: str, url: str = "", author: str = "", note: str = "") -> None:
        self.data.setdefault("provenance", []).append({
            "path": path, "source": source, "license": license, "url": url, "author": author, "note": note, "added": now()})
        self.save()

    # ------------------------------------------------------------------ plan
    def save_plan(self, plan: EditPlan) -> None:
        self.data["plan"] = plan.model_dump(mode="json")
        self.save()

    def load_plan(self) -> EditPlan:
        if not self.data.get("plan"):
            raise ValueError(f"El proyecto {self.root} no tiene plan de edición")
        return EditPlan.model_validate(self.data["plan"])

    def log_attempt(self, entry: dict) -> None:
        entry = {"time": now(), **entry}
        self.data.setdefault("attempts", []).append(entry)
        self.save()

    def set_deliverables(self, items: dict[str, Any]) -> None:
        self.data["deliverables"] = items
        self.save()
