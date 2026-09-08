"""GET /api/health."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from peche import DOTENV_LOADED
from peche.agent.credentials import server_has_api_key
from peche.catalog.harvest import CATALOG_PATH
from peche.reglements.sync import DATA_DIR, INDEX_PATH
from peche.spatial.zones_peche import OUTPUT_PATH as ZONES_PATH

router = APIRouter()


@router.get("/api/health")
def health() -> JSONResponse:
    zones_ok = INDEX_PATH.exists()
    locations_ok = (DATA_DIR / "locations").exists() and any(
        (DATA_DIR / "locations").glob("*.json")
    )
    stations_ok = (DATA_DIR / "hydromet" / "stations.json").exists()
    catalog_ok = CATALOG_PATH.exists()
    zones_peche_ok = ZONES_PATH.exists()
    server_api_key = server_has_api_key()
    mcp_enabled = os.environ.get("MCP_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    web_ok = (Path(__file__).resolve().parents[3] / "web" / "dist" / "index.html").exists()

    zones_count = 0
    if zones_ok:
        try:
            idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
            zones_count = len(idx.get("zones", []))
        except Exception:  # noqa: BLE001
            zones_ok = False

    ready = zones_ok and locations_ok and stations_ok
    return JSONResponse(
        {
            "data_ready": ready,
            "zones_count": zones_count,
            "zones_ok": zones_ok,
            "locations_ok": locations_ok,
            "stations_ok": stations_ok,
            "catalog_ok": catalog_ok,
            "zones_peche_ok": zones_peche_ok,
            "web_ok": web_ok,
            "server_api_key": server_api_key,
            "api_key": server_api_key,
            "mcp_enabled": mcp_enabled,
            "dotenv_loaded": DOTENV_LOADED,
            "model": os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite"),
            "fallback_model": os.environ.get(
                "LLM_MODEL_FALLBACK", "gemini-3.1-flash-lite"
            ),
        }
    )
