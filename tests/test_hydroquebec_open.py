"""Tests parse Hydro-Québec open JSON (sans réseau)."""

from peche.cehq import build_history_payload
from peche.hydroquebec_open import (
    _latest_in_donnees,
    normalize_hq_records,
    readings_from_hq_composition,
)


def test_latest_in_donnees():
    val, ts = _latest_in_donnees(
        {
            "2026/11/01T00:00:00Z": "1.0",
            "2026/11/06T12:00:00Z": "2.5",
        }
    )
    assert val == 2.5
    assert ts == "2026-11-06T12:00:00Z"


def test_normalize_hq_site_row():
    row = {
        "identifiant": "99-1",
        "nom": "Laforge-1",
        "xcoord": "-71.0",
        "ycoord": "54.5",
        "CodeRegionQC": "10",
        "RegionQC": "Nord-du-Québec",
        "Composition": [
            {
                "type_point_donnee": "Apport naturel",
                "nom_unite_mesure": "m³/s",
                "pas_temps": "Journalier",
                "type_mesure": "Moyenne",
                "Donnees": {"2026/11/05T00:00:00Z": "12.3"},
            },
            {
                "type_point_donnee": "Débit turbiné - Laforge-1",
                "nom_unite_mesure": "m³/s",
                "Donnees": {"2026/11/05T16:00:00Z": "40.0"},
            },
        ],
    }
    out = normalize_hq_records("installation", [row])
    assert len(out) == 1
    s = out[0]
    assert s["station"] == "HQ-I-99-1"
    assert s["debit_m3s"] == 40.0
    assert len(s["hq_metrics"]) == 2


def test_hq_history_series():
    composition = [
        {
            "type_point_donnee": "Apport naturel",
            "nom_unite_mesure": "m³/s",
            "Donnees": {
                "2026/11/01T00:00:00Z": "10.0",
                "2026/11/02T00:00:00Z": "11.0",
                "2026/11/03T00:00:00Z": "12.0",
            },
        },
        {
            "type_point_donnee": "Niveau",
            "nom_unite_mesure": "m",
            "Donnees": {
                "2026/11/01T12:00:00Z": "100.5",
                "2026/11/03T12:00:00Z": "101.2",
            },
        },
    ]
    readings = readings_from_hq_composition(composition)
    assert len(readings) == 5
    hist = build_history_payload("HQ-I-99-1", readings, source="hydroquebec_open")
    assert hist is not None
    assert hist["source"] == "hydroquebec_open"
    assert hist["has_debit"]
    assert hist["has_niveau"]
    assert len(hist["series"]) >= 3


def test_flow_series_prefers_debit_total():
    composition = [
        {
            "type_point_donnee": "Débit déversé - test",
            "nom_unite_mesure": "m³/s",
            "Donnees": {f"2026/11/0{i}T12:00:00Z": "0" for i in range(1, 8)},
        },
        {
            "type_point_donnee": "Débit total",
            "nom_unite_mesure": "m³/s",
            "Donnees": {"2026/11/01T12:00:00Z": "557.41"},
        },
    ]
    readings = readings_from_hq_composition(composition)
    assert len(readings) == 1
    assert readings[0]["debit_m3s"] == 557.41


def _m(tpd: str, unit: str) -> dict:
    return {"type_point_donnee": tpd, "nom_unite_mesure": unit}


def test_hq_tags_weather_only():
    from peche.hydroquebec_open import hq_tags

    metrics = [_m("Température Maximum", "°C"), _m("Précipitation", "mm")]
    assert hq_tags("station", metrics) == ["meteo"]


def test_hq_tags_level_and_weather_has_both():
    from peche.hydroquebec_open import hq_tags

    metrics = [_m("Niveau", "m"), _m("Température Minimum", "°C")]
    assert hq_tags("station", metrics) == ["meteo", "hydro"]


def test_hq_tags_flow_only_and_snow_depth_is_not_level():
    from peche.hydroquebec_open import hq_tags

    assert hq_tags("station", [_m("Débit", "m³/s")]) == ["hydro"]
    # « m » sur l'épaisseur de neige ne doit pas compter comme niveau d'eau.
    assert hq_tags("station", [_m("Épaisseur de neige", "m")]) == ["meteo"]


def test_hq_tags_installation_is_always_installation():
    from peche.hydroquebec_open import hq_tags

    assert hq_tags("installation", [_m("Débit total", "m³/s")]) == ["installation"]


def test_features_local_splits_hq_meteo_from_hydro():
    from peche.api.routes import features as feat_mod

    hydro = feat_mod._features_local(
        "vigilance_stations", "data/hydromet/stations.json", {}, None, 10000
    )
    meteo = feat_mod._features_local(
        "meteo_eccc", "data/weather/cities.json", {}, None, 10000
    )
    hydro_ids = {f["properties"].get("station") for f in hydro["features"]}
    meteo_ids = {
        f["properties"].get("station")
        for f in meteo["features"]
        if str(f["properties"].get("station") or "").startswith("HQ-")
    }
    # Aucune station HQ portant de la météo ne reste dans la couche hydro.
    assert not any(
        str(s).startswith("HQ-") and feat_mod._is_hq_meteo({"station": s})
        for s in hydro_ids
    )
    # Les HQ météo apparaissent bien dans la couche ECCC (si le cache HQ existe).
    assert all(str(s).startswith("HQ-") for s in meteo_ids)


def test_hq_tags_water_temperature_is_hydro_not_meteo():
    from peche.hydroquebec_open import hq_tags

    metrics = [_m("Niveau", "m"), _m("Température de l'eau", "°C")]
    assert hq_tags("station", metrics) == ["hydro"]
