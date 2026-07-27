"""Lien RegPec ↔ entités LCE."""

from __future__ import annotations

import json
import math
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

from peche.coords import parse_all_dms, parse_dms, split_name
from peche.hydromet import haversine_km
from peche.matching.normalize import normalize_search_text
from peche.reglements.sync import DATA_DIR, ZONES_DIR
from peche.lce import SPATIAL_DIR as LCE_DIR

MATCHES_PATH = DATA_DIR / "spatial" / "regpec_lce_matches.json"
LOOKUP_PATH = LCE_DIR / "lookup.json"
LOCATIONS_DIR = DATA_DIR / "locations"

MAX_DISTANCE_KM = 2.0
MIN_NAME_SCORE = 0.55


def _name_score(a: str, b: str) -> float:
    na = normalize_search_text(a)
    nb = normalize_search_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.85
    return SequenceMatcher(None, na, nb).ratio()


@lru_cache(maxsize=1)
def _load_lce_lookup() -> list[dict[str, Any]]:
    if not LOOKUP_PATH.exists():
        return []
    return json.loads(LOOKUP_PATH.read_text(encoding="utf-8"))


def _nearest_lce(
    lat: float,
    lon: float,
    *,
    entity_type: str | None = None,
    name_hint: str | None = None,
    radius_km: float = MAX_DISTANCE_KM,
) -> dict[str, Any] | None:
    lookup = _load_lce_lookup()
    best: dict[str, Any] | None = None
    best_score = 0.0
    for entry in lookup:
        if entity_type and entry.get("type") != entity_type:
            continue
        dist = haversine_km(lat, lon, entry["lat"], entry["lon"])
        if dist > radius_km:
            continue
        ns = _name_score(name_hint or "", entry.get("nom") or "") if name_hint else 0.5
        # Favoriser proximité ; bonus nom si disponible
        score = (1.0 - min(dist / radius_km, 1.0)) * 0.6 + ns * 0.4
        if score > best_score:
            best_score = score
            best = {**entry, "distance_km": round(dist, 3), "match_score": round(score, 3)}
    return best


def _segment_points(zone_data: dict, plan: dict) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for seg in plan.get("segments") or []:
        label = seg.get("segment") or ""
        for pair in parse_all_dms(label):
            if pair not in points:
                points.append(pair)
    title_pts = parse_all_dms(plan.get("nom") or "")
    for pair in title_pts:
        if pair not in points:
            points.append(pair)
    return points


def match_plan(
    zone_id: int,
    plan: dict,
    location: dict | None = None,
) -> dict[str, Any] | None:
    plan_id = plan.get("id")
    if plan_id is None:
        return None

    nom = split_name(plan.get("nom") or "")
    lat = location.get("lat") if location else None
    lon = location.get("lon") if location else None
    if lat is None or lon is None:
        coords = parse_dms(plan.get("nom") or "")
        if coords:
            lat, lon = coords["lat"], coords["lon"]

    entity_type = "riviere" if "rivi" in nom.lower() else "lac"
    lce_match = None
    if lat is not None and lon is not None:
        lce_match = _nearest_lce(lat, lon, entity_type=entity_type, name_hint=nom)

    segment_points = _segment_points({}, plan)
    return {
        "zone_id": zone_id,
        "plan_id": plan_id,
        "nom": nom,
        "lat": lat,
        "lon": lon,
        "lce": lce_match,
        "segment_points": segment_points,
    }


def build_matches(
    *,
    zones_dir: Path = ZONES_DIR,
    locations_dir: Path = LOCATIONS_DIR,
    out_path: Path = MATCHES_PATH,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    loc_index: dict[tuple[int, int], dict] = {}
    for path in locations_dir.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        zid = data["meta"]["zone_id"]
        for loc in data.get("locations", []):
            if loc.get("id") is not None:
                loc_index[(zid, loc["id"])] = loc

    for zone_path in sorted(zones_dir.glob("*.json")):
        zone_data = json.loads(zone_path.read_text(encoding="utf-8"))
        zone_id = zone_data["meta"]["zone_id"]
        for plan in zone_data.get("plans_eau", []):
            pid = plan.get("id")
            if pid is None:
                continue
            loc = loc_index.get((zone_id, pid))
            row = match_plan(zone_id, plan, loc)
            if row:
                matches.append(row)

    payload = {
        "nb_matches": len(matches),
        "nb_with_lce": sum(1 for m in matches if m.get("lce")),
        "matches": matches,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def get_match(zone_id: int, plan_id: int, path: Path = MATCHES_PATH) -> dict | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    for m in data.get("matches", []):
        if m.get("zone_id") == zone_id and m.get("plan_id") == plan_id:
            return m
    return None


def load_matches(path: Path = MATCHES_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"matches": []}
    return json.loads(path.read_text(encoding="utf-8"))
