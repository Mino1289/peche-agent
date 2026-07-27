"""Météo live via GeoMet `citypageweather-realtime`.

L'API renvoie un GeoJSON avec, pour chaque ville, un payload riche où chaque
champ est enveloppé dans `{ "value": { "en": ..., "fr": ... } }`. On extrait
le strict nécessaire en français pour l'agent et on garde un cache mémoire
court (15 min) keyé par `(lat,lon)` arrondi à 0.05° (~5 km).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from peche.fetch import fetch_text
from peche.hydromet import haversine_km

GEOMET_URL = "https://api.weather.gc.ca/collections/citypageweather-realtime/items"
DEFAULT_BBOX_HALF = 0.3
DEFAULT_TTL_SECONDS = 15 * 60
DEFAULT_TIMEOUT = 30.0

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


def _build_url(lat: float, lon: float, half: float = DEFAULT_BBOX_HALF) -> str:
    bbox = f"{lon - half},{lat - half},{lon + half},{lat + half}"
    return f"{GEOMET_URL}?bbox={bbox}&lang=fr&limit=5&f=json"


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
        "url": p.get("url"),
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
        features = data.get("features") or []
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


def cmd_get(args: argparse.Namespace) -> int:
    out = get_weather(args.lat, args.lon)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Météo live (GeoMet citypage).")
    sub = parser.add_subparsers(dest="command")
    g = sub.add_parser("get", help="Météo pour des coords WGS84.")
    g.add_argument("lat", type=float)
    g.add_argument("lon", type=float)
    g.set_defaults(func=cmd_get)
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
