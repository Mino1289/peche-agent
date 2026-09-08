"""GET /api/catalog — catalogue de couches curées."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from peche.catalog.harvest import ensure_catalog

router = APIRouter()


@router.get("/api/catalog")
def get_catalog() -> JSONResponse:
    catalog = ensure_catalog()
    return JSONResponse(
        catalog.to_dict(),
        headers={"Cache-Control": "no-store"},
    )
