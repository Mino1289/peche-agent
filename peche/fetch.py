"""Wrapper HTTP minimal partagé par les modules offline (sync règlements,
coords, stations hydro). Les outils live (météo / hydro temps réel) feront
leurs propres requêtes — c'est volontaire pour pouvoir mocker séparément.
"""

from __future__ import annotations

from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (compatible; PecheAgent/1.0)"


def fetch_text(url: str, timeout: float = 30.0, user_agent: str = USER_AGENT) -> str:
    """Retourne le corps d'une réponse HTTP en texte UTF-8 (errors=replace)."""
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_bytes(url: str, timeout: float = 60.0, user_agent: str = USER_AGENT) -> bytes:
    """Retourne le corps binaire d'une réponse HTTP."""
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout) as response:
        return response.read()
