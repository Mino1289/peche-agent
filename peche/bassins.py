"""Bassins hydrographiques multiéchelles (Données Québec).

CLI : python3 -m peche.bassins sync
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from peche.reglements.sync import DATA_DIR
from peche.spatial.ckan import download_zip_resource

BASSINS_PACKAGE_ID = "77099165-a79d-44d9-8361-8f0ce54aae4d"
SPATIAL_DIR = DATA_DIR / "spatial" / "bassins"
CACHE_SQLITE = DATA_DIR / "cache" / "bassins.sqlite"

# Niveaux exportés selon zoom (voir viewport.py)
EXPORT_LEVELS = (4, 5, 6, 7, 8)

SIMPLIFY_TOLERANCE = {
    4: 0.005,
    5: 0.003,
    6: 0.001,
    7: 0.0005,
    8: 0.0002,
}


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
        tol = SIMPLIFY_TOLERANCE.get(level, 0.001)
        subset["geometry"] = subset.geometry.simplify(tol, preserve_topology=True)
        features = []
        for _, row in subset.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(gpd.GeoSeries([geom]).to_json())["features"][0][
                        "geometry"
                    ],
                    "properties": {
                        "niveau": int(row["NIVEAU_BASSIN"]),
                        "nom": row.get("NOM_COURS_DEAU") or row.get("NOM_BV_PRIMAIRE"),
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
    return {"out_dir": str(out_dir), "levels": written}


def load_basin_level(level: int, out_dir: Path = SPATIAL_DIR) -> dict[str, Any]:
    path = out_dir / f"niveau_{level}.geojson"
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(path.read_text(encoding="utf-8"))


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
