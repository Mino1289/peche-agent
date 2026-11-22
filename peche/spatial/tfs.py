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
CHASSE_INTERDITE_TYPE_NAME = "SmartFaunePub:Chasse_Interdite"
CHASSE_INTERDITE_PATH = DATA_DIR / "spatial" / "chasse_interdite.geojson"
CHASSE_INTERDITE_PROPS = (
    "OBJECTID",
    "TOPONYME",
    "NOM",
    "DESIGNOM",
    "DESIG_GR",
    "RESPONSABL",
    "LIEN",
)
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


def _fetch_all(type_name: str = TYPE_NAME) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    start = 0
    while True:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": type_name,
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


def _sync_layer(type_name: str, path: Any, keep_props: tuple[str, ...]) -> int:
    out = []
    for feat in _fetch_all(type_name):
        if not feat.get("geometry"):
            continue
        props = feat.get("properties") or {}
        geom = shape(feat["geometry"]).simplify(STORE_TOLERANCE, preserve_topology=True)
        out.append(
            {
                "type": "Feature",
                "properties": {k: props.get(k) for k in keep_props},
                "geometry": _round(mapping(geom)),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"type": "FeatureCollection", "features": out}
    path.write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    _stored.cache_clear()
    _band.cache_clear()
    return len(out)


def sync() -> int:
    """Télécharge TFS, simplifie, écrit tfs.geojson. Retourne le nombre d'entités."""
    return _sync_layer(TYPE_NAME, TFS_PATH, KEEP_PROPS)


def sync_chasse_interdite() -> int:
    """Télécharge Chasse_Interdite, simplifie, écrit chasse_interdite.geojson."""
    return _sync_layer(
        CHASSE_INTERDITE_TYPE_NAME, CHASSE_INTERDITE_PATH, CHASSE_INTERDITE_PROPS
    )


@lru_cache(maxsize=2)
def _stored(kind: str = "tfs") -> list[dict[str, Any]]:
    path = CHASSE_INTERDITE_PATH if kind == "chasse_interdite" else TFS_PATH
    return json.loads(path.read_text(encoding="utf-8"))["features"]


@lru_cache(maxsize=6)
def _band(
    name: str, kind: str = "tfs"
) -> list[tuple[tuple[float, float, float, float], dict[str, Any]]]:
    """Entités prêtes à servir pour une bande de zoom : (bounds, feature)."""
    out = []
    for feat in _stored(kind):
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


def _zoom_band_name(zoom: int | None) -> str:
    if zoom is None or zoom >= MID_BELOW_ZOOM:
        return "full"
    if zoom >= POINT_BELOW_ZOOM:
        return "mid"
    return "points"


def tfs_geojson(
    bbox: tuple[float, float, float, float] | None,
    *,
    descriptions: set[str] | None,
    zoom: int | None,
) -> dict[str, Any]:
    """FeatureCollection des territoires dans le viewport, filtrés par DESCRIPTION.

    `descriptions` = None → pas de filtre. La couche est bornée (~550 entités) : pas de limite.
    """
    name = _zoom_band_name(zoom)
    features = []
    for (minx, miny, maxx, maxy), feat in _band(name, "tfs"):
        if descriptions is not None and feat["properties"].get("DESCRIPTION") not in descriptions:
            continue
        if bbox and (maxx < bbox[0] or minx > bbox[2] or maxy < bbox[1] or miny > bbox[3]):
            continue
        features.append(feat)
    return {"type": "FeatureCollection", "features": features}


def chasse_interdite_geojson(
    bbox: tuple[float, float, float, float] | None,
    *,
    zoom: int | None,
) -> dict[str, Any]:
    """Zones de chasse/pêche interdite : mêmes seuils de zoom que TFS."""
    name = _zoom_band_name(zoom)
    features = []
    for (minx, miny, maxx, maxy), feat in _band(name, "chasse_interdite"):
        if bbox and (maxx < bbox[0] or minx > bbox[2] or maxy < bbox[1] or miny > bbox[3]):
            continue
        features.append(feat)
    return {"type": "FeatureCollection", "features": features}
