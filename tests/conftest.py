"""Fixtures partagées pour la suite de tests peche-agent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def mini_barrages() -> list[dict]:
    return [
        {
            "numero": "X-001",
            "nom": "Barrage Kénogami",
            "plan_eau": "Lac Kénogami",
            "municipalite": "Saguenay",
            "mrc": "Le Fjord-du-Saguenay",
            "categorie": "Barrage",
            "lat": 48.45,
            "lon": -71.25,
            "url_fiche": "https://example.com/b1",
        },
        {
            "numero": "X-002",
            "nom": "Barrage Test",
            "plan_eau": "Rivière Test",
            "municipalite": "Testville",
            "mrc": "Test",
            "categorie": "Petit barrage",
            "lat": 48.51,
            "lon": -71.30,
            "url_fiche": "https://example.com/b2",
        },
        {
            "numero": "X-003",
            "nom": "Barrage Lointain",
            "plan_eau": "Lac Lointain",
            "municipalite": "Loin",
            "mrc": "Loin",
            "categorie": "Barrage",
            "lat": 50.0,
            "lon": -75.0,
            "url_fiche": "https://example.com/b3",
        },
    ]


@pytest.fixture
def mini_stations() -> list[dict]:
    return [
        {
            "station": "061001",
            "description": "Barrage Chute-Garneau",
            "plan_eau": "Lac Kénogami",
            "lat": 48.45,
            "lon": -71.20,
            "niveau_m": 100.5,
            "debit_m3s": None,
        },
        {
            "station": "061002",
            "description": "Barrage Portage-des-Roches",
            "plan_eau": "Lac Kénogami",
            "lat": 48.46,
            "lon": -71.22,
            "niveau_m": 99.8,
            "debit_m3s": None,
        },
        {
            "station": "072001",
            "description": "Débit rivière Pikauba",
            "plan_eau": "Rivière Pikauba",
            "lat": 48.50,
            "lon": -71.10,
            "niveau_m": None,
            "debit_m3s": 42.0,
        },
    ]


@pytest.fixture
def mini_tide_stations() -> list[dict]:
    return [
        {
            "station_id": "uuid-1",
            "code": "03480",
            "nom": "Chicoutimi",
            "nom_alternatif": "",
            "lat": 48.42,
            "lon": -71.05,
            "operating": True,
            "type": "tide",
        },
        {
            "station_id": "uuid-2",
            "code": "03045",
            "nom": "Rimouski",
            "nom_alternatif": "",
            "lat": 48.45,
            "lon": -68.52,
            "operating": True,
            "type": "tide",
        },
    ]


@pytest.fixture
def mini_search_index() -> list[dict]:
    return [
        {
            "plan_id": 100,
            "zone_id": 32,
            "nom": "Rivière Sainte-Marguerite a)",
            "nom_brut": "Rivière Sainte-Marguerite a) entre un point",
            "nom_search": "riviere sainte marguerite a",
            "segment_label": "a)",
            "river_base_name": "riviere sainte marguerite",
            "aliases": ["ste marguerite", "sainte marguerite"],
            "lat": 48.5,
            "lon": -70.0,
        },
        {
            "plan_id": 101,
            "zone_id": 32,
            "nom": "Rivière Sainte-Marguerite b)",
            "nom_brut": "Rivière Sainte-Marguerite b) entre deux points",
            "nom_search": "riviere sainte marguerite b",
            "segment_label": "b)",
            "river_base_name": "riviere sainte marguerite",
            "aliases": ["ste marguerite b"],
            "lat": 48.51,
            "lon": -70.01,
        },
        {
            "plan_id": 45,
            "zone_id": 1,
            "nom": "Lac au Saumon",
            "nom_brut": "Lac au Saumon",
            "nom_search": "lac au saumon",
            "segment_label": None,
            "river_base_name": "lac au saumon",
            "aliases": ["lac saumon"],
            "lat": 48.420278,
            "lon": -67.326111,
        },
    ]


@pytest.fixture
def tmp_db(tmp_path):
    from peche.conversations.store import ConversationStore

    return ConversationStore(db_path=tmp_path / "test.db")


def _safe_lru_clear(fn) -> None:
    if hasattr(fn, "cache_clear"):
        fn.cache_clear()


@pytest.fixture(autouse=True)
def clear_caches():
    """Vide les caches mémoire entre chaque test."""
    import peche.barrages as barrages_mod
    import peche.geocoding as geocoding_mod
    import peche.tides as tides_mod
    import peche.tools as tools_mod
    import peche.weather as weather_mod

    _safe_lru_clear(tools_mod._load_search_index)
    _safe_lru_clear(tools_mod._load_zone)
    _safe_lru_clear(tools_mod._load_locations)
    _safe_lru_clear(tools_mod._load_match)
    _safe_lru_clear(barrages_mod._barrages_cached)
    _safe_lru_clear(tides_mod._stations_cached)
    weather_mod._CACHE.clear()
    geocoding_mod._CACHE.clear()
    yield
    _safe_lru_clear(tools_mod._load_search_index)
    _safe_lru_clear(tools_mod._load_zone)
    _safe_lru_clear(tools_mod._load_locations)
    _safe_lru_clear(tools_mod._load_match)
    _safe_lru_clear(barrages_mod._barrages_cached)
    _safe_lru_clear(tides_mod._stations_cached)
    weather_mod._CACHE.clear()
    geocoding_mod._CACHE.clear()


@pytest.fixture
def patch_barrages_cache(monkeypatch, mini_barrages):
    import peche.barrages as barrages_mod

    monkeypatch.setattr(barrages_mod, "_barrages_cached", lambda: mini_barrages)
    return mini_barrages


@pytest.fixture
def patch_search_index(monkeypatch, mini_search_index):
    import peche.tools as tools_mod

    monkeypatch.setattr(tools_mod, "_load_search_index", lambda: mini_search_index)
    return mini_search_index


@pytest.fixture
def patch_tide_stations(monkeypatch, mini_tide_stations):
    import peche.tides as tides_mod

    monkeypatch.setattr(
        tides_mod, "_stations_cached", lambda: (mini_tide_stations, "test")
    )
    return mini_tide_stations
