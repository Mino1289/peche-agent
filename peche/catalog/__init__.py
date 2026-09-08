"""Catalogue de couches cartographiques (OGC + curated)."""

from peche.catalog.harvest import ensure_catalog, load_catalog
from peche.catalog.harvest import harvest as harvest_catalog
from peche.catalog.models import Catalog, LayerDef

# Alias public
harvest = harvest_catalog

__all__ = [
    "Catalog",
    "LayerDef",
    "ensure_catalog",
    "harvest",
    "harvest_catalog",
    "load_catalog",
]
