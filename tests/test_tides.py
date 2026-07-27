"""Tests pour peche.tides."""

from peche.tides import (
    _classify_hilo,
    _resolve_zone,
    nearest_tide_station,
    search_tide_stations,
)


def test_classify_hilo_alternating():
    rows = [
        {"value_m": 1.0, "time": "t1"},
        {"value_m": 3.0, "time": "t2"},
        {"value_m": 1.5, "time": "t3"},
    ]
    out = _classify_hilo(rows)
    assert out[0]["type"] == "basse"
    assert out[1]["type"] == "pleine"


def test_classify_hilo_single():
    out = _classify_hilo([{"value_m": 2.0}])
    assert out[0]["type"] == "extremum"


def test_resolve_zone_canada_eastern():
    tz = _resolve_zone("Canada/Eastern")
    assert str(tz) in ("America/Toronto", "Canada/Eastern")


def test_search_tide_stations(patch_tide_stations):
    hits = search_tide_stations("Chicoutimi")
    assert len(hits) >= 1
    assert hits[0]["station_code"] == "03480"


def test_nearest_tide_station(patch_tide_stations):
    near = nearest_tide_station(48.42, -71.05, radius_km=75)
    assert near is not None
    assert near["station_code"] == "03480"
    assert near["distance_km"] < 5


def test_nearest_tide_station_out_of_range(patch_tide_stations):
    assert nearest_tide_station(60.0, -100.0, radius_km=10) is None
