"""Route /api/chat : streaming SSE de la boucle agent.

Format SSE simple : un event JSON par ligne `data: {...}\n\n`. Le client peut
distinguer `text`, `tool_call`, `tool_result`, `done`, `error` via le champ
`type`.

Sessions persistées en SQLite (`data/conversations.db`).
"""

from __future__ import annotations

import json
import logging
import uuid
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from peche.agent.loop import stream_chat
from peche.conversations.store import ConversationStore

logger = logging.getLogger("peche.server.chat")

router = APIRouter()


@lru_cache(maxsize=1)
def _store() -> ConversationStore:
    return ConversationStore()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


def _sse_format(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _ensure_session(session_id: str | None) -> str:
    store = _store()
    if session_id:
        if store.get_conversation(session_id):
            return session_id
    return store.create_conversation()


def _stream_events(message: str, session_id: str):
    store = _store()
    history = store.load_gemini_history(session_id)
    yield _sse_format({"type": "session", "session_id": session_id})

    text_parts: list[str] = []
    tools_log: list[dict] = []

    try:
        for event in stream_chat(message, history=history):
            if event.get("type") == "text":
                text_parts.append(event.get("text", ""))
            elif event.get("type") == "tool_call":
                tools_log.append(
                    {
                        "name": event.get("name"),
                        "args": event.get("args"),
                        "result": None,
                    }
                )
            elif event.get("type") == "tool_result" and tools_log:
                tools_log[-1]["result"] = event.get("result")
            yield _sse_format(event)
    except Exception as exc:  # noqa: BLE001
        logger.exception("stream_chat error")
        yield _sse_format({"type": "error", "error": f"{type(exc).__name__}: {exc}"})
        yield _sse_format({"type": "done"})
        return

    assistant_text = "".join(text_parts)
    store.append_exchange(session_id, message, assistant_text, tools_log or None)
    store.save_gemini_history(session_id, history)


@router.post("/api/chat")
def chat(req: ChatRequest):
    sid = _ensure_session(req.session_id)
    return StreamingResponse(
        _stream_events(req.message, sid),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/conversations")
def list_conversations(limit: int = 50) -> dict:
    return {"conversations": _store().list_conversations(limit=limit)}


@router.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    store = _store()
    meta = store.get_conversation(conversation_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {
        **meta,
        "messages": store.load_messages(conversation_id),
    }


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict:
    if not _store().delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {"deleted": conversation_id}


@router.post("/api/reset")
def reset_chat_sessions() -> dict:
    """Efface toutes les conversations persistées."""
    return {"cleared": reset_sessions()}


def reset_sessions() -> int:
    store = _store()
    convs = store.list_conversations(limit=10_000)
    n = 0
    for c in convs:
        if store.delete_conversation(c["id"]):
            n += 1
    _store.cache_clear()
    return n
