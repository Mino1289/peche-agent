"""Classement des règlements : passé / en vigueur / à venir, par espèce."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from peche.dates import parse_period_range, today

Status = Literal["past", "current", "upcoming", "unknown"]


def classify_period(periode_text: str, day: date | None = None) -> Status:
    day = day or today()
    rng = parse_period_range(periode_text or "")
    if rng is None:
        return "unknown"
    start, end = rng
    if end < day:
        return "past"
    if start > day:
        return "upcoming"
    return "current"


def _row_from_espece(
    *,
    espece: dict[str, Any],
    periode: str,
    segment: str,
    status: Status,
    start: str | None,
    end: str | None,
) -> dict[str, Any]:
    return {
        "espece": espece.get("espece") or "",
        "periode": periode,
        "debut": start,
        "fin": end,
        "status": status,
        "segment": segment,
        "limite_prise": espece.get("limite_prise") or "",
        "limite_longueur": espece.get("limite_longueur") or "",
        "engin": espece.get("engin") or "",
        "note": espece.get("note") or "",
    }


def flatten_segments(
    segments: list[dict[str, Any]] | None,
    *,
    day: date | None = None,
) -> list[dict[str, Any]]:
    """Aplatit segments → lignes classées (une par espèce × période)."""
    day = day or today()
    rows: list[dict[str, Any]] = []
    for seg in segments or []:
        segment = str(seg.get("segment") or "")
        for per in seg.get("periodes") or []:
            periode = str(per.get("periode") or "")
            status = classify_period(periode, day)
            rng = parse_period_range(periode)
            start = rng[0].isoformat() if rng else None
            end = rng[1].isoformat() if rng else None
            for esp in per.get("especes") or []:
                if not isinstance(esp, dict):
                    continue
                rows.append(
                    _row_from_espece(
                        espece=esp,
                        periode=periode,
                        segment=segment,
                        status=status,
                        start=start,
                        end=end,
                    )
                )
    return rows


def timeline_by_species(
    segments: list[dict[str, Any]] | None,
    *,
    day: date | None = None,
) -> dict[str, Any]:
    """Regroupe par espèce avec past / current / upcoming."""
    day = day or today()
    rows = flatten_segments(segments, day=day)
    by_name: dict[str, dict[str, list]] = {}
    order: list[str] = []
    for row in rows:
        name = row["espece"] or "Autres / non précisé"
        if name not in by_name:
            by_name[name] = {"past": [], "current": [], "upcoming": [], "unknown": []}
            order.append(name)
        by_name[name][row["status"]].append(row)

    species = []
    for name in order:
        buckets = by_name[name]
        # Trier : current par début, upcoming par début, past par fin desc
        buckets["current"].sort(key=lambda r: r.get("debut") or "")
        buckets["upcoming"].sort(key=lambda r: r.get("debut") or "")
        buckets["past"].sort(key=lambda r: r.get("fin") or "", reverse=True)
        species.append(
            {
                "espece": name,
                "current": buckets["current"],
                "upcoming": buckets["upcoming"],
                "past": buckets["past"],
                "unknown": buckets["unknown"],
                "has_current": bool(buckets["current"]),
            }
        )

    # Espèces en vigueur d'abord
    species.sort(key=lambda s: (0 if s["has_current"] else 1, s["espece"].lower()))

    return {
        "as_of": day.isoformat(),
        "species": species,
        "counts": {
            "current": sum(len(s["current"]) for s in species),
            "upcoming": sum(len(s["upcoming"]) for s in species),
            "past": sum(len(s["past"]) for s in species),
        },
    }
