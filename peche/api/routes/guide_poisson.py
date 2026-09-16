"""GET /api/guide-poisson — espèces au plan d'eau (guide MELCCFP)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from peche.guide_poisson.lookup import lookup_guide_poisson

router = APIRouter()


@router.get("/api/guide-poisson")
def get_guide_poisson(
    zone_id: int | None = Query(None),
    nom: str | None = Query(None),
    lon: float | None = Query(None),
    lat: float | None = Query(None),
) -> JSONResponse:
    result = lookup_guide_poisson(zone_id=zone_id, nom=nom, lon=lon, lat=lat)
    return JSONResponse(result, headers={"Cache-Control": "public, max-age=3600"})
