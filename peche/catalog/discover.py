"""Découverte GetCapabilities à la demande (Forêt ouverte, sans fusion catalogue)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

from peche.catalog.harvest import (
    CAPS_CACHE_DIR,
    harvest_source,
    parse_wfs_capabilities,
    parse_wms_capabilities,
)
from peche.catalog.models import LayerDef
from peche.catalog.sources import (
    GEOSERVER_SOURCES,
    OgcSource,
    WMS_SOURCES,
    arcgis_sources,
)

_DISCOVER_SOURCES: list[OgcSource] | None = None

_ACCEPTED_CRS = {
    "epsg:3857",
    "epsg:4326",
    "crs:84",
    "ogc:1.3:crs84",
    "urn:ogc:def:crs:EPSG::3857",
    "urn:ogc:def:crs:EPSG::4326",
    "urn:ogc:def:crs:OGC:1.3:CRS84",
    "http://www.opengis.net/gml/srs/epsg.xml#3857",
    "http://www.opengis.net/gml/srs/epsg.xml#4326",
}


def discover_sources() -> list[OgcSource]:
    global _DISCOVER_SOURCES  # noqa: PLW0603
    if _DISCOVER_SOURCES is None:
        _DISCOVER_SOURCES = list(WMS_SOURCES) + list(GEOSERVER_SOURCES) + arcgis_sources()
    return _DISCOVER_SOURCES


def _source_by_url(url: str) -> OgcSource | None:
    base = url.split("?", 1)[0].rstrip("/")
    for src in discover_sources():
        if src.url.rstrip("/") == base:
            return src
    return None


def _make_source(url: str, *, kind: str) -> OgcSource:
    parsed = urlparse(url)
    host = parsed.hostname or "custom"
    sid = re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_") or "custom"
    return OgcSource(
        id=f"custom_{sid}",
        title=host,
        kind=kind,  # type: ignore[arg-type]
        url=url.split("?", 1)[0],
        group="autres",
        wfs_url=url.split("?", 1)[0] if kind == "wfs" else None,
        proxy=True,
    )


def _layers_for_source(source: OgcSource) -> list[LayerDef]:
    return harvest_source(source, cache_dir=CAPS_CACHE_DIR)


def warm_capabilities_cache() -> int:
    """Pré-télécharge les GetCapabilities utilisés par /api/catalog/discover."""
    sources = [s for s in discover_sources() if s.kind not in {"xyz", "wmts"}]
    workers = min(8, max(1, len(sources)))

    def warm_one(source: OgcSource) -> None:
        harvest_source(source, cache_dir=CAPS_CACHE_DIR)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(warm_one, sources))
    return len(sources)


def _normalize_crs(value: str) -> str:
    return value.strip().lower().replace(" ", "")


def _crs_ok(crs_values: list[str]) -> bool:
    if not crs_values:
        return False
    for raw in crs_values:
        norm = _normalize_crs(raw)
        if norm in _ACCEPTED_CRS:
            return True
        if "3857" in norm or "4326" in norm or "crs:84" in norm or "crs84" in norm:
            return True
    return False


def _wms_layer_crs(xml_bytes: bytes, layer_name: str) -> tuple[bool, list[str]]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml_bytes)  # noqa: S314
    crs_values: list[str] = []

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1] if "}" in tag else tag

    def collect_crs(el: ET.Element) -> None:
        for child in el:
            ln = local(child.tag)
            if ln in {"CRS", "SRS"} and child.text:
                crs_values.append(child.text.strip())

    target: ET.Element | None = None

    def walk(el: ET.Element) -> None:
        nonlocal target
        name = ""
        for child in el:
            ln = local(child.tag)
            if ln == "Name" and child.text:
                name = child.text.strip()
            elif ln == "Layer":
                walk(child)
        if name == layer_name:
            target = el

    for el in root.iter():
        if local(el.tag) == "Capability":
            for child in el:
                if local(child.tag) == "Layer":
                    walk(child)
            break

    if target is not None:
        collect_crs(target)
    if not crs_values:
        for el in root.iter():
            ln = local(el.tag)
            if ln in {"CRS", "SRS"} and el.text:
                crs_values.append(el.text.strip())
    return _crs_ok(crs_values), crs_values


def discover_layers(q: str = "", *, limit: int = 40) -> list[dict[str, Any]]:
    """Recherche dans les GetCapabilities (cache disque + récolte parallèle)."""
    needle = q.strip().lower()
    sources = [s for s in discover_sources() if s.kind not in {"xyz", "wmts"}]
    out: list[dict[str, Any]] = []

    def harvest_one(source: OgcSource) -> tuple[OgcSource, list[LayerDef]]:
        try:
            return source, _layers_for_source(source)
        except Exception:  # noqa: BLE001
            return source, []

    workers = min(8, max(1, len(sources)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(harvest_one, src) for src in sources]
        for fut in as_completed(futures):
            source, layers = fut.result()
            for layer in layers:
                hay = f"{layer.title} {layer.layer_name or ''} {layer.id}".lower()
                if needle and needle not in hay:
                    continue
                out.append(
                    {
                        "id": layer.id,
                        "title": layer.title,
                        "layer_name": layer.layer_name,
                        "source_type": layer.source_type,
                        "url": layer.url,
                        "source_id": source.id,
                        "source_title": source.title,
                    }
                )
                if len(out) >= limit:
                    return out
    return out


def validate_custom_layer(
    *,
    url: str,
    layer_name: str,
    source_type: str = "wms",
) -> dict[str, Any]:
    """Valide qu'une couche existe et supporte EPSG:3857 ou 4326/CRS:84."""
    url = url.strip()
    layer_name = layer_name.strip()
    if not url or not layer_name:
        return {"ok": False, "error": "URL et nom de couche requis."}

    stype = source_type.lower()
    if stype not in {"wms", "wfs"}:
        return {"ok": False, "error": "Type supporté : wms ou wfs."}

    source = _source_by_url(url) or _make_source(url, kind=stype)
    if source.kind == "arcgis":
        return {"ok": False, "error": "Utilisez le picker ou une URL WMS/WFS."}

    layers = _layers_for_source(source)
    match = next((layer for layer in layers if layer.layer_name == layer_name), None)
    if match is None:
        match = next(
            (
                layer
                for layer in layers
                if layer.layer_name and layer.layer_name.endswith(layer_name)
            ),
            None,
        )
    if match is None:
        return {"ok": False, "error": f"Couche « {layer_name} » introuvable dans GetCapabilities."}

    crs_ok = True
    crs_list: list[str] = []
    if stype == "wms":
        cache = CAPS_CACHE_DIR / f"{source.id}_wms.xml"
        if cache.exists():
            crs_ok, crs_list = _wms_layer_crs(cache.read_bytes(), layer_name)
        else:
            crs_ok = False
    elif stype == "wfs":
        crs_ok = True  # WFS GeoJSON via proxy utilise EPSG:4326 côté client

    if not crs_ok:
        return {
            "ok": False,
            "error": (
                "CRS non supporté — la couche doit être disponible en "
                "EPSG:3857 ou EPSG:4326 / CRS:84."
            ),
            "crs": crs_list[:8],
        }

    custom_id = f"custom:{source.id}:{layer_name}".replace(" ", "_")
    layer_def = {
        "id": custom_id,
        "title": match.title,
        "group": "custom",
        "source_type": match.source_type,
        "url": match.url,
        "layer_name": match.layer_name,
        "curated": False,
        "identify": False,
        "opacity": 0.85,
        "visible_default": True,
        "extra": {"proxy": True, "custom": True, "source_id": source.id},
    }
    return {"ok": True, "layer": layer_def, "crs_ok": True}
