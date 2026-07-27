"""Tests spatiaux — coords, viewport, reg_link."""

from peche.coords import parse_all_dms, parse_dms
from peche.spatial.reg_link import build_matches, get_match
from peche.spatial.tiles import tile_key
from peche.spatial.viewport import basin_level_for_zoom, features_in_bbox


def test_parse_all_dms_multiple():
    text = (
        "Segment (48°25'13\" N., 67°19'34\" O.) jusqu'à "
        "(48°30'00\" N., 67°20'00\" O.)"
    )
    pairs = parse_all_dms(text)
    assert len(pairs) == 2
    assert pairs[0]["lat"] == parse_dms(text)["lat"]


def test_tile_key_negative_lon():
    key = tile_key(48.5, -71.25)
    assert key.startswith("48.50_")


def test_basin_level_for_zoom():
    assert basin_level_for_zoom(7) == 4
    assert basin_level_for_zoom(11) == 6
    assert basin_level_for_zoom(14) == 8


def test_features_in_bbox_lce_requires_zoom():
    bbox = (-72.0, 45.0, -70.0, 47.0)
    assert features_in_bbox("lce", bbox, zoom=8) == []
    feats = features_in_bbox("lce", bbox, zoom=11)
    assert isinstance(feats, list)


def test_reg_link_build_and_get():
    result = build_matches()
    assert result["nb_matches"] > 0
    m = get_match(1, 45)
    if m:
        assert m["zone_id"] == 1
        assert m["plan_id"] == 45


def test_get_map_context():
    from peche.tools import get_map_context

    ctx = get_map_context(1, 45, zoom=11)
    assert ctx.get("plan_id") == 45
    assert ctx.get("zone_id") == 1
    assert "active_layers" in ctx
