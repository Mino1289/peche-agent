"""Bassins hydrographiques multiéchelles (Données Québec).

CLI : python3 -m peche.bassins sync
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import orjson
from shapely.geometry import mapping, shape

from peche.reglements.sync import DATA_DIR
from peche.spatial.ckan import download_zip_resource

BASSINS_PACKAGE_ID = "77099165-a79d-44d9-8361-8f0ce54aae4d"
SPATIAL_DIR = DATA_DIR / "spatial" / "bassins"
CACHE_SQLITE = DATA_DIR / "cache" / "bassins.sqlite"

# Tous les niveaux exportés ; la couche carte filtre par niveau (sélecteur).
EXPORT_LEVELS = (1, 2, 3, 4, 5, 6, 7, 8)

# Géométrie stockée fine (~30 m). Aux zooms plus bas, simplifiée en mémoire (cache par bande),
# comme zones_peche / tfs : plus on zoome, plus le contour est précis.
FINE_TOLERANCE = 0.0003


def sync_bassins(
    *,
    sqlite_path: Path = CACHE_SQLITE,
    out_dir: Path = SPATIAL_DIR,
    force_download: bool = False,
    levels: tuple[int, ...] = EXPORT_LEVELS,
) -> dict[str, Any]:
    import geopandas as gpd

    if force_download or not sqlite_path.exists():
        download_zip_resource(BASSINS_PACKAGE_ID, cache_path=sqlite_path)

    gdf = gpd.read_file(sqlite_path, layer="bassin_multi")
    gdf = gdf.to_crs(4326)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: dict[int, int] = {}
    for level in levels:
        subset = gdf[gdf["NIVEAU_BASSIN"] == level].copy()
        if subset.empty:
            continue
        subset["geometry"] = subset.geometry.simplify(FINE_TOLERANCE, preserve_topology=True)
        features = []
        for _, row in subset.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": _round_coords(
                        json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"]
                    ),
                    "properties": {
                        "objectid": int(row.name),  # OBJECTID = index fid de read_file
                        "niveau": int(row["NIVEAU_BASSIN"]),
                        "nom": row.get("NOM_COURS_DEAU") or row.get("NOM_BV_PRIMAIRE"),
                        "nom_bv": row.get("NOM_BV_PRIMAIRE") or None,
                        "nom_cours_eau": row.get("NOM_COURS_DEAU") or None,
                        "no_cours_eau": row.get("NO_COURS_DEAU"),
                        "superf_km2": float(row["SUPERF_KM2"])
                        if row.get("SUPERF_KM2") is not None
                        else None,
                        "reg_hydro": row.get("NOM_REG_HYDRO_ABREGE"),
                    },
                }
            )
        path = out_dir / f"niveau_{level}.geojson"
        fc = {"type": "FeatureCollection", "features": features}
        path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
        written[level] = len(features)

    meta = {
        "synced_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "levels": written,
        "source": str(sqlite_path),
    }
    (out_dir / "index.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _level_band.cache_clear()
    return {"out_dir": str(out_dir), "levels": written}


def load_basin_level(level: int, out_dir: Path = SPATIAL_DIR) -> dict[str, Any]:
    path = out_dir / f"niveau_{level}.geojson"
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _round_coords(obj: Any, ndigits: int = 5) -> Any:
    """Coordonnées arrondies à ~1 m : réduit le poids des fichiers sans perte visible."""
    if isinstance(obj, float):
        return round(obj, ndigits)
    if isinstance(obj, list):
        return [_round_coords(x, ndigits) for x in obj]
    if isinstance(obj, dict) and "coordinates" in obj:
        return {**obj, "coordinates": _round_coords(obj["coordinates"], ndigits)}
    return obj


def _simplify_tolerance(zoom: int | None) -> float | None:
    """None = géométrie stockée (fine). Zoom d'ensemble : simplifié ; zoom moyen : moins."""
    if zoom is None or zoom >= 12:
        return None
    return 0.005 if zoom < 9 else 0.001


@lru_cache(maxsize=3 * len(EXPORT_LEVELS))
def _level_band(
    level: int, tol: float | None
) -> tuple[tuple[tuple[float, float, float, float], bytes], ...]:
    """Entités d'un niveau : (bounds, feature sérialisée), géométrie simplifiée à `tol` (None = fine)."""
    path = SPATIAL_DIR / f"niveau_{level}.geojson"
    if not path.exists():
        return ()
    feats = json.loads(path.read_text(encoding="utf-8"))["features"]
    out = []
    for f in feats:
        if tol is not None:
            geom = shape(f["geometry"]).simplify(tol, preserve_topology=True)
            # Un polygone plus petit que la tolérance disparaît : on garde alors la version fine.
            if not geom.is_empty:
                f = {**f, "geometry": _round_coords(mapping(geom))}
        out.append((shape(f["geometry"]).bounds, orjson.dumps(f)))
    return tuple(out)


def bassins_geojson_bytes(
    bbox: tuple[float, float, float, float] | None,
    levels: set[int],
    zoom: int | None = None,
) -> bytes:
    """FeatureCollection JSON des bassins des niveaux demandés qui touchent `bbox` (lon/lat)."""
    tol = _simplify_tolerance(zoom)
    parts: list[bytes] = []
    for level in sorted(levels):
        for (minx, miny, maxx, maxy), blob in _level_band(level, tol):
            if bbox and (maxx < bbox[0] or minx > bbox[2] or maxy < bbox[1] or miny > bbox[3]):
                continue
            parts.append(blob)
    return b'{"type":"FeatureCollection","features":[' + b",".join(parts) + b"]}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync bassins hydrographiques.")
    sub = parser.add_subparsers(dest="command")
    sync = sub.add_parser("sync")
    sync.add_argument("--force-download", action="store_true")
    sync.set_defaults(func=lambda a: _cmd_sync(a))
    return parser


def _cmd_sync(args: argparse.Namespace) -> int:
    result = sync_bassins(force_download=args.force_download)
    print(f"Bassins : {result['levels']} -> {result['out_dir']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        argv = ["sync"]
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
