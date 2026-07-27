"""Tests pour la recherche de plans (peche.tools)."""

from datetime import date

from peche import tools


def test_score_plan_entry_exact(patch_search_index):
    entry = patch_search_index[2]  # Lac au Saumon
    score = tools._score_plan_entry("Lac au Saumon", entry, None)
    assert score >= 0.9


def test_score_plan_entry_ste_alias(patch_search_index):
    entry = patch_search_index[0]  # Ste-Marguerite a)
    score = tools._score_plan_entry("Ste-Marguerite", entry, None)
    assert score >= 0.35


def test_score_plan_entry_zone_bonus(patch_search_index):
    entry = patch_search_index[0]
    with_zone = tools._score_plan_entry("Sainte-Marguerite", entry, zone_id=32)
    without = tools._score_plan_entry("Sainte-Marguerite", entry, zone_id=None)
    assert with_zone >= without


def test_build_segment_groups(patch_search_index):
    candidates = [
        {"plan_id": 100, "zone_id": 32, "nom": "Seg a)", "score": 0.9},
        {"plan_id": 101, "zone_id": 32, "nom": "Seg b)", "score": 0.85},
    ]
    groups = tools._build_segment_groups(candidates, patch_search_index)
    assert len(groups) == 1
    assert groups[0]["segment_count"] == 2


def test_search_plans_empty():
    out = tools.search_plans("")
    assert out["candidates"] == []


def test_search_plans_finds_lac(patch_search_index):
    out = tools.search_plans("Lac au Saumon")
    assert len(out["candidates"]) >= 1
    assert out["candidates"][0]["nom"] == "Lac au Saumon"


def test_search_plans_groups_segments(patch_search_index):
    out = tools.search_plans("Sainte-Marguerite", zone_id=32)
    assert len(out["groups"]) >= 1


def test_get_reglements_filters_period(monkeypatch, tmp_path):
    zone_data = {
        "meta": {
            "zone_id": 1,
            "zone_nom": "Zone 1",
            "saison": "2026",
            "saison_id": 220,
        },
        "regles_generales": [
            {
                "segment": "Règles de la zone",
                "periodes": [
                    {
                        "periode": "Période Du 1 er avril 2026 au 31 mars 2027",
                        "especes": [{"espece": "Truite"}],
                    },
                    {
                        "periode": "Période Du 1 er janvier 2020 au 31 mars 2020",
                        "especes": [{"espece": "Ancienne"}],
                    },
                ],
            }
        ],
        "plans_eau": [],
    }
    zones_dir = tmp_path / "zones"
    zones_dir.mkdir()
    (zones_dir / "1.json").write_text(
        __import__("json").dumps(zone_data), encoding="utf-8"
    )
    monkeypatch.setattr(tools, "ZONES_DIR", zones_dir)
    monkeypatch.setattr(tools, "today", lambda: date(2026, 6, 15))

    out = tools.get_reglements(zone_id=1, only_in_effect=True)
    assert out["filtre_en_vigueur"] is True
    assert len(out["regles_generales"]) == 1
    periodes = out["regles_generales"][0]["periodes"]
    assert len(periodes) == 1
    assert periodes[0]["especes"][0]["espece"] == "Truite"
