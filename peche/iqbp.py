"""IQBP — Indice de Qualité Bactériologique et Physicochimique (MELCC).

Source : ArcGIS REST `Eau/IQBP/MapServer/0`. Les enregistrements sont des
points GPS (LATITUDE/LONGITUDE) avec :
- `NO_BQMA` : id station BQMA
- `HYDRONYME` : nom de la rivière
- `DESCRIPTION` : libellé long
- `IQBP_QUALI_STAT`, `IQBP_MED`, `IQBP_MOY` : indice et qualité
- 6 paramètres (NH3, CHLA, CF, MES, NOX, PTOT) avec leurs stats annuelles
- `URL_RE` (Atlas eau), `URL_DQ` (Données Québec)

L'IQBP est un indice annuel — pas un capteur temps réel. On stocke localement
le snapshot le plus récent par station (`STAT_FIN` le plus tardif), via la CLI
`python3 -m peche.iqbp sync`.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

from peche.fetch import fetch_text
from peche.reglements.sync import DATA_DIR

IQBP_BASE = (
    "https://geo.environnement.gouv.qc.ca/donnees/rest/services/Eau/IQBP/"
    "MapServer/0/query"
)
IQBP_URL = f"{IQBP_BASE}?where=1%3D1&outFields=*&f=geojson&resultRecordCount=2000"
IQBP_DIR = DATA_DIR / "iqbp"
IQBP_PATH = IQBP_DIR / "stations.json"

# Noms de paramètres IQBP « physicochimiques » : on garde les médianes
# (champs `*_MED_*`) qui sont les plus interprétables.
_PARAM_FIELDS: dict[str, list[str]] = {
    "azote_ammoniacal_mgL": ["NH3_MED_MGL"],
    "chlorophylle_a_ugL": ["CHLA_MED_UGL"],
    "coliformes_fecaux_UFC100mL": ["CF_MED_UFC"],
    "matieres_en_suspension_mgL": ["MES_MED_MGL"],
    "nitrites_nitrates_mgL": ["NOX_MED_MGL"],
    "phosphore_total_mgL": ["PTOT_MED_MGL"],
    "azote_total_mgL": ["NTOT_MED_MGL"],
}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _normalize_feature(feature: dict) -> dict | None:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates")
    if geom.get("type") != "Point" or not coords or len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    p = feature.get("properties") or {}

    parametres: dict[str, float | None] = {}
    for label, fields in _PARAM_FIELDS.items():
        v = next((p.get(f) for f in fields if p.get(f) is not None), None)
        if isinstance(v, (int, float)):
            parametres[label] = round(float(v), 4)
    return {
        "no_bqma": str(p.get("NO_BQMA", "")),
        "hydronyme": p.get("HYDRONYME") or "",
        "description": p.get("DESCRIPTION") or "",
        "iqbp_med": p.get("IQBP_MED"),
        "iqbp_moy": p.get("IQBP_MOY"),
        "iqbp_quali": p.get("IQBP_QUALI_STAT") or "",
        "annee": p.get("ANNEE"),
        "stat_debut": p.get("STAT_DEBUT"),
        "stat_fin": p.get("STAT_FIN"),
        "n_echant": p.get("N_ECHANT_STAT"),
        "parametres": parametres,
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "urls": {
            k: p[v]
            for k, v in (("atlas_eau", "URL_RE"), ("donnees_quebec", "URL_DQ"))
            if p.get(v)
        },
    }


def fetch_iqbp_stations(timeout: float = 60.0, page_size: int = 2000) -> list[dict]:
    """Récupère le snapshot IQBP entier en paginant via `resultOffset`.

    Le MapServer ArcGIS limite chaque page à 2000 features ; on continue tant
    qu'une page est pleine.
    """
    out: list[dict] = []
    offset = 0
    while True:
        url = (
            f"{IQBP_BASE}?where=1%3D1&outFields=*&f=geojson"
            f"&resultRecordCount={page_size}&resultOffset={offset}"
        )
        data = json.loads(fetch_text(url, timeout=timeout))
        features = data.get("features", [])
        if not features:
            break
        for feature in features:
            n = _normalize_feature(feature)
            if n:
                out.append(n)
        if len(features) < page_size:
            break
        offset += page_size
    return out


def keep_latest_per_station(stations: list[dict]) -> list[dict]:
    """Une station = plusieurs lignes (différentes années). On garde la plus
    récente par `NO_BQMA` (clé `STAT_FIN`)."""
    best: dict[str, dict] = {}
    for s in stations:
        sid = s["no_bqma"]
        if not sid:
            continue
        prev = best.get(sid)
        if prev is None or (s.get("stat_fin") or "") > (prev.get("stat_fin") or ""):
            best[sid] = s
    return sorted(best.values(), key=lambda s: s["no_bqma"])


def save_stations(stations: list[dict], path: Path = IQBP_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": IQBP_URL,
        "nb_stations": len(stations),
        "stations": stations,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_stations(path: Path = IQBP_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} introuvable — lancer `python3 -m peche.iqbp sync`."
        )
    return json.loads(path.read_text(encoding="utf-8"))["stations"]


def search_iqbp(query: str, limit: int = 8) -> list[dict]:
    """Cherche par NO_BQMA, hydronyme, ou description (fuzzy substr).

    Renvoie les snapshots les plus récents par station (déjà filtrés au sync).
    """
    if not query.strip():
        return []
    q = _norm(query)
    try:
        stations = load_stations()
    except FileNotFoundError as exc:
        return [{"error": str(exc)}]

    out = []
    for s in stations:
        sid = s["no_bqma"]
        score = 0.0
        if sid == query.strip():
            score = 1.0
        elif sid.startswith(query.strip()):
            score = 0.95
        if q and q in _norm(s["hydronyme"]):
            score = max(score, 0.85)
        if q and q in _norm(s["description"]):
            score = max(score, 0.7)
        if score == 0.0:
            continue
        out.append({**s, "score": round(score, 2)})
    out.sort(key=lambda s: s["score"], reverse=True)
    return out[:limit]


# ---------- CLI ----------


def cmd_sync(args: argparse.Namespace) -> int:
    print(f"Téléchargement IQBP MapServer ({IQBP_URL[:80]}…)")
    raw = fetch_iqbp_stations(timeout=args.timeout)
    latest = keep_latest_per_station(raw)
    path = save_stations(latest, args.out)
    print(f"  {len(raw)} enregistrements → {len(latest)} stations distinctes -> {path}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    hits = search_iqbp(args.query, limit=args.limit)
    print(json.dumps(hits, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="IQBP — qualité d'eau MELCC.")
    sub = p.add_subparsers(dest="command")
    s = sub.add_parser("sync", help="Cache IQBP MapServer en local.")
    s.add_argument("--out", type=Path, default=IQBP_PATH)
    s.add_argument("--timeout", type=float, default=60.0)
    s.set_defaults(func=cmd_sync)

    sh = sub.add_parser("show", help="Cherche dans le cache IQBP.")
    sh.add_argument("query")
    sh.add_argument("--limit", type=int, default=5)
    sh.set_defaults(func=cmd_show)
    return p


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
