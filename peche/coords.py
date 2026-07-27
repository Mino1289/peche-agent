"""Extraction de coordonnées DMS depuis les noms de plans d'eau RegPec.

Les noms suivent souvent le motif :
    "Lac au Saumon (48°25'13\" N., 67°19'34\" O.)"

Mais on rencontre aussi :
- secondes manquantes : (47°23' N., 71°10' O.)
- secondes décimales avec virgule : 75°27'27,9''
- `''` au lieu de `"`
- suffixes après les coords : (..., Municipalité de ...)
- tiret ou retour ligne entre nom et parenthèse

Sortie : `{lat: float, lon: float}` en WGS84 (Québec → N positif, O négatif).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from peche.matching.normalize import (
    extract_river_base_name,
    extract_segment_label,
    normalize_search_text,
    search_aliases,
)
from peche.reglements.sync import DATA_DIR, ZONES_DIR
from peche.reglements.zones import ZONES

LOCATIONS_DIR = DATA_DIR / "locations"
SEARCH_INDEX_PATH = DATA_DIR / "search_index.json"

_DMS_RE = re.compile(
    r"""
    (?P<lat_d>\d{1,3})\s*°\s*
    (?P<lat_m>\d{1,2})\s*'\s*
    (?:(?P<lat_s>\d{1,2}(?:[.,]\d+)?)\s*(?:''|"))?\s*
    (?P<lat_h>[NSns])\.?\s*[,;]?\s*
    (?P<lon_d>\d{1,3})\s*°\s*
    (?P<lon_m>\d{1,2})\s*'\s*
    (?:(?P<lon_s>\d{1,2}(?:[.,]\d+)?)\s*(?:''|"))?\s*
    (?P<lon_h>[EeOoWw])\.?
    """,
    re.VERBOSE,
)


def _to_decimal(d: str, m: str, s: str | None, hemi: str) -> float:
    deg = int(d) + int(m) / 60.0
    if s is not None:
        deg += float(s.replace(",", ".")) / 3600.0
    if hemi.upper() in {"S", "O", "W"}:
        deg = -deg
    return round(deg, 6)


def parse_dms(text: str) -> dict[str, float] | None:
    """Renvoie `{lat, lon}` si une paire DMS est trouvée dans `text`, sinon None."""
    pairs = parse_all_dms(text)
    return pairs[0] if pairs else None


def parse_all_dms(text: str) -> list[dict[str, float]]:
    """Extrait toutes les paires DMS d'un texte (segments rivière, libellés longs)."""
    out: list[dict[str, float]] = []
    for match in _DMS_RE.finditer(text):
        lat = _to_decimal(
            match.group("lat_d"),
            match.group("lat_m"),
            match.group("lat_s"),
            match.group("lat_h"),
        )
        lon = _to_decimal(
            match.group("lon_d"),
            match.group("lon_m"),
            match.group("lon_s"),
            match.group("lon_h"),
        )
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            continue
        pair = {"lat": lat, "lon": lon}
        if not out or out[-1] != pair:
            out.append(pair)
    return out


def split_name(nom: str) -> str:
    """Renvoie la portion 'nom propre' avant la parenthèse de coords (best-effort)."""
    pos = nom.find("(")
    if pos == -1:
        return nom.strip()
    return nom[:pos].rstrip(" -–—\t\r\n")


def extract_zone(zone_path: Path) -> dict:
    data = json.loads(zone_path.read_text(encoding="utf-8"))
    zone_id = data["meta"]["zone_id"]
    zone_nom = data["meta"]["zone_nom"]

    locations: list[dict] = []
    n_total = 0
    n_with_coords = 0
    for plan in data.get("plans_eau", []):
        n_total += 1
        coords = parse_dms(plan["nom"])
        nom_brut = plan["nom"]
        nom = split_name(nom_brut)
        base = extract_river_base_name(nom_brut)
        entry = {
            "id": plan["id"],
            "zone_id": zone_id,
            "nom_brut": nom_brut,
            "nom": nom,
            "nom_search": normalize_search_text(nom_brut),
            "segment_label": extract_segment_label(nom_brut),
            "river_base_name": base,
            "aliases": search_aliases(nom_brut, base),
            "lat": coords["lat"] if coords else None,
            "lon": coords["lon"] if coords else None,
        }
        if coords:
            n_with_coords += 1
        locations.append(entry)

    return {
        "meta": {
            "zone_id": zone_id,
            "zone_nom": zone_nom,
            "nb_plans": n_total,
            "nb_geocoded": n_with_coords,
            "pct_geocoded": (
                round(100.0 * n_with_coords / n_total, 1) if n_total else 0.0
            ),
            "source_file": str(zone_path.relative_to(DATA_DIR)),
        },
        "locations": locations,
    }


def write_zone_locations(out_dir: Path, zone_locations: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{zone_locations['meta']['zone_id']}.json"
    path.write_text(
        json.dumps(zone_locations, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def build_search_index(locations_dir: Path = LOCATIONS_DIR) -> dict:
    """Fusionne tous les plans d'eau en un index de recherche global."""
    entries: list[dict] = []
    for path in sorted(locations_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        zone_id = data["meta"]["zone_id"]
        for loc in data.get("locations", []):
            entries.append(
                {
                    "plan_id": loc["id"],
                    "zone_id": zone_id,
                    "nom": loc.get("nom", ""),
                    "nom_brut": loc.get("nom_brut", ""),
                    "nom_search": loc.get("nom_search")
                    or normalize_search_text(loc.get("nom_brut", "")),
                    "segment_label": loc.get("segment_label"),
                    "river_base_name": loc.get("river_base_name", ""),
                    "aliases": loc.get("aliases") or [],
                    "lat": loc.get("lat"),
                    "lon": loc.get("lon"),
                }
            )
    return {
        "nb_entries": len(entries),
        "entries": entries,
    }


def write_search_index(
    locations_dir: Path = LOCATIONS_DIR,
    out_path: Path = SEARCH_INDEX_PATH,
) -> Path:
    payload = build_search_index(locations_dir)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path


def cmd_extract(args: argparse.Namespace) -> int:
    zone_ids = set(args.zone) if args.zone else {z.value for z in ZONES}
    zones_dir: Path = args.zones_dir
    out_dir: Path = args.out_dir

    rows = []
    grand_total = grand_geo = 0
    for zone in ZONES:
        if zone.value not in zone_ids:
            continue
        path = zones_dir / f"{zone.value}.json"
        if not path.exists():
            print(f"[skip] {zone.text}: {path} introuvable", file=sys.stderr)
            continue
        zl = extract_zone(path)
        write_zone_locations(out_dir, zl)
        meta = zl["meta"]
        grand_total += meta["nb_plans"]
        grand_geo += meta["nb_geocoded"]
        rows.append(meta)

    print(f"{'Zone':30s} {'plans':>6s} {'géo':>5s} {'%':>6s}")
    print("-" * 50)
    for m in rows:
        print(
            f"{m['zone_nom']:30s} {m['nb_plans']:6d} "
            f"{m['nb_geocoded']:5d} {m['pct_geocoded']:5.1f}%"
        )
    print("-" * 50)
    pct = 100.0 * grand_geo / grand_total if grand_total else 0.0
    print(f"{'TOTAL':30s} {grand_total:6d} {grand_geo:5d} {pct:5.1f}%")

    if args.build_index:
        idx_path = write_search_index(out_dir, args.index_out)
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
        print(f"Index recherche : {idx['nb_entries']} entrées -> {idx_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrait les coordonnées DMS depuis data/zones/*.json."
    )
    sub = parser.add_subparsers(dest="command")

    extract = sub.add_parser(
        "extract",
        help="Génère data/locations/{zone_id}.json à partir de data/zones/.",
    )
    extract.add_argument("--zone", type=int, action="append")
    extract.add_argument("--all", action="store_true", help="(défaut) toutes les zones")
    extract.add_argument("--zones-dir", type=Path, default=ZONES_DIR)
    extract.add_argument("--out-dir", type=Path, default=LOCATIONS_DIR)
    extract.add_argument(
        "--build-index",
        action="store_true",
        help="Génère aussi data/search_index.json",
    )
    extract.add_argument("--index-out", type=Path, default=SEARCH_INDEX_PATH)
    extract.set_defaults(func=cmd_extract)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        argv = ["extract"]
    elif argv[0] not in {"extract"}:
        argv = ["extract", *argv]
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
