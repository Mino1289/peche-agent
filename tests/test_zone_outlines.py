"""Contours des zones : densité selon le zoom, anneaux extérieurs seulement."""

import json

from peche.spatial.zones_peche import (
    _geometry_to_exteriors,
    _zoom_simplify_tolerance,
    clear_zones_cache,
    zones_geojson_for_viewport,
)


def _ncoords(geom: dict) -> int:
    def walk(c):
        if not c:
            return 0
        if isinstance(c[0], (int, float)):
            return 1
        return sum(walk(x) for x in c)

    return walk(geom.get("coordinates"))


def test_zoom_simplify_tolerance_keeps_detail_when_zoomed():
    assert _zoom_simplify_tolerance(6) == 0.01
    assert _zoom_simplify_tolerance(8) == 0.01
    assert _zoom_simplify_tolerance(9) is None
    assert _zoom_simplify_tolerance(12) is None
    assert _zoom_simplify_tolerance(16) is None
    assert _zoom_simplify_tolerance(None) is None


def test_geometry_to_exteriors_drops_holes():
    geom = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]],
            [[0.2, 0.2], [0.3, 0.2], [0.3, 0.3], [0.2, 0.3], [0.2, 0.2]],
        ],
    }
    out = _geometry_to_exteriors(geom)
    assert out is not None
    assert out["type"] == "LineString"
    assert out["coordinates"] == geom["coordinates"][0]


def test_geometry_to_exteriors_multipolygon():
    geom = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            [[[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]]],
        ],
    }
    out = _geometry_to_exteriors(geom)
    assert out is not None
    assert out["type"] == "MultiLineString"
    assert len(out["coordinates"]) == 2


def test_viewport_high_zoom_keeps_more_vertices(tmp_path, monkeypatch):
    coords = [[-71 + i * 0.001, 47 + (i % 2) * 0.002] for i in range(250)]
    feat = {
        "type": "Feature",
        "properties": {
            "zone_id": 1,
            "zone_nom": "Zone 1",
            "no_zone": "1",
            "partie_zon": "",
        },
        "geometry": {"type": "LineString", "coordinates": coords},
    }
    path = tmp_path / "zones_peche.outlines.geojson"
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": [feat]}),
        encoding="utf-8",
    )
    monkeypatch.setattr("peche.spatial.zones_peche.OUTLINES_PATH", path)
    clear_zones_cache()
    try:
        low = zones_geojson_for_viewport(None, zoom=6)
        high = zones_geojson_for_viewport(None, zoom=14)
        assert low["features"]
        assert high["features"]
        assert high["features"][0]["geometry"]["type"] in {
            "LineString",
            "MultiLineString",
        }
        assert _ncoords(high["features"][0]["geometry"]) > _ncoords(
            low["features"][0]["geometry"]
        )
    finally:
        clear_zones_cache()
