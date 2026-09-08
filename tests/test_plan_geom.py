"""Géométries plans RegPec — Layer 3 zone 21 et normalisation."""

from peche.spatial import plan_geom


def test_query_layer3_url_outfields(monkeypatch):
    from urllib.parse import parse_qs, urlparse

    captured: dict[str, str] = {}

    def fake_fetch(url, timeout=60.0):
        captured["url"] = url
        return '{"features":[]}'

    monkeypatch.setattr(plan_geom, "fetch_text", fake_fetch)
    plan_geom._query_layer(
        plan_geom.REGPEC_EXTRA_LAYERS[0],
        where="1=1",
        bbox=None,
        limit=10,
    )
    qs = parse_qs(urlparse(captured["url"]).query)
    assert qs["outFields"] == ["ID_ENDRO"]
    assert "ID_ZONE" not in qs["outFields"][0]


def test_layer3_outfields_omit_missing_columns():
    url = plan_geom.REGPEC_EXTRA_LAYERS[0]
    assert plan_geom._is_layer3(url)
    assert plan_geom._layer_out_fields(url) == "ID_ENDRO"
    assert "ID_ZONE" not in plan_geom._layer_out_fields(url)
    assert "NM_ENDRO_FR" not in plan_geom._layer_out_fields(url)
    layer2 = plan_geom.REGPEC_PLANS_LAYER
    assert "ID_ZONE" in plan_geom._layer_out_fields(layer2)
    assert "NM_ENDRO_FR" in plan_geom._layer_out_fields(layer2)


def test_normalize_empty_rings_dropped():
    raw = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": []},
        "properties": {
            "ID_ENDRO": 2985,
            "ID_ZONE": 23,
            "NM_ENDRO_FR": "Eaux BAIE-DES-CHALEURS",
            "VA_TYPE_DESCR_FR": "Eaux",
        },
    }
    assert plan_geom._normalize_feature(raw) is None


def test_normalize_layer3_id_endro_only():
    ring = [[-64.2, 48.7], [-64.0, 48.7], [-64.0, 48.5], [-64.2, 48.5], [-64.2, 48.7]]
    raw = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"ID_ENDRO": 2985},
    }
    feat = plan_geom._normalize_feature(raw)
    assert feat is not None
    assert feat["properties"]["plan_id"] == 2985
    assert feat["properties"]["zone_id"] == 0
    assert feat["properties"]["nom"] == ""


def test_fetch_layer3_polygon_when_layer2_empty(monkeypatch):
    ring = [[-64.2, 48.7], [-64.0, 48.7], [-64.0, 48.5], [-64.2, 48.5], [-64.2, 48.7]]
    queried: list[str] = []

    def fake_query(layer_url, *, where, bbox, limit, offset=0):
        queried.append(layer_url)
        if plan_geom._is_layer3(layer_url):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": {"ID_ENDRO": 2985},
                    }
                ],
            }
        if "MapServer/2" in layer_url:
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": []},
                        "properties": {
                            "ID_ENDRO": 2985,
                            "ID_ZONE": 23,
                            "NM_ENDRO_FR": "Eaux BAIE-DES-CHALEURS",
                            "VA_TYPE_DESCR_FR": "Eaux",
                        },
                    }
                ],
            }
        return {"features": []}

    monkeypatch.setattr(plan_geom, "_query_layer", fake_query)
    monkeypatch.setattr(
        plan_geom,
        "_plan_name_index",
        lambda: {2985: {"zone_id": 23, "nom": "Eaux Baie-des-Chaleurs"}},
    )
    feats = plan_geom._fetch_regpec_polygons(None, zone_id=23, limit=50)
    by_id = {f["properties"]["plan_id"]: f for f in feats}
    assert 2985 in by_id
    feat = by_id[2985]
    assert feat["geometry"]["coordinates"]
    assert feat["properties"]["zone_id"] == 23
    assert "Baie-des-Chaleurs" in feat["properties"]["nom"]
    assert feat["properties"]["source"] == "regpec_exceptions_zone21"
    assert any(plan_geom._is_layer3(u) for u in queried)


def test_plan_name_index_zone21():
    idx = plan_geom._plan_name_index()
    if not idx:
        return
    assert 2985 in idx
    assert idx[2985]["zone_id"] == 23
    assert idx[2985].get("nom")
