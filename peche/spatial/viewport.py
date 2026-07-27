"""Requêtes viewport — entités spatiales par bbox et zoom."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from peche.bassins import SPATIAL_DIR as BASSINS_DIR
from peche.lce import INDEX_PATH as LCE_INDEX_PATH
from peche.lce import TILES_DIR as LCE_TILES_DIR
from peche.reglements.sync import DATA_DIR

LCE_MIN_ZOOM = 10

BASIN_LEVEL_BY_ZOOM = [
    (13, 8),
    (12, 7),
    (10, 6),
    (9, 5),
    (0, 4),
]

ATLAS_DIR = DATA_DIR / "spatial" / "atlas"


def _bbox_intersects(
    feat_bbox: list[float],
    query: tuple[float, float, float, float],
) -> bool:
    """bbox format [lon_min, lat_min, lon_max, lat_max]."""
    lon_min, lat_min, lon_max, lat_max = query
    f_lon_min, f_lat_min, f_lon_max, f_lat_max = feat_bbox
    return not (
        f_lon_max < lon_min
        or f_lon_min > lon_max
        or f_lat_max < lat_min
        or f_lat_min > lat_max
    )


def _point_in_bbox(lon: float, lat: float, bbox: tuple[float, float, float, float]) -> bool:
    lon_min, lat_min, lon_max, lat_max = bbox
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


@lru_cache(maxsize=1)
def _lce_index() -> dict[str, Any]:
    if not LCE_INDEX_PATH.exists():
        return {"tiles": []}
    return json.loads(LCE_INDEX_PATH.read_text(encoding="utf-8"))


def basin_level_for_zoom(zoom: int) -> int:
    for threshold, level in BASIN_LEVEL_BY_ZOOM:
        if zoom >= threshold:
            return level
    return 4


def features_in_bbox(
    layer: str,
    bbox: tuple[float, float, float, float],
    zoom: int,
) -> list[dict[str, Any]]:
    """Retourne les entités intersectant `bbox` (lon_min, lat_min, lon_max, lat_max)."""
    if layer == "lce":
        return _lce_in_bbox(bbox, zoom)
    if layer == "bassins":
        return _bassins_in_bbox(bbox, zoom)
    if layer in {"rsvl", "zgie", "drainage"}:
        return _atlas_in_bbox(layer, bbox, zoom)
    return []


def _lce_in_bbox(bbox: tuple[float, float, float, float], zoom: int) -> list[dict]:
    if zoom < LCE_MIN_ZOOM:
        return []
    out: list[dict] = []
    for tile in _lce_index().get("tiles", []):
        if not _bbox_intersects(tile["bbox"], bbox):
            continue
        path = LCE_TILES_DIR / f"{tile['key']}.geojson"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for feat in data.get("features", []):
            coords = feat.get("geometry", {}).get("coordinates")
            if not coords or len(coords) < 2:
                continue
            lon, lat = coords[0], coords[1]
            if _point_in_bbox(lon, lat, bbox):
                out.append(feat)
    return out


def _bassins_in_bbox(bbox: tuple[float, float, float, float], zoom: int) -> list[dict]:
    level = basin_level_for_zoom(zoom)
    path = BASSINS_DIR / f"niveau_{level}.geojson"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict] = []
    lon_min, lat_min, lon_max, lat_max = bbox
    for feat in data.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        # Approximation : centroïde du premier ring
        try:
            if geom["type"] == "Polygon":
                ring = geom["coordinates"][0]
            elif geom["type"] == "MultiPolygon":
                ring = geom["coordinates"][0][0]
            else:
                continue
            lons = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            if lons and lats:
                c_lon = sum(lons) / len(lons)
                c_lat = sum(lats) / len(lats)
                if _point_in_bbox(c_lon, c_lat, bbox):
                    out.append(feat)
        except (KeyError, IndexError, TypeError):
            continue
    return out


def _atlas_in_bbox(layer: str, bbox: tuple[float, float, float, float], zoom: int) -> list[dict]:
    if zoom < 8:
        return []
    path = ATLAS_DIR / f"{layer}.geojson"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict] = []
    for feat in data.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        if geom.get("type") == "Point":
            lon, lat = geom["coordinates"][:2]
            if _point_in_bbox(lon, lat, bbox):
                out.append(feat)
    return out


def layers_for_zoom(zoom: int) -> list[str]:
    layers = ["bassins"]
    if zoom >= LCE_MIN_ZOOM:
        layers.append("lce")
    if zoom >= 8:
        layers.extend(["rsvl", "zgie"])
    return layers
