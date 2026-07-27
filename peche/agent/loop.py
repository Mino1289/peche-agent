"""Boucle agent : LangGraph multi-agents + streaming.

`stream_chat(message, history)` yield des événements :
`text`, `tool_call`, `tool_result`, `done`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import types

from peche.agent.graph.run import run_graph_turn
from peche.agent.prompt import build_system_prompt
from peche.agent.schemas import TOOL_SCHEMAS, TOOLS
from peche.encoding import wrap_tool_result

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite")
MAX_TOOL_TURNS = 10
USE_LANGGRAPH = os.environ.get("USE_LANGGRAPH", "1").lower() not in {"0", "false", "no"}


def _configure_langsmith() -> None:
    """Active le traçage LangSmith si configuré."""
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() in {"1", "true", "yes"}:
        os.environ.setdefault("LANGCHAIN_PROJECT", "peche-agent")


def _make_client() -> genai.Client:
    return genai.Client()


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


def _stream_legacy(
    message: str,
    history: list[types.Content],
    *,
    model: str,
    client: genai.Client,
) -> Iterator[dict]:
    """Boucle monolithique Gemini (repli si USE_LANGGRAPH=0)."""
    decls = [
        types.FunctionDeclaration(
            name=s["name"],
            description=s["description"],
            parameters=s["parameters"],
        )
        for s in TOOL_SCHEMAS
    ]
    tools_def = [types.Tool(function_declarations=decls)]
    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        tools=tools_def,
        temperature=0.4,
    )
    history.append(
        types.Content(role="user", parts=[types.Part.from_text(text=message)])
    )
    for _turn in range(MAX_TOOL_TURNS):
        stream = client.models.generate_content_stream(
            model=model, contents=history, config=config
        )
        model_parts: list[types.Part] = []
        function_call_parts: list[types.Part] = []
        for chunk in stream:
            for cand in chunk.candidates or []:
                if not cand.content or not cand.content.parts:
                    continue
                for part in cand.content.parts:
                    if getattr(part, "text", None):
                        yield {"type": "text", "text": part.text}
                        model_parts.append(part)
                        continue
                    fc = getattr(part, "function_call", None)
                    if fc and getattr(fc, "name", None):
                        model_parts.append(part)
                        function_call_parts.append(part)
        if model_parts:
            history.append(types.Content(role="model", parts=model_parts))
        if not function_call_parts:
            yield {"type": "done"}
            return
        tool_response_parts: list[types.Part] = []
        for part in function_call_parts:
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            yield {"type": "tool_call", "name": fc.name, "args": args}
            result = _execute_tool(fc.name, args)
            yield {"type": "tool_result", "name": fc.name, "result": result}
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name, response=wrap_tool_result(fc.name, result)
                )
            )
        history.append(types.Content(role="user", parts=tool_response_parts))
    yield {
        "type": "text",
        "text": "\n\n[Limite de tours d'outils atteinte.]",
    }
    yield {"type": "done"}


def stream_chat(
    message: str,
    history: list[types.Content] | None = None,
    *,
    model: str = DEFAULT_MODEL,
    client: genai.Client | None = None,
) -> Iterator[dict]:
    """Stream tokens + événements pour une conversation."""
    _configure_langsmith()
    if history is None:
        history = []

    if USE_LANGGRAPH:
        events, updated_history, _final = run_graph_turn(message, history)
        history.clear()
        history.extend(updated_history)
        yield from events
        return

    client = client or _make_client()
    yield from _stream_legacy(message, history, model=model, client=client)
