"""GET /api/features — vecteurs filtrés (cql | arcgis | local)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import orjson
from fastapi import APIRouter, HTTPException, Query
from starlette.responses import Response

from peche.catalog.harvest import ensure_catalog
from peche.reglements.sync import DATA_DIR

router = APIRouter()
_UA = "peche-agent/1.0 (features)"


def _fetch_json(url: str) -> Any:
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urlopen(req, timeout=60) as resp:  # noqa: S310
        raw = resp.read().decode("utf-8", errors="replace")
    start = raw.find("{")
    if start < 0:
        start = raw.find("[")
    return json.loads(raw[start:] if start >= 0 else raw)


def _features_cql(
    url: str,
    type_name: str,
    cql: str | None,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
) -> dict:
    params: dict[str, str] = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "count": str(limit),
    }
    if cql:
        params["CQL_FILTER"] = cql
    if bbox:
        # lon_min,lat_min,lon_max,lat_max → WFS bbox = minx,miny,maxx,maxy,CRS
        params["bbox"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:4326"
    return _fetch_json(f"{url}?{urlencode(params)}")


def _features_arcgis(
    url: str,
    layer_id: str,
    where: str | None,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
) -> dict:
    params: dict[str, str] = {
        "f": "geojson",
        "outFields": "*",
        "returnGeometry": "true",
        "resultRecordCount": str(limit),
        "where": where or "1=1",
    }
    if bbox:
        params["geometry"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
        params["geometryType"] = "esriGeometryEnvelope"
        params["inSR"] = "4326"
        params["spatialRel"] = "esriSpatialRelIntersects"
    endpoint = f"{url.rstrip('/')}/{layer_id}/query"
    return _fetch_json(f"{endpoint}?{urlencode(params)}")


_JSON_CACHE: dict[str, Any] = {}

# Clés injectées par l'API / le viewport — ce ne sont pas des attributs d'entité.
_META_FILTER_KEYS = frozenset(
    {"bbox", "limit", "zoom", "zone_ids", "zone_id", "no_zone", "No_zone"}
)


def _load_local_json(rel: str) -> Any:
    path = Path(rel)
    if not path.is_absolute():
        candidates = [
            DATA_DIR.parent / rel,
            DATA_DIR / rel.removeprefix("data/"),
            Path(rel),
        ]
        for c in candidates:
            if c.exists():
                path = c
                break
    if not path.exists():
        raise FileNotFoundError(rel)
    key = str(path.resolve())
    cached = _JSON_CACHE.get(key)
    if cached is not None:
        return cached
    data = json.loads(path.read_text(encoding="utf-8"))
    _JSON_CACHE[key] = data
    return data


def _geom_intersects_bbox(geom: Any, bbox: tuple[float, float, float, float]) -> bool:
    """Test bbox approximatif (enveloppe) pour GeoJSON Polygon / MultiPolygon."""
    if not isinstance(geom, dict):
        return True
    coords = geom.get("coordinates")
    if not coords:
        return True

    def _walk(c: Any) -> list[tuple[float, float]]:
        if not c:
            return []
        if isinstance(c[0], (int, float)) and len(c) >= 2:
            return [(float(c[0]), float(c[1]))]
        out: list[tuple[float, float]] = []
        for item in c:
            out.extend(_walk(item))
        return out

    pts = _walk(coords)
    if not pts:
        return True
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return not (max(xs) < bbox[0] or min(xs) > bbox[2] or max(ys) < bbox[1] or min(ys) > bbox[3])


def _zone_ids_from_filters(filters: dict[str, Any]) -> list[int] | None:
    zone_ids = filters.get("zone_ids")
    if zone_ids is not None:
        return [int(z) for z in zone_ids]
    zid = filters.get("zone_id")
    if zid is not None and zid != "":
        return [int(zid)]
    return None


def _features_local(
    layer_id: str,
    url: str,
    filters: dict[str, Any],
    bbox: tuple[float, float, float, float] | None,
    limit: int,
) -> dict:
    """Filtre JSON local (stations, barrages, marées, locations)."""
    if layer_id in {"plans_regpec"}:
        from peche.spatial.plan_geom import plans_geojson

        return plans_geojson(
            bbox,
            zone_ids=_zone_ids_from_filters(filters),
            limit=limit,
            zoom=filters.get("zoom"),
        )
    if layer_id in {"zones_peche", "zones_chasse"}:
        from peche.spatial.zones_peche import zones_geojson_for_viewport

        return zones_geojson_for_viewport(
            bbox,
            zone_ids=_zone_ids_from_filters(filters),
            limit=limit,
            zoom=filters.get("zoom"),
        )

    raw = _load_local_json(url)
    items: list[dict]
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("stations") or raw.get("barrages") or raw.get("features") or []
        if items and isinstance(items[0], dict) and "geometry" in items[0]:
            return {"type": "FeatureCollection", "features": items[:limit]}
    else:
        items = []

    as_line = layer_id == "barrages_cehq"
    features: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        skip = False
        for k, v in filters.items():
            if k in _META_FILTER_KEYS:
                continue
            if v is None or v == "" or v == []:
                continue
            item_val = item.get(k)
            if isinstance(v, list):
                if str(item_val) not in {str(x) for x in v}:
                    skip = True
                    break
            elif str(item_val).lower() != str(v).lower():
                skip = True
                break
        if skip:
            continue
        if as_line:
            from peche.spatial.plan_geom import barrage_line_feature

            feat = barrage_line_feature(item)
            if not feat:
                continue
            coords = feat["geometry"]["coordinates"]
            lon_f = (coords[0][0] + coords[1][0]) / 2
            lat_f = (coords[0][1] + coords[1][1]) / 2
            if bbox and not (
                bbox[0] <= lon_f <= bbox[2] and bbox[1] <= lat_f <= bbox[3]
            ):
                continue
            features.append(feat)
        else:
            lat = item.get("lat") or item.get("latitude") or item.get("y")
            lon = item.get("lon") or item.get("longitude") or item.get("lng") or item.get("x")
            if lat is None or lon is None:
                continue
            try:
                lat_f, lon_f = float(lat), float(lon)
            except (TypeError, ValueError):
                continue
            if bbox:
                if not (bbox[0] <= lon_f <= bbox[2] and bbox[1] <= lat_f <= bbox[3]):
                    continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon_f, lat_f]},
                    "properties": {
                        k: v for k, v in item.items() if k not in {"geometry"}
                    },
                }
            )
        if len(features) >= limit:
            break
    return {"type": "FeatureCollection", "features": features}


def _plans_in_bbox(
    bbox: tuple[float, float, float, float] | None,
    filters: dict[str, Any],
    limit: int,
) -> dict:
    locations_dir = DATA_DIR / "locations"
    features: list[dict] = []
    zone_filter = filters.get("zone_id")
    files = sorted(locations_dir.glob("*.json")) if locations_dir.exists() else []
    for path in files:
        try:
            zid = int(path.stem)
        except ValueError:
            continue
        if zone_filter is not None and int(zone_filter) != zid:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        plans = data if isinstance(data, list) else data.get("plans") or data.get("locations") or []
        if isinstance(data, dict) and not plans:
            # {plan_id: {lat, lon, nom}}
            plans = [{"id": k, **v} for k, v in data.items() if isinstance(v, dict)]
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            lat = plan.get("lat")
            lon = plan.get("lon")
            if lat is None or lon is None:
                continue
            lat_f, lon_f = float(lat), float(lon)
            if bbox and not (
                bbox[0] <= lon_f <= bbox[2] and bbox[1] <= lat_f <= bbox[3]
            ):
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon_f, lat_f]},
                    "properties": {
                        "zone_id": zid,
                        "plan_id": plan.get("id") or plan.get("plan_id"),
                        "nom": plan.get("nom") or plan.get("name"),
                        **{
                            k: v
                            for k, v in plan.items()
                            if k not in {"lat", "lon", "geometry"}
                        },
                    },
                }
            )
            if len(features) >= limit:
                return {"type": "FeatureCollection", "features": features}
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/features")
def get_features(
    layer: str = Query(..., description="id de couche catalogue"),
    bbox: str | None = Query(None, description="lon_min,lat_min,lon_max,lat_max"),
    filter: str | None = Query(None, description="CQL ou where ArcGIS"),
    zone_id: int | None = None,
    categorie: str | None = Query(
        None, description="Catégories barrage séparées par virgule"
    ),
    etat: str | None = None,
    no_zone: str | None = Query(None, description="Numéro de zone de pêche affiché"),
    zoom: int | None = Query(None, ge=0, le=22),
    limit: int = Query(2000, ge=1, le=10000),
) -> Response:
    catalog = ensure_catalog()
    layer_def = catalog.layer_by_id(layer)
    if layer_def is None:
        raise HTTPException(status_code=404, detail=f"Couche inconnue: {layer}")

    bbox_t: tuple[float, float, float, float] | None = None
    if bbox:
        try:
            parts = [float(x.strip()) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            bbox_t = (parts[0], parts[1], parts[2], parts[3])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bbox invalide") from exc

    kind = (layer_def.filter_spec.kind if layer_def.filter_spec else None) or "none"
    if layer_def.source_type in {"local", "geojson"}:
        kind = "local"
    elif layer_def.source_type == "wfs":
        kind = "cql"
    elif layer_def.source_type == "arcgis":
        kind = "arcgis"

    try:
        if kind == "cql":
            data = _features_cql(
                layer_def.url,
                layer_def.layer_name or "",
                filter,
                bbox_t,
                limit,
            )
        elif kind == "arcgis":
            data = _features_arcgis(
                layer_def.url,
                layer_def.layer_name or "0",
                filter,
                bbox_t,
                limit,
            )
        elif kind == "local":
            from peche.reglements.zone_filter import (
                parse_zone_expr,
                resolve_zone_ids_for_expr,
                zone_filter_active,
            )

            filters: dict[str, Any] = {}
            zone_raw = no_zone
            if not zone_raw and zone_id is not None:
                zone_raw = str(zone_id)
            if zone_raw:
                try:
                    expr = parse_zone_expr(zone_raw)
                    resolved = resolve_zone_ids_for_expr(expr)
                    if resolved is not None:
                        filters["zone_ids"] = resolved
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                filters["no_zone"] = zone_raw
                filters["No_zone"] = zone_raw
            if categorie:
                filters["categorie"] = [c.strip() for c in categorie.split(",") if c.strip()]
            if etat:
                etats = [e.strip() for e in etat.split(",") if e.strip()]
                filters["etat"] = etats if len(etats) > 1 else etats[0]
            if zoom is not None:
                filters["zoom"] = zoom
            if layer in {"zones_chasse", "zones_peche", "plans_regpec"} and zone_filter_active(
                zone_raw
            ):
                bbox_t = None
            # Couches ponctuelles locales : tout charger d'un coup (pas de bbox).
            if layer in {"vigilance_stations", "marees_shc", "barrages_cehq"} and bbox_t is None:
                limit = 10000
            data = _features_local(layer, layer_def.url, filters, bbox_t, limit)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Couche {layer} non vectorielle (kind={kind})",
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"features: {type(exc).__name__}: {exc}"
        ) from exc

    return Response(content=orjson.dumps(data), media_type="application/json")
