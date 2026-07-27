"""File d'événements streaming pour l'adaptateur loop.py."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_events: ContextVar[list[dict[str, Any]] | None] = ContextVar("graph_events", default=None)


def bind_event_sink() -> list[dict[str, Any]]:
    sink: list[dict[str, Any]] = []
    _events.set(sink)
    return sink


def emit(event: dict[str, Any]) -> None:
    sink = _events.get()
    if sink is not None:
        sink.append(event)


def clear_sink() -> None:
    _events.set(None)
