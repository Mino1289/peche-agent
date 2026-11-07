"""Helpers de traçage Langfuse propres à l'agent Gemini.

Convertissent les objets `google.genai` en structures lisibles dans l'UI
Langfuse : messages au format OpenAI (rôles system/user/assistant/tool, appels
d'outils en `tool_calls` avec `arguments` JSON), usage de tokens, contexte carte.
"""

from __future__ import annotations

import json
from typing import Any

# Noms d'observations : stables et à faible cardinalité (jamais de valeur
# dynamique dedans — elles vont en metadata). Les évaluateurs et dashboards
# Langfuse les ciblent par nom.
TRACE_CHAT_TURN = "chat-turn"
SPAN_MAP_CONTEXT = "load-map-context"
SPAN_ATTEMPT = "run-agent-attempt"
GEN_AGENT_STEP = "generate-agent-step"
SPAN_POINT_CONTEXT = "resolve-point-context"
AGENT_FISHING_EXPERT = "consult-fishing-expert"
GEN_FISHING_ADVICE = "generate-fishing-advice"


def tool_span_name(tool: str) -> str:
    return f"tool-{tool}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def history_to_messages(
    history: list[Any], system_prompt: str | None = None
) -> list[dict[str, Any]]:
    """Historique `types.Content` → messages OpenAI-compatibles.

    Les ids d'appels d'outils sont ceux fournis par Gemini, sinon positionnels
    (`call_N`) ; l'appariement appel → résultat est déterministe, donc stable
    d'une génération à l'autre dans une même conversation.
    """
    msgs: list[dict[str, Any]] = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})

    pending: dict[str, list[str]] = {}
    n_calls = 0
    for content in history:
        role = getattr(content, "role", None) or "user"
        texts: list[str] = []
        calls: list[dict[str, Any]] = []
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            if getattr(part, "text", None):
                texts.append(part.text)
            fc = getattr(part, "function_call", None)
            if fc and getattr(fc, "name", None):
                n_calls += 1
                call_id = getattr(fc, "id", None) or f"call_{n_calls}"
                pending.setdefault(fc.name, []).append(call_id)
                calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": fc.name,
                            "arguments": _json(dict(fc.args) if fc.args else {}),
                        },
                    }
                )
            fr = getattr(part, "function_response", None)
            if fr and getattr(fr, "name", None):
                queue = pending.get(fr.name) or []
                call_id = getattr(fr, "id", None) or (
                    queue.pop(0) if queue else f"call_{fr.name}"
                )
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": fr.name,
                        "content": _json(fr.response),
                    }
                )
        if role == "model":
            if texts or calls:
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": "".join(texts) or None,
                }
                if calls:
                    msg["tool_calls"] = calls
                msgs.append(msg)
        elif texts:
            msgs.append({"role": "user", "content": "\n".join(texts)})
    return msgs


def last_assistant_message(msgs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for msg in reversed(msgs):
        if msg.get("role") == "assistant":
            return msg
    return None


def usage_details(usage: Any) -> dict[str, int] | None:
    """`usage_metadata` Gemini → `usage_details` Langfuse.

    La réflexion (thinking) est facturée comme sortie chez Gemini : on
    l'additionne à `output`. Le reste (cache, thinking) est exposé par `usage_extra`.
    """
    if usage is None:
        return None

    def g(key: str) -> int:
        return int(getattr(usage, key, None) or 0)

    inp = g("prompt_token_count")
    out = g("candidates_token_count") + g("thoughts_token_count")
    return {"input": inp, "output": out, "total": g("total_token_count") or inp + out}


def usage_extra(usage: Any) -> dict[str, int]:
    """Compteurs Gemini qui ne rentrent pas dans input/output (metadata)."""
    if usage is None:
        return {}
    extra = {
        "cached_tokens": getattr(usage, "cached_content_token_count", None),
        "thinking_tokens": getattr(usage, "thoughts_token_count", None),
        "tool_use_prompt_tokens": getattr(usage, "tool_use_prompt_token_count", None),
    }
    return {k: int(v) for k, v in extra.items() if v}


def map_context(map_state: dict[str, Any] | None) -> dict[str, Any]:
    """MapState → contexte lisible : vue, couches visibles, zone, points posés."""
    if not map_state:
        return {"map_state": None}
    layers = [l for l in (map_state.get("layers") or []) if isinstance(l, dict)]
    pins = [p for p in (map_state.get("pins") or []) if isinstance(p, dict)]
    return {
        "center": map_state.get("center"),
        "zoom": map_state.get("zoom"),
        "bbox": map_state.get("bbox"),
        "zone_filter": map_state.get("zoneFilter"),
        "visible_layers": [l.get("id") for l in layers if l.get("visible", True)],
        "layer_filters": {
            l.get("id"): l.get("filters") for l in layers if l.get("filters")
        },
        "pins": [
            {**p, "pin_number": p.get("n") or i + 1} for i, p in enumerate(pins)
        ],
    }
