"""Contexte géographique d'un point (lon/lat) pour pins et assistant."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from peche.catalog.curated import ENV_WSS, FORET_PUB, SMARTFAUNE, curated_layers
from peche.reglements.zones import display_number, zone_by_id
from peche.spatial.plan_geom import plans_geojson
from peche.spatial.zones_peche import load_zones_geojson

_UA = "peche-agent/1.0 (point-context)"
_GFI_SIZE = 101


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray casting — ring GeoJSON [lon, lat]."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-30) + xi
        ):
            inside = not inside
        j = i
    return inside


def _point_in_polygon_coords(lon: float, lat: float, coords: list) -> bool:
    if not coords:
        return False
    outer = coords[0]
    if not _point_in_ring(lon, lat, outer):
        return False
    for hole in coords[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


_GEO_HIT_TOL = 2e-4  # ~20 m en degrés


def _near(lon: float, lat: float, x: float, y: float, tol: float = _GEO_HIT_TOL) -> bool:
    return abs(x - lon) <= tol and abs(y - lat) <= tol


def _point_in_geometry(lon: float, lat: float, geom: dict | None) -> bool:
    if not geom or not isinstance(geom, dict):
        return False
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if gtype == "Point" and coords and len(coords) >= 2:
        return _near(lon, lat, float(coords[0]), float(coords[1]))
    if gtype == "MultiPoint":
        for pt in coords or []:
            if pt and len(pt) >= 2 and _near(lon, lat, float(pt[0]), float(pt[1])):
                return True
    if gtype == "Polygon":
        return _point_in_polygon_coords(lon, lat, coords)
    if gtype == "MultiPolygon":
        for poly in coords or []:
            if _point_in_polygon_coords(lon, lat, poly):
                return True
    return False


def _fetch_text(url: str, timeout: float = 30.0) -> str:
    req = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def _fetch_json(url: str, timeout: float = 30.0) -> Any:
    raw = _fetch_text(url, timeout=timeout)
    start = raw.find("{")
    if start < 0:
        start = raw.find("[")
    return json.loads(raw[start:] if start >= 0 else raw)


def _wms_gfi(
    base_url: str,
    layer: str,
    lon: float,
    lat: float,
    *,
    delta: float = 0.002,
    info_format: str = "application/json",
) -> dict[str, Any] | str | None:
    """GetFeatureInfo WMS 1.3.0 (EPSG:4326 — bbox lat,lon)."""
    bbox = f"{lat - delta},{lon - delta},{lat + delta},{lon + delta}"
    half = _GFI_SIZE // 2
    params = {
        "service": "WMS",
        "version": "1.3.0",
        "request": "GetFeatureInfo",
        "layers": layer,
        "query_layers": layer,
        "info_format": info_format,
        "crs": "EPSG:4326",
        "bbox": bbox,
        "width": str(_GFI_SIZE),
        "height": str(_GFI_SIZE),
        "i": str(half),
        "j": str(half),
    }
    url = f"{base_url}?{urlencode(params)}"
    try:
        if info_format == "text/plain":
            return _fetch_text(url)
        data = _fetch_json(url)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    if data.get("type") == "Feature":
        return data
    feats = data.get("features")
    if not feats:
        return None
    return feats[0] if feats else None


def parse_grhq_toponyme(text: str) -> str | None:
    """Extrait le toponyme d'une réponse GFI GRHQ ``text/plain``."""
    for block in text.split("@"):
        if "Toponyme" not in block or "Shape" not in block:
            continue
        header_seg, _, val_seg = block.partition("Shape;")
        if not val_seg:
            continue
        h_fields = header_seg.split(";")
        v_fields = val_seg.split(";")
        try:
            topo_idx = next(i for i, f in enumerate(h_fields) if f.strip() == "Toponyme")
        except StopIteration:
            continue
        if topo_idx >= len(v_fields):
            continue
        name = v_fields[topo_idx].strip()
        if name and name.lower() not in {"sans toponyme", "n/a"}:
            return name
    return None


def _waterbody_name_from_gfi(feat: dict | None) -> str | None:
    if not feat:
        return None
    props = feat.get("properties") or {}
    for key in (
        "NOM",
        "NOM_TOPO",
        "NOM_HYDRO",
        "NOM_EAU",
        "NOM_PLAN",
        "nom",
        "name",
        "TOPONYME",
        "Toponyme",
    ):
        val = props.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return None


def _waterbody_name_at_point(lon: float, lat: float) -> tuple[str | None, str | None]:
    for layer in ("GRHQ_RES_SURF", "GRHQ_RES_LIN_PERM"):
        plain = _wms_gfi(ENV_WSS, layer, lon, lat, info_format="text/plain")
        if isinstance(plain, str):
            name = parse_grhq_toponyme(plain)
            if name:
                return name, layer
        feat = _wms_gfi(ENV_WSS, layer, lon, lat, info_format="application/json")
        if isinstance(feat, dict):
            name = _waterbody_name_from_gfi(feat)
            if name:
                return name, layer
    return None, None


def hunting_forbidden_label(props: dict[str, Any]) -> tuple[str | None, str | None]:
    """Libellé complet + type (parc national, réserve, …)."""
    toponyme = props.get("TOPONYME")
    if toponyme and str(toponyme).strip():
        kind = props.get("DESIGNOM") or props.get("DESIG_GR")
        return str(toponyme).strip(), (
            str(kind).strip() if kind and str(kind).strip() else None
        )

    designom = str(props.get("DESIGNOM") or props.get("DESIG_GR") or "").strip()
    nom = str(props.get("NOM") or props.get("nom") or props.get("name") or "").strip()
    article = str(props.get("ARTICLE") or "").strip()
    if designom and nom:
        label = f"{designom} {nom}".strip()
        if article:
            label = f"{designom} {article} {nom}".strip()
        return label, designom
    if designom:
        return designom, designom
    if nom:
        return nom, None
    for key in ("NOM_ZONE", "DESCRIPTION"):
        val = props.get(key)
        if val and str(val).strip():
            return str(val).strip(), None
    return None, None


def _wfs_point_query(
    url: str,
    type_name: str,
    lon: float,
    lat: float,
    *,
    delta: float = 0.03,
    limit: int = 5,
) -> list[dict]:
    """Features WFS intersectant un petit bbox autour du point."""
    bbox = f"{lon - delta},{lat - delta},{lon + delta},{lat + delta},EPSG:4326"
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "bbox": bbox,
        "count": str(limit),
    }
    try:
        data = _fetch_json(f"{url}?{urlencode(params)}")
    except Exception:  # noqa: BLE001
        return []
    feats = data.get("features") if isinstance(data, dict) else []
    if not isinstance(feats, list):
        return []
    out = []
    for f in feats:
        if _point_in_geometry(lon, lat, f.get("geometry")):
            out.append(f)
    if not out and feats:
        out.append(feats[0])
    return out


def fishing_zone_at_point(lon: float, lat: float) -> dict[str, Any] | None:
    """Zone de pêche contenant le point (lookup GeoJSON local, sans WFS)."""
    zones = load_zones_geojson()
    for feat in (zones or {}).get("features") or []:
        if not _point_in_geometry(lon, lat, feat.get("geometry")):
            continue
        props = feat.get("properties") or {}
        zid = props.get("zone_id")
        zone = zone_by_id(int(zid)) if zid is not None else None
        return {
            "zone_id": zid,
            "no_zone": props.get("no_zone") or (display_number(zone) if zone else None),
            "zone_nom": props.get("zone_nom") or (zone.text if zone else None),
        }
    return None


_LAYER_TITLES = {layer.id: layer.title for layer in curated_layers()}

_OPTIONAL_LAYERS: dict[str, tuple[str, str]] = {
    "stations_lavage": (FORET_PUB, "ForetOuvertePub:stations_lavages_qc"),
    "tfs": (SMARTFAUNE, "SmartFaunePub:TFS"),
}


def _title_fr(text: str) -> str:
    """Capitalise un libellé FR (ex. CERF DE VIRGINIE → Cerf de Virginie)."""
    small = {"de", "du", "des", "la", "le", "les", "d'", "l'", "et", "à", "au", "aux", "en", "d"}
    words = " ".join((text or "").split()).lower().split(" ")
    out: list[str] = []
    for i, word in enumerate(words):
        if not word:
            continue
        if i > 0 and word in small:
            out.append(word)
        else:
            out.append(word[:1].upper() + word[1:] if word else word)
    return " ".join(out)


def summarize_layer_props(layer_id: str, props: dict[str, Any]) -> list[dict[str, str]]:
    """Résumé lisible des attributs d'une couche WFS pour le popup."""
    rows: list[dict[str, str]] = []

    def add(label: str, keys: tuple[str, ...], transform: Any = None) -> None:
        for key in keys:
            val = props.get(key)
            if val is not None and str(val).strip():
                text = str(val).strip()
                if transform:
                    text = transform(text)
                rows.append({"label": label, "value": text})
                return

    if layer_id == "chasse_interdite":
        name, kind = hunting_forbidden_label(props)
        if name:
            rows.append({"label": "Nom", "value": _title_fr(name)})
        if kind:
            rows.append({"label": "Type", "value": _title_fr(kind)})
        return rows

    if layer_id == "tfs":
        add("Nom", ("NOM", "NOM_TFS", "NOM_ZEC", "nom", "name"), transform=_title_fr)
        add("Type", ("DESCRIPTION", "TYPE", "TYPE_TFS"), transform=_title_fr)
        return rows

    if layer_id == "stations_lavage":
        add("Station", ("NOM", "nom", "name"))
        add("Adresse", ("ADRESSE", "adresse"))
        add("Municipalité", ("MUNICIPALITE", "municipalite"))
        return rows

    for key, val in props.items():
        if key.lower() in {"geometry", "shape", "gid", "objectid", "fid"}:
            continue
        if val is not None and str(val).strip():
            rows.append({"label": key.replace("_", " "), "value": str(val).strip()})
        if len(rows) >= 6:
            break
    return rows


def overlay_at_custom_layer(
    *,
    layer_id: str,
    title: str,
    url: str,
    layer_name: str,
    source_type: str,
    lon: float,
    lat: float,
) -> dict[str, Any] | None:
    """Attributs sous le point pour une couche ajoutée (WFS ou WMS GFI)."""
    if not url or not layer_name:
        return None
    st = source_type.lower()
    props: dict[str, Any] = {}
    if st == "wfs":
        feats = _wfs_point_query(url, layer_name, lon, lat)
        if not feats:
            return None
        props = feats[0].get("properties") or {}
    elif st == "wms":
        hit = None
        for fmt in ("application/json", "application/geo+json", "text/plain"):
            cand = _wms_gfi(url, layer_name, lon, lat, info_format=fmt)
            if not cand:
                continue
            if isinstance(cand, str) and cand.lstrip().startswith("<?xml"):
                continue
            hit = cand
            break
        if not hit:
            return None
        if isinstance(hit, str):
            text = hit.strip()
            if not text or text.lstrip().startswith("<?xml"):
                return None
            return {
                "layer_id": layer_id,
                "title": title or layer_id,
                "rows": [{"label": "Info", "value": text[:600]}],
            }
        if isinstance(hit, dict):
            props = hit.get("properties") if "properties" in hit else hit
            if not isinstance(props, dict):
                props = {}
    else:
        return None
    if not props:
        return None
    summary = summarize_layer_props(layer_id, props)
    if not summary:
        return None
    return {
        "layer_id": layer_id,
        "title": title or layer_id,
        "rows": summary,
    }


def get_point_context(
    lon: float,
    lat: float,
    visible_layers: list[str] | None = None,
    custom_layers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Résout zone pêche, exception, hydro, TFS et chasse interdite pour un point."""
    out: dict[str, Any] = {"lon": lon, "lat": lat}
    visible = set(visible_layers or [])

    fz = fishing_zone_at_point(lon, lat)
    if fz:
        out["fishing_zone"] = fz

    delta = 0.008
    bbox = (lon - delta, lat - delta, lon + delta, lat + delta)
    try:
        plans = plans_geojson(bbox, limit=50).get("features") or []
    except Exception:  # noqa: BLE001
        plans = []
    for feat in plans:
        if _point_in_geometry(lon, lat, feat.get("geometry")):
            props = feat.get("properties") or {}
            zid = props.get("zone_id")
            zone = zone_by_id(int(zid)) if zid is not None else None
            out["exception"] = {
                "plan_id": props.get("plan_id"),
                "nom": props.get("nom"),
                "zone_id": zid,
                "no_zone": display_number(zone) if zone else props.get("no_zone"),
                "zone_nom": zone.text if zone else None,
            }
            break

    water, layer = _waterbody_name_at_point(lon, lat)
    if water:
        out["waterbody"] = {"name": water, "layer": layer}

    if "tfs" in visible:
        tfs_feats = _wfs_point_query(
            SMARTFAUNE, "SmartFaunePub:TFS", lon, lat, delta=0.02
        )
        if tfs_feats:
            props = tfs_feats[0].get("properties") or {}
            for key in ("NOM", "NOM_TFS", "NOM_ZEC", "nom", "name", "TYPE"):
                val = props.get(key)
                if val and str(val).strip():
                    out["tfs"] = {"name": str(val).strip()}
                    break

    hunt_feats = _wfs_point_query(
        SMARTFAUNE, "SmartFaunePub:Chasse_Interdite", lon, lat, delta=0.02
    )
    if hunt_feats:
        props = hunt_feats[0].get("properties") or {}
        name, kind = hunting_forbidden_label(props)
        if name:
            payload: dict[str, Any] = {"name": name}
            if kind:
                payload["kind"] = kind
            out["hunting_forbidden"] = payload

    overlays: list[dict[str, Any]] = []
    for layer_id, (url, type_name) in _OPTIONAL_LAYERS.items():
        if layer_id not in visible:
            continue
        feats = _wfs_point_query(url, type_name, lon, lat, delta=0.02)
        if not feats:
            continue
        props = feats[0].get("properties") or {}
        summary = summarize_layer_props(layer_id, props)
        if summary:
            overlays.append(
                {
                    "layer_id": layer_id,
                    "title": _LAYER_TITLES.get(layer_id, layer_id),
                    "rows": summary,
                }
            )
    for cl in custom_layers or []:
        if not cl.get("url") or not cl.get("layer_name"):
            continue
        overlay = overlay_at_custom_layer(
            layer_id=str(cl.get("id") or "custom"),
            title=str(cl.get("title") or cl.get("id") or "Couche"),
            url=str(cl["url"]),
            layer_name=str(cl["layer_name"]),
            source_type=str(cl.get("source_type") or "wms"),
            lon=lon,
            lat=lat,
        )
        if overlay:
            overlays.append(overlay)
    if overlays:
        out["layer_overlays"] = overlays

    return out
