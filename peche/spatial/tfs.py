"""Territoires fauniques structurés (SmartFaunePub:TFS) — snapshot local simplifié.

La couche WFS pèse ~86 Mo (géométries brutes, ~50 s côté GeoServer). `sync` la télécharge
une fois, simplifie à ~50 m et écrit data/spatial/tfs.geojson. Le service sert ensuite
des centroïdes à zoom bas, des polygones simplifiés à zoom moyen, et les géométries
stockées à zoom élevé.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import mapping, shape

from peche.reglements.sync import DATA_DIR

WFS_URL = "https://servicesvecto3.mern.gouv.qc.ca/geoserver/SmartFaunePub/ows"
TYPE_NAME = "SmartFaunePub:TFS"
TFS_PATH = DATA_DIR / "spatial" / "tfs.geojson"
KEEP_PROPS = ("NOM", "DESCRIPTION", "DATE_MAJ")
STORE_TOLERANCE = 0.0005  # ~50 m, géométrie stockée
MID_TOLERANCE = 0.002  # ~200 m, zoom moyen
POINT_BELOW_ZOOM = 9  # sous ce zoom : centroïdes
MID_BELOW_ZOOM = 12  # sous ce zoom : polygones simplifiés
_PAGE_SIZE = 500
_UA = "peche-agent/1.0 (tfs-sync)"


def _round(obj: Any) -> Any:
    if isinstance(obj, float):
        return round(obj, 5)
    if isinstance(obj, (list, tuple)):
        return [_round(x) for x in obj]
    return obj


def _fetch_all() -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    start = 0
    while True:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": TYPE_NAME,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "count": str(_PAGE_SIZE),
            "startIndex": str(start),
        }
        req = Request(f"{WFS_URL}?{urlencode(params)}", headers={"User-Agent": _UA})
        with urlopen(req, timeout=180) as resp:  # noqa: S310
            batch = json.loads(resp.read().decode("utf-8")).get("features") or []
        features.extend(batch)
        if len(batch) < _PAGE_SIZE:
            return features
        start += _PAGE_SIZE


def sync() -> int:
    """Télécharge la couche, simplifie, écrit tfs.geojson. Retourne le nombre d'entités."""
    out = []
    for feat in _fetch_all():
        props = feat.get("properties") or {}
        geom = shape(feat["geometry"]).simplify(STORE_TOLERANCE, preserve_topology=True)
        out.append(
            {
                "type": "Feature",
                "properties": {k: props.get(k) for k in KEEP_PROPS},
                "geometry": _round(mapping(geom)),
            }
        )
    TFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = {"type": "FeatureCollection", "features": out}
    TFS_PATH.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _stored.cache_clear()
    _band.cache_clear()
    return len(out)


@lru_cache(maxsize=1)
def _stored() -> list[dict[str, Any]]:
    return json.loads(TFS_PATH.read_text(encoding="utf-8"))["features"]


@lru_cache(maxsize=3)
def _band(name: str) -> list[tuple[tuple[float, float, float, float], dict[str, Any]]]:
    """Entités prêtes à servir pour une bande de zoom : (bounds, feature)."""
    out = []
    for feat in _stored():
        geom = shape(feat["geometry"])
        if name == "points":
            geom = geom.representative_point()
        elif name == "mid":
            geom = geom.simplify(MID_TOLERANCE, preserve_topology=True)
        out.append(
            (
                geom.bounds,
                {
                    "type": "Feature",
                    "properties": feat["properties"],
                    "geometry": _round(mapping(geom)),
                },
            )
        )
    return out


def tfs_geojson(
    bbox: tuple[float, float, float, float] | None,
    *,
    descriptions: set[str] | None,
    zoom: int | None,
) -> dict[str, Any]:
    """FeatureCollection des territoires dans le viewport, filtrés par DESCRIPTION.

    `descriptions` = None → pas de filtre. La couche est bornée (~550 entités) : pas de limite.
    """
    if zoom is None or zoom >= MID_BELOW_ZOOM:
        name = "full"
    elif zoom >= POINT_BELOW_ZOOM:
        name = "mid"
    else:
        name = "points"
    features = []
    for (minx, miny, maxx, maxy), feat in _band(name):
        if descriptions is not None and feat["properties"].get("DESCRIPTION") not in descriptions:
            continue
        if bbox and (maxx < bbox[0] or minx > bbox[2] or maxy < bbox[1] or miny > bbox[3]):
            continue
        features.append(feat)
    return {"type": "FeatureCollection", "features": features}
