"""Tests unitaires pour la carte interactive."""

import pytest

folium = pytest.importorskip("folium")

from peche.map_view import (  # noqa: E402
    build_folium_map,
    map_context_from_messages,
    map_layer_counts,
)


def test_map_context_empty_messages():
    ctx = map_context_from_messages([], fetch_weather=False)
    assert ctx["plan_pin"] is None
    assert ctx["weather"] is None
    assert ctx["center"] is None
    assert ctx["zoom"] == 7
    assert ctx["label"] is None


def test_map_context_from_search_plans():
    messages = [
        {
            "role": "assistant",
            "text": "Voici les plans.",
            "tools": [
                {
                    "name": "search_plans",
                    "args": {"query": "Lac au Saumon"},
                    "result": {
                        "candidates": [
                            {
                                "plan_id": 45,
                                "zone_id": 1,
                                "nom": "Lac au Saumon",
                                "score": 0.95,
                            }
                        ],
                        "groups": [],
                    },
                }
            ],
        }
    ]
    ctx = map_context_from_messages(messages, fetch_weather=False)
    assert ctx["label"] == "Lac au Saumon"
    assert ctx["plan_pin"] is not None
    assert ctx["plan_pin"]["plan_id"] == 45
    assert ctx["plan_pin"]["zone_id"] == 1
    assert ctx["center"] == (ctx["plan_pin"]["lat"], ctx["plan_pin"]["lon"])
    assert ctx["zoom"] == 11


def test_map_context_from_get_weather_at_plan():
    messages = [
        {
            "role": "assistant",
            "text": "Météo.",
            "tools": [
                {
                    "name": "get_weather_at_plan",
                    "args": {"plan_id": 45, "zone_id": 1},
                    "result": {
                        "plan_id": 45,
                        "zone_id": 1,
                        "plan_nom": "Lac au Saumon",
                        "plan_lat": 48.420278,
                        "plan_lon": -67.326111,
                        "temperature_c": 12.5,
                        "source": "GeoMet citypageweather-realtime",
                    },
                }
            ],
        }
    ]
    ctx = map_context_from_messages(messages, fetch_weather=False)
    assert ctx["label"] == "Lac au Saumon"
    assert ctx["plan_pin"]["nom"] == "Lac au Saumon"
    assert ctx["weather"] is not None
    assert ctx["weather"]["lat"] == pytest.approx(48.420278)
    assert ctx["weather"]["conditions"]["temperature_c"] == 12.5


def test_map_context_place_overridden_by_plan():
    messages = [
        {
            "role": "assistant",
            "text": "Résultats.",
            "tools": [
                {
                    "name": "get_weather_at_place",
                    "args": {"place": "Chicoutimi"},
                    "result": {
                        "place": "Chicoutimi",
                        "geocoded": {
                            "lat": 48.42,
                            "lon": -71.05,
                            "display_name": "Chicoutimi",
                        },
                        "temperature_c": 10.0,
                    },
                },
                {
                    "name": "get_hydromet_for_waterbody",
                    "args": {"plan_id": 45, "zone_id": 1},
                    "result": {
                        "plan_id": 45,
                        "zone_id": 1,
                        "plan_nom": "Lac au Saumon",
                        "stations": [],
                    },
                },
            ],
        }
    ]
    ctx = map_context_from_messages(messages, fetch_weather=False)
    assert ctx["plan_pin"]["plan_id"] == 45
    assert ctx["label"] == "Lac au Saumon"


def test_build_folium_map_minimal_layers():
    m = build_folium_map(
        center=(48.5, -71.0),
        zoom=8,
        hydro_stations=[
            {
                "lat": 48.5,
                "lon": -71.0,
                "station": "TEST01",
                "plan_eau": "Lac test",
                "description": "Station test",
            }
        ],
        tide_stations=[],
        cehq_barrages=[
            {
                "lat": 48.51,
                "lon": -71.01,
                "nom": "Barrage test",
                "numero": "B-001",
                "plan_eau": "Rivière test",
                "categorie": "Barrage",
                "municipalite": "Testville",
                "url_fiche": "https://example.com",
            }
        ],
        plan_pin={"lat": 48.5, "lon": -71.0, "nom": "Plan test"},
        weather={
            "lat": 48.5,
            "lon": -71.0,
            "conditions": {"temperature_c": 15},
        },
    )
    assert m is not None
    html = m.get_root().render()
    assert "Barrage test" in html
    assert "TEST01" in html


def test_map_layer_counts_keys():
    counts = map_layer_counts()
    assert {"hydro", "barrages", "tides"}.issubset(counts)
    assert all(isinstance(v, int) for v in counts.values())


def test_map_context_includes_bbox():
    messages = [
        {
            "role": "assistant",
            "text": "Plan.",
            "tools": [
                {
                    "name": "search_plans",
                    "args": {"query": "Lac au Saumon"},
                    "result": {
                        "candidates": [
                            {"plan_id": 45, "zone_id": 1, "nom": "Lac au Saumon", "score": 0.9}
                        ],
                        "groups": [],
                    },
                }
            ],
        }
    ]
    ctx = map_context_from_messages(messages, fetch_weather=False)
    assert ctx.get("bbox") is not None
    assert len(ctx["bbox"]) == 4
