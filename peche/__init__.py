"""peche — agent de pêche au Québec (règlements + météo + hydro)."""

from __future__ import annotations

import os
from pathlib import Path

# Chargement automatique de .env. Les clés LLM y sont prioritaires sur l'env
# shell ; les autres variables ne remplacent pas une valeur déjà définie
# (ex. PECHE_HOST=0.0.0.0 injecté par Docker Compose).
_DOTENV_OVERRIDES = frozenset({"GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_MODEL"})
try:
    from dotenv import dotenv_values as _dotenv_values

    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.exists():
        for _k, _v in _dotenv_values(_ENV_PATH).items():
            if _v and _v.strip() and not _v.strip().lower().startswith("your-"):
                if _k in _DOTENV_OVERRIDES or _k not in os.environ:
                    os.environ[_k] = _v
except ImportError:  # pragma: no cover
    pass

# Sentinelle pour les modules qui veulent forcer un rechargement explicite.
DOTENV_LOADED = bool(os.environ.get("LLM_MODEL"))

__all__ = ["DOTENV_LOADED", "fetch", "reglements"]
