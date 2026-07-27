"""Tests pour l'endpoint /api/health."""

import json

from fastapi.testclient import TestClient

from peche.server.app import create_app


def _write_minimal_data(tmp_path, *, with_api_key: bool = True):
    index = {"zones": [{"id": 1}, {"id": 2}]}
    (tmp_path / "index.json").write_text(json.dumps(index), encoding="utf-8")
    locations = tmp_path / "locations"
    locations.mkdir()
    (locations / "1.json").write_text(
        json.dumps({"zone_id": 1, "locations": []}), encoding="utf-8"
    )
    hydromet = tmp_path / "hydromet"
    hydromet.mkdir()
    (hydromet / "stations.json").write_text(
        json.dumps({"stations": []}), encoding="utf-8"
    )
    return with_api_key


def test_health_all_ready(monkeypatch, tmp_path):
    import peche.server.app as app_mod

    _write_minimal_data(tmp_path)
    monkeypatch.setattr(app_mod, "INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setattr(app_mod, "LOCATIONS_DIR", tmp_path / "locations")
    monkeypatch.setattr(app_mod, "HYDROMET_STATIONS", tmp_path / "hydromet" / "stations.json")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    client = TestClient(create_app())
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data_ready"] is True
    assert data["zones_count"] == 2
    assert data["api_key"] is True


def test_health_missing_api_key(monkeypatch, tmp_path):
    import peche.server.app as app_mod

    _write_minimal_data(tmp_path)
    monkeypatch.setattr(app_mod, "INDEX_PATH", tmp_path / "index.json")
    monkeypatch.setattr(app_mod, "LOCATIONS_DIR", tmp_path / "locations")
    monkeypatch.setattr(app_mod, "HYDROMET_STATIONS", tmp_path / "hydromet" / "stations.json")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    client = TestClient(create_app())
    data = client.get("/api/health").json()
    assert data["data_ready"] is False
    assert data["api_key"] is False
    assert "GEMINI_API_KEY" in (data["message"] or "")
