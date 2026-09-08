"""Sync des règlements : URL → cache HTML → JSON structuré → index global."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

from peche.fetch import fetch_text
from peche.reglements.parser import (
    build_endroits_catalog,
    group_rows,
    match_endroit_id,
    parse_endroits,
    parse_endroits_from_partial_grid,
    parse_grid_rows,
    parse_saison,
)
from peche.reglements.zones import ZONES, Zone

BASE_URL = "https://peche.faune.gouv.qc.ca/RegPec/fr/Info/Reglements"
PARTIAL_GRID_URL = (
    "https://peche.faune.gouv.qc.ca/RegPec/fr/Info/PartialGrilleReglementsPlanEau"
)
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
ZONES_DIR = DATA_DIR / "zones"
CACHE_DIR = DATA_DIR / "cache"
INDEX_PATH = DATA_DIR / "index.json"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def zone_page_url(zone_id: int) -> str:
    return f"{BASE_URL}?id_zone={zone_id}"


def endroit_page_url(zone_id: int, endro_id: int, saison_id: int) -> str:
    return f"{BASE_URL}?id_zone={zone_id}&id_endro={endro_id}&id_saisn={saison_id}"


def partial_grid_url(zone_id: int, saison_id: int) -> str:
    """URL de la grille HTML complète des plans d'eau d'une zone.

    Contourne la pagination (100 items) du combobox DevExpress de la page
    principale. Utilisé quand `parse_endroits` renvoie ≥ 100 items.
    """
    return f"{PARTIAL_GRID_URL}?id_zone={zone_id}&id_saisn={saison_id}&courantes=False"


def zone_json_path(zone_id: int) -> Path:
    return ZONES_DIR / f"{zone_id}.json"


def load_zone_page(
    zone: Zone,
    cache_dir: Path,
    timeout: float,
    skip_existing: bool,
) -> str:
    zone_cache = cache_dir / str(zone.value) / "zone.html"
    if skip_existing and zone_cache.exists():
        return zone_cache.read_text(encoding="utf-8")
    page_html = fetch_text(zone_page_url(zone.value), timeout=timeout)
    zone_cache.parent.mkdir(parents=True, exist_ok=True)
    zone_cache.write_text(page_html, encoding="utf-8")
    return page_html


def load_partial_grid(
    zone_id: int,
    saison_id: int,
    cache_dir: Path,
    timeout: float,
    skip_existing: bool,
) -> str:
    path = cache_dir / str(zone_id) / "grid.html"
    if skip_existing and path.exists():
        return path.read_text(encoding="utf-8")
    page_html = fetch_text(partial_grid_url(zone_id, saison_id), timeout=timeout)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page_html, encoding="utf-8")
    return page_html


def load_endroit_page(
    zone_id: int,
    endro_id: int,
    saison_id: int,
    cache_dir: Path,
    timeout: float,
    skip_existing: bool,
) -> str:
    path = cache_dir / str(zone_id) / f"{endro_id}.html"
    if skip_existing and path.exists():
        return path.read_text(encoding="utf-8")
    page_html = fetch_text(
        endroit_page_url(zone_id, endro_id, saison_id), timeout=timeout
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page_html, encoding="utf-8")
    return page_html


def save_zone_json(zone_data: dict) -> Path:
    ZONES_DIR.mkdir(parents=True, exist_ok=True)
    path = zone_json_path(zone_data["meta"]["zone_id"])
    path.write_text(
        json.dumps(zone_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


def sync_zone(
    zone: Zone,
    cache_dir: Path = CACHE_DIR,
    timeout: float = 30.0,
    delay: float = 0.3,
    skip_existing: bool = False,
    force: bool = False,
) -> dict:
    zone_path = zone_json_path(zone.value)
    if skip_existing and not force and zone_path.exists():
        print(f"{zone.text:30s} (id={zone.value}) [skipped, already synced]")
        return json.loads(zone_path.read_text(encoding="utf-8"))

    print(f"{zone.text} (id={zone.value})")
    fetched_at = now_iso()
    page_html = load_zone_page(zone, cache_dir, timeout, skip_existing)
    saison_id, saison_text = parse_saison(page_html)

    # On utilise systématiquement la grille partielle pour l'inventaire des
    # plans d'eau (le combobox DevExpress plafonne à 100 items). On garde le
    # combobox uniquement comme fallback si la grille n'est pas joignable.
    endroits: list[dict] = []
    try:
        partial_html = load_partial_grid(
            zone.value, saison_id, cache_dir, timeout, skip_existing
        )
        endroits = parse_endroits_from_partial_grid(partial_html)
    except (HTTPError, URLError, OSError) as exc:
        print(f"  WARN partial grid indisponible ({exc}), fallback combobox")
    if not endroits:
        endroits = parse_endroits(page_html)

    zone_data: dict = {
        "meta": {
            "zone_id": zone.value,
            "zone_nom": zone.text,
            "saison_id": saison_id,
            "saison": saison_text,
            "fetched_at": fetched_at,
            "source_url": zone_page_url(zone.value),
            "nb_endroits_total": len(endroits),
            "nb_endroits_avec_id": sum(1 for e in endroits if e.get("id") is not None),
        },
        "regles_generales": group_rows(
            parse_grid_rows(page_html, "GrilleReglementsZonePeche")
        ),
        "plans_eau": [],
    }

    ids_to_fetch = {
        int(endroit["id"]) for endroit in endroits if endroit.get("id") is not None
    }
    endroit_pages: dict[int, str] = {}
    for index, endro_id in enumerate(sorted(ids_to_fetch)):
        endroit_pages[endro_id] = load_endroit_page(
            zone.value, endro_id, saison_id, cache_dir, timeout, skip_existing
        )
        if delay and index < len(ids_to_fetch) - 1:
            time.sleep(delay)

    catalog = build_endroits_catalog(page_html, *endroit_pages.values())
    newly_resolved = 0
    for endroit in endroits:
        if endroit.get("id") is not None:
            continue
        plan_label = str(endroit.get("plan_label") or endroit["nom"])
        resolved_id = match_endroit_id(plan_label, catalog)
        if resolved_id is None:
            continue
        endroit["id"] = resolved_id
        endroit.pop("segment_only", None)
        newly_resolved += 1
        if resolved_id in endroit_pages:
            continue
        if delay:
            time.sleep(delay)
        endroit_pages[resolved_id] = load_endroit_page(
            zone.value, resolved_id, saison_id, cache_dir, timeout, skip_existing
        )
        catalog.update(build_endroits_catalog(endroit_pages[resolved_id]))

    if newly_resolved:
        zone_data["meta"]["nb_endroits_avec_id"] = sum(
            1 for e in endroits if e.get("id") is not None
        )
        print(f"  {newly_resolved} plan(s) résolu(s) via combobox id_endro")

    fetched_count = 0
    seen_ids: set[int] = set()
    for endroit in endroits:
        endro_id = endroit.get("id")
        if endro_id is None:
            zone_data["plans_eau"].append(
                {
                    "id": None,
                    "nom": endroit["nom"],
                    "segment_only": True,
                    "source_url": None,
                    "segments": [],
                }
            )
            continue
        endro_id = int(endro_id)
        if endro_id in seen_ids:
            continue
        seen_ids.add(endro_id)
        detail_html = endroit_pages[endro_id]
        zone_data["plans_eau"].append(
            {
                "id": endro_id,
                "nom": endroit["nom"],
                "source_url": endroit_page_url(zone.value, endro_id, saison_id),
                "segments": group_rows(
                    parse_grid_rows(detail_html, "GrilleReglementsPlansEau")
                ),
            }
        )
        fetched_count += 1
        print(f"  {endroit['nom'][:70]}")

    save_zone_json(zone_data)
    print(
        f"  -> {zone_path}  ({len(endroits)} entrées, "
        f"{fetched_count} avec page individuelle)"
    )
    return zone_data


def build_index(zones: list[Zone] | None = None) -> dict:
    zones = zones or ZONES
    entries = []
    for zone in zones:
        path = zone_json_path(zone.value)
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data["meta"]
        entries.append(
            {
                "zone_id": meta["zone_id"],
                "zone_nom": meta["zone_nom"],
                "saison": meta.get("saison", ""),
                "fetched_at": meta.get("fetched_at"),
                "nb_plans_eau": len(data.get("plans_eau", [])),
                "file": str(path.relative_to(DATA_DIR)),
            }
        )

    return {
        "updated_at": now_iso(),
        "source": BASE_URL,
        "zones": entries,
    }


def write_index(index: dict) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return INDEX_PATH
