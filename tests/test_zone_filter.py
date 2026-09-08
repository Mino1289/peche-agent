"""Tests parse_zone_expr et résolution multi-zones."""

import pytest

from peche.reglements.zone_filter import (
    ZoneExprAll,
    ZoneExprList,
    parse_zone_expr,
    resolve_zone_ids_for_expr,
    zone_filter_active,
)


def test_parse_zone_expr_all():
    assert isinstance(parse_zone_expr(""), ZoneExprAll)
    assert isinstance(parse_zone_expr("*"), ZoneExprAll)
    assert isinstance(parse_zone_expr("  *  "), ZoneExprAll)


def test_parse_zone_expr_list_and_range():
    expr = parse_zone_expr("21,23,25-28")
    assert isinstance(expr, ZoneExprList)
    assert expr.values == (21, 23, 25, 26, 27, 28)


def test_parse_zone_expr_reversed_range():
    expr = parse_zone_expr("28-25")
    assert isinstance(expr, ZoneExprList)
    assert expr.values == (25, 26, 27, 28)


def test_parse_zone_expr_invalid():
    with pytest.raises(ValueError):
        parse_zone_expr("a,b")
    with pytest.raises(ValueError):
        parse_zone_expr("1-")


def test_resolve_zone_ids_display_number():
    expr = parse_zone_expr("28")
    ids = resolve_zone_ids_for_expr(expr)
    assert ids == [32]


def test_resolve_zone_ids_zone_19_parts():
    expr = parse_zone_expr("19")
    ids = resolve_zone_ids_for_expr(expr)
    assert set(ids or []) == {3063, 2652, 2653}


def test_zone_filter_active():
    assert not zone_filter_active("")
    assert not zone_filter_active("*")
    assert zone_filter_active("28")
    assert zone_filter_active("21,23")


def test_features_local_multi_zone(monkeypatch):
    from peche.api.routes import features as feat_mod

    sample = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                "properties": {"zone_id": 32, "no_zone": "28"},
            },
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[2, 0], [3, 0], [3, 1], [2, 0]]]},
                "properties": {"zone_id": 23, "no_zone": "21"},
            },
        ],
    }

    monkeypatch.setattr(
        "peche.spatial.zones_peche.load_zones_geojson",
        lambda: sample,
    )
    out = feat_mod._features_local(
        "zones_chasse",
        "data/spatial/zones_peche.geojson",
        {"zone_ids": [32, 23]},
        None,
        100,
    )
    assert len(out["features"]) == 2
    zids = {f["properties"]["zone_id"] for f in out["features"]}
    assert zids == {32, 23}


def test_features_local_zoom_is_not_an_item_filter():
    """Le viewport envoie toujours `zoom` ; ce n'est pas un attribut station/barrage."""
    from peche.api.routes import features as feat_mod

    hydro = feat_mod._features_local(
        "vigilance_stations",
        "data/hydromet/stations.json",
        {"zoom": 6},
        None,
        500,
    )
    tides = feat_mod._features_local(
        "marees_shc",
        "data/tides/stations.json",
        {"zoom": 6},
        None,
        500,
    )
    dams = feat_mod._features_local(
        "barrages_cehq",
        "data/barrages/barrages.json",
        {"zoom": 10},
        None,
        200,
    )
    assert len(hydro["features"]) > 0
    assert hydro["features"][0]["geometry"]["type"] == "Point"
    assert len(tides["features"]) > 0
    assert tides["features"][0]["geometry"]["type"] == "Point"
    assert len(dams["features"]) == 200
    assert dams["features"][0]["geometry"]["type"] == "LineString"


def test_features_local_categorie_still_filters_barrages():
    from peche.api.routes import features as feat_mod

    out = feat_mod._features_local(
        "barrages_cehq",
        "data/barrages/barrages.json",
        {"categorie": ["Petit barrage"], "zoom": 10},
        None,
        50,
    )
    assert len(out["features"]) > 0
    assert all(
        f["properties"].get("categorie") == "Petit barrage" for f in out["features"]
    )
