"""Sync CKAN → index compact zone + nom + espèces."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from peche.fetch import fetch_bytes, fetch_text
from peche.guide_poisson.lookup import INDEX_PATH, GUIDE_URL
from peche.guide_poisson.names import uninvert_hydronyme
from peche.matching.normalize import normalize_search_text
from peche.reglements.sync import DATA_DIR
from peche.spatial.ckan import CKAN_API, package_show
from peche.spatial.point_context import fishing_zone_at_point

PACKAGE_ID = "guide-de-consommation-du-poisson-de-peche-sportive-en-eau-douce"
OUTPUT_DIR = DATA_DIR / "guide_poisson"
CACHE_CSV = DATA_DIR / "cache" / "guide_poisson.csv"


def _pick_resource_url() -> str:
    pkg = package_show(PACKAGE_ID)
    for res in pkg.get("resources") or []:
        fmt = (res.get("format") or "").lower()
        name = (res.get("name") or "").lower()
        if "csv" in fmt or "csv" in name:
            url = res.get("url")
            if url:
                return url
    for res in pkg.get("resources") or []:
        fmt = (res.get("format") or "").lower()
        if fmt in {"zip", "x-zip-compressed"}:
            url = res.get("url")
            if url:
                return url
    raise RuntimeError(f"Aucune ressource CSV/zip pour {PACKAGE_ID}")


def _download_csv(*, cache_path: Path = CACHE_CSV) -> Path:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    url = _pick_resource_url()
    data = fetch_bytes(url, timeout=180.0)
    if url.lower().endswith(".zip") or data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise RuntimeError("Archive sans CSV")
            cache_path.write_bytes(zf.read(names[0]))
    else:
        cache_path.write_bytes(data)
    return cache_path


def _col(row: dict[str, str], *keys: str) -> str:
    lower_map = {
        k.lower(): v for k, v in row.items() if k is not None and str(k).strip()
    }
    for key in keys:
        val = lower_map.get(key.lower())
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _float_val(raw: str) -> float | None:
    try:
        v = float(str(raw).replace(",", ".").strip())
        if not (-180 <= v <= 180):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _site_id(nom: str, lon: float, lat: float) -> str:
    key = f"{nom}|{lon:.5f}|{lat:.5f}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def build_index(rows: list[dict[str, str]]) -> dict[str, Any]:
    sites: dict[str, dict[str, Any]] = {}
    species_by_site: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        hyd_raw = _col(row, "HYDRONYME", "hydronyme")
        if not hyd_raw:
            continue
        nom = uninvert_hydronyme(hyd_raw)
        lon = _float_val(_col(row, "LONGITUDE", "longitude", "X", "lon"))
        lat = _float_val(_col(row, "LATITUDE", "latitude", "Y", "lat"))
        if lon is None or lat is None:
            continue

        sid = _site_id(nom, lon, lat)
        if sid not in sites:
            zone = fishing_zone_at_point(lon, lat) or {}
            sites[sid] = {
                "id": sid,
                "nom": nom,
                "nom_norm": normalize_search_text(nom),
                "zone_id": zone.get("zone_id"),
                "lon": lon,
                "lat": lat,
                "bassin": _col(row, "BV_N1M", "bassin"),
                "zgiebv": _col(row, "ZGIEBV", "zgiebv"),
            }

        species = {
            "nom_commun": _col(row, "NOM_COMMUN", "nom_commun"),
            "nom_latin": _col(row, "NOM_LATIN", "nom_latin"),
            "autres_noms": _col(row, "AUTRES_NOMS", "autres_noms"),
            "statut": _col(row, "STATUT_PECHE", "statut_peche"),
            "repas_p": _col(row, "P_NB_REPAS", "p_nb_repas"),
            "repas_m": _col(row, "M_NB_REPAS", "m_nb_repas"),
            "repas_g": _col(row, "G_NB_REPAS", "g_nb_repas"),
        }
        if not species["nom_commun"]:
            continue
        species_by_site.setdefault(sid, []).append(species)

    site_list = sorted(sites.values(), key=lambda s: (s.get("zone_id") or 0, s.get("nom") or ""))
    return {
        "version": 1,
        "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_id": PACKAGE_ID,
        "source_url": f"{CKAN_API}/package_show?id={PACKAGE_ID}",
        "guide_url": GUIDE_URL,
        "sites": site_list,
        "species_by_site": species_by_site,
    }


def sync(*, skip_download: bool = False) -> Path:
    """Télécharge le CSV CKAN et écrit data/guide_poisson/index.json."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if skip_download and CACHE_CSV.exists():
        csv_path = CACHE_CSV
        print(f"Lecture cache {csv_path}")
    else:
        print(f"Téléchargement {PACKAGE_ID}…")
        csv_path = _download_csv()
        print(f"  → {csv_path}")

    text = csv_path.read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rows = list(reader)
    print(f"  {len(rows)} lignes CSV")

    index = build_index(rows)
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Écrit {INDEX_PATH} "
        f"({len(index['sites'])} sites, "
        f"{sum(len(v) for v in index['species_by_site'].values())} espèces)"
    )
    return INDEX_PATH


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Sync guide consommation poisson")
    parser.add_argument(
        "command",
        nargs="?",
        default="sync",
        choices=["sync"],
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Réutiliser data/cache/guide_poisson.csv",
    )
    args = parser.parse_args(argv)
    if args.command == "sync":
        sync(skip_download=args.skip_download)


if __name__ == "__main__":
    main()
