"""Proxy OGC avec cache disque — contourne CORS et limite les re-téléchargements."""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException, Query, Request as FastRequest
from fastapi.responses import Response

from peche.reglements.sync import DATA_DIR

router = APIRouter()

CACHE_DIR = DATA_DIR / "cache" / "ogc_proxy"
CACHE_TTL_S = 6 * 3600  # 6 h pour GetCapabilities / légendes
_GETMAP_TTL_S = 15 * 60  # tuiles GetMap — cache court
_UA = "peche-agent/1.0 (ogc-proxy)"

# Domaines autorisés (pas de proxy ouvert)
_ALLOWED_HOSTS = {
    "geoegl.msp.gouv.qc.ca",
    "servicescarto.mrnf.gouv.qc.ca",
    "servicesvecto3.mern.gouv.qc.ca",
    "servicesmatriciels.mern.gouv.qc.ca",
    "servicesvectoriels.atlas.gouv.qc.ca",
    "geo.environnement.gouv.qc.ca",
    "www.servicesgeo.enviroweb.gouv.qc.ca",
    "carto.cptaq.gouv.qc.ca",
    "maps.ducks.ca",
    "peche.faune.gouv.qc.ca",
}


def _allowed(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        return False
    return host in _ALLOWED_HOSTS


def _cache_path(url: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / digest[:2] / digest


def _is_getmap(url: str) -> bool:
    lower = url.lower()
    return "request=getmap" in lower


def _cache_ttl(url: str) -> int:
    return _GETMAP_TTL_S if _is_getmap(url) else CACHE_TTL_S


@router.api_route("/api/ogc", methods=["GET", "HEAD"])
def ogc_proxy(
    request: FastRequest,
    url: str = Query(..., description="URL OGC absolue à proxifier"),
):
    if not _allowed(url):
        raise HTTPException(status_code=400, detail="Hôte non autorisé")

    # Transmettre query string additionnelle (déjà dans `url` côté client)
    cache_path = _cache_path(url)
    now = time.time()
    ttl = _cache_ttl(url)
    if cache_path.exists() and now - cache_path.stat().st_mtime < ttl:
        data = cache_path.read_bytes()
        ctype = _guess_content_type(url, data)
        headers = {"Cache-Control": f"public, max-age={ttl}"}
        return Response(content=data, media_type=ctype, headers=headers)

    try:
        req = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
        with urlopen(req, timeout=60) as resp:  # noqa: S310
            data = resp.read()
            ctype = resp.headers.get("Content-Type") or _guess_content_type(url, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"Proxy OGC: {type(exc).__name__}: {exc}"
        ) from exc

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(data)
    headers = {"Cache-Control": f"public, max-age={ttl}"}
    return Response(content=data, media_type=ctype, headers=headers)


def _guess_content_type(url: str, data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    lower = url.lower()
    if "format=image/png" in lower or lower.endswith(".png"):
        return "image/png"
    if "format=image/jpeg" in lower or lower.endswith(".jpg"):
        return "image/jpeg"
    if data[:1] == b"{" or data[:1] == b"[":
        return "application/json"
    if data[:5] == b"<?xml" or data[:1] == b"<":
        return "application/xml"
    return "application/octet-stream"
