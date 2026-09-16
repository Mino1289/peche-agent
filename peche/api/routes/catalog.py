"""GET /api/catalog — catalogue de couches curées."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from peche.catalog.discover import discover_layers, validate_custom_layer
from peche.catalog.harvest import ensure_catalog

router = APIRouter()


@router.get("/api/catalog")
def get_catalog() -> JSONResponse:
    catalog = ensure_catalog()
    return JSONResponse(
        catalog.to_dict(),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/catalog/discover")
def catalog_discover(
    q: str = Query("", description="Recherche dans GetCapabilities"),
    limit: int = Query(40, ge=1, le=100),
) -> JSONResponse:
    items = discover_layers(q, limit=limit)
    return JSONResponse(
        {"query": q, "layers": items},
        headers={"Cache-Control": "no-store"},
    )


class ValidateLayerBody(BaseModel):
    url: str
    layer_name: str
    source_type: str = Field(default="wms", pattern="^(?i:wms|wfs)$")


@router.post("/api/catalog/validate")
def catalog_validate(body: ValidateLayerBody) -> JSONResponse:
    result: dict[str, Any] = validate_custom_layer(
        url=body.url,
        layer_name=body.layer_name,
        source_type=body.source_type.lower(),
    )
    status = 200 if result.get("ok") else 400
    return JSONResponse(result, status_code=status)
