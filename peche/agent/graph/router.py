"""Routeur : heuristiques d'abord, LLM Gemma si ambigu."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from peche.agent.graph.rate_limit import wait_for_model

ROUTER_MODEL = os.environ.get("LLM_MODEL_ROUTER", "gemma-4-26b-a4b-it")

_REG_KW = re.compile(
    r"\b(règlement|réglement|reglement|limite|espèce|espece|pêcher|pecher|autorisé|autorise|interdit|saison)\b",
    re.I,
)
_HYDRO_KW = re.compile(r"\b(niveau|débit|debit|hydro|station|vigilance|barrage|étage)\b", re.I)
_WX_KW = re.compile(r"\b(météo|meteo|température|temperature|vent|pluie|marée|maree)\b", re.I)
_FISH_KW = re.compile(r"\b(leurre|technique|stratégie|strategie|conseil|appât|appat|mouche)\b", re.I)
_MAP_KW = re.compile(r"\b(carte|localisation|bassin|lce|où se trouve|ou se trouve)\b", re.I)


def route_heuristic(message: str) -> tuple[list[str], bool]:
    """Retourne (agents, confident)."""
    hits: list[str] = []
    if _REG_KW.search(message):
        hits.append("regulations")
    if _HYDRO_KW.search(message):
        hits.append("hydro")
    if _WX_KW.search(message):
        hits.append("weather")
    if _FISH_KW.search(message):
        hits.append("fishing")
    if _MAP_KW.search(message):
        hits.append("geomap")

    if not hits:
        return ["regulations"], False

    if len(hits) == 1:
        return hits, True

    # Intention composite explicite
    composite_markers = (" et ", " ainsi ", " aussi ", "demain", "sortie", "planifier")
    if any(m in message.lower() for m in composite_markers) and len(hits) >= 2:
        return hits[:3], True

    return hits[:1], True


def route_llm(message: str) -> list[str]:
    from google import genai
    from google.genai import types

    if not wait_for_model(ROUTER_MODEL):
        return ["regulations"]

    client = genai.Client()
    prompt = (
        "Classifie l'intention en JSON {\"agents\": [...]} parmi : "
        "regulations, hydro, weather, fishing, geomap. "
        "Un seul agent sauf question composite. Message : "
        + json.dumps(message, ensure_ascii=False)
    )
    try:
        resp = client.models.generate_content(
            model=ROUTER_MODEL,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        text = resp.text or ""
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start : end + 1])
            agents = data.get("agents") or []
            valid = {"regulations", "hydro", "weather", "fishing", "geomap"}
            return [a for a in agents if a in valid] or ["regulations"]
    except Exception:
        pass
    return ["regulations"]


def select_agents(message: str) -> tuple[list[str], bool]:
    agents, confident = route_heuristic(message)
    if confident:
        return agents, False
    return route_llm(message), True
