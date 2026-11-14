"""Tests pour peche.hydromet."""

from unittest.mock import patch

import pytest

from peche.hydromet import (
    fetch_live_stations,
    _normalize_station,
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


def test_normalize_station_valid():
    # Coordonnées EPSG:3857 de la station 061004 (lon ≈ -71.19, lat ≈ 48.4)
    row = {
        "id": 517,
        "label": "061004",
        "description": "Test",
        "plan_deau": "Rivière Chicoutimi",
        "geom_p": {"type": "Point", "coordinates": [-7925613.786008699, 6157914.152953517]},
        "dern_valeur_niv": 151.012,
        "dern_valeur_deb": 28.15,
        "date_prise_valeur": "2026-11-13T23:00:00",
        "refoule_niv": False,
        "refoule_deb": False,
        "etat_max": 1,
    }
    out = _normalize_station(row)
    assert out is not None
    assert out["station"] == "061004"
    assert out["url_vigilance"].endswith("/stations/517")
    assert abs(out["lon"] - -71.19) < 0.01 and abs(out["lat"] - 48.4) < 0.1
    assert out["niveau_m"] == 151.012
    assert out["etat"] == "État normal"


def test_normalize_station_invalid_geometry():
    assert _normalize_station({"geom_p": {"type": "LineString"}}) is None


def test_plan_station_list_geo_fallback_when_match_empty(monkeypatch):
    # Matching précalculé vide (périmé) : la station à ~12 km doit être trouvée via les coords du plan.
    from peche import tools

    live = [
        {"station": "HQ-S-1-2921", "description": "Bersimis 1 Est", "plan_eau": "",
         "lat": 49.6058, "lon": -70.1111, "niveau_m": 397.3, "debit_m3s": None},
        {"station": "FAR", "description": "Loin", "plan_eau": "",
         "lat": 40.0, "lon": -60.0, "niveau_m": 1.0, "debit_m3s": None},
    ]
    monkeypatch.setattr(tools, "load_stations", lambda: live)
    match = {"plan_id": 10946, "lat": 49.541667, "lon": -70.239444, "stations": []}
    stations = tools._plan_station_list(match)
    assert [s["station"] for s in stations] == ["HQ-S-1-2921"]
    assert stations[0]["role"] == "level"
    assert stations[0]["match_reason"] == "geo"


def test_fetch_live_stations_rejects_wfs_exception_report():
    xml = "<ows:ExceptionReport><ows:ExceptionText>Query error</ows:ExceptionText></ows:ExceptionReport>"
    with patch("peche.hydromet.fetch_text", return_value=xml):
        with pytest.raises(RuntimeError, match="inattendue"):
            fetch_live_stations()
