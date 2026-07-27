"""Tests pour peche.reglements.parser."""

import json
from pathlib import Path

from peche.reglements.parser import (
    clean_html,
    extract_plan_label_from_grid_row,
    group_rows,
    match_endroit_id,
    parse_grid_rows,
    parse_saison,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_clean_html_strips_tags():
    assert clean_html("<b>Lac</b> <script>x</script> test") == "Lac test"


def test_parse_saison():
    html = (
        '<input id="id_saisn_VI" value="220"/>'
        '<input id="id_saisn_I" value="Saison 2026"/>'
    )
    sid, text = parse_saison(html)
    assert sid == 220
    assert "2026" in text


def test_parse_grid_rows(fixtures_dir):
    html = (fixtures_dir / "reglements_grid_snippet.html").read_text(encoding="utf-8")
    rows = parse_grid_rows(html, "TestGrid")
    types = [r["type"] for r in rows]
    assert "periode" in types
    assert "plan_eau" in types
    assert "espece" in types


def test_group_rows():
    rows = [
        {"type": "plan_eau", "texte": "Lac au Saumon"},
        {"type": "periode", "texte": "Période Du 1 er avril 2026 au 31 mars 2027"},
        {
            "type": "espece",
            "espece": "Truite",
            "limite_prise": "5",
            "limite_longueur": "—",
            "engin": "Canne",
            "note": "",
        },
    ]
    grouped = group_rows(rows)
    assert len(grouped) == 1
    assert grouped[0]["segment"] == "Lac au Saumon"
    assert len(grouped[0]["periodes"]) == 1
    assert grouped[0]["periodes"][0]["especes"][0]["espece"] == "Truite"


def test_match_endroit_id():
    catalog = {42: "Lac au Saumon", 99: "Rivière Test"}
    assert match_endroit_id("Lac au Saumon", catalog) == 42
    assert match_endroit_id("Inconnu", catalog) is None


def test_extract_plan_label_bold():
    row = '<td><span class="gras">Lac Test</span></td>'
    assert extract_plan_label_from_grid_row(row) == "Lac Test"
