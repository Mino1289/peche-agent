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

    app = create_app()
    inner = app._app if hasattr(app, "_app") else app
    routes = [getattr(r, "path", "") for r in inner.routes]
    assert any(str(p).startswith("/mcp") for p in routes)

    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health.get("mcp_enabled") is True

        init = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        resp = client.post(
            "/mcp",
            json=init,
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert resp.status_code == 200
        assert "peche-agent" in resp.text
