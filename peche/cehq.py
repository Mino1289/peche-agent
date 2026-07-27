"""Historique hydrométrique CEHQ (niveau / débit, ~7 derniers jours).

Source : `fichier_donnees.asp?NoStation={id}` — même données que le tableau
https://www.cehq.gouv.qc.ca/suivihydro/tableau.asp?NoStation=061004
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from peche.fetch import fetch_text

TZ_QC = ZoneInfo("America/Montreal")
CEHQ_BASE = "https://www.cehq.gouv.qc.ca/suivihydro"
CEHQ_EXPORT_URL = CEHQ_BASE + "/fichier_donnees.asp?NoStation={station_id}"
CEHQ_TABLEAU_URL = CEHQ_BASE + "/tableau.asp?NoStation={station_id}"
CEHQ_GRAPHIQUE_URL = CEHQ_BASE + "/graphique.asp?NoStation={station_id}"

_CACHE: dict[str, tuple[float, dict]] = {}
DEFAULT_TTL_SECONDS = 15 * 60


def is_cehq_station_id(station_id: str, fournisseur_url: str | None = None) -> bool:
    if fournisseur_url and "cehq.gouv.qc.ca" in fournisseur_url.lower():
        return True
    return bool(re.fullmatch(r"\d{6}", str(station_id).strip()))


def cehq_urls(station_id: str) -> dict[str, str]:
    sid = str(station_id).strip()
    return {
        "cehq": CEHQ_GRAPHIQUE_URL.format(station_id=sid),
        "cehq_tableau": CEHQ_TABLEAU_URL.format(station_id=sid),
        "cehq_export": CEHQ_EXPORT_URL.format(station_id=sid),
    }


def _norm_header(cell: str) -> str | None:
    s = unicodedata.normalize("NFKD", cell.strip())
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    if s == "date":
        return "date"
    if s == "heure":
        return "heure"
    if s.startswith("niveau"):
        return "niveau_m"
    if s.startswith("debit"):
        return "debit_m3s"
    return None


def _parse_fr_float(raw: str) -> float | None:
    s = raw.strip().replace(",", ".")
    if not s or s in {"-", "--", "na", "n/a"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_cehq_export(raw: str) -> list[dict]:
    """Parse le fichier tabulé CEHQ en liste de lectures chronologiques."""
    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []

    header_cells = re.split(r"\t+", lines[0])
    columns: list[str | None] = [_norm_header(c) for c in header_cells]
    if "date" not in columns or "heure" not in columns:
        return []

    readings: list[dict] = []
    for line in lines[1:]:
        cells = re.split(r"\t+", line.strip())
        row: dict[str, str | float] = {}
        for idx, key in enumerate(columns):
            if key is None or idx >= len(cells):
                continue
            val = cells[idx].strip()
            if key in ("date", "heure"):
                row[key] = val
            else:
                parsed = _parse_fr_float(val)
                if parsed is not None:
                    row[key] = parsed
        if "date" not in row or "heure" not in row:
            continue
        try:
            dt = datetime.strptime(
                f"{row['date']} {row['heure']}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=TZ_QC)
        except ValueError:
            continue
        entry: dict = {"observed_at": dt.isoformat()}
        if "niveau_m" in row:
            entry["niveau_m"] = row["niveau_m"]
        if "debit_m3s" in row:
            entry["debit_m3s"] = row["debit_m3s"]
        readings.append(entry)

    readings.sort(key=lambda r: r["observed_at"])
    return readings


def _downsample_hourly(readings: list[dict]) -> list[dict]:
    """Garde la dernière lecture de chaque heure (série plus légère pour l'UI)."""
    buckets: dict[str, dict] = {}
    for r in readings:
        dt = datetime.fromisoformat(r["observed_at"])
        key = dt.strftime("%Y-%m-%dT%H:00")
        buckets[key] = {
            **r,
            "observed_at": dt.replace(minute=0, second=0, microsecond=0).isoformat(),
        }
    return [buckets[k] for k in sorted(buckets)]


def _daily_summary(readings: list[dict]) -> list[dict]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in readings:
        day = r["observed_at"][:10]
        by_date[day].append(r)

    out: list[dict] = []
    for day in sorted(by_date):
        rows = by_date[day]
        item: dict = {"date": day}
        for field in ("niveau_m", "debit_m3s"):
            vals = [r[field] for r in rows if r.get(field) is not None]
            if not vals:
                continue
            item[f"{field}_mean"] = round(sum(vals) / len(vals), 3)
            item[f"{field}_min"] = round(min(vals), 3)
            item[f"{field}_max"] = round(max(vals), 3)
        out.append(item)
    return out


def _trend_label(readings: list[dict], field: str) -> str | None:
    vals = [r[field] for r in readings if r.get(field) is not None]
    if len(vals) < 8:
        return None
    first = sum(vals[: len(vals) // 4]) / max(len(vals) // 4, 1)
    last = sum(vals[-len(vals) // 4 :]) / max(len(vals) // 4, 1)
    if last > first * 1.03:
        return "en hausse"
    if last < first * 0.97:
        return "en baisse"
    return "stable"


def fetch_cehq_history(
    station_id: str,
    *,
    timeout: float = 30.0,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> dict | None:
    """Historique ~7 jours pour une station CEHQ, avec cache court."""
    sid = str(station_id).strip()
    now = time.monotonic()
    cached = _CACHE.get(sid)
    if cached and now - cached[0] < ttl_seconds:
        return cached[1]

    url = CEHQ_EXPORT_URL.format(station_id=sid)
    try:
        raw = fetch_text(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"CEHQ indisponible: {exc}", "source": url}

    readings = parse_cehq_export(raw)
    if not readings:
        return {"error": "Aucune donnée CEHQ parsée.", "source": url}

    has_level = any(r.get("niveau_m") is not None for r in readings)
    has_flow = any(r.get("debit_m3s") is not None for r in readings)
    daily = _daily_summary(readings)
    series = _downsample_hourly(readings)

    payload = {
        "station_id": sid,
        "source": url,
        "period_days": len(daily),
        "readings_count": len(readings),
        "has_niveau": has_level,
        "has_debit": has_flow,
        "first_observed_at": readings[0]["observed_at"],
        "last_observed_at": readings[-1]["observed_at"],
        "daily": daily,
        "series": series,
        "trend": {
            k: v
            for k, v in {
                "niveau_m": _trend_label(readings, "niveau_m") if has_level else None,
                "debit_m3s": _trend_label(readings, "debit_m3s") if has_flow else None,
            }.items()
            if v
        },
    }
    _CACHE[sid] = (now, payload)
    return payload
