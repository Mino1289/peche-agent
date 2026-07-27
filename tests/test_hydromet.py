"""Tests pour peche.hydromet."""

from peche.hydromet import (
    _normalize_feature,
    _station_role,
    _water_names_match,
    haversine_km,
    match_stations_for_plan,
    nearest_stations,
    search_stations_offline,
)


def test_haversine_same_point():
    assert haversine_km(48.5, -71.0, 48.5, -71.0) == 0.0


def test_haversine_positive_distance():
    d = haversine_km(48.5, -71.0, 48.6, -71.1)
    assert d > 0


def test_water_names_match():
    assert _water_names_match("Lac Kénogami", "Lac Kénogami") is True
    assert _water_names_match("Lac Kénogami", "Rivière Pikauba") is False


def test_station_role():
    assert _station_role({"niveau_m": 1.0, "debit_m3s": 2.0}) == "both"
    assert _station_role({"niveau_m": 1.0}) == "level"
    assert _station_role({"debit_m3s": 2.0}) == "flow"


def test_nearest_stations(mini_stations):
    hits = nearest_stations(48.45, -71.20, mini_stations, radius_km=25, limit=3)
    assert len(hits) >= 1
    assert hits[0]["distance_km"] <= 25


def test_match_stations_for_plan_name_match(mini_stations):
    hits = match_stations_for_plan(
        "Lac Kénogami", 48.45, -71.20, mini_stations
    )
    assert len(hits) >= 2
    assert all(h["match_reason"] == "name" for h in hits)


def test_search_stations_offline(mini_stations):
    hits = search_stations_offline("Kénogami", mini_stations)
    assert len(hits) >= 1


def test_normalize_feature_valid():
    feature = {
        "geometry": {"type": "Point", "coordinates": [-71.0, 48.5]},
        "properties": {
            "station": "TEST01",
            "description": "Test",
            "plan_deau": "Lac Test",
        },
    }
    out = _normalize_feature(feature)
    assert out is not None
    assert out["station"] == "TEST01"
    assert out["lat"] == 48.5


def test_normalize_feature_invalid_geometry():
    assert _normalize_feature({"geometry": {"type": "LineString"}}) is None
