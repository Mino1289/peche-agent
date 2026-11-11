"""Scout conditions : espèces du règlement plan (zone 21 exception) et pin vide."""

from peche import tools
from peche.agent import map_tools


def _regs(plan_species, zone_species=()):
    return {
        "plan_eau": {
            "segments": [
                {"periodes": [{"especes": [{"espece": n} for n in plan_species]}]}
            ]
        },
        "regles_generales": [
            {"periodes": [{"especes": [{"espece": n} for n in zone_species]}]}
        ],
    }


def test_species_names_dedupes_nested():
    segs = [
        {"periodes": [{"especes": [{"espece": "Truite"}, {"espece": "Doré"}]}]},
        {"periodes": [{"especes": [{"espece": "Truite"}]}]},
    ]
    assert tools._species_names(segs) == ["Truite", "Doré"]


def test_species_regs_plan_only_outside_zone21(monkeypatch):
    monkeypatch.setattr(
        tools, "get_reglements", lambda *_a, **_k: _regs(["Truite"], ["Brochet"])
    )
    assert tools._species_regs(32, 1)["especes"] == ["Truite"]
    assert tools._species_regs(23, 1)["especes"] == ["Truite", "Brochet"]


def test_species_regs_error_passthrough(monkeypatch):
    monkeypatch.setattr(tools, "get_reglements", lambda *_a, **_k: {"error": "x"})
    assert tools._species_regs(32, 1) == {"error": "x"}


def test_scout_empty_point_adds_nearby_plan_regs(monkeypatch):
    monkeypatch.setattr(tools, "get_weather", lambda lat, lon: {"temperature_c": 12})
    monkeypatch.setattr(
        tools,
        "_scout_hydro",
        lambda lat, lon: {"station_id": "061004", "water_temp": None},
    )
    monkeypatch.setattr(
        tools,
        "_load_locations",
        lambda zid: [{"id": 7, "nom": "Lac X", "lat": 46.0, "lon": -71.0}],
    )
    monkeypatch.setattr(
        tools, "get_reglements", lambda *_a, **_k: _regs(["Doré"])
    )
    out = tools.scout_conditions(46.0, -71.0, zone_id=32, include_nearby_regs=True)
    assert out["weather"] == {"temperature_c": 12}
    assert out["water_temp"] is None
    assert "nearby_hydro" in out and "species_guide" in out
    assert out["nearby_plan"]["plan_id"] == 7
    assert out["nearby_plan"]["species_regs"]["especes"] == ["Doré"]


def test_scout_hydro_keeps_hq_meteo_and_skips_air_temp_as_water(monkeypatch):
    from peche import tools as t

    stations = [{"station": "HQ-S-1-6690", "lat": 49.36, "lon": -70.92}]
    monkeypatch.setattr(t, "load_stations", lambda: stations)
    live = {
        "station_id": "HQ-S-1-6690",
        "hq_metrics": [
            {"type_point_donnee": "Température Minimum", "valeur": -2.6, "nom_unite_mesure": "°C"},
            {"type_point_donnee": "Vitesse du vent.10 mètres", "valeur": 15.3, "nom_unite_mesure": "km/h"},
            {"type_point_donnee": "Température de l'eau", "valeur": 6.1, "nom_unite_mesure": "°C"},
        ],
    }
    monkeypatch.setattr(t, "get_hydromet", lambda _sid: live)
    out = t._scout_hydro(49.3598, -70.9152)
    assert out["station_id"] == "HQ-S-1-6690"
    assert len(out["meteo_hq"]) == 3
    assert out["water_temp"] == [
        {"type": "Température de l'eau", "valeur": 6.1, "unite": "°C"}
    ]


def test_point_info_empty_point_passes_lat_then_lon(monkeypatch):
    seen = {}

    def fake_scout(lat, lon, **_k):
        seen["lat"], seen["lon"] = lat, lon
        return {"weather": {}}

    monkeypatch.setattr(tools, "scout_conditions", fake_scout)
    monkeypatch.setattr(
        map_tools,
        "_resolve_point",
        lambda lon, lat, **_k: {"lon": lon, "lat": lat, "fishing_zone": {"zone_id": 32}},
    )
    out = map_tools.get_point_info(lon=-70.44, lat=48.43)
    assert (seen["lat"], seen["lon"]) == (48.43, -70.44)
    assert out["lon"] == -70.44 and out["lat"] == 48.43


def test_point_info_on_waterbody_skips_scout(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("scout must not run on a waterbody")

    monkeypatch.setattr(tools, "scout_conditions", boom)
    monkeypatch.setattr(
        map_tools,
        "_resolve_point",
        lambda lon, lat, **_k: {
            "lon": lon,
            "lat": lat,
            "waterbody": {"name": "Lac"},
        },
    )
    out = map_tools.get_point_info(lon=-71.0, lat=46.0)
    assert "weather" not in out
    assert out["waterbody"]["name"] == "Lac"


def test_nearest_hq_meteo_picks_meteo_station_not_nearest_hydro(monkeypatch):
    stations = [
        {"station": "HYDRO-1", "lat": 49.5417, "lon": -70.2394, "hq_metrics": None},
        {"station": "HQ-METEO-1", "lat": 49.60, "lon": -70.30, "hq_metrics": [{"type_point_donnee": "vent"}]},
    ]
    monkeypatch.setattr(tools, "load_stations", lambda: stations)
    monkeypatch.setattr(
        tools,
        "get_hydromet",
        lambda sid: {
            "station_id": sid,
            "observed_at": "2026-11-11T01:00:00Z",
            "hq_metrics": [{"type_point_donnee": "vent", "valeur": 12, "nom_unite_mesure": "km/h"}],
        },
    )
    out = tools._nearest_hq_meteo(49.5417, -70.2394)
    assert out["station_id"] == "HQ-METEO-1"
    assert out["distance_km"] < 25
    assert out["meteo_hq"][0]["valeur"] == 12


def test_stations_proches_sorted_across_sources(monkeypatch):
    stations = [
        {"station": "HQ-NEAR", "description": "Lac Porto", "lat": 49.5842, "lon": -70.2759, "hq_metrics": [{"type_point_donnee": "x"}]},
        {"station": "HQ-MID", "description": "Bersimis 1 Est", "lat": 49.6058, "lon": -70.1111, "hq_metrics": [{"type_point_donnee": "x"}]},
    ]
    cities = [{"ville": "Baie-Comeau", "lat": 48.74, "lon": -69.08}]
    monkeypatch.setattr(tools, "load_stations", lambda: stations)
    monkeypatch.setattr(tools, "_load_eccc_cities", lambda: cities)
    monkeypatch.setattr(
        tools,
        "get_hydromet",
        lambda sid: {"observed_at": None, "plan_eau": None, "hq_metrics": [{"type_point_donnee": "x", "valeur": 1}]},
    )
    geomet = {"ville": "Baie-Comeau", "temperature_c": 1.9}
    out = tools._stations_proches(49.5417, -70.2394, geomet)
    assert [e["source"] for e in out] == ["HQ", "HQ", "GeoMet/ECCC"]
    assert out[0]["station_id"] == "HQ-NEAR"
    assert out[0]["distance_km"] < out[1]["distance_km"] < out[2]["distance_km"]
    assert out[2]["mesures"][0]["valeur"] == 1.9
    assert "mesures" in out[0] and "mesures" in out[1]
