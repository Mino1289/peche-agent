"""Zones de pêche — géométries GeoJSON + règlements de zone."""

from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from peche.reglements.timeline import timeline_by_species
from peche.reglements.zones import (
    ZONES,
    display_number,
    resolve_zone_by_kind,
    resolve_zone_ref,
    zone_by_id,
)
from peche.spatial.point_context import fishing_zone_at_point
from peche.spatial.zones_peche import get_zone_geometry, load_zones_geojson
from peche.tools import get_reglements, today

router = APIRouter()


@router.get("/api/zones")
def zones_list() -> JSONResponse:
    """Liste des zones de pêche (sélecteur UI)."""
    return JSONResponse(
        [
            {
                "zone_id": zone.value,
                "zone_nom": zone.text,
                "no_zone": display_number(zone),
            }
            for zone in ZONES
        ]
    )


@router.get("/api/zones/geojson")
def zones_geojson() -> JSONResponse:
    data = load_zones_geojson()
    if not data:
        return JSONResponse(
            {
                "type": "FeatureCollection",
                "features": [],
                "meta": {"message": "Lancer python3 -m peche.spatial zones-peche"},
            }
        )
    for feat in data.get("features") or []:
        props = feat.setdefault("properties", {})
        if "no_zone" not in props or props.get("no_zone") in (None, ""):
            z = zone_by_id(int(props.get("zone_id", -1)))
            if z:
                props["no_zone"] = str(display_number(z) or "")
                props["zone_nom"] = z.text
    return JSONResponse(data)


@router.get("/api/zones/at")
def zone_at_point(
    lon: float = Query(..., description="Longitude WGS84"),
    lat: float = Query(..., description="Latitude WGS84"),
) -> JSONResponse:
    """Zone de pêche au point (lookup local rapide, sans WFS)."""
    zone = fishing_zone_at_point(lon, lat)
    if not zone:
        raise HTTPException(status_code=404, detail="Aucune zone de pêche à cet endroit")
    return JSONResponse(zone)


@router.get("/api/zones/{zone_ref}/geometry")
def zone_geometry(zone_ref: int) -> JSONResponse:
    """Accepte le numéro affiché (28) ou l'id RegPec (32)."""
    zone = resolve_zone_ref(zone_ref)
    if zone:
        data = load_zones_geojson()
        if data:
            want = zone.value
            no_want = str(display_number(zone) or "")
            for feat in data.get("features") or []:
                props = feat.get("properties") or {}
                zid = props.get("zone_id")
                no = str(props.get("no_zone") or "")
                if zid is not None and int(zid) == want:
                    return JSONResponse(feat)
                if no_want and no == no_want:
                    return JSONResponse(feat)
        feat = get_zone_geometry(zone.value)
        if feat:
            return JSONResponse(feat)
    raise HTTPException(status_code=404, detail="Zone introuvable")


@router.get("/api/zones/resolve/{zone_ref}")
def resolve_zone(zone_ref: int) -> JSONResponse:
    zone = resolve_zone_ref(zone_ref)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone introuvable")
    return JSONResponse(
        {
            "zone_id": zone.value,
            "zone_nom": zone.text,
            "no_zone": display_number(zone),
        }
    )


@router.get("/api/zones/{zone_ref}/reglements")
def zone_reglements(
    zone_ref: int,
    date: str | None = Query(None),
    id_kind: str = Query(
        "auto",
        description="auto | regpec (id interne) | display (numéro affiché)",
    ),
) -> JSONResponse:
    """Règlements généraux de zone, classés passé / en vigueur / à venir."""
    zone = resolve_zone_by_kind(zone_ref, id_kind=id_kind)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone introuvable")
    day = date_cls.fromisoformat(date) if date else today()
    try:
        regs = get_reglements(zone_id=zone.value, plan_id=None, only_in_effect=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if regs.get("error"):
        raise HTTPException(status_code=404, detail=regs["error"])

    generals = regs.get("regles_generales") or []
    if generals and isinstance(generals[0], dict) and "periodes" in generals[0]:
        segments = generals
    else:
        segments = [{"segment": "Règles générales de zone", "periodes": generals}]

    timeline = timeline_by_species(segments, day=day)
    return JSONResponse(
        {
            "kind": "zone",
            "zone_id": zone.value,
            "zone_nom": zone.text,
            "no_zone": display_number(zone),
            "nom": zone.text,
            "source_url": regs.get("source_url"),
            "reglements": regs,
            "timeline": timeline,
            "as_of": day.isoformat(),
        }
    )
