"""Résolution de la clé Gemini (BYOK client ou serveur)."""

from __future__ import annotations

import os
from contextvars import ContextVar

current_api_key: ContextVar[str | None] = ContextVar("current_api_key", default=None)


def resolve_api_key(client_key: str | None = None) -> str | None:
    """Clé fournie par le client (header), sinon variables d'environnement."""
    key = (client_key or "").strip()
    if key:
        return key
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def server_has_api_key() -> bool:
    return bool(
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    )
