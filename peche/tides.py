"""Marées — API IWLS (Service hydrographique du Canada).

Source officielle : https://api-iwls.dfo-mpo.gc.ca (SINE / marees.gc.ca).
Série `wlp-hilo` = heures et hauteurs des pleines et basses mers (prédictions).

CLI :
  python3 -m peche.tides sync          # cache data/tides/stations.json (région QUE)
  python3 -m peche.tides get 03045     # test rapide
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from peche.dates import today
from peche.fetch import fetch_text
from peche.hydromet import haversine_km
from peche.reglements.sync import DATA_DIR

IWLS_BASE = "https://api-iwls.dfo-mpo.gc.ca"
TIDE_SERIES_CODE = "wlp-hilo"
WLP_SERIES_CODE = "wlp"
WLO_SERIES_CODE = "wlo"
DEFAULT_REGION = "QUE"
DEFAULT_DAYS = 7
DEFAULT_MAX_DAYS = 31
DEFAULT_NEAREST_KM = 75.0
DEFAULT_TIMEOUT = 30.0
DEFAULT_TZ = "America/Montreal"

# L'API renvoie souvent Canada/* ; sur Linux sans paquet tzdata, ZoneInfo
# ne les résout pas — on mappe vers les IANA équivalents.
_TZ_ALIASES: dict[str, str] = {
    "Canada/Eastern": "America/Toronto",
    "Canada/Atlantic": "America/Halifax",
    "Canada/Newfoundland": "America/St_Johns",
    "Canada/Central": "America/Winnipeg",
    "Canada/Mountain": "America/Edmonton",
    "Canada/Pacific": "America/Vancouver",
}

TIDES_DIR = DATA_DIR / "tides"
STATIONS_PATH = TIDES_DIR / "stations.json"

_STATION_PAGE_FR = "https://marees.gc.ca/fr/stations/{code}"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _fetch_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> Any:
    return json.loads(fetch_text(url, timeout=timeout))


def _station_url(code: str) -> str:
    return _STATION_PAGE_FR.format(code=quote(code, safe=""))


def _has_hilo_series(station: dict) -> bool:
    return any(
        ts.get("code") == TIDE_SERIES_CODE for ts in station.get("timeSeries") or []
    )


def _flatten_station(raw: dict) -> dict:
    return {
        "station_id": raw["id"],
        "code": raw.get("code", ""),
        "nom": raw.get("officialName") or "",
        "nom_alternatif": raw.get("alternativeName") or "",
        "lat": raw.get("latitude"),
        "lon": raw.get("longitude"),
        "operating": raw.get("operating"),
        "type": raw.get("type"),
    }


def fetch_tide_stations(
    region: str = DEFAULT_REGION,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Stations avec prédictions pleines/basses mers pour une région SHC."""
    url = (
        f"{IWLS_BASE}/api/v1/stations"
        f"?chs-region-code={quote(region)}"
        f"&time-series-code={quote(TIDE_SERIES_CODE)}"
    )
    raw = _fetch_json(url, timeout=timeout)
    return [_flatten_station(s) for s in raw if _has_hilo_series(s)]


def save_stations(
    stations: list[dict],
    path: Path = STATIONS_PATH,
    region: str = DEFAULT_REGION,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": IWLS_BASE,
        "region": region,
        "nb_stations": len(stations),
        "stations": stations,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_stations(path: Path = STATIONS_PATH) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("stations", [])


@lru_cache(maxsize=1)
def _stations_cached() -> tuple[list[dict], str]:
    """Cache mémoire : fichier local, sinon téléchargement live."""
    local = load_stations()
    if local:
        return local, "cache"
    live = fetch_tide_stations()
    return live, "iwls-live"


def get_station_by_code(code: str, timeout: float = DEFAULT_TIMEOUT) -> dict | None:
    url = f"{IWLS_BASE}/api/v1/stations?code={quote(code.strip(), safe='')}"
    rows = _fetch_json(url, timeout=timeout)
    if not rows:
        return None
    s = _flatten_station(rows[0])
    if not _has_hilo_series(rows[0]):
        s["error"] = "Cette station n'a pas de prédictions de marées (wlp-hilo)."
    return s


def _resolve_zone(tz_name: str) -> ZoneInfo:
    for candidate in (tz_name, _TZ_ALIASES.get(tz_name, ""), DEFAULT_TZ):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except Exception:  # noqa: BLE001 — ZoneInfoNotFoundError
            continue
    return ZoneInfo("UTC")


def _get_timezone(station_id: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    try:
        meta = _fetch_json(
            f"{IWLS_BASE}/api/v1/stations/{station_id}/metadata",
            timeout=timeout,
        )
        tz = meta.get("timeZoneCode")
        if tz:
            return tz
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return DEFAULT_TZ


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _to_local_hm(iso_utc: str, tz_name: str) -> tuple[str, str]:
    """Renvoie (date ISO locale, heure HH:MM) pour affichage."""
    local = _parse_utc(iso_utc).astimezone(_resolve_zone(tz_name))
    return local.date().isoformat(), local.strftime("%H:%M")


def _classify_hilo(rows: list[dict]) -> list[dict]:
    """Étiquette pleine/basse à partir de l'alternance des extrema."""
    if not rows:
        return []
    if len(rows) == 1:
        return [{**rows[0], "type": "extremum"}]
    first_is_low = float(rows[0]["value_m"]) < float(rows[1]["value_m"])
    out: list[dict] = []
    for i, row in enumerate(rows):
        is_low = first_is_low if i % 2 == 0 else not first_is_low
        label = "basse" if is_low else "pleine"
        out.append({**row, "type": label})
    return out


def _fetch_series_raw(
    station_id: str,
    series_code: str,
    start: datetime,
    end: datetime,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict]:
    url = (
        f"{IWLS_BASE}/api/v1/stations/{station_id}/data"
        f"?time-series-code={quote(series_code)}"
        f"&from={quote(_utc_iso(start))}"
        f"&to={quote(_utc_iso(end))}"
    )
    return _fetch_json(url, timeout=timeout)


def _fetch_hilo_raw(
    station_id: str,
    start: datetime,
    end: datetime,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict]:
    return _fetch_series_raw(station_id, TIDE_SERIES_CODE, start, end, timeout=timeout)


def _has_series(station_raw: dict, series_code: str) -> bool:
    return any(
        ts.get("code") == series_code for ts in station_raw.get("timeSeries") or []
    )


def get_water_level_live(
    station_code: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Dernière observation de niveau d'eau (série IWLS `wlo`, temps réel SHC)."""
    code = station_code.strip()
    if not code:
        return {"error": "Code de station vide."}

    url = f"{IWLS_BASE}/api/v1/stations?code={quote(code, safe='')}"
    try:
        rows = _fetch_json(url, timeout=timeout)
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return {"error": f"API IWLS indisponible : {exc}", "source": IWLS_BASE}

    if not rows:
        return {"error": f"Station « {code} » introuvable.", "source": IWLS_BASE}
    raw = rows[0]
    if not _has_series(raw, WLO_SERIES_CODE):
        return {
            "station_code": code,
            "station_nom": raw.get("officialName"),
            "error": "Pas d'observations temps réel (wlo) pour cette station.",
            "source": IWLS_BASE,
        }

    station = _flatten_station(raw)
    tz_name = _get_timezone(station["station_id"], timeout=timeout)
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(hours=6)

    try:
        points = _fetch_series_raw(
            station["station_id"],
            WLO_SERIES_CODE,
            start_utc,
            end_utc,
            timeout=timeout,
        )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return {
            "station_code": code,
            "station_nom": station.get("nom"),
            "error": f"API IWLS indisponible : {exc}",
            "source": IWLS_BASE,
        }

    if not points:
        return {
            "station_code": code,
            "station_nom": station.get("nom"),
            "error": "Aucune observation wlo récente (6 h).",
            "source": IWLS_BASE,
        }

    latest = max(points, key=lambda p: p.get("eventDate", ""))
    iso = latest.get("eventDate", "")
    d_loc, h_loc = _to_local_hm(iso, tz_name)
    return {
        "station_code": code,
        "station_nom": station.get("nom"),
        "station_id": station["station_id"],
        "niveau_m": round(float(latest["value"]), 3),
        "observed_at_utc": iso,
        "observed_at_local": f"{d_loc} {h_loc}",
        "fuseau": tz_name,
        "unite": "m (zéro des cartes)",
        "type_donnee": "observation temps réel",
        "source": "IWLS wlo / SHC",
        "urls": {"marees_gc_ca": _station_url(code)},
    }


def _downsample_curve(
    points: list[dict],
    *,
    step_minutes: int = 15,
) -> list[dict[str, float]]:
    """Réduit une série wlp pour le graphique (pas ~15 min)."""
    if not points:
        return []
    out: list[dict[str, float]] = []
    last_t: float | None = None
    step_s = step_minutes * 60
    for pt in sorted(points, key=lambda p: p.get("eventDate", "")):
        val = pt.get("value")
        iso = pt.get("eventDate", "")
        if val is None or not iso:
            continue
        try:
            t = _parse_utc(iso).timestamp()
            v = float(val)
        except (TypeError, ValueError):
            continue
        if last_t is not None and t - last_t < step_s:
            continue
        out.append({"t": t, "value": round(v, 3)})
        last_t = t
    return out


def _fetch_wlp_curve(
    station_id: str,
    start: datetime,
    end: datetime,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, float]]:
    """Courbe de prédiction continue (série IWLS ``wlp``)."""
    try:
        raw = _fetch_series_raw(station_id, WLP_SERIES_CODE, start, end, timeout)
    except (json.JSONDecodeError, OSError, ValueError):
        return []
    return _downsample_curve(raw)


def get_tide_predictions(
    station_code: str,
    *,
    days: int = DEFAULT_DAYS,
    start_date: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """Heures et hauteurs des pleines et basses mers pour une station SHC.

    `station_code` : code à 5 chiffres (ex. `03045` pour Pointe-au-Pic).
    `start_date` : ISO `YYYY-MM-DD` (début de la fenêtre, défaut = aujourd'hui).
    Hauteurs en mètres par rapport au zéro des cartes (CD).
    """
    code = station_code.strip()
    if not code:
        return {"error": "Code de station vide."}

    days = max(1, min(int(days), DEFAULT_MAX_DAYS))

    station = get_station_by_code(code, timeout=timeout)
    if station is None:
        return {
            "error": f"Station marégraphique « {code} » introuvable.",
            "source": IWLS_BASE,
        }
    if station.get("error"):
        return {
            "station_code": code,
            "station_nom": station.get("nom"),
            "error": station["error"],
            "source": IWLS_BASE,
        }

    if start_date:
        try:
            day0 = date.fromisoformat(start_date)
        except ValueError:
            return {"error": f"Date invalide « {start_date} », format YYYY-MM-DD."}
    else:
        day0 = today()

    tz_name = _get_timezone(station["station_id"], timeout=timeout)
    start_local = datetime.combine(
        day0, datetime.min.time(), tzinfo=_resolve_zone(tz_name)
    )
    end_local = start_local + timedelta(days=days)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    try:
        raw = _fetch_hilo_raw(
            station["station_id"], start_utc, end_utc, timeout=timeout
        )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return {
            "station_code": code,
            "station_nom": station.get("nom"),
            "error": f"API IWLS indisponible : {exc}",
            "source": IWLS_BASE,
        }

    rows: list[dict] = []
    for pt in raw:
        val = pt.get("value")
        if val is None:
            continue
        iso = pt.get("eventDate", "")
        d_loc, h_loc = _to_local_hm(iso, tz_name)
        q = pt.get("qualifier")
        type_hint = None
        if q == "EXTREMA_FLOOD":
            type_hint = "pleine"
        elif q == "EXTREMA_EBB":
            type_hint = "basse"
        rows.append(
            {
                "datetime_utc": iso,
                "date": d_loc,
                "heure": h_loc,
                "value_m": round(float(val), 3),
                "type_hint": type_hint,
            }
        )

    classified = _classify_hilo(rows)
    for row in classified:
        if row.get("type_hint"):
            row["type"] = row["type_hint"]
        row.pop("type_hint", None)

    by_day: dict[str, list[dict]] = {}
    for row in classified:
        by_day.setdefault(row["date"], []).append(
            {
                "heure": row["heure"],
                "type": row["type"],
                "hauteur_m": row["value_m"],
                "datetime_utc": row["datetime_utc"],
            }
        )

    def _fmt_cell(evt: dict | None) -> str:
        if not evt:
            return ""
        return f"{evt['heure']} ({evt['hauteur_m']:.2f} m)"

    # Tableau 5 colonnes: jour, basse1, haute1, basse2, haute2
    days_sorted = sorted(by_day.keys())
    table_rows: list[dict] = []
    for d in days_sorted:
        evts = sorted(by_day[d], key=lambda e: e["heure"])
        lows = [e for e in evts if e.get("type") == "basse"]
        highs = [e for e in evts if e.get("type") == "pleine"]
        row = {
            "jour": d,
            "maree_basse_1": _fmt_cell(lows[0] if len(lows) > 0 else None),
            "maree_haute_1": _fmt_cell(highs[0] if len(highs) > 0 else None),
            "maree_basse_2": _fmt_cell(lows[1] if len(lows) > 1 else None),
            "maree_haute_2": _fmt_cell(highs[1] if len(highs) > 1 else None),
        }
        table_rows.append(row)

    table_markdown_lines = [
        "| Jour | Marée basse 1 | Marée haute 1 | Marée basse 2 | Marée haute 2 |",
        "|---|---|---|---|---|",
    ]
    for r in table_rows:
        table_markdown_lines.append(
            f"| {r['jour']} | {r['maree_basse_1']} | {r['maree_haute_1']} | {r['maree_basse_2']} | {r['maree_haute_2']} |"
        )
    table_markdown = "\n".join(table_markdown_lines)

    curve = _fetch_wlp_curve(station["station_id"], start_utc, end_utc, timeout=timeout)

    return {
        "station_code": code,
        "station_nom": station.get("nom"),
        "station_id": station["station_id"],
        "lat": station.get("lat"),
        "lon": station.get("lon"),
        "fuseau": tz_name,
        "periode": {
            "debut": day0.isoformat(),
            "jours": days,
            "fin_exclue": (day0 + timedelta(days=days)).isoformat(),
        },
        "marées": by_day,
        "table": {
            "colonnes": [
                "jour",
                "marée_basse_1",
                "marée_haute_1",
                "marée_basse_2",
                "marée_haute_2",
            ],
            "lignes": table_rows,
            "markdown": table_markdown,
        },
        "nb_extremes": len(classified),
        "curve": curve,
        "unite": "m (zéro des cartes)",
        "source": "IWLS / SHC (api-iwls.dfo-mpo.gc.ca)",
        "urls": {"marees_gc_ca": _station_url(code)},
    }


def search_tide_stations(query: str, limit: int = 8) -> list[dict]:
    """Recherche une station de marées par code ou nom (cache local ou API)."""
    if not query.strip():
        return []
    q = _norm(query)
    stations, _src = _stations_cached()
    out: list[dict] = []
    for s in stations:
        code = s.get("code", "")
        nom = _norm(s.get("nom", ""))
        alt = _norm(s.get("nom_alternatif", ""))
        score = 0.0
        if code == query.strip():
            score = 1.0
        elif code.startswith(query.strip()):
            score = 0.95
        elif q in nom and nom:
            score = max(score, 0.85)
        elif q in alt and alt:
            score = max(score, 0.8)
        elif q in _norm(code):
            score = max(score, 0.7)
        if score <= 0:
            continue
        out.append(
            {
                "station_code": code,
                "station_nom": s.get("nom"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
                "score": round(score, 3),
                "urls": {"marees_gc_ca": _station_url(code)},
            }
        )
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:limit]


def nearest_tide_station(
    lat: float,
    lon: float,
    radius_km: float = DEFAULT_NEAREST_KM,
) -> dict | None:
    stations, _ = _stations_cached()
    best = None
    best_d = float("inf")
    for s in stations:
        slat, slon = s.get("lat"), s.get("lon")
        if slat is None or slon is None:
            continue
        d = haversine_km(lat, lon, float(slat), float(slon))
        if d < best_d:
            best_d = d
            best = s
    if best is None or best_d > radius_km:
        return None
    return {
        "station_code": best["code"],
        "station_nom": best.get("nom"),
        "lat": best.get("lat"),
        "lon": best.get("lon"),
        "distance_km": round(best_d, 2),
        "urls": {"marees_gc_ca": _station_url(best["code"])},
    }


def cmd_sync(args: argparse.Namespace) -> int:
    region = args.region
    print(f"Téléchargement stations marées IWLS (région {region})…")
    stations = fetch_tide_stations(region=region, timeout=args.timeout)
    path = save_stations(stations, args.out, region=region)
    print(f"  {len(stations)} stations -> {path}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    result = get_tide_predictions(
        args.code,
        days=args.days,
        start_date=args.date,
        timeout=args.timeout,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0 if "error" not in result else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Marées IWLS (SHC)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sync = sub.add_parser("sync", help="Cache local des stations (région QUE)")
    p_sync.add_argument("--region", default=DEFAULT_REGION)
    p_sync.add_argument("--out", type=Path, default=STATIONS_PATH)
    p_sync.set_defaults(func=cmd_sync)

    p_get = sub.add_parser("get", help="Prédictions pleines/basses mers")
    p_get.add_argument("code", help="Code station (ex. 03045)")
    p_get.add_argument("--days", type=int, default=DEFAULT_DAYS)
    p_get.add_argument("--date", help="Date début YYYY-MM-DD")
    p_get.set_defaults(func=cmd_get)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
