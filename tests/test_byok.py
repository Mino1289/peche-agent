"""Tests BYOK / chat API key resolution."""

from fastapi.testclient import TestClient

from peche.api import create_app
from peche.agent.credentials import resolve_api_key


def test_resolve_api_key_prefers_client():
    assert resolve_api_key("client-key") == "client-key"


def test_chat_missing_api_key_returns_sse_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    client = TestClient(create_app())
    resp = client.post(
        "/api/chat",
        json={"message": "Bonjour"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert '"type": "error"' in body
    assert "Clé API Gemini" in body or "Gemini API key" in body
    assert '"type": "done"' in body


def test_chat_accepts_header_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    calls: list[dict] = []

    def fake_stream_chat(message, history=None, **kwargs):
        calls.append(kwargs)
        yield {"type": "text", "text": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr("peche.api.routes.chat.stream_chat", fake_stream_chat)

    client = TestClient(create_app())
    resp = client.post(
        "/api/chat",
        headers={"X-Gemini-Api-Key": "test-key-123"},
        json={"message": "Bonjour", "locale": "fr"},
    )
    assert resp.status_code == 200
    assert '"type": "text"' in resp.text
    assert calls
    assert calls[0]["client"] is not None
