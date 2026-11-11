"""Bassins hydrographiques : filtre niveau + bbox sur les snapshots locaux."""

import json
import math

import pytest

from peche import bassins


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    square = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    far = {"type": "Polygon", "coordinates": [[[10, 10], [11, 10], [11, 11], [10, 10]]]}
    layers = {4: [square, far], 5: [square]}
    for level, geoms in layers.items():
        feats = [
            {"type": "Feature", "geometry": g, "properties": {"niveau": level}} for g in geoms
        ]
        body = {"type": "FeatureCollection", "features": feats}
        (tmp_path / f"niveau_{level}.geojson").write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(bassins, "SPATIAL_DIR", tmp_path)
    bassins._level_band.cache_clear()
    yield tmp_path
    bassins._level_band.cache_clear()


def test_bassins_geojson_filters_levels_and_bbox(snapshot):
    out = json.loads(bassins.bassins_geojson_bytes((-1, -1, 2, 2), {4, 5}))
    assert [f["properties"]["niveau"] for f in out["features"]] == [4, 5]


def test_bassins_geojson_without_bbox_returns_all_of_level(snapshot):
    out = json.loads(bassins.bassins_geojson_bytes(None, {4}))
    assert len(out["features"]) == 2


def test_bassins_geojson_missing_level_is_empty(snapshot):
    out = json.loads(bassins.bassins_geojson_bytes(None, {8}))
    assert out == {"type": "FeatureCollection", "features": []}


def test_bassins_geometry_is_finer_when_zoomed_in(snapshot):
    # Contour dentelé (amplitude 0.001°) : simplifié à grande échelle, intact de près.
    ring = [
        [0.5 + 0.5 * math.cos(a) + (0.001 if i % 2 else 0), 0.5 + 0.5 * math.sin(a)]
        for i, a in enumerate(2 * math.pi * k / 100 for k in range(100))
    ]
    ring.append(ring[0])
    feat = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}}
    body = {"type": "FeatureCollection", "features": [{**feat, "properties": {"niveau": 4}}]}
    (snapshot / "niveau_4.geojson").write_text(json.dumps(body), encoding="utf-8")
    bassins._level_band.cache_clear()

    def n_vertices(zoom):
        out = json.loads(bassins.bassins_geojson_bytes(None, {4}, zoom))
        return len(out["features"][0]["geometry"]["coordinates"][0])

    assert n_vertices(5) < n_vertices(10) < n_vertices(12) == len(ring)
