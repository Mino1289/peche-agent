"""Hydrométrie : référentiel Vigilance + matching plan d'eau ↔ station.

Offline (CLI) :
  python3 -m peche.hydromet sync-stations  # cache data/hydromet/stations.json
  python3 -m peche.hydromet match --all    # produit data/hydromet/matches/{zone_id}.json

Runtime (live) :
  fetch_live_stations() / get_live_station(station_id)
    → données fraîches Vigilance (niveau, débit, état, observed_at).

Le WFS Vigilance accepte directement `srsName=EPSG:4326` ; pyproj est gardé
dans `requirements.txt` comme filet de sécurité si l'API change.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

from peche.fetch import fetch_text
from peche.reglements.sync import DATA_DIR
from peche.reglements.zones import ZONES

VIGILANCE_WFS = (
    "https://geoegl.msp.gouv.qc.ca/apis/mapserver-vigilance/ws/vigilance.fcgi"
    "?service=wfs&version=1.1.0&request=GetFeature"
    "&typename=stations_igo2_public&outputformat=geojson&srsName=EPSG:4326"
)

HYDROMET_DIR = DATA_DIR / "hydromet"
STATIONS_PATH = HYDROMET_DIR / "stations.json"
MATCHES_DIR = HYDROMET_DIR / "matches"
LOCATIONS_DIR = DATA_DIR / "locations"

DEFAULT_RADIUS_KM = 25.0
NAME_MATCH_RADIUS_KM = 30.0
MAX_STATIONS_PER_PLAN = 8


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance grand-cercle entre deux points (km), modèle sphérique R=6371."""
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _normalize_feature(feature: dict) -> dict | None:
    """Aplati un Feature WFS Vigilance en dict station prête à stocker."""
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates")
    if geom.get("type") != "Point" or not coords or len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    p = feature.get("properties") or {}
    return {
        "station": str(p.get("station", "")),
        "description": p.get("description") or "",
        "plan_eau": p.get("plan_deau") or "",
        "fournisseur": p.get("fournisseur_nom") or "",
        "fournisseur_url": p.get("fournisseur_url") or "",
        "url_vigilance": p.get("url_vigilance") or "",
        "etat": p.get("etat") or "",
        "previsions": p.get("previsions") or "",
        "refoulement": p.get("refoulement") or "",
        "niveau_m": p.get("dern_valeur_niv"),
        "debit_m3s": p.get("dern_valeur_deb"),
        "observed_at": p.get("dern_date_prise_valeur_utc") or None,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
    }


def fetch_live_stations(timeout: float = 30.0) -> list[dict]:
    """Récupère les ~342 stations Vigilance (live, EPSG:4326)."""
    raw = fetch_text(VIGILANCE_WFS, timeout=timeout)
    data = json.loads(raw)
    out = []
    for feature in data.get("features", []):
        normalized = _normalize_feature(feature)
        if normalized:
            out.append(normalized)
    return out


def save_stations(stations: list[dict], path: Path = STATIONS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": VIGILANCE_WFS,
        "nb_stations": len(stations),
        "stations": stations,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_stations(path: Path = STATIONS_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} introuvable — lancer `python3 -m peche.hydromet sync-stations`."
        )
    return json.loads(path.read_text(encoding="utf-8"))["stations"]


def nearest_station(
    lat: float,
    lon: float,
    stations: list[dict],
    radius_km: float = DEFAULT_RADIUS_KM,
) -> dict | None:
    """Renvoie la station la plus proche dans le rayon, ou None."""
    ranked = nearest_stations(lat, lon, stations, radius_km=radius_km, limit=1)
    return ranked[0] if ranked else None


def nearest_stations(
    lat: float,
    lon: float,
    stations: list[dict],
    radius_km: float = DEFAULT_RADIUS_KM,
    limit: int = MAX_STATIONS_PER_PLAN,
) -> list[dict]:
    """Stations triées par distance croissante dans le rayon."""
    ranked: list[tuple[float, dict]] = []
    for s in stations:
        d = haversine_km(lat, lon, s["lat"], s["lon"])
        if d <= radius_km:
            ranked.append((d, s))
    ranked.sort(key=lambda x: x[0])
    out: list[dict] = []
    for d, s in ranked[:limit]:
        out.append({**s, "distance_km": round(d, 2)})
    return out


def _water_names_match(plan_nom: str, station_plan_eau: str) -> bool:
    """True si le nom du plan matche le plan_eau Vigilance (ex. Lac Kénogami)."""
    from peche.matching.normalize import normalize_water_name, token_jaccard

    plan_core = normalize_water_name(plan_nom)
    station_core = normalize_water_name(station_plan_eau)
    if not plan_core or not station_core:
        return False
    if plan_core == station_core:
        return True
    if plan_core in station_core or station_core in plan_core:
        return True
    return token_jaccard(plan_nom, station_plan_eau) >= 0.6


def _station_role(station: dict) -> str:
    """Rôle hydro : level (niveau seul), flow (débit), both."""
    has_niv = station.get("niveau_m") is not None
    has_deb = station.get("debit_m3s") is not None
    if has_niv and has_deb:
        return "both"
    if has_deb:
        return "flow"
    return "level"


def _station_entry(station: dict, match_reason: str) -> dict:
    return {
        "id": station["station"],
        "plan_eau": station.get("plan_eau", ""),
        "description": station.get("description", ""),
        "lat": station["lat"],
        "lon": station["lon"],
        "distance_km": station["distance_km"],
        "role": _station_role(station),
        "match_reason": match_reason,
    }


def match_stations_for_plan(
    plan_nom: str,
    lat: float,
    lon: float,
    stations: list[dict],
    radius_km: float = DEFAULT_RADIUS_KM,
    name_radius_km: float = NAME_MATCH_RADIUS_KM,
) -> list[dict]:
    """Trouve toutes les stations pertinentes pour un plan d'eau.

    Passe 1 : match par nom (`plan_eau` Vigilance) dans `name_radius_km`.
    Passe 2 : fallback géographique (stations les plus proches dans `radius_km`).
    """
    name_matches: list[dict] = []
    for s in stations:
        d = haversine_km(lat, lon, s["lat"], s["lon"])
        if d > name_radius_km:
            continue
        if _water_names_match(plan_nom, s.get("plan_eau", "")):
            name_matches.append({**s, "distance_km": round(d, 2)})

    name_matches.sort(key=lambda x: x["distance_km"])
    if name_matches:
        return [_station_entry(s, "name") for s in name_matches[:MAX_STATIONS_PER_PLAN]]

    geo = nearest_stations(lat, lon, stations, radius_km=radius_km)
    return [_station_entry(s, "geo") for s in geo]


def get_live_station(station_id: str, timeout: float = 30.0) -> dict | None:
    """Données live d'une station précise (re-fetch complet Vigilance)."""
    for s in fetch_live_stations(timeout=timeout):
        if s["station"] == str(station_id):
            return s
    return None


def search_stations_offline(
    query: str,
    stations: list[dict],
    limit: int = 8,
) -> list[dict]:
    """Cherche dans le cache Vigilance par id, plan_eau, ou description.

    Stratégie simple : score = combinaison de match exact sur l'id,
    sous-chaîne sur plan_eau, sous-chaîne sur description (toutes les trois
    insensibles à la casse / aux accents).
    """
    import unicodedata

    def _norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return " ".join(s.lower().split())

    if not query.strip():
        return []
    q = _norm(query)
    tokens = [t for t in q.split() if len(t) >= 2]
    out = []
    for s in stations:
        sid = s["station"]
        plan = _norm(s.get("plan_eau", ""))
        desc = _norm(s.get("description", ""))
        haystack = f"{sid} {plan} {desc}"
        score = 0.0
        # ID exact ou préfixe
        if sid == query.strip():
            score = 1.0
        elif sid.startswith(query.strip()):
            score = 0.95
        # Sous-chaîne plan d'eau
        if q in plan and plan:
            score = max(score, 0.85)
        if q in desc and desc:
            score = max(score, 0.75)
        # Requête multi-mots (ex. « saguenay chicoutimi »)
        if tokens:
            if all(t in haystack for t in tokens):
                score = max(score, 0.88)
            elif any(t in haystack for t in tokens):
                score = max(score, 0.65)
        if score == 0.0:
            continue
        out.append({**s, "score": round(score, 2)})
    out.sort(key=lambda s: s["score"], reverse=True)
    return out[:limit]


def cmd_sync_stations(args: argparse.Namespace) -> int:
    print(f"Téléchargement Vigilance WFS ({VIGILANCE_WFS[:80]}…)")
    stations = fetch_live_stations(timeout=args.timeout)
    path = save_stations(stations, args.out)
    print(f"  {len(stations)} stations -> {path}")
    return 0


def _match_zone(zone_id: int, stations: list[dict], radius_km: float) -> dict:
    loc_path = LOCATIONS_DIR / f"{zone_id}.json"
    if not loc_path.exists():
        return {
            "zone_id": zone_id,
            "error": f"{loc_path} introuvable (lancer peche.coords extract)",
        }
    locations = json.loads(loc_path.read_text(encoding="utf-8"))["locations"]
    matched: list[dict] = []
    n_with_coords = 0
    n_matched = 0
    for loc in locations:
        if loc["lat"] is None or loc["lon"] is None:
            continue
        n_with_coords += 1
        station_list = match_stations_for_plan(
            loc["nom"], loc["lat"], loc["lon"], stations, radius_km=radius_km
        )
        if not station_list:
            matched.append(
                {
                    "plan_id": loc["id"],
                    "plan_nom": loc["nom"],
                    "lat": loc["lat"],
                    "lon": loc["lon"],
                    "stations": [],
                    "primary_station_id": None,
                    "station": None,
                }
            )
            continue
        n_matched += 1
        primary = station_list[0]
        matched.append(
            {
                "plan_id": loc["id"],
                "plan_nom": loc["nom"],
                "lat": loc["lat"],
                "lon": loc["lon"],
                "stations": station_list,
                "primary_station_id": primary["id"],
                # Rétrocompat : première station (primaire)
                "station": {
                    "id": primary["id"],
                    "plan_eau": primary["plan_eau"],
                    "description": primary["description"],
                    "lat": primary["lat"],
                    "lon": primary["lon"],
                    "distance_km": primary["distance_km"],
                },
            }
        )
    return {
        "meta": {
            "zone_id": zone_id,
            "radius_km": radius_km,
            "nb_with_coords": n_with_coords,
            "nb_station_matched": n_matched,
        },
        "matches": matched,
    }


def cmd_match(args: argparse.Namespace) -> int:
    stations = load_stations(args.stations)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    zone_ids = set(args.zone) if args.zone else {z.value for z in ZONES}

    print(f"{'Zone':30s} {'géo':>5s} {'matched':>8s} {'%':>6s}")
    print("-" * 55)
    grand_geo = grand_match = 0
    for zone in ZONES:
        if zone.value not in zone_ids:
            continue
        result = _match_zone(zone.value, stations, args.radius_km)
        if "error" in result:
            print(f"{zone.text:30s} -- {result['error']}")
            continue
        meta = result["meta"]
        n_geo = meta["nb_with_coords"]
        n_match = meta["nb_station_matched"]
        grand_geo += n_geo
        grand_match += n_match
        pct = 100.0 * n_match / n_geo if n_geo else 0.0
        print(f"{zone.text:30s} {n_geo:5d} {n_match:8d} {pct:5.1f}%")
        path = out_dir / f"{zone.value}.json"
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print("-" * 55)
    pct = 100.0 * grand_match / grand_geo if grand_geo else 0.0
    print(f"{'TOTAL':30s} {grand_geo:5d} {grand_match:8d} {pct:5.1f}%")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Affiche les données live d'une station (debug)."""
    s = get_live_station(args.station_id, timeout=args.timeout)
    if s is None:
        print(f"Station {args.station_id} introuvable.", file=sys.stderr)
        return 1
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Hydrométrie : sync stations + matching."
    )
    sub = parser.add_subparsers(dest="command")

    s = sub.add_parser("sync-stations", help="Cache Vigilance WFS dans data/hydromet/")
    s.add_argument("--out", type=Path, default=STATIONS_PATH)
    s.add_argument("--timeout", type=float, default=30.0)
    s.set_defaults(func=cmd_sync_stations)

    m = sub.add_parser(
        "match",
        help="Plan d'eau (avec coords) → stations (nom + geo) dans le rayon.",
    )
    m.add_argument("--zone", type=int, action="append")
    m.add_argument("--all", action="store_true")
    m.add_argument("--radius-km", type=float, default=DEFAULT_RADIUS_KM)
    m.add_argument("--stations", type=Path, default=STATIONS_PATH)
    m.add_argument("--out-dir", type=Path, default=MATCHES_DIR)
    m.set_defaults(func=cmd_match)

    sh = sub.add_parser("show", help="Affiche les données live d'une station (debug).")
    sh.add_argument("station_id")
    sh.add_argument("--timeout", type=float, default=30.0)
    sh.set_defaults(func=cmd_show)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        parser.print_help()
        return 2
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
