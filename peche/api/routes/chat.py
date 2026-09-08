"""POST /api/chat — SSE streaming avec map_state."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from google import genai
from pydantic import BaseModel, Field

from peche.agent.credentials import resolve_api_key
from peche.agent.loop import stream_chat
from peche.conversations.store import ConversationStore

logger = logging.getLogger("peche.api.chat")
router = APIRouter()

_AI_STUDIO_URL = "https://aistudio.google.com/app/apikey"


@lru_cache(maxsize=1)
def _store() -> ConversationStore:
    return ConversationStore()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None
    map_state: dict[str, Any] | None = None
    locale: Literal["fr", "en"] | None = None


def _sse_format(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _ensure_session(session_id: str | None) -> str:
    store = _store()
    if session_id and store.get_conversation(session_id):
        return session_id
    return store.create_conversation()


def _missing_key_message(locale: str | None) -> str:
    if (locale or "fr").lower().startswith("en"):
        return (
            "Gemini API key missing. Add your free key from Google AI Studio "
            f"in Settings, or set GEMINI_API_KEY on the server: {_AI_STUDIO_URL}"
        )
    return (
        "Clé API Gemini manquante. Ajoutez votre clé gratuite Google AI Studio "
        f"dans les paramètres, ou définissez GEMINI_API_KEY sur le serveur : "
        f"{_AI_STUDIO_URL}"
    )


def _no_key_stream(locale: str | None):
    yield _sse_format({"type": "error", "error": _missing_key_message(locale)})
    yield _sse_format({"type": "done"})


def _stream_events(
    message: str,
    session_id: str,
    map_state: dict | None,
    *,
    api_key: str,
    locale: str | None,
):
    store = _store()
    history = store.load_gemini_history(session_id)
    yield _sse_format({"type": "session", "session_id": session_id})

    text_parts: list[str] = []
    tools_log: list[dict] = []
    result_map_state = map_state
    client = genai.Client(api_key=api_key)

    try:
        for event in stream_chat(
            message,
            history=history,
            map_state=map_state,
            client=client,
            locale=locale,
            api_key=api_key,
        ):
            etype = event.get("type")
            if etype == "text":
                text_parts.append(event.get("text", ""))
            elif etype == "tool_call":
                tools_log.append(
                    {
                        "name": event.get("name"),
                        "args": event.get("args"),
                        "result": None,
                    }
                )
            elif etype == "tool_result" and tools_log:
                tools_log[-1]["result"] = event.get("result")
            elif etype == "map_action" and result_map_state is not None:
                result_map_state = _apply_map_action_locally(
                    result_map_state, event
                )
            yield _sse_format(event)
    except Exception as exc:  # noqa: BLE001
        logger.exception("stream_chat error")
        yield _sse_format({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
        yield _sse_format({"type": "done"})
        return

    assistant_text = "".join(text_parts)
    store.append_exchange(
        session_id,
        message,
        assistant_text,
        tools_log or None,
        map_state=result_map_state,
        user_map_state=map_state,
    )
    store.save_gemini_history(session_id, history)


def _apply_map_action_locally(state: dict, event: dict) -> dict:
    """Met à jour une copie du MapState côté serveur pour la persistance."""
    import copy

    s = copy.deepcopy(state)
    action = event.get("action")
    if action == "set_view":
        if "center" in event:
            s["center"] = event["center"]
        if "zoom" in event:
            s["zoom"] = event["zoom"]
        if "bbox" in event:
            s["bbox"] = event["bbox"]
    elif action == "toggle_layers":
        layers = {layer["id"]: layer for layer in s.get("layers") or []}
        for lid in event.get("show") or []:
            layers.setdefault(lid, {"id": lid, "visible": True, "opacity": 1.0})
            layers[lid]["visible"] = True
        for lid in event.get("hide") or []:
            if lid in layers:
                layers[lid]["visible"] = False
        for lid, op in (event.get("opacity") or {}).items():
            layers.setdefault(lid, {"id": lid, "visible": True, "opacity": 1.0})
            layers[lid]["opacity"] = float(op)
        s["layers"] = list(layers.values())
    elif action == "set_layer_filter":
        lid = event.get("layer_id")
        layers = {layer["id"]: layer for layer in s.get("layers") or []}
        layers.setdefault(lid, {"id": lid, "visible": True, "opacity": 1.0})
        layers[lid]["filters"] = event.get("filters") or {}
        layers[lid]["visible"] = True
        s["layers"] = list(layers.values())
    elif action == "filter_by_zone":
        if event.get("clear"):
            s.pop("zoneFilter", None)
        else:
            s["zoneFilter"] = {"zoneId": event.get("zone_id")}
    return s


@router.post("/api/chat")
def chat(
    req: ChatRequest,
    x_gemini_api_key: str | None = Header(None, alias="X-Gemini-Api-Key"),
):
    api_key = resolve_api_key(x_gemini_api_key)
    if not api_key:
        return StreamingResponse(
            _no_key_stream(req.locale),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    sid = _ensure_session(req.session_id)
    return StreamingResponse(
        _stream_events(
            req.message,
            sid,
            req.map_state,
            api_key=api_key,
            locale=req.locale,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
