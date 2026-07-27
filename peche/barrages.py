"""Répertoire des barrages CEHQ — sync, recherche et proximité.

Source : https://www.cehq.gouv.qc.ca/barrages/ (version téléchargeable Excel).

CLI :
  python3 -m peche.barrages sync
  python3 -m peche.barrages search Kénogami
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from peche.fetch import fetch_bytes, fetch_text
from peche.hydromet import haversine_km
from peche.matching.normalize import expand_abbreviations, normalize_search_text
from peche.reglements.sync import DATA_DIR

CEHQ_BARRAGES_PAGE = "https://www.cehq.gouv.qc.ca/barrages/default.asp"
DEFAULT_XLS_URL = (
    "https://www.cehq.gouv.qc.ca/depot/Barrages/bd/repertoire_des_barrages.xls"
)
FICHE_URL = "https://www.cehq.gouv.qc.ca/barrages/default.asp"

BARRAGES_DIR = DATA_DIR / "barrages"
CSV_PATH = BARRAGES_DIR / "barrages.csv"
JSON_PATH = BARRAGES_DIR / "barrages.json"
CACHE_XLS = DATA_DIR / "cache" / "barrages-source.xls"

DEFAULT_RADIUS_KM = 10.0
DEFAULT_TIMEOUT = 60.0

_CSV_FIELDS = (
    "numero",
    "nom",
    "plan_eau",
    "municipalite",
    "mrc",
    "categorie",
    "lat",
    "lon",
    "url_fiche",
)

_FISHING_CONTEXT = (
    "Présence d'ouvrages à proximité — zones de retenue, déversoirs et structures "
    "bétonnées peuvent concentrer les poissons (bord de barrage, fosses d'aval, "
    "courants). À croiser avec les règlements et `get_fishing_advice`."
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _resolve_xls_url(timeout: float = DEFAULT_TIMEOUT) -> str:
    html = fetch_text(CEHQ_BARRAGES_PAGE, timeout=timeout)
    match = re.search(
        r'href=["\']([^"\']*repertoire_des_barrages\.xls)["\']',
        html,
        re.I,
    )
    if match:
        return urljoin(CEHQ_BARRAGES_PAGE, match.group(1))
    return DEFAULT_XLS_URL


def _plan_eau_from_row(lac: Any, cours: Any) -> str:
    parts: list[str] = []
    for raw in (lac, cours):
        text = str(raw or "").strip()
        if text and text.lower() not in ("nan", "—", "-"):
            parts.append(text)
    return " / ".join(dict.fromkeys(parts))


def _parse_coord(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return None
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text or text.lower() in ("nan", "—", "-"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _is_data_row(numero: Any) -> bool:
    text = str(numero or "").strip()
    if not text or text.lower() in ("nan", "mis à jour"):
        return False
    return text.upper().startswith("X")


def parse_xls_bytes(data: bytes) -> list[dict]:
    """Parse le classeur CEHQ et retourne les barrages dédupliqués."""
    import pandas as pd

    df = pd.read_excel(io.BytesIO(data), header=1, engine="xlrd")
    seen: set[str] = set()
    out: list[dict] = []

    for _, row in df.iterrows():
        numero = str(row.get("Numéro du barrage", "")).strip()
        if not _is_data_row(numero):
            continue
        if numero in seen:
            continue
        lat = _parse_coord(row.get("Latitude (NAD 83)"))
        lon = _parse_coord(row.get("Longitude (NAD 83)"))
        if lat is None or lon is None:
            continue
        seen.add(numero)
        nom = str(row.get("Nom du barrage", "") or "").strip() or None
        out.append(
            {
                "numero": numero,
                "nom": nom,
                "plan_eau": _plan_eau_from_row(row.get("Lac"), row.get("Cours d'eau")),
                "municipalite": str(row.get("Municipalité", "") or "").strip() or None,
                "mrc": str(row.get("MRC", "") or "").strip() or None,
                "categorie": str(row.get("Catégorie administrative", "") or "").strip()
                or None,
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "url_fiche": FICHE_URL,
            }
        )
    return out


def save_barrages(
    barrages: list[dict],
    *,
    csv_path: Path = CSV_PATH,
    json_path: Path = JSON_PATH,
    source_url: str = DEFAULT_XLS_URL,
) -> tuple[Path, Path]:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS, delimiter=";")
        writer.writeheader()
        for b in barrages:
            writer.writerow({k: b.get(k, "") for k in _CSV_FIELDS})

    payload = {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source_url,
        "nb_barrages": len(barrages),
        "barrages": barrages,
    }
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return csv_path, json_path


def load_barrages(path: Path = JSON_PATH) -> list[dict]:
    if not path.exists():
        if CSV_PATH.exists():
            return _load_from_csv(CSV_PATH)
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("barrages", [])


def _load_from_csv(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            lat = _parse_coord(row.get("lat"))
            lon = _parse_coord(row.get("lon"))
            if lat is None or lon is None:
                continue
            rows.append(
                {
                    "numero": row.get("numero", "").strip(),
                    "nom": row.get("nom") or None,
                    "plan_eau": row.get("plan_eau") or "",
                    "municipalite": row.get("municipalite") or None,
                    "mrc": row.get("mrc") or None,
                    "categorie": row.get("categorie") or None,
                    "lat": lat,
                    "lon": lon,
                    "url_fiche": row.get("url_fiche") or FICHE_URL,
                }
            )
    return rows


@lru_cache(maxsize=1)
def _barrages_cached() -> list[dict]:
    return load_barrages()


def sync_barrages(
    *,
    xls_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    cache_path: Path = CACHE_XLS,
) -> list[dict]:
    url = xls_url or _resolve_xls_url(timeout=timeout)
    data = fetch_bytes(url, timeout=timeout)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    barrages = parse_xls_bytes(data)
    save_barrages(barrages, source_url=url)
    return barrages


def _score_barrage(query_norm: str, barrage: dict) -> float:
    fields = [
        barrage.get("nom") or "",
        barrage.get("plan_eau") or "",
        barrage.get("municipalite") or "",
        barrage.get("numero") or "",
    ]
    hay = _norm(" ".join(fields))
    q = _norm(query_norm)
    if not q:
        return 0.0
    if q in hay:
        return 1.0
    return SequenceMatcher(None, q, hay).ratio()


def search_barrages_offline(query: str, limit: int = 8) -> list[dict]:
    q = normalize_search_text(expand_abbreviations(query))
    scored: list[tuple[float, dict]] = []
    for b in _barrages_cached():
        score = _score_barrage(q, b)
        if score >= 0.45:
            scored.append((score, {**b, "score": round(score, 3)}))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


def nearest_barrages(
    lat: float,
    lon: float,
    *,
    radius_km: float = DEFAULT_RADIUS_KM,
    limit: int = 20,
) -> list[dict]:
    radius_km = min(radius_km, DEFAULT_RADIUS_KM)
    hits: list[dict] = []
    for b in _barrages_cached():
        blat, blon = b.get("lat"), b.get("lon")
        if blat is None or blon is None:
            continue
        dist = haversine_km(lat, lon, float(blat), float(blon))
        if dist <= radius_km:
            hits.append({**b, "distance_km": round(dist, 2)})
    hits.sort(key=lambda x: x["distance_km"])
    return hits[:limit]


def barrages_near_response(
    *,
    lat: float,
    lon: float,
    label: str,
    radius_km: float = DEFAULT_RADIUS_KM,
    extra: dict | None = None,
) -> dict:
    radius_km = min(radius_km, DEFAULT_RADIUS_KM)
    hits = nearest_barrages(lat, lon, radius_km=radius_km)
    out: dict[str, Any] = {
        "label": label,
        "lat": lat,
        "lon": lon,
        "radius_km": radius_km,
        "barrages": hits,
        "count": len(hits),
        "fishing_context": _FISHING_CONTEXT,
        "source": "cehq_repertoire_barrages",
        "urls": {"repertoire_cehq": CEHQ_BARRAGES_PAGE},
    }
    if extra:
        out.update(extra)
    if not hits:
        out["error_no_barrage"] = (
            f"Aucun barrage du répertoire CEHQ à moins de {radius_km:g} km."
        )
    return out


def cmd_sync(args: argparse.Namespace) -> int:
    url = args.url or _resolve_xls_url(timeout=args.timeout)
    print(f"Téléchargement {url}…")
    barrages = sync_barrages(xls_url=url, timeout=args.timeout, cache_path=args.cache)
    print(f"  {len(barrages)} barrages -> {CSV_PATH}")
    print(f"  JSON -> {JSON_PATH}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    hits = search_barrages_offline(args.query, limit=args.limit)
    json.dump(hits, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


def cmd_near(args: argparse.Namespace) -> int:
    result = barrages_near_response(
        lat=args.lat,
        lon=args.lon,
        label=args.label or "point",
        radius_km=args.radius,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Répertoire des barrages CEHQ")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sync = sub.add_parser("sync", help="Télécharger XLS et produire CSV/JSON")
    p_sync.add_argument("--url", default=None)
    p_sync.add_argument("--cache", type=Path, default=CACHE_XLS)
    p_sync.set_defaults(func=cmd_sync)

    p_search = sub.add_parser("search", help="Recherche locale par nom / cours d'eau")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=8)
    p_search.set_defaults(func=cmd_search)

    p_near = sub.add_parser("near", help="Barrages proches d'un point")
    p_near.add_argument("--lat", type=float, required=True)
    p_near.add_argument("--lon", type=float, required=True)
    p_near.add_argument("--radius", type=float, default=DEFAULT_RADIUS_KM)
    p_near.add_argument("--label", default="point")
    p_near.set_defaults(func=cmd_near)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
