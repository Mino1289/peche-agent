"""GET /api/point-context — contexte géographique d'un point lon/lat."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from peche.spatial.point_context import get_point_context

router = APIRouter()


@router.get("/api/point-context")
def point_context(
    lon: float = Query(..., description="Longitude WGS84"),
    lat: float = Query(..., description="Latitude WGS84"),
) -> JSONResponse:
    return JSONResponse(get_point_context(lon, lat))
