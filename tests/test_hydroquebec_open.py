"""Tests parse Hydro-Québec open JSON (sans réseau)."""

from peche.hydroquebec_open import normalize_hq_records, _latest_in_donnees


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
