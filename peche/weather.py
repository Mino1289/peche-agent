"""Météo live via GeoMet `citypageweather-realtime`.

L'API renvoie un GeoJSON avec, pour chaque ville, un payload riche où chaque
champ est enveloppé dans `{ "value": { "en": ..., "fr": ... } }`. On extrait
le strict nécessaire en français pour l'agent et on garde un cache mémoire
court (15 min) keyé par `(lat,lon)` arrondi à 0.05° (~5 km).

CLI :
  python3 -m peche.weather sync   # cache data/weather/cities.json (identifiants qc-*)
  python3 -m peche.weather get LAT LON
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

from peche.fetch import fetch_text
from peche.hydromet import haversine_km
from peche.reglements.sync import DATA_DIR

GEOMET_URL = "https://api.weather.gc.ca/collections/citypageweather-realtime/items"
DEFAULT_BBOX_HALF = 0.3
DEFAULT_TTL_SECONDS = 15 * 60
DEFAULT_TIMEOUT = 30.0
# Emprise pour le sync GeoMet (toutes les villes `qc-*` tombent dedans).
QUEBEC_BBOX: tuple[float, float, float, float] = (-79.85, 44.90, -57.05, 62.65)
QUEBEC_CITYPAGE_PREFIX = "qc-"

WEATHER_DIR = DATA_DIR / "weather"
CITIES_PATH = WEATHER_DIR / "cities.json"

_CACHE: dict[tuple[float, float], tuple[float, dict]] = {}


def _fr(node: Any) -> Any:
    """Déballe `{"en": ..., "fr": ...}` en favorisant FR, sinon retourne tel quel."""
    if isinstance(node, dict):
        if "fr" in node and "en" in node and len(node) == 2:
            return node.get("fr")
        if "value" in node and isinstance(node["value"], dict):
            v = node["value"]
            if "fr" in v or "en" in v:
                return v.get("fr", v.get("en"))
    return node


def _value(node: Any) -> Any:
    """Pour les champs avec `{units, value:{fr,en}}`, renvoie la valeur brute."""
    if isinstance(node, dict) and "value" in node:
        v = node["value"]
        if isinstance(v, dict):
            return v.get("fr", v.get("en"))
        return v
    return node


def _intersect_bbox(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    lon_min = max(a[0], b[0])
    lat_min = max(a[1], b[1])
    lon_max = min(a[2], b[2])
    lat_max = min(a[3], b[3])
    if lon_min >= lon_max or lat_min >= lat_max:
        return None
    return (lon_min, lat_min, lon_max, lat_max)


def _citypage_identifier(feature: dict) -> str:
    return str((feature.get("properties") or {}).get("identifier") or "").strip()


def _is_quebec_citypage(feature: dict) -> bool:
    return _citypage_identifier(feature).lower().startswith(QUEBEC_CITYPAGE_PREFIX)


def _feature_lon_lat(feature: dict) -> tuple[float, float] | None:
    geom = feature.get("geometry") or {}
    if geom.get("type") != "Point":
        return None
    coords = geom.get("coordinates") or []
    if len(coords) < 2:
        return None
    return float(coords[0]), float(coords[1])


def _build_url(lat: float, lon: float, half: float = DEFAULT_BBOX_HALF) -> str:
    raw = (lon - half, lat - half, lon + half, lat + half)
    clipped = _intersect_bbox(raw, QUEBEC_BBOX)
    if clipped is None:
        clipped = QUEBEC_BBOX
    bbox = f"{clipped[0]},{clipped[1]},{clipped[2]},{clipped[3]}"
    return f"{GEOMET_URL}?bbox={bbox}&lang=fr&limit=5&f=json"


def _page_url(p: dict, lat: float | None, lon: float | None) -> str | None:
    raw = p.get("url")
    if isinstance(raw, dict):
        url = raw.get("fr") or raw.get("en")
        if url:
            return str(url)
    elif isinstance(raw, str) and raw.strip():
        return raw.strip()
    if lat is not None and lon is not None:
        return (
            f"https://meteo.gc.ca/fr/location/index.html?coords={lat:.2f},{lon:.2f}"
        )
    return None


def citypage_geojson_in_bbox(
    bbox: tuple[float, float, float, float],
    *,
    limit: int = 500,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Points ville GeoMet dans une bbox WGS84 (lon_min, lat_min, lon_max, lat_max), Québec seulement."""
    clipped = _intersect_bbox(bbox, QUEBEC_BBOX)
    if clipped is None:
        return {"type": "FeatureCollection", "features": []}
    lon_min, lat_min, lon_max, lat_max = clipped
    cap = max(1, min(int(limit), 10000))
    url = (
        f"{GEOMET_URL}?bbox={lon_min},{lat_min},{lon_max},{lat_max}"
        f"&lang=fr&limit={cap}&f=json"
    )
    raw = fetch_text(url, timeout=timeout)
    data = json.loads(raw)
    features_out: list[dict] = []
    for feature in data.get("features") or []:
        ll = _feature_lon_lat(feature)
        if ll is None:
            continue
        lon_f, lat_f = ll
        if not _is_quebec_citypage(feature):
            continue
        parsed = _parse_feature(feature, lat_f, lon_f)
        features_out.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon_f, lat_f]},
                "properties": {
                    "ville": parsed.get("ville"),
                    "temperature_c": parsed.get("temperature_c"),
                    "observed_at": parsed.get("observed_at"),
                    "lat": lat_f,
                    "lon": lon_f,
                    "url": parsed.get("url"),
                },
            }
        )
        if len(features_out) >= cap:
            break
    return {"type": "FeatureCollection", "features": features_out}


def _parse_feature(feature: dict, query_lat: float, query_lon: float) -> dict:
    p = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or [None, None]
    feat_lon, feat_lat = coords[0], coords[1]

    cc = p.get("currentConditions") or {}
    name_node = p.get("name") or {}

    forecasts_out = []
    for fc in (p.get("forecastGroup") or {}).get("forecasts", [])[:4]:
        period = (fc.get("period") or {}).get("textForecastName") or {}
        temps = []
        for t in (fc.get("temperatures") or {}).get("temperature", []):
            klass = _fr(t.get("class")) if isinstance(t.get("class"), dict) else None
            temps.append({"class": klass, "value_c": _value(t)})
        forecasts_out.append(
            {
                "periode": period.get("fr") or period.get("en"),
                "resume": _fr(fc.get("textSummary")),
                "temperatures": temps,
            }
        )

    distance_km = None
    if feat_lat is not None and feat_lon is not None:
        distance_km = round(
            haversine_km(query_lat, query_lon, float(feat_lat), float(feat_lon)), 1
        )

    return {
        "ville": name_node.get("fr") or name_node.get("en"),
        "ville_lat": feat_lat,
        "ville_lon": feat_lon,
        "distance_km": distance_km,
        "observed_at": _fr(cc.get("timestamp")),
        "temperature_c": _value(cc.get("temperature")),
        "humidite_pct": _value(cc.get("relativeHumidity")),
        "vent_kmh": _value((cc.get("wind") or {}).get("speed")),
        "vent_dir": _value((cc.get("wind") or {}).get("direction")),
        "rafales_kmh": _value((cc.get("wind") or {}).get("gust")),
        "pression_kpa": _value(cc.get("pressure")),
        "station": _fr((cc.get("station") or {}).get("value"))
        if isinstance(cc.get("station"), dict)
        else None,
        "previsions": forecasts_out,
        "url": _page_url(
            p,
            float(feat_lat) if feat_lat is not None else None,
            float(feat_lon) if feat_lon is not None else None,
        ),
        "source": "GeoMet citypageweather-realtime",
    }


def _cache_key(lat: float, lon: float) -> tuple[int, int]:
    # Bucket ~10 km (0.1°) — granularité cohérente avec le TTL (15 min)
    # et la résolution typique des points de pêche.
    return (int(round(lat * 10)), int(round(lon * 10)))


def get_weather(
    lat: float,
    lon: float,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> dict:
    """Météo + courte prévision pour `(lat, lon)`. Cache mémoire ~15 min."""
    key = _cache_key(lat, lon)
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl_seconds:
        return {**hit[1], "_cache": "hit"}

    half = DEFAULT_BBOX_HALF
    for attempt in range(3):
        url = _build_url(lat, lon, half)
        raw = fetch_text(url, timeout=timeout)
        data = json.loads(raw)
        features = [
            f
            for f in (data.get("features") or [])
            if _is_quebec_citypage(f) and _feature_lon_lat(f) is not None
        ]
        if features:
            features.sort(
                key=lambda f: haversine_km(
                    lat,
                    lon,
                    float((f.get("geometry") or {}).get("coordinates", [0, 0])[1]),
                    float((f.get("geometry") or {}).get("coordinates", [0, 0])[0]),
                )
            )
            parsed = _parse_feature(features[0], lat, lon)
            _CACHE[key] = (now, parsed)
            return {**parsed, "_cache": "miss"}
        half *= 2  # élargir si rien dans la bbox
    return {
        "ville": None,
        "error": "Aucune ville GeoMet dans la bbox élargie.",
        "source": "GeoMet citypageweather-realtime",
        "_cache": "miss",
    }


def _flatten_city(feature: dict) -> dict | None:
    if not _is_quebec_citypage(feature):
        return None
    ll = _feature_lon_lat(feature)
    if ll is None:
        return None
    lon_f, lat_f = ll
    p = feature.get("properties") or {}
    name = p.get("name") or {}
    ville = name.get("fr") or name.get("en") or ""
    return {
        "identifier": _citypage_identifier(feature),
        "ville": ville,
        "lat": lat_f,
        "lon": lon_f,
    }


def fetch_citypage_cities_qc(
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Villes citypage ECCC dont l'identifiant GeoMet commence par `qc-`."""
    lon_min, lat_min, lon_max, lat_max = QUEBEC_BBOX
    url = (
        f"{GEOMET_URL}?bbox={lon_min},{lat_min},{lon_max},{lat_max}"
        f"&lang=fr&limit=10000&f=json"
    )
    data = json.loads(fetch_text(url, timeout=timeout))
    out: list[dict] = []
    for feature in data.get("features") or []:
        row = _flatten_city(feature)
        if row:
            out.append(row)
    out.sort(key=lambda c: unicodedata.normalize("NFKD", c.get("ville") or "").lower())
    return out


def save_cities(
    cities: list[dict],
    path: Path = CITIES_PATH,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": GEOMET_URL,
        "filter": QUEBEC_CITYPAGE_PREFIX,
        "nb_cities": len(cities),
        "cities": cities,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_cities(path: Path = CITIES_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("cities", [])


def cmd_sync(args: argparse.Namespace) -> int:
    print("Téléchargement villes météo GeoMet (identifiants qc-*)…")
    cities = fetch_citypage_cities_qc(timeout=args.timeout)
    path = save_cities(cities, args.out)
    print(f"  {len(cities)} villes -> {path}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    out = get_weather(args.lat, args.lon)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Météo live (GeoMet citypage).")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    sub = parser.add_subparsers(dest="command", required=True)
    p_sync = sub.add_parser("sync", help="Cache local des villes (qc-*)")
    p_sync.add_argument("--out", type=Path, default=CITIES_PATH)
    p_sync.set_defaults(func=cmd_sync)
    g = sub.add_parser("get", help="Météo pour des coords WGS84.")
    g.add_argument("lat", type=float)
    g.add_argument("lon", type=float)
    g.set_defaults(func=cmd_get)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv if argv is not None else sys.argv[1:]))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
