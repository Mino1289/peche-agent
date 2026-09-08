"""Modèles du catalogue de couches cartographiques."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

FilterKind = Literal["cql", "arcgis", "local", "none", "colorkey"]
SourceType = Literal["wms", "wmts", "wfs", "xyz", "arcgis", "geojson", "local"]


@dataclass
class FilterSpec:
    kind: FilterKind
    """Mécanisme de filtrage."""
    attr: str | None = None
    """Champ attributaire (CQL / ArcGIS / local)."""
    options: list[dict[str, Any]] = field(default_factory=list)
    """Options UI : [{value, label, color?}]."""
    multi: bool = True
    """Sélection multiple autorisée."""


@dataclass
class LayerDef:
    id: str
    title: str
    group: str
    source_type: SourceType
    url: str
    """URL du service (WMS/WFS/ArcGIS/XYZ) ou chemin relatif local."""
    layer_name: str | None = None
    """Nom de couche WMS/WFS ou id ArcGIS."""
    curated: bool = False
    filter_spec: FilterSpec | None = None
    legend_url: str | None = None
    min_zoom: int | None = None
    max_zoom: int | None = None
    opacity: float = 1.0
    visible_default: bool = False
    identify: bool = True
    attribution: str | None = None
    queryable: bool = True
    color: str | None = None
    """Couleur de style vectoriel (#rrggbb) ou teinte WMS."""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["filter_spec"] is None:
            del d["filter_spec"]
        return d


@dataclass
class CatalogGroup:
    id: str
    title: str
    layers: list[LayerDef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "layers": [layer.to_dict() for layer in self.layers],
        }


@dataclass
class Catalog:
    version: int
    harvested_at: str
    basemaps: list[LayerDef]
    groups: list[CatalogGroup]
    curated_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "harvested_at": self.harvested_at,
            "basemaps": [b.to_dict() for b in self.basemaps],
            "groups": [g.to_dict() for g in self.groups],
            "curated_ids": self.curated_ids,
        }

    def layer_by_id(self, layer_id: str) -> LayerDef | None:
        for group in self.groups:
            for layer in group.layers:
                if layer.id == layer_id:
                    return layer
        for basemap in self.basemaps:
            if basemap.id == layer_id:
                return basemap
        return None
