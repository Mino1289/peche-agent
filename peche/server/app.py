"""FastAPI app : /api/chat (SSE), /api/reset, /api/health."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from peche import DOTENV_LOADED
from peche.reglements.sync import DATA_DIR, INDEX_PATH
from peche.server.chat import router as chat_router

LOCATIONS_DIR = DATA_DIR / "locations"
HYDROMET_STATIONS = DATA_DIR / "hydromet" / "stations.json"


def create_app() -> FastAPI:
    app = FastAPI(title="peche-agent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)

    @app.get("/api/map/features")
    def map_features(
        bbox: str,
        zoom: int = 10,
        layers: str = "lce,bassins",
    ) -> JSONResponse:
        """Entités spatiales dans le viewport (lon_min,lat_min,lon_max,lat_max)."""
        from peche.spatial.viewport import features_in_bbox

        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError("bbox must have 4 values")
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        query = (parts[0], parts[1], parts[2], parts[3])
        out: dict = {}
        for layer in layers.split(","):
            layer = layer.strip()
            if layer:
                out[layer] = features_in_bbox(layer, query, zoom)
        return JSONResponse({"bbox": parts, "zoom": zoom, "layers": out})

    @app.get("/api/health")
    def health() -> JSONResponse:
        zones_ok = INDEX_PATH.exists()
        locations_ok = LOCATIONS_DIR.exists() and any(LOCATIONS_DIR.glob("*.json"))
        stations_ok = HYDROMET_STATIONS.exists()
        api_key = bool(
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        )

        zones_count = 0
        if zones_ok:
            try:
                idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
                zones_count = len(idx.get("zones", []))
            except Exception:  # noqa: BLE001
                zones_ok = False

        ready = zones_ok and locations_ok and stations_ok and api_key
        message = None
        if not ready:
            missing = []
            if not zones_ok:
                missing.append(
                    "data/zones (lancer `python3 -m peche.reglements sync`)"
                )
            if not locations_ok:
                missing.append(
                    "data/locations (lancer `python3 -m peche.coords extract`)"
                )
            if not stations_ok:
                missing.append(
                    "data/hydromet/stations.json (lancer "
                    "`python3 -m peche.hydromet sync-stations`)"
                )
            if not api_key:
                missing.append("GEMINI_API_KEY (env ou .env)")
            message = "Prérequis manquants : " + " ; ".join(missing)

        return JSONResponse(
            {
                "data_ready": ready,
                "zones_count": zones_count,
                "zones_ok": zones_ok,
                "locations_ok": locations_ok,
                "stations_ok": stations_ok,
                "api_key": api_key,
                "dotenv_loaded": DOTENV_LOADED,
                "message": message,
                "model": os.environ.get("LLM_MODEL", "gemini-2.5-flash"),
            }
        )

    return app


app = create_app()
