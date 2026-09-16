"""Index guide poisson — lookup par zone + nom ou proximité."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

from peche.matching.normalize import normalize_search_text, token_jaccard
from peche.reglements.sync import DATA_DIR

INDEX_PATH = DATA_DIR / "guide_poisson" / "index.json"
GUIDE_URL = (
    "https://www.donneesquebec.ca/recherche/dataset/"
    "guide-de-consommation-du-poisson-de-peche-sportive-en-eau-douce"
)
MELCCFP_FALLBACK = (
    "https://www.environnement.gouv.qc.ca/eau/poisson/guide_consommation/index.htm"
)

MAX_DISTANCE_KM = 10.0


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


@lru_cache(maxsize=1)
def load_index() -> dict[str, Any] | None:
    if not INDEX_PATH.exists():
        return None
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def lookup_guide_poisson(
    *,
    zone_id: int | None = None,
    nom: str | None = None,
    lon: float | None = None,
    lat: float | None = None,
) -> dict[str, Any]:
    """Retourne site + espèces ou message + lien officiel."""
    idx = load_index()
    base = {
        "guide_url": (idx or {}).get("guide_url") or MELCCFP_FALLBACK,
        "source_url": (idx or {}).get("source_url"),
    }
    if not idx:
        return {
            **base,
            "species": [],
            "message": "Index guide poisson absent — lancer peche.guide_poisson sync.",
        }

    sites: list[dict[str, Any]] = idx.get("sites") or []
    if zone_id is not None:
        sites = [s for s in sites if s.get("zone_id") == zone_id]

    if not sites:
        return {
            **base,
            "species": [],
            "message": "Aucun site du guide dans cette zone.",
        }

    species_by_site: dict[str, list[dict[str, Any]]] = idx.get("species_by_site") or {}
    chosen: dict[str, Any] | None = None

    if nom and nom.strip():
        q = normalize_search_text(nom)
        best_score = 0.0
        for site in sites:
            score = max(
                token_jaccard(q, site.get("nom_norm") or ""),
                token_jaccard(q, site.get("nom") or ""),
            )
            if score > best_score:
                best_score = score
                chosen = site
        if chosen is None or best_score < 0.35:
            chosen = None

    if chosen is None and lon is not None and lat is not None:
        nearest: tuple[float, dict[str, Any]] | None = None
        for site in sites:
            slon, slat = site.get("lon"), site.get("lat")
            if slon is None or slat is None:
                continue
            dist = _haversine_km(lon, lat, float(slon), float(slat))
            if dist <= MAX_DISTANCE_KM and (nearest is None or dist < nearest[0]):
                nearest = (dist, site)
        if nearest:
            chosen = nearest[1]

    if chosen is None and nom and nom.strip():
        return {
            **base,
            "species": [],
            "message": f"Aucun site du guide ne correspond à « {nom.strip()} ».",
        }

    if chosen is None:
        return {
            **base,
            "species": [],
            "message": "Précisez un nom de plan d'eau ou des coordonnées.",
        }

    sid = str(chosen.get("id"))
    return {
        **base,
        "site": {
            "id": sid,
            "nom": chosen.get("nom"),
            "zone_id": chosen.get("zone_id"),
            "lon": chosen.get("lon"),
            "lat": chosen.get("lat"),
            "bassin": chosen.get("bassin"),
        },
        "species": species_by_site.get(sid, []),
    }
