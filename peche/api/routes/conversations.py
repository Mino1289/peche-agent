"""Conversations CRUD."""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException

from peche.conversations.store import ConversationStore

router = APIRouter()


@lru_cache(maxsize=1)
def _store() -> ConversationStore:
    return ConversationStore()


@router.get("/api/conversations")
def list_conversations(limit: int = 50, q: str | None = None) -> dict:
    return {"conversations": _store().list_conversations(limit=limit, query=q)}


@router.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    store = _store()
    meta = store.get_conversation(conversation_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {**meta, "messages": store.load_messages(conversation_id)}


@router.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict:
    if not _store().delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return {"deleted": conversation_id}


@router.post("/api/reset")
def reset_chat_sessions() -> dict:
    store = _store()
    convs = store.list_conversations(limit=10_000)
    n = 0
    for c in convs:
        if store.delete_conversation(c["id"]):
            n += 1
    _store.cache_clear()
    return {"cleared": n}
