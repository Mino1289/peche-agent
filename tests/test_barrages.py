"""Tests pour peche.barrages."""

from peche.barrages import (
    _parse_coord,
    _plan_eau_from_row,
    barrages_near_response,
    nearest_barrages,
    search_barrages_offline,
)


def test_parse_coord_variants():
    assert _parse_coord(48.5) == 48.5
    assert _parse_coord("48,5") == 48.5
    assert _parse_coord("—") is None
    assert _parse_coord(None) is None


def test_plan_eau_from_row():
    assert _plan_eau_from_row("Lac A", "Rivière B") == "Lac A / Rivière B"
    assert _plan_eau_from_row("", "") == ""


def test_search_barrages_offline(patch_barrages_cache):
    hits = search_barrages_offline("Kénogami", limit=5)
    assert len(hits) >= 1
    assert hits[0]["nom"] == "Barrage Kénogami"


def test_nearest_barrages(patch_barrages_cache):
    hits = nearest_barrages(48.45, -71.25, radius_km=10)
    assert len(hits) >= 1
    assert hits[0]["distance_km"] == 0.0


def test_barrages_near_response_empty(monkeypatch):
    import peche.barrages as barrages_mod

    monkeypatch.setattr(barrages_mod, "_barrages_cached", lambda: [])
    out = barrages_near_response(lat=48.45, lon=-71.25, label="Sans barrage")
    assert out["count"] == 0
    assert "error_no_barrage" in out
