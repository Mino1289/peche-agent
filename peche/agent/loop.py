"""Boucle agent Gemini unique avec streaming + fallback modèle + map_action."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from google import genai
from google.genai import types

from peche.agent.credentials import current_api_key, resolve_api_key
from peche.agent import map_tools
from peche.agent import tracing
from peche.agent.prompt import build_system_prompt
from peche.agent.schemas import TOOL_SCHEMAS, TOOLS
from peche.encoding import wrap_tool_result
from peche.observability import NOOP, Span, start_trace

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3.5-flash-lite")
FALLBACK_MODEL = os.environ.get("LLM_MODEL_FALLBACK", "gemini-3.1-flash-lite")
MAX_TOOL_TURNS = 10
MAX_MODEL_RETRIES = 3
_RETRY_BACKOFF_S = 0.6
# Réflexion visible dans Langfuse (champ `thinking`). 0 = désactivée côté budget.
THINKING_BUDGET = int(os.environ.get("LLM_THINKING_BUDGET") or "1024")


def _make_client(api_key: str | None = None) -> genai.Client:
    key = api_key or current_api_key.get() or resolve_api_key(None)
    if key:
        return genai.Client(api_key=key)
    return genai.Client()


def _call_tool(name: str, args: dict[str, Any]) -> dict:
    if name not in TOOLS:
        return {"error": f"Outil inconnu: {name}"}
    try:
        result = TOOLS[name](**args)
    except TypeError as exc:
        return {"error": f"Mauvais arguments pour {name}: {exc}"}
    except Exception as exc:
        return {"error": f"{name} a levé {type(exc).__name__}: {exc}"}
    return json.loads(json.dumps(result, default=str, ensure_ascii=False))


def _execute_tool(
    name: str,
    args: dict[str, Any],
    *,
    api_key: str | None = None,
    trace: Span = NOOP,
    tool_call_id: str | None = None,
    turn: int | None = None,
) -> dict:
    if api_key:
        current_api_key.set(api_key)
    # Section 100 % synchrone : l'observation est « courante » le temps de
    # l'appel, donc les sous-observations (point, sous-agent expert…) s'y
    # rattachent d'elles-mêmes.
    with trace.current(
        tracing.tool_span_name(name),
        as_type="tool",
        input=args,
        metadata={"tool": name, "tool_call_id": tool_call_id, "turn": turn},
    ) as span:
        result = _call_tool(name, args)
        failed = isinstance(result, dict) and result.get("error")
        if failed:
            span.update(output=result, level="ERROR", status_message=str(failed))
        else:
            span.update(output=result)
    trace.count("tool_calls")
    if failed:
        trace.count("tool_errors")
    trace.append("tools_called", name)
    return result


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
    trace: Span = NOOP,
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
    system_prompt = build_system_prompt(map_state=map_state, locale=locale)
    temperature = 0.4
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools_def,
        temperature=temperature,
        thinking_config=types.ThinkingConfig(
            include_thoughts=True, thinking_budget=THINKING_BUDGET
        ),
    )
    map_tools.clear_map_actions()

    for turn in range(MAX_TOOL_TURNS):
        attempt_checkpoint = len(history)
        # Une génération Langfuse par appel modèle (jamais une seule pour toute
        # la boucle) : on voit ce que le modèle a décidé après chaque résultat
        # d'outil, avec le contexte exact qu'il avait.
        gen = trace.child(
            tracing.GEN_AGENT_STEP,
            as_type="generation",
            model=model,
            model_parameters={"temperature": temperature},
            input=tracing.history_to_messages(history, system_prompt) if trace else None,
            metadata={
                "turn": turn + 1,
                "max_turns": MAX_TOOL_TURNS,
                "history_contents": len(history),
                "tools_declared": len(decls),
            },
        )
        try:
            stream = client.models.generate_content_stream(
                model=model, contents=history, config=config
            )
        except Exception as exc:
            gen.fail(exc)
            gen.end()
            if len(history) > attempt_checkpoint:
                del history[attempt_checkpoint:]
            raise

        model_parts: list[types.Part] = []
        function_call_parts: list[types.Part] = []
        thoughts: list[str] = []
        usage = None
        finish_reason = None
        first_chunk_at = None
        completed = False
        try:
            for chunk in stream:
                if first_chunk_at is None:
                    first_chunk_at = datetime.now(timezone.utc)
                usage = getattr(chunk, "usage_metadata", None) or usage
                for cand in chunk.candidates or []:
                    finish_reason = getattr(cand, "finish_reason", None) or finish_reason
                    if not cand.content or not cand.content.parts:
                        continue
                    for part in cand.content.parts:
                        if getattr(part, "thought", False):
                            # Réflexion : tracée, jamais montrée à l'utilisateur.
                            if getattr(part, "text", None):
                                thoughts.append(part.text)
                            model_parts.append(part)
                            continue
                        if getattr(part, "text", None):
                            yield {"type": "text", "text": part.text}
                            model_parts.append(part)
                            continue
                        fc = getattr(part, "function_call", None)
                        if fc and getattr(fc, "name", None):
                            model_parts.append(part)
                            function_call_parts.append(part)
            completed = True
        except Exception as exc:
            gen.fail(exc)
            # Conserver les tool results déjà dans l'historique ; retirer
            # seulement la réponse modèle incomplète de cette tentative.
            if model_parts:
                del history[attempt_checkpoint:]
            raise
        finally:
            if not completed:  # erreur ou client déconnecté en cours de stream
                gen.end()

        if model_parts:
            history.append(types.Content(role="model", parts=model_parts))

        tool_call_ids: list[str] = []
        if gen:
            out_msg = tracing.last_assistant_message(
                tracing.history_to_messages(history)
            ) if model_parts else None
            tool_call_ids = [c["id"] for c in (out_msg or {}).get("tool_calls", [])]
            details = tracing.usage_details(usage)
            gen.update(
                output=out_msg,
                usage_details=details,
                completion_start_time=first_chunk_at,
                metadata={
                    "finish_reason": str(finish_reason) if finish_reason else None,
                    "tool_calls_requested": [
                        p.function_call.name for p in function_call_parts
                    ]
                    or None,
                    "thinking": "\n".join(thoughts) or None,
                    **tracing.usage_extra(usage),
                },
            )
            trace.count("llm_calls")
            for key, label in (("input", "input_tokens"), ("output", "output_tokens")):
                trace.count(label, (details or {}).get(key, 0))
        gen.end()

        if not function_call_parts:
            for action in map_tools.drain_map_actions():
                yield {"type": "map_action", **action}
            yield {"type": "done"}
            return

        tool_response_parts: list[types.Part] = []
        for i, part in enumerate(function_call_parts):
            fc = part.function_call
            args = dict(fc.args) if fc.args else {}
            yield {"type": "tool_call", "name": fc.name, "args": args}
            result = _execute_tool(
                fc.name,
                args,
                api_key=api_key,
                trace=trace,
                tool_call_id=tool_call_ids[i] if i < len(tool_call_ids) else None,
                turn=turn + 1,
            )
            yield {"type": "tool_result", "name": fc.name, "result": result}
            for action in map_tools.drain_map_actions():
                yield {"type": "map_action", **action}
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=fc.name, response=wrap_tool_result(fc.name, result)
                )
            )
        history.append(types.Content(role="user", parts=tool_response_parts))

    trace.update(level="WARNING", status_message="Limite de tours d'outils atteinte")
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
    session_id: str | None = None,
    user_id: str | None = None,
    source: str = "web",
) -> Iterator[dict]:
    """Stream tokens + tool events + map_action pour une conversation.

    Une trace Langfuse `chat-turn` par message utilisateur ; `session_id`
    regroupe les tours d'une même conversation (vue Sessions).
    """
    if history is None:
        history = []
    primary = model or DEFAULT_MODEL
    root = start_trace(
        tracing.TRACE_CHAT_TURN,
        as_type="agent",
        session_id=session_id,
        user_id=user_id,
        tags=["peche-agent", f"locale:{locale or 'fr'}", f"source:{source}"],
        trace_metadata={"locale": locale or "fr", "source": source},
        input=message,
        metadata={
            "model": primary,
            "fallback_model": FALLBACK_MODEL,
            "locale": locale or "fr",
            "source": source,
            "history_contents_before": len(history),
        },
    )
    texts: list[str] = []
    status = "aborted"  # reste tel quel si le consommateur ferme le générateur
    error: str | None = None
    try:
        for event in _stream_chat(
            message,
            history,
            model=primary,
            client=client,
            map_state=map_state,
            locale=locale,
            api_key=api_key,
            trace=root,
        ):
            etype = event.get("type")
            if etype == "text":
                texts.append(event.get("text", ""))
            elif etype == "error":
                error = event.get("error")
                status = "error"
            elif etype == "done" and status != "error":
                status = "completed"
            yield event
    except BaseException as exc:
        if not isinstance(exc, GeneratorExit):
            status, error = "error", f"{type(exc).__name__}: {exc}"
        raise
    finally:
        root.update(
            output="".join(texts),
            metadata={"status": status, **root.stats},
            **({"level": "ERROR", "status_message": error} if error else {}),
        )
        root.end()


def _stream_chat(
    message: str,
    history: list[types.Content],
    *,
    model: str,
    client: genai.Client | None,
    map_state: dict | None,
    locale: str | None,
    api_key: str | None,
    trace: Span,
) -> Iterator[dict]:
    client = client or _make_client()
    primary = model
    models_to_try = [primary]
    if primary != FALLBACK_MODEL:
        models_to_try.append(FALLBACK_MODEL)

    # Contexte carte injecté dans le prompt : vue, couches, zone, points posés.
    if trace:
        trace.child(
            tracing.SPAN_MAP_CONTEXT,
            as_type="retriever",
            input=map_state,
            output=tracing.map_context(map_state),
            metadata={"pins": len((map_state or {}).get("pins") or [])},
        ).end()

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
                trace.count("model_fallbacks")
                yield {
                    "type": "text",
                    "text": f"\n_[bascule vers {active_model}]_\n",
                }

            for attempt in range(MAX_MODEL_RETRIES):
                checkpoint = len(history)
                if attempt or model_idx:
                    trace.count("retries")
                attempt_span = trace.child(
                    tracing.SPAN_ATTEMPT,
                    as_type="span",
                    metadata={
                        "model": active_model,
                        "attempt": attempt + 1,
                        "max_attempts": MAX_MODEL_RETRIES,
                        "is_fallback_model": model_idx > 0,
                    },
                )
                try:
                    yield from _run_agent_turn(
                        history,
                        model=active_model,
                        client=client,
                        map_state=map_state,
                        locale=locale,
                        api_key=api_key,
                        trace=attempt_span,
                    )
                    return
                except Exception as exc:
                    last_exc = exc
                    attempt_span.fail(exc)
                    if not _is_retryable(exc):
                        yield {"type": "error", "error": _friendly_error(exc)}
                        yield {"type": "done"}
                        return
                    # Rewind contenu généré depuis le début de cette tentative
                    if len(history) > checkpoint:
                        del history[checkpoint:]
                    if attempt < MAX_MODEL_RETRIES - 1:
                        time.sleep(_RETRY_BACKOFF_S * (2**attempt))
                finally:
                    attempt_span.end()

        if last_exc is not None:
            yield {"type": "error", "error": _friendly_error(last_exc)}
        yield {"type": "done"}
    finally:
        map_tools.set_current_map_state(None)
