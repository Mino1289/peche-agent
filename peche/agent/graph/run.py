"""Point d'entrée graphe — utilisé par loop.py."""

from __future__ import annotations

from typing import Any

from google.genai import types

from peche.agent.graph.build import compile_graph
from peche.agent.graph.events import bind_event_sink, clear_sink, emit
from peche.agent.graph.state import AgentState


def run_graph_turn(
    message: str,
    history: list[types.Content] | None = None,
) -> tuple[list[dict[str, Any]], list[types.Content], str]:
    """Exécute un tour multi-agents ; retourne (événements, historique, texte final)."""
    sink = bind_event_sink()
    graph = compile_graph()
    state: AgentState = {
        "user_message": message,
        "gemini_history": list(history or []),
        "agent_outputs": {},
        "needs_synthesis": False,
    }
    result = graph.invoke(state)
    final = result.get("final_answer") or ""
    if final and not any(e.get("type") == "text" for e in sink):
        emit({"type": "text", "text": final})
    emit({"type": "done"})
    updated = result.get("gemini_history") or list(history or [])
    events = list(sink)
    clear_sink()
    return events, updated, final
