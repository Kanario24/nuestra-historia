"""Lógica de marketing: objetivo, mensajes, ganchos y llamada a la acción.

Genera un texto base coherente con el objetivo. El agente (Claude) debe
reescribirlo con el contexto real de la marca antes de renderizar; este módulo
garantiza que siempre exista una estructura de mensaje completa.
"""
from __future__ import annotations

import re
import unicodedata

from . import config


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def keyword_hits(text: str, keywords: list[str]) -> int:
    """Cuenta coincidencias de palabras clave como inicio de palabra (completas si tienen ≤3 letras)."""
    folded = _fold(text)
    hits = 0
    for k in keywords:
        k = _fold(k).strip()
        if not k:
            continue
        pat = rf"\b{re.escape(k)}\b" if len(k) <= 3 else rf"\b{re.escape(k)}"
        hits += len(re.findall(pat, folded))
    return hits


def detect_goal(brief: str, default: str = "brand") -> str:
    best, best_score = default, 0
    for key, g in config.goals().items():
        score = keyword_hits(brief, g.get("keywords", []))
        if score > best_score:
            best, best_score = key, score
    return best


def detect_language(brief: str) -> str:
    t = f" {_fold(brief)} "
    es = sum(t.count(w) for w in [" de ", " para ", " que ", " un ", " una ", " video ", " con ", " mi ", " quiero ", " el ", " la "])
    en = sum(t.count(w) for w in [" the ", " for ", " with ", " my ", " want ", " video ", " a ", " an ", " and "])
    return "es" if es >= en else "en"


def copy_for(goal: str, brand: str, language: str = "es") -> dict:
    goals = config.goals()
    g = goals.get(goal) or goals["brand"]
    block = g.get(language) or g.get("es")
    name = brand or ("tu marca" if language == "es" else "your brand")
    fill = lambda s: s.replace("{brand}", name)
    return {
        "hooks": [fill(h) for h in block["hooks"]],
        "problem": fill(block["problem"]),
        "solution": fill(block["solution"]),
        "benefits": [fill(b) for b in block["benefits"]],
        "cta": fill(block["cta"]),
        "label": g.get("label", goal),
    }


HOOK_ANGLES_ES = [
    "¿Y si {x}?", "Nadie te cuenta esto sobre {x}", "3 razones para elegir {x}", "Deja de perder tiempo: {x}",
    "Esto es {x}", "Antes vs. después de {x}",
]
HOOK_ANGLES_EN = [
    "What if {x}?", "Nobody tells you this about {x}", "3 reasons to choose {x}", "Stop wasting time: {x}",
    "This is {x}", "Before vs. after {x}",
]


def hook_variants(base_hooks: list[str], brand: str, language: str, count: int) -> list[str]:
    """Ganchos alternativos con ángulos distintos (pregunta, curiosidad, lista, dolor, marca, contraste)."""
    angles = HOOK_ANGLES_ES if language == "es" else HOOK_ANGLES_EN
    x = brand or ("tu negocio" if language == "es" else "your business")
    pool = list(dict.fromkeys(base_hooks + [a.format(x=x) for a in angles]))
    return pool[:count]


def extract_keywords(texts: list[str], brand: str = "") -> list[str]:
    """Palabras a resaltar: la marca y términos con mayúscula o cifras."""
    words = set(brand.split()) if brand else set()
    for t in texts:
        for w in re.findall(r"\b[\wÁÉÍÓÚÑáéíóúñ%+]+\b", t):
            if re.search(r"\d", w) or (w[:1].isupper() and len(w) > 3 and not t.startswith(w)):
                words.add(w)
    return sorted(words)
