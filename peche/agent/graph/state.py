"""État partagé du graphe multi-agents."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_message: str
    intent: str
    agents: list[str]
    agent_outputs: dict[str, str]
    plan_context: dict[str, Any] | None
    needs_synthesis: bool
    final_answer: str
    degraded: bool
    gemini_history: list[Any]
