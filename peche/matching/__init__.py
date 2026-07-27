"""Recherche et normalisation de toponymes (plans d'eau RegPec)."""

from peche.matching.normalize import (
    expand_abbreviations,
    extract_river_base_name,
    extract_segment_label,
    normalize_search_text,
    search_aliases,
    tokenize,
)

__all__ = [
    "expand_abbreviations",
    "extract_river_base_name",
    "extract_segment_label",
    "normalize_search_text",
    "search_aliases",
    "tokenize",
]
