"""Géocodage libre via Nominatim (OpenStreetMap).

Utilisé pour résoudre des noms de lieu qui ne sont pas dans RegPec
(ex. « Laterrière », « Rivière Saguenay à Chicoutimi »). On limite la
recherche au Canada par défaut, on cache les réponses en mémoire, et on
respecte la politique d'usage Nominatim (User-Agent identifiable, < 1 req/s
serait idéal — pour un agent interactif ce sera très en-dessous).
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlencode

from peche.fetch import fetch_text

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "peche-agent/0.1 (+https://example.invalid/)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_TTL_SECONDS = 24 * 3600  # le placement d'une ville bouge peu

_CACHE: dict[str, tuple[float, list[dict]]] = {}


def _cache_get(key: str, ttl: float) -> list[dict] | None:
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    return None


def geocode(
    query: str,
    *,
    country_codes: str = "ca",
    limit: int = 5,
    timeout: float = DEFAULT_TIMEOUT,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> list[dict]:
    """Cherche `query` dans Nominatim, renvoie une liste `[{lat, lon, display_name, type, importance}]`.

    Liste vide si aucun résultat. Les exceptions réseau remontent.
    """
    if not query or not query.strip():
        return []

    key = f"{country_codes}|{limit}|{query.strip().lower()}"
    cached = _cache_get(key, ttl_seconds)
    if cached is not None:
        return cached

    params: dict[str, Any] = {
        "q": query.strip(),
        "format": "json",
        "limit": str(limit),
        "addressdetails": "0",
    }
    if country_codes:
        params["countrycodes"] = country_codes
    url = f"{NOMINATIM_URL}?{urlencode(params)}"

    raw = fetch_text(url, timeout=timeout, user_agent=USER_AGENT)
    data = json.loads(raw)
    out: list[dict] = []
    for item in data:
        try:
            out.append(
                {
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                    "display_name": item.get("display_name", ""),
                    "type": item.get("type", ""),
                    "category": item.get("class", ""),
                    "importance": float(item.get("importance", 0)),
                }
            )
        except (KeyError, ValueError):
            continue
    _CACHE[(key)] = (time.monotonic(), out)
    return out
