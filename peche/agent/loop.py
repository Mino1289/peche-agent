"""Boucle agent Gemini unique avec streaming + fallback modèle + map_action."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import types

from peche.agent.credentials import current_api_key, resolve_api_key
from peche.agent import map_tools
from peche.agent.prompt import build_system_prompt
from peche.agent.schemas import TOOL_SCHEMAS, TOOLS
from peche.encoding import wrap_tool_result

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODEL = os.environ.get("LLM_MODEL_FALLBACK", "gemini-3.1-flash-lite")
MAX_TOOL_TURNS = 10
MAX_MODEL_RETRIES = 3
_RETRY_BACKOFF_S = 0.6


def _make_client(api_key: str | None = None) -> genai.Client:
    key = api_key or current_api_key.get() or resolve_api_key(None)
    if key:
        return genai.Client(api_key=key)
    return genai.Client()


def _execute_tool(name: str, args: dict[str, Any], *, api_key: str | None = None) -> dict:
    if api_key:
        current_api_key.set(api_key)
    if name not in TOOLS:
        return {"error": f"Outil inconnu: {name}"}
    try:
        result = TOOLS[name](**args)
    except TypeError as exc:
        return {"error": f"Mauvais arguments pour {name}: {exc}"}
    except Exception as exc:
        return {"error": f"{name} a levé {type(exc).__name__}: {exc}"}
    return json.loads(json.dumps(result, default=str, ensure_ascii=False))


def _is_retryable(exc: BaseException) -> bool:
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    return any(
        token in msg or token in name
        for token in (
            "429",
            "resource_exhausted",
            "rate",
            "quota",
            "unavailable",
            "timeout",
            "503",
            "500",
            "internal",
        )
    )


def _friendly_error(exc: BaseException) -> str:
    msg = str(exc)
    if "503" in msg or "unavailable" in msg.lower():
        return (
            "Le modèle IA est temporairement surchargé. "
            "Réessayez dans quelques instants."
        )
    return f"{type(exc).__name__}: {exc}"


def _run_agent_turn(
    history: list[types.Content],
    *,
    model: str,
    client: genai.Client,
    map_state: dict | None,
    locale: str | None = None,
    api_key: str | None = None,
) -> Iterator[dict]:
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
        system_instruction=build_system_prompt(map_state=map_state, locale=locale),
        tools=tools_def,
        temperature=0.4,
    )
    map_tools.clear_map_actions()

    for _turn in range(MAX_TOOL_TURNS):
        attempt_checkpoint = len(history)
        try:
            stream = client.models.generate_content_stream(
                model=model, contents=history, config=config
            )
        except Exception:
            if len(history) > attempt_checkpoint:
                del history[attempt_checkpoint:]
            raise

        model_parts: list[types.Part] = []
        function_call_parts: list[types.Part] = []
        try:
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
        except Exception:
            # Conserver les tool results déjà dans l'historique ; retirer
            # seulement la réponse modèle incomplète de cette tentative.
            if model_parts:
                del history[attempt_checkpoint:]
            raise

        if model_parts:
            history.append(types.Content(role="model", parts=model_parts))
        if not function_call_parts:
            for action in map_tools.drain_map_actions():
                yield {"type": "map_action", **action}
            yield {"type": "done"}
            return

        tool_response_parts: list[types.Part] = []
        for part in function_call_parts:
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            yield {"type": "tool_call", "name": fc.name, "args": args}
            result = _execute_tool(fc.name, args, api_key=api_key)
            yield {"type": "tool_result", "name": fc.name, "result": result}
            for action in map_tools.drain_map_actions():
                yield {"type": "map_action", **action}
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name, response=wrap_tool_result(fc.name, result)
                )
            )
        history.append(types.Content(role="user", parts=tool_response_parts))

    yield {"type": "text", "text": "\n\n[Limite de tours d'outils atteinte.]"}
    yield {"type": "done"}


def stream_chat(
    message: str,
    history: list[types.Content] | None = None,
    *,
    model: str | None = None,
    client: genai.Client | None = None,
    map_state: dict | None = None,
    locale: str | None = None,
    api_key: str | None = None,
) -> Iterator[dict]:
    """Stream tokens + tool events + map_action pour une conversation."""
    if history is None:
        history = []
    client = client or _make_client()
    primary = model or DEFAULT_MODEL
    models_to_try = [primary]
    if primary != FALLBACK_MODEL:
        models_to_try.append(FALLBACK_MODEL)

    map_tools.set_current_map_state(map_state)
    try:
        history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        )
        turn_start = len(history)

        last_exc: BaseException | None = None
        for model_idx, active_model in enumerate(models_to_try):
            if model_idx > 0:
                del history[turn_start:]
                yield {
                    "type": "text",
                    "text": f"\n_[bascule vers {active_model}]_\n",
                }

            for attempt in range(MAX_MODEL_RETRIES):
                checkpoint = len(history)
                try:
                    yield from _run_agent_turn(
                        history,
                        model=active_model,
                        client=client,
                        map_state=map_state,
                        locale=locale,
                        api_key=api_key,
                    )
                    return
                except Exception as exc:
                    last_exc = exc
                    if not _is_retryable(exc):
                        yield {"type": "error", "error": _friendly_error(exc)}
                        yield {"type": "done"}
                        return
                    # Rewind contenu généré depuis le début de cette tentative
                    if len(history) > checkpoint:
                        del history[checkpoint:]
                    if attempt < MAX_MODEL_RETRIES - 1:
                        time.sleep(_RETRY_BACKOFF_S * (2**attempt))

        if last_exc is not None:
            yield {"type": "error", "error": _friendly_error(last_exc)}
        yield {"type": "done"}
    finally:
        map_tools.set_current_map_state(None)
