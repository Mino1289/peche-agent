"""Base LCE — lacs et cours d'eau (Données Québec).

CLI : python3 -m peche.lce sync
"""

from __future__ import annotations

import argparse
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from peche.reglements.sync import DATA_DIR
from peche.spatial.ckan import download_zip_resource
from peche.spatial.tiles import build_index, flush_tiles, group_points_into_tiles, write_index

LCE_PACKAGE_ID = "a4a5575d-e8e8-4410-bfc6-18e9361ffd3f"
SPATIAL_DIR = DATA_DIR / "spatial" / "lce"
TILES_DIR = SPATIAL_DIR / "tiles"
INDEX_PATH = SPATIAL_DIR / "index.json"
CACHE_SQLITE = DATA_DIR / "cache" / "lce.sqlite"


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v):
        return None
    return v


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _extract_points_from_layer(
    gdf: Any,
    *,
    entity_type: str,
    name_fields: tuple[str, ...],
    id_field: str = "objectid",
) -> list[tuple[float, float, dict[str, Any]]]:
    gdf = gdf.to_crs(4326)
    out: list[tuple[float, float, dict[str, Any]]] = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        lon, lat = geom.x, geom.y
        nom = None
        for field in name_fields:
            nom = _safe_str(row.get(field))
            if nom:
                break
        props: dict[str, Any] = {
            "id_lce": int(row[id_field]) if row.get(id_field) is not None else None,
            "type": entity_type,
            "nom": nom,
        }
        if entity_type == "lac":
            for key in (
                "profondeur_max_lac",
                "superficie_nette_lac",
                "altitude_lac",
                "volume_lac",
                "no_lac",
            ):
                val = row.get(key)
                fval = _safe_float(val)
                if fval is not None:
                    props[key] = fval
                else:
                    sval = _safe_str(val)
                    if sval:
                        props[key] = sval
        else:
            for key in ("no_cours_deau", "superf_bassin_versant", "niveau_bassin"):
                fval = _safe_float(row.get(key))
                if fval is not None:
                    props[key] = fval
                else:
                    sval = _safe_str(row.get(key))
                    if sval:
                        props[key] = sval
        out.append((lon, lat, props))
    return out


def sync_lce(
    *,
    sqlite_path: Path = CACHE_SQLITE,
    tiles_dir: Path = TILES_DIR,
    index_path: Path = INDEX_PATH,
    force_download: bool = False,
) -> dict[str, Any]:
    import geopandas as gpd

    if force_download or not sqlite_path.exists():
        download_zip_resource(LCE_PACKAGE_ID, cache_path=sqlite_path)

    lakes = gpd.read_file(sqlite_path, layer="embouchures_cours_eau")
    rivers = gpd.read_file(sqlite_path, layer="centroides_lacs")

    points: list[tuple[float, float, dict[str, Any]]] = []
    points.extend(
        _extract_points_from_layer(
            lakes,
            entity_type="lac",
            name_fields=("nom_lac", "nom_lac_minuscule"),
        )
    )
    points.extend(
        _extract_points_from_layer(
            rivers,
            entity_type="riviere",
            name_fields=("nom_cours_deau", "nom_cours_deau_minuscule"),
        )
    )

    if tiles_dir.exists():
        for p in tiles_dir.glob("*.geojson"):
            p.unlink()
    buckets = group_points_into_tiles(points)
    nb_tiles = flush_tiles(buckets, tiles_dir)
    index = build_index(tiles_dir)
    index["synced_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    index["nb_features"] = len(points)
    index["nb_lacs"] = sum(1 for _, _, p in points if p["type"] == "lac")
    index["nb_rivieres"] = sum(1 for _, _, p in points if p["type"] == "riviere")
    write_index(index, index_path)

    lookup_path = SPATIAL_DIR / "lookup.json"
    lookup = [
        {
            "id_lce": props.get("id_lce"),
            "type": props["type"],
            "nom": props.get("nom"),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
        }
        for lon, lat, props in points
    ]
    lookup_path.write_text(
        __import__("json").dumps(lookup, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "sqlite": str(sqlite_path),
        "tiles_dir": str(tiles_dir),
        "index": str(index_path),
        "nb_features": len(points),
        "nb_tiles": nb_tiles,
    }


def load_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"tiles": []}
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync base LCE (lacs et cours d'eau).")
    sub = parser.add_subparsers(dest="command")
    sync = sub.add_parser("sync", help="Télécharge et génère les tuiles GeoJSON.")
    sync.add_argument("--force-download", action="store_true")
    sync.set_defaults(func=lambda a: _cmd_sync(a))
    return parser


def _cmd_sync(args: argparse.Namespace) -> int:
    result = sync_lce(force_download=args.force_download)
    print(
        f"LCE : {result['nb_features']} entités, "
        f"{result['nb_tiles']} tuiles -> {result['tiles_dir']}"
    )
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
