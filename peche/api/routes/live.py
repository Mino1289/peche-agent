"""Mesures live hydrométrie / marées pour les fiches carte."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from peche.hydromet import fetch_live_stations
from peche.tides import get_tide_predictions, get_water_level_live
from peche.tools import _build_station_links
from peche.cehq import fetch_cehq_history, is_cehq_station_id

router = APIRouter()

_LIVE_HYDRO: tuple[float, list[dict]] | None = None
_LIVE_TTL_S = 60.0


def _live_hydromet_stations() -> list[dict]:
    global _LIVE_HYDRO
    now = time.monotonic()
    if _LIVE_HYDRO and now - _LIVE_HYDRO[0] < _LIVE_TTL_S:
        return _LIVE_HYDRO[1]
    stations = fetch_live_stations()
    _LIVE_HYDRO = (now, stations)
    return stations


@router.get("/api/hydromet/{station_id}")
def hydromet_station(
    station_id: str,
    include_history: bool = Query(False),
) -> JSONResponse:
    sid = str(station_id)
    s = next((row for row in _live_hydromet_stations() if row["station"] == sid), None)
    if s is None:
        raise HTTPException(status_code=404, detail="Station introuvable")
    payload: dict = {
        "station_id": s["station"],
        "plan_eau": s.get("plan_eau"),
        "description": s.get("description"),
        "lat": s.get("lat"),
        "lon": s.get("lon"),
        "etat": s.get("etat"),
        "niveau_m": s.get("niveau_m"),
        "debit_m3s": s.get("debit_m3s"),
        "observed_at": s.get("observed_at"),
        "urls": _build_station_links(s),
        "source": "Vigilance WFS",
    }
    if include_history and is_cehq_station_id(sid, s.get("fournisseur_url")):
        history = fetch_cehq_history(sid)
        if history:
            payload["history"] = history
    return JSONResponse(payload)


@router.get("/api/tides/{station_code}")
def tide_station(
    station_code: str,
    days: int = Query(2, ge=1, le=7),
) -> JSONResponse:
    live = get_water_level_live(station_code)
    pred = get_tide_predictions(station_code, days=days)
    if pred.get("error") and live.get("error"):
        raise HTTPException(
            status_code=404,
            detail=str(pred.get("error") or live.get("error")),
        )
    out = dict(pred)
    if not live.get("error"):
        out["niveau_m"] = live.get("niveau_m")
        out["observed_at"] = live.get("observed_at_local") or live.get("observed_at_utc")
        out["observation"] = live
    if pred.get("error"):
        out["predictions_error"] = pred["error"]
    return JSONResponse(out)
