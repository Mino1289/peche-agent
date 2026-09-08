"""Détail d'un plan d'eau RegPec (règlements + géométrie) pour la sidebar."""

from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from peche.fetch import fetch_text
from peche.reglements.parser import group_rows, parse_grid_rows
from peche.reglements.sync import endroit_page_url
from peche.reglements.timeline import timeline_by_species
from peche.reglements.zones import display_number, resolve_zone_by_kind
from peche.spatial.plan_geom import fetch_plan_geometry, geometry_for_plan
from peche.tools import _load_zone, get_reglements, today

router = APIRouter()


def _live_plan_eau(zone_id: int, plan_id: int, saison_id: int) -> dict:
    """Fetch + parse une page RegPec individuelle (id_endro carte interactive)."""
    url = endroit_page_url(zone_id, plan_id, saison_id)
    html = fetch_text(url, timeout=45.0)
    segments = group_rows(parse_grid_rows(html, "GrilleReglementsPlansEau"))
    nom = ""
    if segments:
        nom = str(segments[0].get("segment") or "")
    return {
        "id": plan_id,
        "nom": nom,
        "source_url": url,
        "segments": segments,
        "live": True,
    }


def _day_from_query(date: str | None) -> date_cls:
    if date:
        return date_cls.fromisoformat(date)
    return today()


@router.get("/api/plans/{zone_ref}/{plan_id}")
def plan_detail(
    zone_ref: int,
    plan_id: int,
    date: str | None = None,
    id_kind: str = Query(
        "auto",
        description="auto | regpec (id interne) | display (numéro affiché)",
    ),
) -> JSONResponse:
    zone = resolve_zone_by_kind(zone_ref, id_kind=id_kind)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone introuvable")
    zone_id = zone.value
    day = _day_from_query(date)

    try:
        # Toujours charger la saison complète — le classement passé/présent/futur
        # se fait côté timeline.
        regs = get_reglements(
            zone_id=zone_id,
            plan_id=plan_id,
            only_in_effect=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if regs.get("error"):
        raise HTTPException(status_code=404, detail=regs["error"])

    plan = regs.get("plan_eau") or {}
    segs = plan.get("segments") or []
    if plan.get("error") or not segs:
        try:
            z = _load_zone(zone_id)
            saison_id = int(z["meta"]["saison_id"])
            live = _live_plan_eau(zone_id, plan_id, saison_id)
            if live["segments"] or not segs:
                plan = live
                regs["plan_eau"] = plan
                regs["source_url"] = live.get("source_url") or regs.get("source_url")
                segs = plan.get("segments") or []
        except Exception:  # noqa: BLE001
            pass

    lat = plan.get("lat")
    lon = plan.get("lon")
    if lat is None or lon is None:
        from peche.reglements.sync import DATA_DIR
        import json

        loc_path = DATA_DIR / "locations" / f"{zone_id}.json"
        if loc_path.exists():
            data = json.loads(loc_path.read_text(encoding="utf-8"))
            for loc in data.get("locations") or []:
                if loc.get("id") == plan_id:
                    lat, lon = loc.get("lat"), loc.get("lon")
                    plan = {**loc, **plan}
                    break

    geom = fetch_plan_geometry(zone_id, plan_id)
    if geom is None and lat is not None and lon is not None:
        geom = geometry_for_plan(
            zone_id, plan_id, float(lat), float(lon), plan.get("nom")
        )

    timeline = timeline_by_species(segs, day=day)

    return JSONResponse(
        {
            "kind": "plan",
            "zone_id": zone_id,
            "zone_nom": zone.text,
            "no_zone": display_number(zone),
            "plan_id": plan_id,
            "nom": plan.get("nom") or regs.get("plan_nom"),
            "lat": lat,
            "lon": lon,
            "source_url": plan.get("source_url") or regs.get("source_url"),
            "reglements": regs,
            "timeline": timeline,
            "geometry": geom,
        }
    )
