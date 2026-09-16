"""Tests guide poisson — uninvert, index, lookup."""

import json

from peche.guide_poisson.lookup import lookup_guide_poisson, load_index
from peche.guide_poisson.names import uninvert_hydronyme
from peche.guide_poisson.sync import build_index


def test_uninvert_hydronyme():
    assert uninvert_hydronyme("Sept Îles, Lac des") == "Lac des Sept Îles"
    assert uninvert_hydronyme("Sans virgule") == "Sans virgule"


def test_build_index_assigns_zone(monkeypatch):
    monkeypatch.setattr(
        "peche.guide_poisson.sync.fishing_zone_at_point",
        lambda lon, lat: {"zone_id": 8, "no_zone": "8", "zone_nom": "Zone 8"},
    )
    rows = [
        {
            "HYDRONYME": "Témiscouata, Lac",
            "NOM_COMMUN": "Brochet",
            "NOM_LATIN": "Esox lucius",
            "STATUT_PECHE": "Pêche sportive",
            "P_NB_REPAS": "4",
            "M_NB_REPAS": "3",
            "G_NB_REPAS": "2",
            "LONGITUDE": "-68.123",
            "LATITUDE": "47.456",
        }
    ]
    index = build_index(rows)
    assert len(index["sites"]) == 1
    site = index["sites"][0]
    assert site["zone_id"] == 8
    assert "Témiscouata" in site["nom"]
    assert index["species_by_site"][site["id"]][0]["nom_commun"] == "Brochet"


def test_lookup_by_name_and_zone(tmp_path, monkeypatch):
    idx = {
        "guide_url": "https://example.com/guide",
        "sites": [
            {
                "id": "abc",
                "nom": "Lac Témiscouata",
                "nom_norm": "lac temiscouata",
                "zone_id": 8,
                "lon": -68.1,
                "lat": 47.4,
            }
        ],
        "species_by_site": {
            "abc": [{"nom_commun": "Ombre", "nom_latin": "Salvelinus fontinalis"}]
        },
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(idx), encoding="utf-8")
    monkeypatch.setattr("peche.guide_poisson.lookup.INDEX_PATH", path)
    load_index.cache_clear()

    hit = lookup_guide_poisson(zone_id=8, nom="Temiscouata")
    assert hit["site"]["id"] == "abc"
    assert hit["species"][0]["nom_commun"] == "Ombre"


def test_lookup_empty_without_match(tmp_path, monkeypatch):
    idx = {"sites": [], "species_by_site": {}}
    path = tmp_path / "index.json"
    path.write_text(json.dumps(idx), encoding="utf-8")
    monkeypatch.setattr("peche.guide_poisson.lookup.INDEX_PATH", path)
    load_index.cache_clear()

    hit = lookup_guide_poisson(zone_id=99, nom="Inconnu")
    assert hit["species"] == []
    assert "message" in hit


def test_lookup_nearest_by_coords(tmp_path, monkeypatch):
    idx = {
        "sites": [
            {
                "id": "near",
                "nom": "Lac Test",
                "nom_norm": "lac test",
                "zone_id": 8,
                "lon": -68.0,
                "lat": 47.0,
            }
        ],
        "species_by_site": {"near": [{"nom_commun": "Truite"}]},
    }
    path = tmp_path / "index.json"
    path.write_text(json.dumps(idx), encoding="utf-8")
    monkeypatch.setattr("peche.guide_poisson.lookup.INDEX_PATH", path)
    load_index.cache_clear()

    hit = lookup_guide_poisson(zone_id=8, lon=-68.001, lat=47.001)
    assert hit["site"]["id"] == "near"
