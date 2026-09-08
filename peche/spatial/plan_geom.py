"""Géométries des plans RegPec — polygones officiels (carte interactive).

Source primaire : MapServer RegPec
  https://peche.faune.gouv.qc.ca/arcgiswa/rest/services/PRODC-E/PlansEauExceptions/MapServer/2
  (couche « Plan d'eau - Exception réglementaire » de la carte interactive).

Champs : ID_ENDRO = plan_id, ID_ZONE = zone_id RegPec, NM_ENDRO_FR = nom.
"""

from __future__ import annotations

import json
import math
import time
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from peche.fetch import fetch_text
from peche.reglements.sync import DATA_DIR
from peche.spatial.reg_link import get_match

MATCHES_PATH = DATA_DIR / "spatial" / "regpec_lce_matches.json"
LOCATIONS_DIR = DATA_DIR / "locations"
PLANS_OFFLINE_PATH = DATA_DIR / "spatial" / "plans_regpec.geojson"
_ARCGIS_TIMEOUT_S = 12.0
_PLANS_CACHE_TTL_S = 6 * 3600
_PLANS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

# Carte interactive RegPec — polygones d'exception
REGPEC_PLANS_LAYER = (
    "https://peche.faune.gouv.qc.ca/arcgiswa/rest/services/PRODC-E/"
    "PlansEauExceptions/MapServer/2"
)
# Couches complémentaires (zone 21, nouveautés, pêche d'hiver)
REGPEC_ZONE21_LAYER = (
    "https://peche.faune.gouv.qc.ca/arcgiswa/rest/services/PRODC-E/"
    "PlansEauExceptions/MapServer/3"
)
REGPEC_EXTRA_LAYERS = (
    REGPEC_ZONE21_LAYER,
    "https://peche.faune.gouv.qc.ca/arcgiswa/rest/services/PRODC-E/"
    "PlansEauExceptions/MapServer/4",
    "https://peche.faune.gouv.qc.ca/arcgiswa/rest/services/PRODC-E/"
    "PlansEauExceptions/MapServer/5",
)

DEFAULT_RADIUS_M = 450.0
PAGE_SIZE = 500
ZONE21_REGPEC_ID = 23  # Zone 21 affichée → id RegPec 23

LAYER3_OUT_FIELDS = "ID_ENDRO"
DEFAULT_OUT_FIELDS = (
    "ID_ENDRO,ID_ZONE,NM_ENDRO_FR,NM_ENDRO_EN,VA_TYPE_DESCR_FR,ID_ENDRO_PARNT"
)


def _is_layer3(layer_url: str) -> bool:
    return "MapServer/3" in layer_url


def _layer_out_fields(layer_url: str) -> str:
    """Layer 3 (exceptions zone 21) n'a que ID_ENDRO — les autres champs 400."""
    return LAYER3_OUT_FIELDS if _is_layer3(layer_url) else DEFAULT_OUT_FIELDS


@lru_cache(maxsize=1)
def _plan_name_index() -> dict[int, dict[str, Any]]:
    """plan_id → {zone_id, nom} depuis locations (noms courts) puis zones."""
    out: dict[int, dict[str, Any]] = {}
    if LOCATIONS_DIR.exists():
        for path in sorted(LOCATIONS_DIR.glob("*.json")):
            try:
                zid = int(path.stem)
            except ValueError:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            plans = data.get("locations") or []
            if isinstance(data, list):
                plans = data
            for plan in plans:
                if not isinstance(plan, dict):
                    continue
                pid = plan.get("id") or plan.get("plan_id")
                if pid is None:
                    continue
                nom = plan.get("nom") or plan.get("name") or ""
                out[int(pid)] = {"zone_id": int(plan.get("zone_id") or zid), "nom": nom}
    zones_dir = DATA_DIR / "zones"
    if zones_dir.exists():
        for path in sorted(zones_dir.glob("*.json")):
            try:
                zid = int(path.stem)
            except ValueError:
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for plan in data.get("plans_eau") or []:
                if not isinstance(plan, dict):
                    continue
                pid = plan.get("id")
                if pid is None:
                    continue
                pid_i = int(pid)
                if pid_i in out and out[pid_i].get("nom"):
                    continue
                nom = plan.get("nom") or ""
                out[pid_i] = {"zone_id": zid, "nom": nom}
    return out


def _enrich_zone_labels(props: dict[str, Any]) -> None:
    """Ajoute no_zone et zone_nom à partir du zone_id RegPec."""
    from peche.reglements.zones import display_number, zone_by_id

    zid = props.get("zone_id")
    if zid in (None, "", 0):
        return
    try:
        zone = zone_by_id(int(zid))
    except (TypeError, ValueError):
        return
    if not zone:
        return
    props.setdefault("zone_nom", zone.text)
    no = display_number(zone)
    if no is not None:
        props.setdefault("no_zone", no)


def _enrich_feature(feat: dict[str, Any], layer_url: str) -> dict[str, Any]:
    """Complète zone_id / nom (Layer 3 n'a ni ID_ZONE ni NM_ENDRO_FR)."""
    props = feat["properties"]
    if _is_layer3(layer_url):
        props["zone_id"] = ZONE21_REGPEC_ID
        props["source"] = "regpec_exceptions_zone21"
    info = _plan_name_index().get(int(props["plan_id"]))
    if info:
        if not props.get("nom"):
            props["nom"] = info.get("nom") or ""
        if not props.get("zone_id"):
            props["zone_id"] = int(info.get("zone_id") or 0)
    _enrich_zone_labels(props)
    return feat


def _circle_coords(lon: float, lat: float, radius_m: float, n: int = 32) -> list[list[float]]:
    lat_rad = math.radians(lat)
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(math.cos(lat_rad), 0.01))
    ring = []
    for i in range(n + 1):
        ang = 2 * math.pi * i / n
        ring.append([lon + dlon * math.cos(ang), lat + dlat * math.sin(ang)])
    return ring


def _line_buffer_coords(
    points: list[tuple[float, float]], width_m: float = 80.0
) -> list[list[float]] | None:
    if len(points) < 2:
        return None
    (lon1, lat1), (lon2, lat2) = points[0], points[-1]
    mid_lat = math.radians((lat1 + lat2) / 2)
    dx = (lon2 - lon1) * 111_320.0 * math.cos(mid_lat)
    dy = (lat2 - lat1) * 111_320.0
    length = math.hypot(dx, dy) or 1.0
    px, py = -dy / length, dx / length
    half = width_m / 2
    off_lon = (px * half) / (111_320.0 * max(math.cos(mid_lat), 0.01))
    off_lat = (py * half) / 111_320.0
    return [
        [lon1 + off_lon, lat1 + off_lat],
        [lon2 + off_lon, lat2 + off_lat],
        [lon2 - off_lon, lat2 - off_lat],
        [lon1 - off_lon, lat1 - off_lat],
        [lon1 + off_lon, lat1 + off_lat],
    ]


def _dam_line(lon: float, lat: float, length_m: float = 80.0) -> list[list[float]]:
    lat_rad = math.radians(lat)
    dlon = (length_m / 2) / (111_320.0 * max(math.cos(lat_rad), 0.01))
    return [[lon - dlon, lat], [lon + dlon, lat]]


def _simplify_offset(bbox: tuple[float, float, float, float] | None) -> float | None:
    """Tolérance de simplification ArcGIS selon la largeur du viewport."""
    if not bbox:
        return 0.0002
    width = max(bbox[2] - bbox[0], bbox[3] - bbox[1], 0.01)
    # ~1/2500 de la largeur, borné
    return max(min(width / 2500.0, 0.01), 0.00005)


def _normalize_feature(raw: dict[str, Any]) -> dict[str, Any] | None:
    """GeoJSON ArcGIS → feature plans_regpec (zone_id / plan_id)."""
    props = raw.get("properties") or raw.get("attributes") or {}
    geom = raw.get("geometry")
    if not geom:
        return None
    # Esri JSON rings → GeoJSON
    if "rings" in geom and "type" not in geom:
        geom = {"type": "Polygon", "coordinates": geom["rings"]}
    if geom.get("type") not in {"Polygon", "MultiPolygon"}:
        return None
    coords = geom.get("coordinates") or []
    if not coords:
        return None

    try:
        plan_id = int(props.get("ID_ENDRO"))
    except (TypeError, ValueError):
        return None
    try:
        raw_zone = props.get("ID_ZONE")
        zone_id = int(raw_zone) if raw_zone not in (None, "") else 0
    except (TypeError, ValueError):
        zone_id = 0

    nom = props.get("NM_ENDRO_FR") or props.get("NM_ENDRO_EN") or ""
    kind = props.get("VA_TYPE_DESCR_FR") or ""
    return {
        "type": "Feature",
        "geometry": geom,
        "properties": {
            "zone_id": zone_id,
            "plan_id": plan_id,
            "nom": nom,
            "type_endro": kind,
            "kind": "plan_regpec",
            "source": "regpec_plans_eau_exceptions",
        },
    }


def _query_layer(
    layer_url: str,
    *,
    where: str,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
    offset: int = 0,
) -> dict[str, Any]:
    params: dict[str, str] = {
        "where": where,
        "outFields": _layer_out_fields(layer_url),
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
        "resultRecordCount": str(min(PAGE_SIZE, limit)),
        "resultOffset": str(offset),
    }
    if bbox:
        params["geometry"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        params["geometryType"] = "esriGeometryEnvelope"
        params["inSR"] = "4326"
        params["spatialRel"] = "esriSpatialRelIntersects"
    off = _simplify_offset(bbox)
    if off is not None:
        params["maxAllowableOffset"] = str(off)
    url = f"{layer_url}/query?{urlencode(params)}"
    return json.loads(fetch_text(url, timeout=_ARCGIS_TIMEOUT_S))


def _fetch_regpec_polygons(
    bbox: tuple[float, float, float, float] | None,
    *,
    zone_id: int | None = None,
    zone_ids: list[int] | None = None,
    plan_id: int | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    ids: list[int] | None = zone_ids
    if ids is None and zone_id is not None:
        ids = [int(zone_id)]

    clauses: list[str] = ["1=1"]
    if ids:
        if len(ids) == 1:
            clauses.append(f"ID_ZONE={ids[0]}")
        else:
            clauses.append(f"ID_ZONE IN ({','.join(str(i) for i in ids)})")
    if plan_id is not None:
        clauses.append(f"ID_ENDRO={int(plan_id)}")
    where = " AND ".join(clauses)

    features: list[dict] = []
    seen: set[int] = set()
    # Layer 3 d'abord : polygones maritimes zone 21 (Layer 2 a des anneaux vides).
    layers = (REGPEC_ZONE21_LAYER, REGPEC_PLANS_LAYER, *REGPEC_EXTRA_LAYERS[1:])

    for layer_url in layers:
        if len(features) >= limit:
            break
        offset = 0
        # Layer 3 n'a pas ID_ZONE — ignorer le filtre zone via where adapté
        layer_where = where
        if _is_layer3(layer_url) and ids is not None:
            if ZONE21_REGPEC_ID not in ids:
                continue
            layer_where = "1=1" if plan_id is None else f"ID_ENDRO={int(plan_id)}"

        while len(features) < limit:
            try:
                data = _query_layer(
                    layer_url,
                    where=layer_where,
                    bbox=bbox,
                    limit=limit - len(features),
                    offset=offset,
                )
            except Exception:  # noqa: BLE001
                break
            raw_feats = data.get("features") or []
            if not raw_feats:
                break
            for raw in raw_feats:
                feat = _normalize_feature(raw)
                if not feat:
                    continue
                feat = _enrich_feature(feat, layer_url)
                pid = int(feat["properties"]["plan_id"])
                if pid in seen:
                    continue
                if ids is not None and feat["properties"]["zone_id"] not in {
                    0,
                    *ids,
                }:
                    continue
                seen.add(pid)
                features.append(feat)
                if len(features) >= limit:
                    break
            if not data.get("exceededTransferLimit") and len(raw_feats) < PAGE_SIZE:
                break
            offset += len(raw_feats)
            if offset > 20000:
                break
    return features


def fetch_plan_geometry(zone_id: int, plan_id: int) -> dict[str, Any] | None:
    """Polygone officiel RegPec pour un plan, ou None."""
    feats = _fetch_regpec_polygons(None, zone_id=zone_id, plan_id=plan_id, limit=1)
    if not feats:
        # Retry sans filtre zone (ID_ENDRO unique)
        feats = _fetch_regpec_polygons(None, plan_id=plan_id, limit=1)
    if feats:
        return feats[0]["geometry"]
    return None


def geometry_for_plan(
    zone_id: int,
    plan_id: int,
    lat: float,
    lon: float,
    nom: str | None = None,
) -> dict[str, Any]:
    """Polygone officiel RegPec, sinon approximation LCE/cercle."""
    official = fetch_plan_geometry(zone_id, plan_id)
    if official:
        return official

    match = get_match(zone_id, plan_id) or {}
    entity = (match.get("lce") or {}).get("type") or (
        "riviere" if nom and "rivi" in nom.lower() else "lac"
    )
    segs = match.get("segment_points") or []
    if entity == "riviere" and len(segs) >= 2:
        pts = [(float(p["lon"]), float(p["lat"])) for p in segs if "lat" in p and "lon" in p]
        ring = _line_buffer_coords(pts)
        if ring:
            return {"type": "Polygon", "coordinates": [ring]}
    if entity == "riviere" and len(segs) == 1:
        lat, lon = float(segs[0]["lat"]), float(segs[0]["lon"])
    radius = 550.0 if entity == "lac" else DEFAULT_RADIUS_M
    return {
        "type": "Polygon",
        "coordinates": [_circle_coords(lon, lat, radius)],
    }


@lru_cache(maxsize=1)
def _matches_index() -> dict[tuple[int, int], dict]:
    if not MATCHES_PATH.exists():
        return {}
    data = json.loads(MATCHES_PATH.read_text(encoding="utf-8"))
    out: dict[tuple[int, int], dict] = {}
    for m in data.get("matches") or []:
        try:
            out[(int(m["zone_id"]), int(m["plan_id"]))] = m
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _quantize_bbox(
    bbox: tuple[float, float, float, float] | None,
    *,
    steps: int = 40,
) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    w = max(bbox[2] - bbox[0], 1e-6)
    h = max(bbox[3] - bbox[1], 1e-6)
    q = max(w, h) / steps
    return tuple(round(v / q) * q for v in bbox)  # type: ignore[return-value]


def _plans_cache_key(
    bbox: tuple[float, float, float, float] | None,
    zone_ids: list[int] | None,
    zoom: int | None,
    limit: int,
) -> str:
    qb = _quantize_bbox(bbox)
    zids = ",".join(str(z) for z in sorted(zone_ids or []))
    return f"{qb}|{zids}|{zoom}|{limit}"


def _plans_cache_get(key: str) -> dict[str, Any] | None:
    row = _PLANS_CACHE.get(key)
    if not row:
        return None
    ts, data = row
    if time.monotonic() - ts > _PLANS_CACHE_TTL_S:
        _PLANS_CACHE.pop(key, None)
        return None
    return data


def _plans_cache_set(key: str, data: dict[str, Any]) -> None:
    _PLANS_CACHE[key] = (time.monotonic(), data)


@lru_cache(maxsize=1)
def _load_offline_plans() -> list[dict[str, Any]]:
    if not PLANS_OFFLINE_PATH.exists():
        return []
    raw = json.loads(PLANS_OFFLINE_PATH.read_text(encoding="utf-8"))
    return list(raw.get("features") or [])


def _filter_plan_features(
    features: list[dict[str, Any]],
    bbox: tuple[float, float, float, float] | None,
    zone_ids: list[int] | None,
    limit: int,
) -> list[dict[str, Any]]:
    allowed = set(zone_ids) if zone_ids else None
    out: list[dict[str, Any]] = []
    for feat in features:
        props = feat.get("properties") or {}
        zid = int(props.get("zone_id", -1))
        if allowed is not None and zid not in allowed:
            continue
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if bbox and coords:
            if geom.get("type") == "Point" and len(coords) >= 2:
                lon_f, lat_f = float(coords[0]), float(coords[1])
                if not (bbox[0] <= lon_f <= bbox[2] and bbox[1] <= lat_f <= bbox[3]):
                    continue
            elif geom.get("type") in {"Polygon", "MultiPolygon"}:
                from peche.spatial.zones_peche import _bbox_intersects, _envelope_from_coords

                env = _envelope_from_coords(coords)
                if env and not _bbox_intersects(env, bbox):
                    continue
        out.append(feat)
        if len(out) >= limit:
            break
    return out


def _plans_points_geojson(
    bbox: tuple[float, float, float, float] | None,
    *,
    resolved_zone_ids: list[int] | None = None,
    limit: int,
) -> dict[str, Any]:
    """Centroïdes légers depuis locations (zoom bas)."""
    allowed: set[int] | None = set(resolved_zone_ids) if resolved_zone_ids else None
    features: list[dict] = []
    files = sorted(LOCATIONS_DIR.glob("*.json")) if LOCATIONS_DIR.exists() else []
    for path in files:
        try:
            zid = int(path.stem)
        except ValueError:
            continue
        if allowed is not None and zid not in allowed:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        plans = data.get("locations") or []
        if isinstance(data, list):
            plans = data
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            lat = plan.get("lat")
            lon = plan.get("lon")
            if lat is None or lon is None:
                continue
            lat_f, lon_f = float(lat), float(lon)
            if bbox and not (
                bbox[0] <= lon_f <= bbox[2] and bbox[1] <= lat_f <= bbox[3]
            ):
                continue
            pid = plan.get("id") or plan.get("plan_id")
            if pid is None:
                continue
            nom = plan.get("nom") or plan.get("name") or ""
            props = {
                "zone_id": zid,
                "plan_id": int(pid),
                "nom": nom,
                "lat": lat_f,
                "lon": lon_f,
                "kind": "plan_regpec",
                "source": "locations_point",
            }
            _enrich_zone_labels(props)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon_f, lat_f]},
                    "properties": props,
                }
            )
            if len(features) >= limit:
                return {"type": "FeatureCollection", "features": features}
    return {"type": "FeatureCollection", "features": features}


def plans_geojson(
    bbox: tuple[float, float, float, float] | None,
    *,
    zone_id: int | None = None,
    zone_ids: list[int] | None = None,
    limit: int = 2000,
    zoom: int | None = None,
) -> dict[str, Any]:
    """FeatureCollection de polygones officiels RegPec dans le viewport.

    ``zone_ids`` sont des ids RegPec déjà résolus (filtre utilisateur).
    """
    resolved_ids: list[int] | None = zone_ids
    if resolved_ids is None and zone_id is not None:
        resolved_ids = [int(zone_id)]

    cache_key = _plans_cache_key(bbox, resolved_ids, zoom, limit)
    cached = _plans_cache_get(cache_key)
    if cached is not None:
        return cached

    if zoom is not None and zoom < 11:
        data = _plans_points_geojson(
            bbox, resolved_zone_ids=resolved_ids, limit=limit
        )
        _plans_cache_set(cache_key, data)
        return data

    offline = _filter_plan_features(
        _load_offline_plans(), bbox, resolved_ids, limit
    )
    if offline:
        data = {"type": "FeatureCollection", "features": offline}
        _plans_cache_set(cache_key, data)
        return data

    try:
        features = _fetch_regpec_polygons(
            bbox, zone_ids=resolved_ids, limit=limit
        )
        if features:
            for feat in features:
                _enrich_zone_labels(feat.get("properties") or {})
            data = {"type": "FeatureCollection", "features": features}
            _plans_cache_set(cache_key, data)
            return data
    except Exception:  # noqa: BLE001
        pass

    data = _plans_geojson_fallback(
        bbox, resolved_zone_ids=resolved_ids, limit=limit
    )
    _plans_cache_set(cache_key, data)
    return data


def _plans_geojson_fallback(
    bbox: tuple[float, float, float, float] | None,
    *,
    resolved_zone: int | None = None,
    resolved_zone_ids: list[int] | None = None,
    limit: int,
) -> dict[str, Any]:
    allowed: set[int] | None = None
    if resolved_zone_ids is not None:
        allowed = set(resolved_zone_ids)
    elif resolved_zone is not None:
        allowed = {int(resolved_zone)}

    features: list[dict] = []
    files = sorted(LOCATIONS_DIR.glob("*.json")) if LOCATIONS_DIR.exists() else []
    for path in files:
        try:
            zid = int(path.stem)
        except ValueError:
            continue
        if allowed is not None and zid not in allowed:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        plans = data.get("locations") or []
        if isinstance(data, list):
            plans = data
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            lat = plan.get("lat")
            lon = plan.get("lon")
            if lat is None or lon is None:
                continue
            lat_f, lon_f = float(lat), float(lon)
            if bbox and not (
                bbox[0] <= lon_f <= bbox[2] and bbox[1] <= lat_f <= bbox[3]
            ):
                continue
            pid = plan.get("id") or plan.get("plan_id")
            if pid is None:
                continue
            nom = plan.get("nom") or plan.get("name") or ""
            geom = geometry_for_plan(zid, int(pid), lat_f, lon_f, nom)
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "zone_id": zid,
                        "plan_id": int(pid),
                        "nom": nom,
                        "lat": lat_f,
                        "lon": lon_f,
                        "kind": "plan_regpec",
                        "source": "fallback_approx",
                    },
                }
            )
            props = features[-1]["properties"]
            _enrich_zone_labels(props)
            if len(features) >= limit:
                return {"type": "FeatureCollection", "features": features}
    return {"type": "FeatureCollection", "features": features}


def sync_offline_plans(*, limit: int = 50000) -> Path:
    """Harvest polygones RegPec → data/spatial/plans_regpec.geojson (offline)."""
    PLANS_OFFLINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    print("Harvest plans RegPec (ArcGIS)…")
    features = _fetch_regpec_polygons(None, limit=limit)
    for feat in features:
        _enrich_zone_labels(feat.get("properties") or {})
    collection = {
        "type": "FeatureCollection",
        "features": features,
        "meta": {"nb_features": len(features), "source": "regpec_plans_eau_exceptions"},
    }
    PLANS_OFFLINE_PATH.write_text(
        json.dumps(collection, ensure_ascii=False), encoding="utf-8"
    )
    _load_offline_plans.cache_clear()
    _PLANS_CACHE.clear()
    print(f"Écrit {PLANS_OFFLINE_PATH} ({len(features)} plans)")
    return PLANS_OFFLINE_PATH


def barrage_line_feature(item: dict[str, Any]) -> dict[str, Any] | None:
    lat = item.get("lat")
    lon = item.get("lon")
    if lat is None or lon is None:
        return None
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": _dam_line(lon_f, lat_f),
        },
        "properties": {k: v for k, v in item.items() if k not in {"geometry"}},
    }
