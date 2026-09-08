"""Tests MCP mount on FastAPI."""

import os

from fastapi.testclient import TestClient


def test_mcp_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MCP_ENABLED", raising=False)
    from peche.api import create_app

    client = TestClient(create_app())
    health = client.get("/api/health").json()
    assert health.get("mcp_enabled") is False
    assert client.get("/mcp").status_code == 404


def test_mcp_enabled_mount(monkeypatch):
    monkeypatch.setenv("MCP_ENABLED", "1")
    from peche.api import create_app

    client = TestClient(create_app())
    health = client.get("/api/health").json()
    assert health.get("mcp_enabled") is True
    # Mounted — inner handler may 404/405 on bare GET; route exists
    routes = [getattr(r, "path", "") for r in client.app.routes]
    assert any(str(p).startswith("/mcp") for p in routes)
