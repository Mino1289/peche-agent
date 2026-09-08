"""Catalogue de couches curées → data/catalog/catalog.json."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from peche.catalog.curated import GROUP_TITLES, curated_ids, curated_layers
from peche.catalog.models import Catalog, CatalogGroup, LayerDef
from peche.catalog.sources import BASEMAP_SOURCES, OgcSource
from peche.reglements.sync import DATA_DIR

CATALOG_DIR = DATA_DIR / "catalog"
CATALOG_PATH = CATALOG_DIR / "catalog.json"
CAPS_CACHE_DIR = CATALOG_DIR / "capabilities"

_NS = {
    "wms": "http://www.opengis.net/wms",
    "ows": "http://www.opengis.net/ows/1.1",
    "wfs": "http://www.opengis.net/wfs/2.0",
    "ogc": "http://www.opengis.net/ogc",
}

_TIMEOUT = 60
_UA = "peche-agent/1.0 (catalog-harvest)"


def _fetch(url: str, *, timeout: int = _TIMEOUT) -> bytes:
    req = Request(url, headers={"User-Agent": _UA, "Accept": "*/*"})
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def parse_wms_capabilities(xml_bytes: bytes, source: OgcSource) -> list[LayerDef]:
    """Parse WMS 1.3.0 GetCapabilities → LayerDef list."""
    root = ET.fromstring(xml_bytes)  # noqa: S314
    layers: list[LayerDef] = []
    seen: set[str] = set()

    def walk(el: ET.Element) -> None:
        name_el = None
        title_el = None
        for child in el:
            ln = _local_name(child.tag)
            if ln == "Name" and name_el is None:
                name_el = child
            elif ln == "Title" and title_el is None:
                title_el = child
            elif ln == "Layer":
                walk(child)
        name = _text(name_el)
        if not name or name in seen:
            return
        # Skip root/service-level names that match the service itself
        if name.lower() in {source.id, "wms", "layers"}:
            return
        seen.add(name)
        title = _text(title_el) or name
        queryable = el.attrib.get("queryable", "0") == "1"
        layer_id = f"{source.id}:{name}"
        layers.append(
            LayerDef(
                id=layer_id,
                title=title,
                group=source.group,
                source_type="wms",
                url=source.url,
                layer_name=name,
                curated=False,
                queryable=queryable,
                identify=queryable,
                attribution=source.title,
                extra={"source_id": source.id, "proxy": source.proxy},
            )
        )

    # Find Capability/Layer or just any Layer tree
    for el in root.iter():
        if _local_name(el.tag) == "Capability":
            for child in el:
                if _local_name(child.tag) == "Layer":
                    walk(child)
            break
    else:
        for el in root.iter():
            if _local_name(el.tag) == "Layer":
                walk(el)
                break
    return layers


def parse_wfs_capabilities(xml_bytes: bytes, source: OgcSource) -> list[LayerDef]:
    """Parse WFS 2.0 GetCapabilities FeatureTypeList."""
    root = ET.fromstring(xml_bytes)  # noqa: S314
    layers: list[LayerDef] = []
    for ft in root.iter():
        if _local_name(ft.tag) != "FeatureType":
            continue
        name = ""
        title = ""
        for child in ft:
            ln = _local_name(child.tag)
            if ln == "Name" and not name:
                name = _text(child)
            elif ln == "Title" and not title:
                title = _text(child)
        if not name:
            continue
        layer_id = f"{source.id}:{name}"
        layers.append(
            LayerDef(
                id=layer_id,
                title=title or name,
                group=source.group,
                source_type="wfs",
                url=source.wfs_url or source.url,
                layer_name=name,
                curated=False,
                attribution=source.title,
                extra={"source_id": source.id, "proxy": source.proxy},
            )
        )
    return layers


def parse_arcgis_mapserver(data: dict[str, Any], source: OgcSource) -> list[LayerDef]:
    """Parse ArcGIS MapServer JSON layer list."""
    layers: list[LayerDef] = []
    for item in data.get("layers") or []:
        lid = item.get("id")
        name = item.get("name") or str(lid)
        if lid is None:
            continue
        layer_id = f"{source.id}:{lid}"
        layers.append(
            LayerDef(
                id=layer_id,
                title=name,
                group=source.group,
                source_type="arcgis",
                url=source.url,
                layer_name=str(lid),
                curated=False,
                attribution=source.title,
                extra={"source_id": source.id, "proxy": source.proxy},
            )
        )
    return layers


def _basemap_layers() -> list[LayerDef]:
    out: list[LayerDef] = []
    for src in BASEMAP_SOURCES:
        # Imagerie : URL déjà en template tuile XYZ-compatible (z/y/x)
        stype: str = "xyz"
        if src.kind == "xyz":
            stype = "xyz"
        elif src.id == "imagerie_continue":
            stype = "xyz"
        elif src.kind == "wmts":
            stype = "wmts"
        out.append(
            LayerDef(
                id=src.id,
                title=src.title,
                group="basemaps",
                source_type=stype,  # type: ignore[arg-type]
                url=src.url,
                curated=True,
                visible_default=src.id == "fond_quebec",
                identify=False,
                queryable=False,
                attribution="Gouvernement du Québec",
                extra={"source_id": src.id, "proxy": src.proxy},
            )
        )
    return out


def harvest_source(source: OgcSource, *, cache_dir: Path) -> list[LayerDef]:
    """Récolte un endpoint ; renvoie [] en cas d'échec (non fatal)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        if source.kind == "xyz":
            return []
        if source.kind == "wmts":
            # WMTS capabilities are large; register as single basemap only
            return []
        if source.kind == "arcgis":
            url = f"{source.url}?f=json"
            cache_path = cache_dir / f"{source.id}.json"
            raw = _fetch(url)
            cache_path.write_bytes(raw)
            # ArcGIS sometimes returns HTML/JSONP-ish; try json
            text = raw.decode("utf-8", errors="replace")
            # Strip possible leading garbage
            start = text.find("{")
            if start < 0:
                return []
            data = json.loads(text[start:])
            return parse_arcgis_mapserver(data, source)
        if source.kind == "wfs":
            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetCapabilities",
            }
            url = f"{source.url}?{urlencode(params)}"
            raw = _fetch(url)
            (cache_dir / f"{source.id}_wfs.xml").write_bytes(raw)
            return parse_wfs_capabilities(raw, source)
        # WMS
        params = {
            "service": "WMS",
            "version": "1.3.0",
            "request": "GetCapabilities",
        }
        url = f"{source.url}?{urlencode(params)}"
        raw = _fetch(url)
        (cache_dir / f"{source.id}_wms.xml").write_bytes(raw)
        return parse_wms_capabilities(raw, source)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! {source.id}: {type(exc).__name__}: {exc}")
        return []


# Groupes issus du dump GetCapabilities — jamais affichés.
_DROPPED_GROUPS = frozenset(
    {"foret", "qualite_eau", "biodiversite", "perturbations", "autres"}
)

_PREFERRED_GROUPS = [
    "reglementation",
    "faune",
    "hydro_temps_reel",
    "hydrographie",
    "lidar",
    "territoire",
]


def keep_harvested_layer(layer: LayerDef) -> bool:
    """Le catalogue UI n'affiche que les couches curées."""
    return layer.curated and layer.group not in _DROPPED_GROUPS


def _merge_catalog(
    harvested: list[LayerDef], curated: list[LayerDef], basemaps: list[LayerDef]
) -> Catalog:
    """Catalogue fishing-first : curated uniquement (harvested ignoré)."""
    _ = harvested  # GetCapabilities dump volontairement non fusionné.

    groups_map: dict[str, CatalogGroup] = {}
    for layer in curated:
        if not keep_harvested_layer(layer):
            continue
        gid = layer.group
        if gid not in groups_map:
            groups_map[gid] = CatalogGroup(
                id=gid, title=GROUP_TITLES.get(gid, gid.replace("_", " ").title())
            )
        groups_map[gid].layers.append(layer)

    groups: list[CatalogGroup] = []
    for gid in _PREFERRED_GROUPS:
        if gid in groups_map:
            groups.append(groups_map.pop(gid))
    for gid in sorted(groups_map):
        groups.append(groups_map[gid])

    return Catalog(
        version=1,
        harvested_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        basemaps=basemaps,
        groups=groups,
        curated_ids=curated_ids(),
    )


def harvest(*, skip_remote: bool = False) -> Catalog:
    """Écrit un catalogue curated-only (pas de dump GetCapabilities)."""
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    if skip_remote:
        print("Catalogue curated + basemaps (skip-remote).")
    else:
        print("Catalogue curated + basemaps (GetCapabilities non récolté).")
    catalog = _merge_catalog([], curated_layers(), _basemap_layers())
    CATALOG_PATH.write_text(
        json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Écrit {CATALOG_PATH} ({sum(len(g.layers) for g in catalog.groups)} couches)")
    return catalog


def load_catalog() -> Catalog | None:
    """Charge le catalogue local ; None si absent."""
    if not CATALOG_PATH.exists():
        # Fallback : curated-only catalog so the API works without harvest
        return _merge_catalog([], curated_layers(), _basemap_layers())
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    # Reconstruct lightly from dict
    basemaps = [_layer_from_dict(d) for d in raw.get("basemaps", [])]
    groups: list[CatalogGroup] = []
    for g in raw.get("groups", []):
        if g.get("id") in _DROPPED_GROUPS:
            continue
        groups.append(
            CatalogGroup(
                id=g["id"],
                title=g["title"],
                layers=[_layer_from_dict(layer) for layer in g.get("layers", [])],
            )
        )
    curated_now = set(curated_ids())
    removed = set(raw.get("curated_ids") or []) - curated_now
    curated_by_id = {layer.id: layer for layer in curated_layers()}
    for group in groups:
        group.layers = [
            curated_by_id.get(layer.id, layer)
            for layer in group.layers
            if layer.id not in removed
            and not (layer.curated and layer.id not in curated_now)
        ]
        group.layers = [
            layer for layer in group.layers if keep_harvested_layer(layer)
        ]
    groups = [group for group in groups if group.layers]
    present = {layer.id for group in groups for layer in group.layers}
    # Garantir les couches curées (ids nouveaux / defs mises à jour).
    for layer in curated_layers():
        if layer.id in present:
            continue
        gid = layer.group
        if gid in _DROPPED_GROUPS:
            continue
        found = next((g for g in groups if g.id == gid), None)
        if found is None:
            found = CatalogGroup(id=gid, title=GROUP_TITLES.get(gid, gid))
            groups.append(found)
        found.layers.append(layer)
    return Catalog(
        version=int(raw.get("version", 1)),
        harvested_at=raw.get("harvested_at", ""),
        basemaps=basemaps,
        groups=groups,
        curated_ids=curated_ids(),
    )


def _layer_from_dict(d: dict[str, Any]) -> LayerDef:
    from peche.catalog.models import FilterSpec

    fs = d.get("filter_spec")
    filter_spec = FilterSpec(**fs) if isinstance(fs, dict) else None
    known = {
        "id",
        "title",
        "group",
        "source_type",
        "url",
        "layer_name",
        "curated",
        "filter_spec",
        "legend_url",
        "min_zoom",
        "max_zoom",
        "opacity",
        "visible_default",
        "identify",
        "attribution",
        "queryable",
        "color",
        "extra",
    }
    kwargs = {k: v for k, v in d.items() if k in known and k != "filter_spec"}
    kwargs["filter_spec"] = filter_spec
    return LayerDef(**kwargs)


_CATALOG_INSTANCE: Catalog | None = None


def ensure_catalog() -> Catalog:
    """Charge ou génère un catalogue curated-only (cache processus)."""
    global _CATALOG_INSTANCE  # noqa: PLW0603
    if _CATALOG_INSTANCE is not None:
        return _CATALOG_INSTANCE
    catalog = load_catalog()
    if catalog is None:
        catalog = harvest(skip_remote=True)
    # Persist curated-only if file missing
    if not CATALOG_PATH.exists():
        CATALOG_DIR.mkdir(parents=True, exist_ok=True)
        CATALOG_PATH.write_text(
            json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    _CATALOG_INSTANCE = catalog
    return catalog
