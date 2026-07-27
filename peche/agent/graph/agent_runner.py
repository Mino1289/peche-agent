"""Exécution d'un agent spécialisé (boucle outils Gemini)."""

from __future__ import annotations

import json
import os
from typing import Any

from google import genai
from google.genai import types

from peche.agent.graph.events import emit
from peche.agent.graph.rate_limit import wait_for_model
from peche.agent.graph.tools_subset import AGENT_TOOLS
from peche.agent.prompts import AGENT_PROMPTS
from peche.agent.schemas import TOOL_SCHEMAS, TOOLS
from peche.encoding import wrap_tool_result

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite")
MAX_TOOL_TURNS = 8


def _schemas_for_agent(agent: str) -> list[types.FunctionDeclaration]:
    allowed = AGENT_TOOLS.get(agent, set())
    decls = []
    for s in TOOL_SCHEMAS:
        if s["name"] in allowed:
            decls.append(
                types.FunctionDeclaration(
                    name=s["name"],
                    description=s["description"],
                    parameters=s["parameters"],
                )
            )
    return decls


def _execute_tool(name: str, args: dict[str, Any]) -> dict:
    if name not in TOOLS:
        return {"error": f"Outil inconnu: {name}"}
    try:
        result = TOOLS[name](**args)
    except TypeError as exc:
        return {"error": f"Mauvais arguments pour {name}: {exc}"}
    except Exception as exc:
        return {"error": f"{name} a levé {type(exc).__name__}: {exc}"}
    return json.loads(json.dumps(result, default=str, ensure_ascii=False))


def run_agent(
    agent: str,
    message: str,
    *,
    history: list[types.Content] | None = None,
    model: str = DEFAULT_MODEL,
    client: genai.Client | None = None,
) -> tuple[str, list[types.Content]]:
    """Exécute un agent et retourne (texte, historique mis à jour)."""
    if agent == "geomap":
        return _run_geomap_deterministic(message), history or []

    if not wait_for_model(model):
        return (
            "[Mode dégradé : quota API atteint. Consultez les données via les outils manuellement.]",
            history or [],
        )

    client = client or genai.Client()
    decls = _schemas_for_agent(agent)
    if not decls:
        return ("", history or [])

    tools_def = [types.Tool(function_declarations=decls)]
    system = AGENT_PROMPTS.get(agent, "")
    config = types.GenerateContentConfig(
        system_instruction=system,
        tools=tools_def,
        temperature=0.4,
    )

    local_history: list[types.Content] = list(history or [])
    local_history.append(
        types.Content(role="user", parts=[types.Part.from_text(text=message)])
    )

    collected_text: list[str] = []

    for _turn in range(MAX_TOOL_TURNS):
        stream = client.models.generate_content_stream(
            model=model, contents=local_history, config=config
        )
        model_parts: list[types.Part] = []
        function_call_parts: list[types.Part] = []

        for chunk in stream:
            for cand in chunk.candidates or []:
                if not cand.content or not cand.content.parts:
                    continue
                for part in cand.content.parts:
                    if getattr(part, "text", None):
                        emit({"type": "text", "text": part.text})
                        collected_text.append(part.text)
                        model_parts.append(part)
                        continue
                    fc = getattr(part, "function_call", None)
                    if fc and getattr(fc, "name", None):
                        model_parts.append(part)
                        function_call_parts.append(part)

        if model_parts:
            local_history.append(types.Content(role="model", parts=model_parts))

        if not function_call_parts:
            break

        tool_response_parts: list[types.Part] = []
        for part in function_call_parts:
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            emit({"type": "tool_call", "name": fc.name, "args": args})
            result = _execute_tool(fc.name, args)
            emit({"type": "tool_result", "name": fc.name, "result": result})
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name, response=wrap_tool_result(fc.name, result)
                )
            )
        local_history.append(types.Content(role="user", parts=tool_response_parts))

    return ("".join(collected_text), local_history)


def _run_geomap_deterministic(message: str) -> str:
    """GeoMap sans LLM si possible : tente search_plans sur mots-clés."""
    import re

    words = re.findall(r"[A-Za-zÀ-ÿ0-9'-]{3,}", message)
    if not words:
        return "Précisez un plan d'eau pour le contexte carte."
    query = " ".join(words[:4])
    result = _execute_tool("search_plans", {"query": query, "limit": 3})
    if result.get("error"):
        return f"Recherche carte impossible : {result['error']}"
    cands = result.get("candidates") or []
    if not cands:
        return f"Aucun plan trouvé pour « {query} »."
    best = cands[0]
    ctx = _execute_tool(
        "get_map_context",
        {"zone_id": best["zone_id"], "plan_id": best["plan_id"]},
    )
    emit({"type": "tool_call", "name": "search_plans", "args": {"query": query}})
    emit({"type": "tool_result", "name": "search_plans", "result": result})
    emit({"type": "tool_call", "name": "get_map_context", "args": {"zone_id": best["zone_id"], "plan_id": best["plan_id"]}})
    emit({"type": "tool_result", "name": "get_map_context", "result": ctx})
    nom = ctx.get("plan_nom") or best.get("nom")
    especes = ", ".join(ctx.get("reg_especes_en_vigueur") or []) or "—"
    return (
        f"**{nom}** (zone {best['zone_id']}, plan {best['plan_id']}) — "
        f"match LCE : {ctx.get('lce_match') is not None}. "
        f"Espèces en vigueur : {especes}. "
        f"Voir l'onglet Carte (zoom ≥ 10 pour LCE)."
    )
