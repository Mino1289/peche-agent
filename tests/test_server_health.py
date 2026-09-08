"""Tests /api/health (nouvelle API map-first)."""

from fastapi.testclient import TestClient

from peche.api import create_app


def test_health_endpoint_shape():
    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "data_ready" in data
    assert "zones_ok" in data
    assert "catalog_ok" in data
    assert "zones_peche_ok" in data
    assert "model" in data
    assert "fallback_model" in data


def test_catalog_endpoint():
    client = TestClient(create_app())
    resp = client.get("/api/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert "basemaps" in data
    assert "groups" in data
    assert "curated_ids" in data
    assert len(data["curated_ids"]) >= 10
    assert any(b["id"] == "fond_quebec" for b in data["basemaps"])
    assert resp.headers.get("cache-control") == "no-store"
    assert "lidar_pentes" in data["curated_ids"]
    assert "pente_cpl" not in data["curated_ids"]
    assert "grhq_flow" in data["curated_ids"]
    assert "aq_reseau" in data["curated_ids"]
    assert "aq_forestier" in data["curated_ids"]
    lidar_ids = [
        layer["id"]
        for g in data["groups"]
        if g["id"] == "lidar"
        for layer in g["layers"]
    ]
    assert lidar_ids == ["lidar_pentes"]


def test_zones_geojson_endpoint():
    client = TestClient(create_app())
    resp = client.get("/api/zones/geojson")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data


def test_zones_list_endpoint():
    client = TestClient(create_app())
    resp = client.get("/api/zones")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 30
    assert "zone_id" in data[0]
    assert "zone_nom" in data[0]


def test_zones_at_endpoint():
    client = TestClient(create_app())
    resp = client.get("/api/zones/at", params={"lon": -73.5, "lat": 45.5})
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        data = resp.json()
        assert "zone_id" in data


def test_catalog_has_no_foret_group():
    client = TestClient(create_app())
    data = client.get("/api/catalog").json()
    assert all(g["id"] != "foret" for g in data["groups"])
    assert all(g["id"] != "biodiversite" for g in data["groups"])
    assert all(g["id"] != "perturbations" for g in data["groups"])
    assert "peuplements" not in data["curated_ids"]
    assert all(layer["curated"] for g in data["groups"] for layer in g["layers"])
    zones = next(
        layer
        for g in data["groups"]
        for layer in g["layers"]
        if layer["id"] == "zones_chasse"
    )
    assert zones["source_type"] == "local"


def test_maps_routes_removed():
    client = TestClient(create_app())
    assert client.get("/api/maps").status_code == 404


def test_features_zone_filter_without_bbox():
    client = TestClient(create_app())
    resp = client.get("/api/features", params={"layer": "zones_chasse", "no_zone": "28"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    feats = data.get("features") or []
    if feats:
        nos = {
            str((f.get("properties") or {}).get("no_zone") or "").lstrip("0")
            for f in feats
        }
        assert "28" in nos
        assert all(
            str((f.get("properties") or {}).get("zone_id")) != "28" for f in feats
        )


def test_index_html_no_cache():
    client = TestClient(create_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "no-cache" in (resp.headers.get("cache-control") or "")


def test_local_point_layers_ignore_zoom_query():
    """Le front envoie toujours `zoom` ; ça ne doit pas vider stations / marées / barrages."""
    client = TestClient(create_app())
    hydro = client.get(
        "/api/features",
        params={"layer": "vigilance_stations", "zoom": 6, "limit": 50},
    )
    assert hydro.status_code == 200
    h = hydro.json()["features"]
    assert len(h) > 50
    assert h[0]["geometry"]["type"] == "Point"

    tides = client.get(
        "/api/features",
        params={"layer": "marees_shc", "zoom": 6, "limit": 50},
    )
    assert tides.status_code == 200
    t = tides.json()["features"]
    assert len(t) > 50
    assert t[0]["geometry"]["type"] == "Point"

    dams = client.get(
        "/api/features",
        params={"layer": "barrages_cehq", "zoom": 10, "limit": 50},
    )
    assert dams.status_code == 200
    d = dams.json()["features"]
    assert len(d) > 50
    assert d[0]["geometry"]["type"] == "LineString"


def test_zone_geometry_28_is_display_zone_not_id_28():
    client = TestClient(create_app())
    resp = client.get("/api/zones/28/geometry")
    assert resp.status_code == 200
    data = resp.json()
    props = data.get("properties") or {}
    no = str(props.get("no_zone") or "").lstrip("0")
    zid = str(props.get("zone_id") or "")
    assert no == "28" or "28" in str(props.get("zone_nom") or "")
    assert zid != "28"
