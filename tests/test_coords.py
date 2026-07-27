"""Tests pour peche.coords."""

import json

from peche.coords import extract_zone, parse_dms, split_name


def test_parse_dms_full_seconds():
    text = 'Lac (48°25\'13" N., 67°19\'34" O.)'
    coords = parse_dms(text)
    assert coords is not None
    assert abs(coords["lat"] - 48.420278) < 0.001
    assert abs(coords["lon"] - (-67.326111)) < 0.001


def test_parse_dms_missing_seconds():
    text = "(47°23' N., 71°10' O.)"
    coords = parse_dms(text)
    assert coords is not None
    assert coords["lat"] > 47.3


def test_parse_dms_invalid():
    assert parse_dms("pas de coords") is None


def test_split_name():
    assert split_name("Lac au Saumon (48°25' N., 67°19' O.)") == "Lac au Saumon"
    assert split_name("Sans parenthèse") == "Sans parenthèse"


def test_extract_zone(tmp_path, monkeypatch):
    import peche.coords as coords_mod

    monkeypatch.setattr(coords_mod, "DATA_DIR", tmp_path)
    zone_data = {
        "meta": {"zone_id": 99, "zone_nom": "Zone test"},
        "plans_eau": [
            {
                "id": 1,
                "nom": "Lac Test (48°25'13\" N., 67°19'34\" O.)",
                "segments": [],
            },
            {"id": 2, "nom": "Plan sans coords", "segments": []},
        ],
    }
    zone_path = tmp_path / "99.json"
    zone_path.write_text(json.dumps(zone_data), encoding="utf-8")
    result = extract_zone(zone_path)
    assert result["meta"]["zone_id"] == 99
    assert result["meta"]["nb_geocoded"] >= 1
    locs = result["locations"]
    assert any(loc["id"] == 1 and loc["lat"] is not None for loc in locs)
