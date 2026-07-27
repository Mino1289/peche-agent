"""Nœuds LangGraph."""

from __future__ import annotations

import json
import os
from typing import Literal

from google import genai
from google.genai import types

from peche.agent.graph.agent_runner import run_agent
from peche.agent.graph.rate_limit import wait_for_model
from peche.agent.graph.router import select_agents
from peche.agent.graph.state import AgentState
from peche.agent.prompts.synthesize import SYNTHESIZE_PROMPT

SYNTH_MODEL = os.environ.get("LLM_MODEL_SYNTH", os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite"))


def router_node(state: AgentState) -> dict:
    message = state.get("user_message") or ""
    agents, used_llm = select_agents(message)
    return {
        "agents": agents,
        "needs_synthesis": len(agents) > 1,
        "agent_outputs": {},
        "degraded": False,
    }


def run_agents_node(state: AgentState) -> dict:
    message = state.get("user_message") or ""
    agents = state.get("agents") or ["regulations"]
    history = state.get("gemini_history") or []
    outputs: dict[str, str] = dict(state.get("agent_outputs") or {})

    for agent in agents:
        if agent in outputs and outputs[agent]:
            continue
        text, history = run_agent(agent, message, history=history)
        outputs[agent] = text

    return {"agent_outputs": outputs, "gemini_history": history}


def synthesize_node(state: AgentState) -> dict:
    outputs = state.get("agent_outputs") or {}
    if len(outputs) <= 1:
        only = next(iter(outputs.values()), "")
        return {"final_answer": only, "needs_synthesis": False}

    if not wait_for_model(SYNTH_MODEL):
        merged = "\n\n".join(f"**{k}** : {v}" for k, v in outputs.items() if v)
        return {"final_answer": merged, "degraded": True}

    client = genai.Client()
    payload = json.dumps(outputs, ensure_ascii=False, indent=2)
    prompt = f"{SYNTHESIZE_PROMPT}\n\nRéponses agents :\n{payload}"
    resp = client.models.generate_content(
        model=SYNTH_MODEL,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        config=types.GenerateContentConfig(temperature=0.3),
    )
    text = resp.text or "\n\n".join(outputs.values())
    return {"final_answer": text}


def finalize_node(state: AgentState) -> dict:
    outputs = state.get("agent_outputs") or {}
    if state.get("final_answer"):
        return {}
    if len(outputs) == 1:
        return {"final_answer": next(iter(outputs.values()), "")}
    return {}


def route_after_agents(state: AgentState) -> Literal["synthesize", "finalize"]:
    if state.get("needs_synthesis") and len(state.get("agent_outputs") or {}) > 1:
        return "synthesize"
    return "finalize"
