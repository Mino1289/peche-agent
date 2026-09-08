"""Zones de pêche (polygones) depuis SmartFaune Zone_chasse_da3_sefaq.

Sync WFS → dissolve par (No_zone, Partie_zon) → map vers les 34 ids RegPec
→ data/spatial/zones_peche.geojson.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from peche.reglements.sync import DATA_DIR
from peche.reglements.zones import ZONES, Zone

WFS_URL = "https://servicesvecto3.mern.gouv.qc.ca/geoserver/SmartFaunePub/ows"
TYPE_NAME = "SmartFaunePub:Zone_chasse_da3_sefaq"
OUTPUT_PATH = DATA_DIR / "spatial" / "zones_peche.geojson"
SIMPLIFIED_PATH = DATA_DIR / "spatial" / "zones_peche.simplified.geojson"
OUTLINES_PATH = DATA_DIR / "spatial" / "zones_peche.outlines.geojson"
CACHE_PATH = DATA_DIR / "cache" / "zones_chasse_raw.geojson"
# Contours carte : ~4–6 m. Les polygones (clip / point-in-polygon) restent à 0.001°.
OUTLINE_TOLERANCE = 0.00005

_UA = "peche-agent/1.0 (zones-peche)"
_PAGE_SIZE = 500


def _fetch(url: str, *, timeout: int = 120) -> bytes:
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def _fetch_all_features() -> list[dict[str, Any]]:
    """Pagination WFS GeoJSON en EPSG:4326."""
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
        url = f"{WFS_URL}?{urlencode(params)}"
        print(f"  WFS startIndex={start}…")
        data = json.loads(_fetch(url).decode("utf-8"))
        batch = data.get("features") or []
        features.extend(batch)
        if len(batch) < _PAGE_SIZE:
            break
        start += _PAGE_SIZE
    return features


def _display_number(zone: Zone) -> int | None:
    """Extrait le numéro affiché (« Zone 19 sud… » → 19)."""
    m = re.search(r"Zone\s+(\d+)", zone.text)
    return int(m.group(1)) if m else None


def _partie_key(zone: Zone) -> str:
    """Normalise la partie : '', 'nord', 'sud', 'est', 'ouest', 'a', 'b'."""
    text = zone.text.lower()
    if "partie a" in text or "partie-a" in text:
        # 19 sud - partie A
        if "sud" in text:
            return "sud_a"
        return "a"
    if "partie b" in text or "partie-b" in text:
        if "sud" in text:
            return "sud_b"
        return "b"
    if "nord" in text:
        return "nord"
    if "sud" in text:
        return "sud"
    # « ouest » avant « est » (sinon « est » matche dans « ouest »)
    if re.search(r"\bouest\b", text):
        return "ouest"
    if re.search(r"\best\b", text):
        return "est"
    return ""


def _normalize_partie_zon(raw: str | None) -> str:
    if not raw:
        return ""
    s = str(raw).strip().lower()
    # Valeurs observées / attendues côté SmartFaune
    mapping = {
        "est": "est",
        "ouest": "ouest",
        "nord": "nord",
        "sud": "sud",
        "a": "a",
        "b": "b",
        "partie a": "a",
        "partie b": "b",
        "sud - partie a": "sud_a",
        "sud - partie b": "sud_b",
        "sud partie a": "sud_a",
        "sud partie b": "sud_b",
    }
    if s in mapping:
        return mapping[s]
    if "partie a" in s and "sud" in s:
        return "sud_a"
    if "partie b" in s and "sud" in s:
        return "sud_b"
    if "partie a" in s:
        return "a"
    if "partie b" in s:
        return "b"
    return s


# Alias observés côté SmartFaune (clé = no affiché + partie normalisée).
_WFS_PARTIE_ALIASES: dict[tuple[int, str], str] = {
    (13, ""): "est",
    (13, "sud-ouest"): "ouest",
    (19, "sud-est"): "sud_a",
    (19, "sud-ouest"): "sud_b",
    (19, "sud-nord-ouest"): "sud_b",
}


def build_regpec_lookup() -> dict[tuple[int, str], Zone]:
    """(display_no, partie_key) → Zone RegPec."""
    lookup: dict[tuple[int, str], Zone] = {}
    for zone in ZONES:
        num = _display_number(zone)
        if num is None:
            continue
        partie = _partie_key(zone)
        lookup[(num, partie)] = zone
    return lookup


def match_zone(no_zone: str | int, partie_zon: str | None) -> Zone | None:
    """Mappe une feature SmartFaune vers une Zone RegPec."""
    zones = match_zones(no_zone, partie_zon)
    return zones[0] if zones else None


def match_zones(no_zone: str | int, partie_zon: str | None) -> list[Zone]:
    """Mappe une feature SmartFaune vers une ou plusieurs zones RegPec."""
    try:
        num = int(str(no_zone).strip())
    except (TypeError, ValueError):
        return []
    partie = _normalize_partie_zon(partie_zon)
    partie = _WFS_PARTIE_ALIASES.get((num, partie), partie)
    lookup = build_regpec_lookup()

    for key in (
        (num, partie),
        (num, f"sud_{partie}") if partie in {"a", "b"} else None,
        (num, ""),
    ):
        if key is None:
            continue
        if key in lookup:
            return [lookup[key]]

    candidates = [z for (n, p), z in lookup.items() if n == num]
    if len(candidates) == 1:
        return [candidates[0]]

    # WFS non subdivisé (ex. zone 22) mais RegPec nord/sud : réutiliser le polygone.
    if partie == "":
        splits = [lookup[k] for k in ((num, "nord"), (num, "sud")) if k in lookup]
        if len(splits) >= 2:
            return splits

    return []


def _dissolve_features(
    features: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Regroupe les polygones par (No_zone, Partie_zon) et dissout."""
    try:
        import geopandas as gpd
        from shapely.geometry import shape
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("geopandas requis pour zones_peche sync") from exc

    rows = []
    for feat in features:
        props = feat.get("properties") or {}
        geom = feat.get("geometry")
        if not geom:
            continue
        no_zone = props.get("No_zone") or props.get("Zone")
        partie = props.get("Partie_zon") or ""
        matched = match_zones(no_zone, partie)
        if not matched:
            continue
        for zone in matched:
            rows.append(
                {
                    "zone_id": zone.value,
                    "zone_nom": zone.text,
                    "no_zone": str(no_zone),
                    "partie_zon": str(partie or ""),
                    "geometry": shape(geom),
                }
            )
    if not rows:
        return []

    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    dissolved = gdf.dissolve(by="zone_id", as_index=False)
    # Recoller les attributs zone_nom / no_zone / partie
    meta = (
        gdf.drop(columns="geometry")
        .drop_duplicates(subset=["zone_id"])
        .set_index("zone_id")
    )
    _write_outlines_from_dissolved(dissolved, meta)
    # Polygones (clip) : ~80 m suffisent ; les contours carte sont ailleurs.
    dissolved["geometry"] = dissolved.geometry.simplify(0.001, preserve_topology=True)
    out_features: list[dict[str, Any]] = []
    for _, row in dissolved.iterrows():
        zid = int(row["zone_id"])
        m = meta.loc[zid]
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        out_features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone_id": zid,
                    "zone_nom": str(m["zone_nom"]),
                    "no_zone": str(m["no_zone"]),
                    "partie_zon": str(m["partie_zon"]),
                },
                "geometry": json.loads(gpd.GeoSeries([geom]).to_json())["features"][0][
                    "geometry"
                ],
            }
        )
    return out_features


def _envelope_from_coords(coords: Any) -> tuple[float, float, float, float] | None:
    """Enveloppe lon/lat pour Polygon / MultiPolygon GeoJSON."""

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
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_intersects(
    env: tuple[float, float, float, float],
    bbox: tuple[float, float, float, float],
) -> bool:
    return not (env[2] < bbox[0] or env[0] > bbox[2] or env[3] < bbox[1] or env[1] > bbox[3])


def _exteriors(geom: Any) -> Any:
    """Anneaux extérieurs seulement (pas les lacs / trous) → LineString GeoJSON."""
    from shapely.geometry import LineString, MultiLineString

    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        parts = [geom]
    elif geom.geom_type == "MultiPolygon":
        parts = list(geom.geoms)
    elif geom.geom_type == "GeometryCollection":
        parts = []
        for g in geom.geoms:
            if g.geom_type == "Polygon":
                parts.append(g)
            elif g.geom_type == "MultiPolygon":
                parts.extend(g.geoms)
    else:
        return None
    lines = [
        LineString(p.exterior.coords)
        for p in parts
        if p.geom_type == "Polygon" and not p.is_empty and p.exterior
    ]
    if not lines:
        return None
    return MultiLineString(lines) if len(lines) > 1 else lines[0]


def _round_coords(obj: Any, ndigits: int = 6) -> Any:
    if isinstance(obj, dict):
        out = dict(obj)
        if "coordinates" in out:
            out["coordinates"] = _round_coords(out["coordinates"], ndigits)
        return out
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(float(x), ndigits) for x in obj]
        return [_round_coords(x, ndigits) for x in obj]
    return obj


def _geometry_to_exteriors(geom: dict[str, Any] | None) -> dict[str, Any] | None:
    """GeoJSON polygone → LineString / MultiLineString des anneaux extérieurs."""
    if not geom:
        return None
    t = geom.get("type")
    coords = geom.get("coordinates") or []
    if t in {"LineString", "MultiLineString"}:
        return geom
    if t == "LinearRing" and coords:
        return {"type": "LineString", "coordinates": coords}
    lines: list[Any] = []
    if t == "Polygon" and coords:
        lines.append(coords[0])
    elif t == "MultiPolygon":
        for poly in coords:
            if poly:
                lines.append(poly[0])
    if not lines:
        return None
    if len(lines) == 1:
        return {"type": "LineString", "coordinates": lines[0]}
    return {"type": "MultiLineString", "coordinates": lines}


def _write_outlines_from_dissolved(dissolved: Any, meta: Any) -> None:
    """Contours haute résolution pour le rendu carte (anneaux extérieurs)."""
    try:
        from shapely.geometry import mapping
    except ImportError:
        return

    features: list[dict[str, Any]] = []
    for _, row in dissolved.iterrows():
        ext = _exteriors(row.geometry)
        if ext is None or ext.is_empty:
            continue
        ext = ext.simplify(OUTLINE_TOLERANCE, preserve_topology=True)
        if ext.geom_type == "LinearRing":
            from shapely.geometry import LineString

            ext = LineString(ext.coords)
        zid = int(row["zone_id"])
        m = meta.loc[zid]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "zone_id": zid,
                    "zone_nom": str(m["zone_nom"]),
                    "no_zone": str(m["no_zone"]),
                    "partie_zon": str(m["partie_zon"]),
                },
                "geometry": _round_coords(mapping(ext)),
            }
        )
    OUTLINES_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTLINES_PATH.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": features,
                "meta": {"kind": "exteriors", "simplify": OUTLINE_TOLERANCE},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_simplified_geojson(features: list[dict[str, Any]]) -> None:
    """Écrit une version simplifiée pour les zooms bas."""
    try:
        import geopandas as gpd
        from shapely.geometry import shape
    except ImportError:
        return

    rows = []
    for feat in features:
        geom = feat.get("geometry")
        if not geom:
            continue
        rows.append(
            {
                **(feat.get("properties") or {}),
                "geometry": shape(geom).simplify(0.01, preserve_topology=True),
            }
        )
    if not rows:
        return
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    SIMPLIFIED_PATH.write_text(gdf.to_json(), encoding="utf-8")


@lru_cache(maxsize=1)
def load_zones_geojson() -> dict[str, Any] | None:
    if not OUTPUT_PATH.exists():
        return None
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))


def _polygons_as_outlines(data: dict[str, Any]) -> dict[str, Any]:
    feats: list[dict[str, Any]] = []
    for feat in data.get("features") or []:
        geom = _geometry_to_exteriors(feat.get("geometry"))
        if not geom:
            continue
        feats.append({**feat, "geometry": geom})
    return {"type": "FeatureCollection", "features": feats}


@lru_cache(maxsize=1)
def load_zone_outlines() -> dict[str, Any] | None:
    """Contours pour la carte. Fallback : anneaux extérieurs des polygones."""
    if OUTLINES_PATH.exists():
        data = json.loads(OUTLINES_PATH.read_text(encoding="utf-8"))
        for feat in data.get("features") or []:
            geom = feat.get("geometry") or {}
            if geom.get("type") == "LinearRing":
                feat["geometry"] = {
                    "type": "LineString",
                    "coordinates": geom.get("coordinates") or [],
                }
        return data
    data = load_zones_geojson()
    if not data:
        return None
    return _polygons_as_outlines(data)


@lru_cache(maxsize=1)
def _zones_index() -> list[dict[str, Any]]:
    """Index léger polygones : feature + enveloppe précalculée."""
    data = load_zones_geojson()
    if not data:
        return []
    out: list[dict[str, Any]] = []
    for feat in data.get("features") or []:
        geom = feat.get("geometry") or {}
        env = _envelope_from_coords(geom.get("coordinates"))
        if env is None:
            continue
        out.append({"feature": feat, "env": env, "zone_id": int((feat.get("properties") or {}).get("zone_id", -1))})
    return out


def _zoom_simplify_tolerance(zoom: int | None) -> float | None:
    """None = géométrie stockée (~5 m). Zoom d'ensemble seulement : 0.01°."""
    if zoom is not None and zoom < 9:
        return 0.01
    return None


def _zoom_band(zoom: int | None) -> int:
    if zoom is not None and zoom < 9:
        return 0
    return 1


@lru_cache(maxsize=4)
def _outline_index(band: int) -> list[dict[str, Any]]:
    data = load_zone_outlines()
    if not data:
        return []
    zoom_for_band = {0: 6, 1: 14}.get(band, 14)
    tol = _zoom_simplify_tolerance(zoom_for_band)
    feats = list(data.get("features") or [])
    if tol is not None and feats:
        try:
            from shapely.geometry import mapping, shape

            simplified: list[dict[str, Any]] = []
            for feat in feats:
                g = shape(feat.get("geometry"))
                g = g.simplify(tol, preserve_topology=True)
                if g.geom_type == "LinearRing":
                    from shapely.geometry import LineString

                    g = LineString(g.coords)
                simplified.append(
                    {
                        **feat,
                        "geometry": _round_coords(mapping(g)),
                    }
                )
            feats = simplified
        except Exception:  # noqa: BLE001
            pass
    out: list[dict[str, Any]] = []
    for feat in feats:
        geom = feat.get("geometry") or {}
        env = _envelope_from_coords(geom.get("coordinates"))
        if env is None:
            continue
        out.append(
            {
                "feature": feat,
                "env": env,
                "zone_id": int((feat.get("properties") or {}).get("zone_id", -1)),
            }
        )
    return out


def zones_geojson_for_viewport(
    bbox: tuple[float, float, float, float] | None,
    *,
    zone_ids: list[int] | None = None,
    limit: int = 2000,
    zoom: int | None = None,
) -> dict[str, Any]:
    """FeatureCollection de contours, densité adaptée au zoom."""
    index = _outline_index(_zoom_band(zoom))

    allowed = set(zone_ids) if zone_ids else None
    feats: list[dict] = []
    for row in index:
        if allowed is not None and row["zone_id"] not in allowed:
            continue
        env = row["env"]
        if bbox and allowed is None and env and not _bbox_intersects(env, bbox):
            continue
        feats.append(row["feature"])
        if len(feats) >= limit:
            break

    return {"type": "FeatureCollection", "features": feats}


def clear_zones_cache() -> None:
    load_zones_geojson.cache_clear()
    load_zone_outlines.cache_clear()
    _zones_index.cache_clear()
    _outline_index.cache_clear()


def sync(*, use_cache: bool = False) -> Path:
    """Télécharge, dissout, écrit zones_peche.geojson. Retourne le chemin."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if use_cache and CACHE_PATH.exists():
        print(f"Lecture cache {CACHE_PATH}")
        raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        features = raw.get("features") or []
    else:
        print("Téléchargement WFS Zone_chasse_da3_sefaq…")
        features = _fetch_all_features()
        CACHE_PATH.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}),
            encoding="utf-8",
        )
        print(f"  {len(features)} features → {CACHE_PATH}")

    print("Dissolve + mapping RegPec…")
    out = _dissolve_features(features)
    collection = {
        "type": "FeatureCollection",
        "features": out,
        "meta": {
            "source": TYPE_NAME,
            "nb_zones": len(out),
            "nb_input_features": len(features),
        },
    }
    OUTPUT_PATH.write_text(
        json.dumps(collection, ensure_ascii=False), encoding="utf-8"
    )
    _write_simplified_geojson(out)
    clear_zones_cache()
    print(f"Écrit {OUTPUT_PATH} ({len(out)} zones)")
    return OUTPUT_PATH


def get_zone_geometry(zone_id: int) -> dict[str, Any] | None:
    data = load_zones_geojson()
    if not data:
        return None
    for feat in data.get("features") or []:
        props = feat.get("properties") or {}
        if int(props.get("zone_id", -1)) == int(zone_id):
            return feat
    return None
