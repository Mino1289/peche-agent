"""Tests catalogue + mapping zones de pêche."""

from peche.catalog.curated import curated_ids, curated_layers
from peche.catalog.harvest import ensure_catalog
from peche.catalog.models import FilterSpec, LayerDef
from peche.spatial.zones_peche import build_regpec_lookup, match_zone, match_zones


def test_curated_layers_have_ids():
    layers = curated_layers()
    ids = curated_ids()
    assert len(layers) >= 18
    assert len(ids) == len(layers)
    assert "lidar_pentes" in ids
    assert "zones_chasse" in ids
    assert "plans_regpec" in ids
    assert "hydrolidar_lits" in ids
    assert "vigilance_stations" in ids
    assert "grhq_flow" in ids
    assert "aq_reseau" in ids
    assert "aq_forestier" in ids
    assert "pente_cpl" not in ids
    assert "lidar_mnt" not in ids
    assert "peuplements" not in ids
    assert "feux" not in ids
    assert "qualite_eau" not in {layer.group for layer in layers}
    assert "foret" not in {layer.group for layer in layers}
    assert "biodiversite" not in {layer.group for layer in layers}
    assert "perturbations" not in {layer.group for layer in layers}
    zones = next(layer for layer in layers if layer.id == "zones_chasse")
    assert zones.source_type == "local"
    assert zones.extra.get("outline") is True
    assert zones.opacity == 1.0
    pente = next(layer for layer in layers if layer.id == "lidar_pentes")
    assert pente.filter_spec is not None
    assert pente.filter_spec.kind == "none"
    assert pente.extra.get("proxy") is True
    plans = next(layer for layer in layers if layer.id == "plans_regpec")
    assert plans.extra.get("always_on") is None
    assert zones.extra.get("always_on") is None
    vig = next(layer for layer in layers if layer.id == "vigilance_stations")
    assert vig.filter_spec is not None
    assert vig.filter_spec.kind == "none"
    assert vig.extra.get("etat_colors") is True


def test_harvest_skip_remote(tmp_path, monkeypatch):
    import importlib

    harvest_mod = importlib.import_module("peche.catalog.harvest")
    monkeypatch.setattr(harvest_mod, "CATALOG_DIR", tmp_path / "catalog")
    monkeypatch.setattr(harvest_mod, "CATALOG_PATH", tmp_path / "catalog" / "catalog.json")
    monkeypatch.setattr(harvest_mod, "CAPS_CACHE_DIR", tmp_path / "catalog" / "capabilities")
    catalog = harvest_mod.harvest(skip_remote=True)
    assert catalog.version == 1
    assert len(catalog.basemaps) >= 1
    assert sum(len(g.layers) for g in catalog.groups) >= 18
    assert (tmp_path / "catalog" / "catalog.json").exists()


def test_ensure_catalog_loads():
    catalog = ensure_catalog()
    assert catalog.layer_by_id("lidar_pentes") is not None
    assert catalog.layer_by_id("pente_cpl") is None
    assert catalog.layer_by_id("fond_quebec") is not None


def test_catalog_is_curated_only():
    catalog = ensure_catalog()
    group_ids = {g.id for g in catalog.groups}
    assert "biodiversite" not in group_ids
    assert "perturbations" not in group_ids
    assert "foret" not in group_ids
    assert "qualite_eau" not in group_ids
    for group in catalog.groups:
        assert group.layers
        assert all(layer.curated for layer in group.layers)
    assert catalog.layer_by_id("environnement_wss:Sols") is None
    assert catalog.layer_by_id("environnement_wss:Zone_chasse_da3_sefaq") is None


def test_merge_ignores_harvested_dumps():
    from peche.catalog.harvest import _merge_catalog

    harvested = [
        LayerDef(
            id="environnement_wss:Sols",
            title="Sols",
            group="hydrographie",
            source_type="wms",
            url="https://example.com/wms",
            layer_name="Sols",
        ),
        LayerDef(
            id="aires_protegees:x",
            title="Parc",
            group="biodiversite",
            source_type="wms",
            url="https://example.com/wms",
            layer_name="x",
        ),
        LayerDef(
            id="aleas:feux",
            title="Feux",
            group="perturbations",
            source_type="wms",
            url="https://example.com/wms",
            layer_name="feux",
        ),
    ]
    catalog = _merge_catalog(harvested, curated_layers(), [])
    assert {g.id for g in catalog.groups}.isdisjoint(
        {"biodiversite", "perturbations"}
    )
    assert catalog.layer_by_id("environnement_wss:Sols") is None
    assert catalog.layer_by_id("aires_protegees:x") is None
    hydro = next(g for g in catalog.groups if g.id == "hydrographie")
    assert all(layer.curated for layer in hydro.layers)


def test_harvest_sources_are_basemaps_only():
    from peche.catalog.sources import (
        BASEMAP_SOURCES,
        GEOSERVER_SOURCES,
        WMS_SOURCES,
        all_harvest_sources,
    )

    ids = {src.id for src in all_harvest_sources()}
    assert ids == {src.id for src in BASEMAP_SOURCES}
    assert {src.id for src in GEOSERVER_SOURCES}.isdisjoint(ids)
    assert {src.id for src in WMS_SOURCES}.isdisjoint(ids)


def test_layer_def_to_dict():
    layer = LayerDef(
        id="x",
        title="X",
        group="g",
        source_type="wms",
        url="https://example.com",
        filter_spec=FilterSpec(kind="none"),
    )
    d = layer.to_dict()
    assert d["id"] == "x"
    assert d["filter_spec"]["kind"] == "none"


def test_zone_mapping_basic():
    assert match_zone(18, "") is not None
    assert match_zone(18, "").text == "Zone 18"
    z13e = match_zone(13, "Est")
    assert z13e is not None
    assert "est" in z13e.text.lower()
    z13o = match_zone(13, "Ouest")
    assert z13o is not None
    assert "ouest" in z13o.text.lower()
    z19n = match_zone(19, "nord")
    assert z19n is not None
    assert z19n.value == 3063


def test_regpec_lookup_covers_splits():
    lookup = build_regpec_lookup()
    assert (13, "est") in lookup
    assert (13, "ouest") in lookup
    assert (19, "nord") in lookup
    assert (22, "nord") in lookup
    assert (22, "sud") in lookup


def test_zone_mapping_wfs_aliases():
    z13e = match_zone(13, "")
    assert z13e is not None
    assert z13e.value == 13
    z13o = match_zone(13, "Sud-ouest")
    assert z13o is not None
    assert z13o.value == 14
    z19a = match_zone(19, "Sud-Est")
    assert z19a is not None
    assert z19a.value == 2652
    z19b = match_zone(19, "Sud-Ouest")
    assert z19b is not None
    assert z19b.value == 2653
    split22 = match_zones(22, "")
    assert {z.value for z in split22} == {24, 25}
    split23 = match_zones(23, "")
    assert {z.value for z in split23} == {26, 27}
