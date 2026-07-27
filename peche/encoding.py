"""Encodage TOON pour les retours d'outils envoyés au LLM.

TOON (https://github.com/toon-format/toon-python) est un format compact,
type-safe et lisible qui réduit de 30-60 % le nombre de tokens vs JSON, en
particulier pour les listes uniformes (`[N]{cols}: ...`). On l'utilise
uniquement côté **transmission au modèle** ; les outils continuent d'être
testés avec du JSON Python natif.

L'agent reçoit une explication courte du format dans le system prompt, puis
chaque résultat d'outil est encodé via `wrap_tool_result(name, result)`.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from toon_format import encode as _toon_encode
except ImportError:  # pragma: no cover
    _toon_encode = None  # type: ignore[assignment]


TOON_PROMPT_HINT = """Format des résultats d'outils :
Les retours d'outils sont encodés en TOON (Token-Oriented Object Notation),
un format compact type YAML. Exemple :

  [3]{id,name,score}:
    1,Alice,0.9
    2,Bob,0.7
    3,Carla,null

  ↑ Ceci équivaut au JSON :
  [{"id":1,"name":"Alice","score":0.9},
   {"id":2,"name":"Bob","score":0.7},
   {"id":3,"name":"Carla","score":null}]

- `[N]{cols}:` introduit une liste de N objets uniformes (en-tête puis valeurs CSV).
- Les objets simples sont indentés en `clé: valeur`.
- `null` est explicite, les chaînes contenant `,` ou `:` sont entre guillemets.
- Tu dois lire et raisonner sur ces résultats ; ta sortie reste du texte normal.
"""


def _serialize_safe(data: Any) -> Any:
    """Convertit `data` en types primitifs JSON-compatibles (ce que TOON attend)."""
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def to_toon(data: Any) -> str:
    """Encode un payload Python en chaîne TOON (fallback JSON si TOON absent)."""
    if _toon_encode is None:
        return json.dumps(data, ensure_ascii=False)
    safe = _serialize_safe(data)
    try:
        return _toon_encode(safe)
    except Exception:  # noqa: BLE001  — fallback large : ne jamais bloquer
        return json.dumps(safe, ensure_ascii=False)


def wrap_tool_result(name: str, result: Any) -> dict:
    """Forme finale du payload de `function_response` envoyée à Gemini.

    On utilise `{"toon": "..."}` plutôt que `{"result": ...}` pour signaler
    explicitement le format, et garder un canal JSON minuscule.
    """
    if name in (
        "get_hydromet",
        "get_hydromet_at_plan",
        "get_hydromet_for_waterbody",
    ) and isinstance(result, dict):
        result = _slim_hydro_for_llm(result)
    return {"toon": to_toon(result)}


def _slim_hydro_for_llm(result: dict) -> dict:
    """Retire la série horaire (réservée à l'UI) avant envoi au LLM."""
    if "stations" in result and isinstance(result["stations"], list):
        slim = dict(result)
        slim["stations"] = [
            _slim_hydro_for_llm(s) if isinstance(s, dict) else s
            for s in result["stations"]
        ]
        return slim
    history = result.get("history")
    if not isinstance(history, dict) or "series" not in history:
        return result
    slim = dict(result)
    slim["history"] = {k: v for k, v in history.items() if k != "series"}
    return slim
