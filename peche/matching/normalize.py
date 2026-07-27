"""Normalisation de toponymes québécois pour la recherche de plans d'eau.

Unifie la comparaison query ↔ index : accents, abréviations (Ste/Sainte),
ponctuation et tokenisation.
"""

from __future__ import annotations

import re
import unicodedata

# Abréviations courantes dans les requêtes utilisateur.
_ABBREV_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bste\b", "sainte"),
    (r"\bst\b", "saint"),
    (r"\briv\b", "riviere"),
    (r"\br\b", "riviere"),
)

_SEGMENT_RE = re.compile(r"\b([a-e])\)", re.I)
_RIVER_PREFIX_RE = re.compile(
    r"^(riviere|lac|ruisseau|fleuve|etang|reservoir)\s+",
    re.I,
)


def _strip_accents(text: str) -> str:
    s = unicodedata.normalize("NFKD", text)
    return "".join(c for c in s if not unicodedata.combining(c))


def expand_abbreviations(text: str) -> str:
    """Étend Ste → sainte, St → saint, etc."""
    out = text
    for pattern, repl in _ABBREV_REPLACEMENTS:
        out = re.sub(pattern, repl, out, flags=re.I)
    return out


def normalize_search_text(text: str) -> str:
    """Normalise pour comparaison : accents, casse, ponctuation, abréviations."""
    s = _strip_accents(text).lower()
    s = expand_abbreviations(s)
    s = re.sub(r"[-–—']", " ", s)
    s = re.sub(r"[^\w\s)]", " ", s)
    return " ".join(s.split())


def normalize_water_name(text: str) -> str:
    """Normalise un nom de plan d'eau (lac, rivière) pour matching hydro."""
    s = normalize_search_text(text)
    # Retire préfixes génériques pour comparer le corps du nom.
    s = _RIVER_PREFIX_RE.sub("", s).strip()
    return s


def tokenize(text: str) -> list[str]:
    """Tokens significatifs (longueur ≥ 2, hors mots vides)."""
    stop = {"de", "du", "des", "la", "le", "les", "et", "au", "en", "un", "une"}
    norm = normalize_search_text(text)
    return [t for t in norm.split() if len(t) >= 2 and t not in stop]


def extract_segment_label(nom: str) -> str | None:
    """Extrait le libellé de segment RegPec (ex. « b) ») depuis le nom brut."""
    m = _SEGMENT_RE.search(nom)
    return f"{m.group(1).lower()})" if m else None


def extract_river_base_name(nom: str) -> str:
    """Nom de base d'une rivière/lac sans segment ni coords.

    Ex. « Rivière Sainte-Marguerite b) entre un point » → « Rivière Sainte-Marguerite »
    """
    base = nom.split("(")[0].strip()
    base = _SEGMENT_RE.sub("", base).strip()
    for sep in (" entre ", " - ", " à l'exception"):
        if sep in base.lower():
            idx = base.lower().find(sep)
            base = base[:idx].strip()
    return base.strip()


def search_aliases(nom: str, base_name: str | None = None) -> list[str]:
    """Variantes de recherche pour un plan d'eau."""
    base = base_name or extract_river_base_name(nom)
    aliases: set[str] = set()
    for candidate in (nom, base):
        norm = normalize_search_text(candidate)
        if norm:
            aliases.add(norm)
        # Variante sans préfixe rivière/lac
        stripped = _RIVER_PREFIX_RE.sub("", norm).strip()
        if stripped:
            aliases.add(stripped)
        # Ste- / Sainte- pour noms composés
        for word in stripped.split():
            if word.startswith("sainte") and len(word) > 5:
                aliases.add("ste " + word[5:])
            if word.startswith("saint") and len(word) > 5:
                aliases.add("st " + word[5:])
    return sorted(aliases)


def token_jaccard(a: str, b: str) -> float:
    """Score Jaccard sur tokens normalisés."""
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0
