"""Découpage spatial en tuiles GeoJSON (~0.25°)."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

TILE_SIZE = 0.25


def tile_key(lat: float, lon: float) -> str:
    lat_bin = math.floor(lat / TILE_SIZE) * TILE_SIZE
    lon_bin = math.floor(lon / TILE_SIZE) * TILE_SIZE
    return f"{lat_bin:.2f}_{lon_bin:.2f}"


def tile_bbox(key: str) -> tuple[float, float, float, float]:
    lat0, lon0 = (float(x) for x in key.split("_"))
    return lat0, lon0, lat0 + TILE_SIZE, lon0 + TILE_SIZE


def point_feature(
    lon: float,
    lat: float,
    properties: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "properties": properties,
    }


def write_tile(
    out_dir: Path,
    key: str,
    features: list[dict],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{key}.geojson"
    fc = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return path


def build_index(tiles_dir: Path) -> dict[str, Any]:
    entries: list[dict] = []
    for path in sorted(tiles_dir.glob("*.geojson")):
        key = path.stem
        lat_min, lon_min, lat_max, lon_max = tile_bbox(key)
        data = json.loads(path.read_text(encoding="utf-8"))
        entries.append(
            {
                "key": key,
                "bbox": [lon_min, lat_min, lon_max, lat_max],
                "count": len(data.get("features", [])),
            }
        )
    return {
        "tile_size_deg": TILE_SIZE,
        "nb_tiles": len(entries),
        "tiles": entries,
    }


def write_index(index: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def group_points_into_tiles(
    points: list[tuple[float, float, dict[str, Any]]],
) -> dict[str, list[dict]]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for lon, lat, props in points:
        if lat is None or lon is None:
            continue
        key = tile_key(lat, lon)
        buckets[key].append(point_feature(lon, lat, props))
    return buckets


def flush_tiles(buckets: dict[str, list[dict]], out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, features in buckets.items():
        write_tile(out_dir, key, features)
    return len(buckets)
