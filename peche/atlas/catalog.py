"""Catalogue des jeux de données Atlas de l'eau (Données Québec)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from peche.reglements.sync import DATA_DIR

ATLAS_DIR = DATA_DIR / "spatial" / "atlas"


@dataclass(frozen=True)
class AtlasLayer:
    key: str
    package_id: str
    title: str
    format_hint: str = "SQLite"
    entity_type: str = "point"
    map_layer: str = ""


LAYERS: dict[str, AtlasLayer] = {
    "rsvl": AtlasLayer(
        key="rsvl",
        package_id="da90ed32-e5f8-4b1f-b522-2eeadbfb5682",
        title="Lacs participants au RSVL",
        map_layer="RSVL",
    ),
    "zgie": AtlasLayer(
        key="zgie",
        package_id="c8e8e8e8-placeholder",  # resolved at sync via search
        title="Zones de gestion intégrée de l'eau",
        entity_type="polygon",
        map_layer="ZGIE",
    ),
    "drainage": AtlasLayer(
        key="drainage",
        package_id="72ec636b-e9da-4faf-98c6-718fc83c0967",
        title="Aires de drainage des lacs",
        entity_type="polygon",
        map_layer="Drainage",
    ),
}


def layer_keys() -> list[str]:
    return list(LAYERS.keys())


def layer_meta() -> list[dict[str, Any]]:
    return [
        {
            "key": layer.key,
            "title": layer.title,
            "package_id": layer.package_id,
            "map_layer": layer.map_layer or layer.title,
        }
        for layer in LAYERS.values()
    ]
