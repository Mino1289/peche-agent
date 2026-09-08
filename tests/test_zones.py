"""Tests pour peche.reglements.zones."""

import pytest

from peche.reglements.zones import ZONES, display_number, resolve_zone_ref, zone_by_id


def test_zones_count():
    assert len(ZONES) == 34


def test_zone_by_id_known():
    z = zone_by_id(32)
    assert z is not None
    assert z.value == 32
    assert "28" in z.text


def test_zone_by_id_special_ids():
    assert zone_by_id(3063) is not None
    assert zone_by_id(2652) is not None
    assert zone_by_id(2653) is not None


def test_zone_by_id_unknown():
    assert zone_by_id(99999) is None


def test_zones_frozen():
    z = zone_by_id(1)
    assert z is not None
    with pytest.raises(AttributeError):
        z.value = 99  # type: ignore[misc]


def test_resolve_zone_ref_prefers_display_number():
    z = resolve_zone_ref(28)
    assert z is not None
    assert z.text == "Zone 28"
    assert z.value == 32
    assert display_number(z) == 28
    by_id = resolve_zone_ref(32)
    assert by_id is not None
    assert by_id.value == 32


def test_resolve_zone_by_kind_regpec_zone21():
    """zone_id RegPec 23 = Zone 21 affichée, pas Zone 23 nord."""
    from peche.reglements.zones import resolve_zone_by_kind

    z = resolve_zone_by_kind(23, id_kind="regpec")
    assert z is not None
    assert z.text == "Zone 21"
    assert z.value == 23
    # auto / display : 23 = Zone 23 nord
    z_nord = resolve_zone_by_kind(23, id_kind="display")
    assert z_nord is not None
    assert "23" in z_nord.text


def test_plans_geojson_no_double_resolve(monkeypatch):
    """plans_geojson(23) doit rester Zone 21 (id 23), pas Zone 23 nord (26)."""
    from peche.spatial.plan_geom import plans_geojson

    captured: list[list[int] | None] = []

    def fake_fetch(bbox, *, zone_id=None, zone_ids=None, plan_id=None, limit=2000):
        captured.append(zone_ids if zone_ids is not None else ([zone_id] if zone_id is not None else None))
        return []

    monkeypatch.setattr("peche.spatial.plan_geom._load_offline_plans", lambda: [])
    monkeypatch.setattr("peche.spatial.plan_geom._plans_cache_get", lambda _key: None)
    monkeypatch.setattr(
        "peche.spatial.plan_geom._fetch_regpec_polygons", fake_fetch
    )
    monkeypatch.setattr(
        "peche.spatial.plan_geom._plans_geojson_fallback",
        lambda bbox, *, resolved_zone=None, resolved_zone_ids=None, limit: {
            "type": "FeatureCollection",
            "features": [],
        },
    )
    plans_geojson(None, zone_id=23)
    assert captured == [[23]]
