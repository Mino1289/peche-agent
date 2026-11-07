"""GET/POST /api/point-context — contexte géographique d'un point lon/lat."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from peche.spatial.point_context import get_point_context

router = APIRouter()


class CustomLayerAtPoint(BaseModel):
    id: str
    title: str = ""
    url: str
    layer_name: str = ""
    source_type: str = "wms"


class PointContextBody(BaseModel):
    lon: float
    lat: float
    layers: list[str] | None = None
    custom_layers: list[CustomLayerAtPoint] | None = None


def _point_context_response(
    lon: float,
    lat: float,
    visible: list[str],
    custom_layers: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    payload = get_point_context(
        lon,
        lat,
        visible_layers=visible,
        custom_layers=custom_layers,
    )
    return JSONResponse(payload)


@router.get("/api/point-context")
def point_context(
    lon: float = Query(..., description="Longitude WGS84"),
    lat: float = Query(..., description="Latitude WGS84"),
    layers: str | None = Query(
        None,
        description="Couches visibles (ids séparés par des virgules)",
    ),
) -> JSONResponse:
    visible = [x.strip() for x in (layers or "").split(",") if x.strip()]
    return _point_context_response(lon, lat, visible)


@router.post("/api/point-context")
def point_context_post(body: PointContextBody) -> JSONResponse:
    custom = [c.model_dump() for c in body.custom_layers or []]
    return _point_context_response(
        body.lon,
        body.lat,
        body.layers or [],
        custom_layers=custom,
    )
