"""Données ouvertes Hydro-Québec (débits / niveaux) — même source que l'outil web.

Deux fichiers JSON (référencés par le widget crues.min.js sur le site HQ) :
  - stations hydrométriques / météo (rivières, etc.)
  - sites (installations : apports, déversés, turbinage, …)

Les séries temporelles complètes sont volumineuses ; on ne conserve que la dernière
valeur par série pour le cache carte / sync.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from typing import Any

from peche.cehq import build_history_payload
from peche.fetch import fetch_text

HQ_TOOL_PAGE = "https://www.hydroquebec.com/production/debits-niveaux-eau.html"

HQ_JSON_STATIONS = (
    "https://www.hydroquebec.com/data/documents-donnees/donnees-ouvertes/"
    "json/Donnees_VUE_STATIONS_ET_TARAGES.json"
)
HQ_JSON_SITES = (
    "https://www.hydroquebec.com/data/documents-donnees/donnees-ouvertes/"
    "json/Donnees_VUE_CENTRALES_ET_OUVRAGES.json"
)

_TS_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")


def _ts_sort_key(raw: str) -> tuple[int, ...]:
    m = _TS_RE.match(raw.strip())
    if not m:
        return (0, 0, 0, 0, 0, 0)
    return tuple(int(x) for x in m.groups())


def _ts_to_iso_z(raw: str) -> str:
    m = _TS_RE.match(raw.strip())
    if not m:
        return raw
    y, mo, d, h, mi, s = m.groups()
    return f"{y}-{mo}-{d}T{h}:{mi}:{s}Z"


def _parse_float(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _latest_in_donnees(donnees: Any) -> tuple[float | None, str | None]:
    if not isinstance(donnees, dict) or not donnees:
        return None, None
    last_key = max(donnees.keys(), key=_ts_sort_key)
    val = _parse_float(donnees.get(last_key))
    return val, _ts_to_iso_z(last_key)


def _composition_metrics(composition: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(composition, list):
        return out
    for block in composition:
        if not isinstance(block, dict):
            continue
        donnees = block.get("Donnees")
        val, obs = _latest_in_donnees(donnees)
        tpd_raw = block.get("type_point_donnee")
        tpd = tpd_raw.strip() if isinstance(tpd_raw, str) else ""
        unit = str(block.get("nom_unite_mesure") or "").strip()
        pt = str(block.get("pas_temps") or "").strip()
        tm = str(block.get("type_mesure") or "").strip()
        label_parts = [p for p in (tpd, tm, pt) if p]
        variable = " — ".join(label_parts) if label_parts else (unit or "mesure")
        out.append(
            {
                "variable": variable,
                "type_point_donnee": tpd,
                "nom_unite_mesure": unit,
                "pas_temps": pt,
                "type_mesure": tm,
                "valeur": val,
                "observed_at": obs,
            }
        )
    return out


def _ascii_lower(value: str) -> str:
    return (
        unicodedata.normalize("NFD", value)
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )


def _debit_series_tier(type_point_donnee: str) -> int:
    """0 = débit total rivière ; évite déversé/turbinage pour le débit « principal »."""
    key = _ascii_lower(type_point_donnee)
    if "debit total" in key:
        return 0
    if "devers" in key:
        return 3
    if "turbin" in key:
        return 2
    if "apport" in key:
        return 4
    return 1


def _pick_primary_niveau_debit(
    metrics: list[dict[str, Any]],
) -> tuple[Any, Any, str | None]:
    """Déduit niveau_m / debit_m3s à partir des unités HQ (affichage carte)."""
    niveau_m = None
    debit_m3s = None
    observed_at = None
    debit_tier = 99
    for m in metrics:
        u = (m.get("nom_unite_mesure") or "").lower()
        v = m.get("valeur")
        o = m.get("observed_at")
        if v is None:
            continue
        if "m³/s" in u or "m3/s" in u or "m^3/s" in u:
            tier = _debit_series_tier(str(m.get("type_point_donnee") or ""))
            if tier < debit_tier:
                debit_tier = tier
                debit_m3s = v
                observed_at = o or observed_at
        elif u == "m" and "neige" not in (m.get("type_point_donnee") or "").lower():
            niveau_m = v
            observed_at = o or observed_at
    return niveau_m, debit_m3s, observed_at


def _normalize_coords(x: Any, y: Any) -> tuple[float, float] | None:
    try:
        lon = float(str(x).strip())
        lat = float(str(y).strip())
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return round(lat, 6), round(lon, 6)


_HQ_WEATHER_KEYWORDS = ("temperature", "precipitation", "humidite", "vent", "neige")


def hq_tags(kind: str, metrics: list[dict[str, Any]]) -> list[str]:
    """Tags HQ : `installation` (centrale/ouvrage) ; sinon `meteo` et/ou `hydro`.

    Une station peut avoir les deux (ex. niveau + météo). `meteo` = au moins une
    mesure météo ; `hydro` = au moins un niveau (m) ou débit (m³/s).
    """
    if kind == "installation":
        return ["installation"]
    has_hydro = False
    has_meteo = False
    for m in metrics:
        unit = str(m.get("nom_unite_mesure") or "").strip().lower()
        tpd = _ascii_lower(str(m.get("type_point_donnee") or ""))
        if "m³/s" in unit or "m3/s" in unit or "m^3/s" in unit:
            has_hydro = True
        elif unit == "m" and "neige" not in tpd:
            has_hydro = True
        if tpd.startswith("temperature de l"):
            # Température de l'eau : mesure hydrique, pas météo.
            has_hydro = True
            continue
        if any(k in tpd for k in _HQ_WEATHER_KEYWORDS):
            has_meteo = True
    tags: list[str] = []
    if has_meteo:
        tags.append("meteo")
    if has_hydro:
        tags.append("hydro")
    return tags


def normalize_hq_records(kind: str, records: Any) -> list[dict[str, Any]]:
    """kind: 'station' | 'installation'."""
    if not isinstance(records, list):
        return []
    prefix = "S" if kind == "station" else "I"
    out: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("identifiant") or "").strip()
        if not ident:
            continue
        coords = _normalize_coords(row.get("xcoord"), row.get("ycoord"))
        if coords is None:
            continue
        lat, lon = coords
        nom = str(row.get("nom") or "").strip()
        metrics = _composition_metrics(row.get("Composition"))
        niveau_m, debit_m3s, obs = _pick_primary_niveau_debit(metrics)

        sid = f"HQ-{prefix}-{ident}"
        entry: dict[str, Any] = {
            "station": sid,
            "description": nom,
            "plan_eau": "",
            "fournisseur": "Hydro-Québec",
            "fournisseur_url": HQ_TOOL_PAGE,
            "url_vigilance": "",
            "etat": "",
            "previsions": "",
            "refoulement": "",
            "niveau_m": niveau_m,
            "debit_m3s": debit_m3s,
            "observed_at": obs,
            "lat": lat,
            "lon": lon,
            "source_sub": "hydroquebec_open",
            "hq_kind": kind,
            "hq_identifiant": ident,
            "hq_code_region": str(row.get("CodeRegionQC") or "").strip(),
            "hq_region": str(row.get("RegionQC") or "").strip(),
            "hq_metrics": metrics,
            "hq_tags": hq_tags(kind, metrics),
        }
        out.append(entry)
    return out


def fetch_hydroquebec_open_stations(timeout: float = 120.0) -> list[dict[str, Any]]:
    """Télécharge les deux vues HQ et renvoie des entrées « station » uniformes."""
    raw_s = fetch_text(HQ_JSON_STATIONS, timeout=timeout)
    raw_i = fetch_text(HQ_JSON_SITES, timeout=timeout)
    data_s = json.loads(raw_s)
    data_i = json.loads(raw_i)
    stations = normalize_hq_records("station", data_s.get("Station"))
    installations = normalize_hq_records("installation", data_i.get("Site"))
    return stations + installations


# Cache mémoire pour le détail API (évite de retélécharger ~17 Mo à chaque clic).
_HQ_DETAIL_CACHE: tuple[float, tuple[list[dict[str, Any]], list[dict[str, Any]]]] | None = (
    None
)
_HQ_DETAIL_TTL_S = 3600.0


def _load_hq_raw_pair(timeout: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    global _HQ_DETAIL_CACHE
    now = time.monotonic()
    if _HQ_DETAIL_CACHE and now - _HQ_DETAIL_CACHE[0] < _HQ_DETAIL_TTL_S:
        return _HQ_DETAIL_CACHE[1]
    raw_s = fetch_text(HQ_JSON_STATIONS, timeout=timeout)
    raw_i = fetch_text(HQ_JSON_SITES, timeout=timeout)
    data_s = json.loads(raw_s)
    data_i = json.loads(raw_i)
    pair = (
        data_s.get("Station") if isinstance(data_s.get("Station"), list) else [],
        data_i.get("Site") if isinstance(data_i.get("Site"), list) else [],
    )
    _HQ_DETAIL_CACHE = (now, pair)
    return pair


def _block_hydro_kind(block: dict[str, Any]) -> str | None:
    u = (block.get("nom_unite_mesure") or "").lower()
    tpd = str(block.get("type_point_donnee") or "").lower()
    if "m³/s" in u or "m3/s" in u or "m^3/s" in u:
        return "debit"
    if u == "m" and "neige" not in tpd:
        return "niveau"
    return None


def _best_composition_block(
    composition: Any, kind: str
) -> dict[str, Any] | None:
    if not isinstance(composition, list):
        return None
    best: dict[str, Any] | None = None
    best_key: tuple[int, int] = (99, 0)
    for block in composition:
        if not isinstance(block, dict) or _block_hydro_kind(block) != kind:
            continue
        donnees = block.get("Donnees")
        if not isinstance(donnees, dict) or not donnees:
            continue
        n = len(donnees)
        if kind == "debit":
            tier = _debit_series_tier(str(block.get("type_point_donnee") or ""))
            key = (tier, n)
        else:
            key = (0, n)
        if best is None or key < best_key:
            best = block
            best_key = key
    return best


def _readings_from_block(block: dict[str, Any], field: str) -> list[dict[str, Any]]:
    donnees = block.get("Donnees")
    if not isinstance(donnees, dict):
        return []
    out: list[dict[str, Any]] = []
    for ts_raw, val_raw in sorted(donnees.items(), key=lambda kv: _ts_sort_key(kv[0])):
        val = _parse_float(val_raw)
        if val is None:
            continue
        out.append({"observed_at": _ts_to_iso_z(str(ts_raw)), field: val})
    return out


def readings_from_hq_composition(composition: Any) -> list[dict[str, Any]]:
    """Fusionne la meilleure série niveau (m) et débit (m³/s) du JSON HQ."""
    level_block = _best_composition_block(composition, "niveau")
    flow_block = _best_composition_block(composition, "debit")
    level = _readings_from_block(level_block, "niveau_m") if level_block else []
    flow = _readings_from_block(flow_block, "debit_m3s") if flow_block else []
    if not level and not flow:
        return []
    by_ts: dict[str, dict[str, Any]] = {}
    for r in level:
        ts = r["observed_at"]
        by_ts.setdefault(ts, {"observed_at": ts})
        by_ts[ts]["niveau_m"] = r["niveau_m"]
    for r in flow:
        ts = r["observed_at"]
        by_ts.setdefault(ts, {"observed_at": ts})
        by_ts[ts]["debit_m3s"] = r["debit_m3s"]
    return [by_ts[k] for k in sorted(by_ts)]


def _parse_hq_station_id(station_id: str) -> tuple[str, str] | None:
    """Renvoie (kind, identifiant) pour `HQ-S-…` ou `HQ-I-…`."""
    sid = str(station_id).strip()
    parts = sid.split("-", 2)
    if len(parts) != 3 or parts[0] != "HQ":
        return None
    kind_key = parts[1].upper()
    ident = parts[2]
    if kind_key == "S":
        return "station", ident
    if kind_key == "I":
        return "installation", ident
    return None


def _find_hq_raw_row(station_id: str, timeout: float = 120.0) -> dict[str, Any] | None:
    parsed = _parse_hq_station_id(station_id)
    if not parsed:
        return None
    kind, ident = parsed
    st_list, site_list = _load_hq_raw_pair(timeout)
    source = st_list if kind == "station" else site_list
    for row in source:
        if not isinstance(row, dict):
            continue
        if str(row.get("identifiant") or "").strip() == ident:
            return row
    return None


def fetch_hydroquebec_history(
    station_id: str, timeout: float = 120.0
) -> dict[str, Any] | None:
    """Historique ~10 j depuis les `Donnees` du JSON ouvert HQ (même source que le site)."""
    row = _find_hq_raw_row(station_id, timeout=timeout)
    if not row:
        return None
    readings = readings_from_hq_composition(row.get("Composition"))
    if not readings:
        return None
    sid = str(station_id).strip()
    return build_history_payload(sid, readings, source="hydroquebec_open")


def get_hydroquebec_open_station(
    station_id: str, timeout: float = 120.0
) -> dict[str, Any] | None:
    """Reconstitue une entrée HQ à jour pour un id `HQ-S-…` ou `HQ-I-…`."""
    parsed = _parse_hq_station_id(station_id)
    if not parsed:
        return None
    kind, _ident = parsed
    row = _find_hq_raw_row(station_id, timeout=timeout)
    if not row:
        return None
    norm = normalize_hq_records(kind, [row])
    return norm[0] if norm else None
