"""Snapshot TFS : sélection par zoom, filtre DESCRIPTION et bbox."""

import pytest

from peche.spatial import tfs


def _square(x: float, y: float, size: float = 0.1) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]],
    }


STORED = [
    {"type": "Feature", "properties": {"NOM": "A", "DESCRIPTION": "ZEC"}, "geometry": _square(-72.0, 47.0)},
    {"type": "Feature", "properties": {"NOM": "B", "DESCRIPTION": "Réserve faunique"}, "geometry": _square(-70.0, 48.0)},
]


@pytest.fixture(autouse=True)
def _stored_fixture(monkeypatch):
    monkeypatch.setattr(tfs, "_stored", lambda: STORED)
    tfs._band.cache_clear()
    yield
    tfs._band.cache_clear()


def test_far_zoom_returns_points():
    data = tfs.tfs_geojson(None, descriptions=None, zoom=7)
    assert {f["geometry"]["type"] for f in data["features"]} == {"Point"}


def test_close_zoom_returns_polygons():
    data = tfs.tfs_geojson(None, descriptions=None, zoom=13)
    assert {f["geometry"]["type"] for f in data["features"]} == {"Polygon"}


def test_description_filter_and_bbox():
    data = tfs.tfs_geojson((-73.0, 46.0, -71.0, 49.0), descriptions={"ZEC"}, zoom=13)
    assert [f["properties"]["NOM"] for f in data["features"]] == ["A"]
    empty = tfs.tfs_geojson((0.0, 0.0, 1.0, 1.0), descriptions=None, zoom=13)
    assert empty["features"] == []
