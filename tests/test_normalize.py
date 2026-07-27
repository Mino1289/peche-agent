"""Tests pour peche.matching.normalize."""

from peche.matching.normalize import (
    expand_abbreviations,
    extract_river_base_name,
    extract_segment_label,
    normalize_search_text,
    normalize_water_name,
    search_aliases,
    token_jaccard,
    tokenize,
)


def test_expand_abbreviations_ste_st():
    assert "sainte" in expand_abbreviations("Ste-Marguerite").lower()
    assert "saint" in expand_abbreviations("St-Jean").lower()
    assert "riviere" in expand_abbreviations("riv Saguenay").lower()


def test_normalize_search_text_accents():
    a = normalize_search_text("Lac Kénogami")
    b = normalize_search_text("lac kenogami")
    assert a == b


def test_normalize_water_name_strips_prefix():
    assert normalize_water_name("Lac Kénogami") == "kenogami"
    assert normalize_water_name("Rivière Saguenay") == "saguenay"


def test_tokenize_drops_stop_words():
    tokens = tokenize("Lac de la Truite")
    assert "lac" in tokens
    assert "truite" in tokens
    assert "de" not in tokens
    assert "la" not in tokens


def test_extract_segment_label():
    assert extract_segment_label("Rivière X b) entre un point") == "b)"
    assert extract_segment_label("Lac sans segment") is None


def test_extract_river_base_name():
    base = extract_river_base_name(
        "Rivière Sainte-Marguerite b) entre un point et un autre"
    )
    assert "Sainte-Marguerite" in base
    assert "b)" not in base


def test_search_aliases_includes_ste_variant():
    aliases = search_aliases("Rivière Sainte-Marguerite")
    assert any("ste" in a for a in aliases)


def test_token_jaccard_identical():
    assert token_jaccard("Lac Kénogami", "Lac Kénogami") == 1.0


def test_token_jaccard_disjoint():
    assert token_jaccard("Lac A", "Rivière B") == 0.0
