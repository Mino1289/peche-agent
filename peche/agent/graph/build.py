"""Construction du StateGraph multi-agents."""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from peche.agent.graph.nodes import (
    finalize_node,
    route_after_agents,
    router_node,
    run_agents_node,
    synthesize_node,
)
from peche.agent.graph.state import AgentState

try:
    from langsmith import traceable
except ImportError:

    def traceable(*_a, **_kw):  # type: ignore[misc]
        def deco(fn):
            return fn

        return deco


@traceable(name="peche_router")
def _router(state: AgentState) -> dict:
    return router_node(state)


@traceable(name="peche_agents")
def _agents(state: AgentState) -> dict:
    return run_agents_node(state)


@traceable(name="peche_synthesize")
def _synth(state: AgentState) -> dict:
    return synthesize_node(state)


@traceable(name="peche_finalize")
def _finalize(state: AgentState) -> dict:
    return finalize_node(state)


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("router", _router)
    g.add_node("agents", _agents)
    g.add_node("synthesize", _synth)
    g.add_node("finalize", _finalize)

    g.add_edge(START, "router")
    g.add_edge("router", "agents")
    g.add_conditional_edges("agents", route_after_agents, {"synthesize": "synthesize", "finalize": "finalize"})
    g.add_edge("synthesize", "finalize")
    g.add_edge("finalize", END)
    return g


@lru_cache(maxsize=1)
def compile_graph():
    return build_graph().compile()
