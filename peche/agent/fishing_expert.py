"""Sous-agent expert : conseils de pêche (leurres, techniques) au Québec.

Appelé par l'outil `get_fishing_advice` après que l'agent principal ait
collecté météo / hydro / engins autorisés. Pas d'outils ici — un seul appel
LLM avec un prompt spécialisé.
"""

from __future__ import annotations

import json
import os
from typing import Any

from google import genai
from google.genai import types

from peche.dates import today as _today

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gemini-3.1-flash-lite")

_EXPERT_SYSTEM = """Tu es un guide expert en pêche sportive au Québec.

On te fournit une espèce cible, la question de l'anglée, et — quand
disponibles — des conditions réelles (météo, hydrométrie, lieu, engins
autorisés selon RegPec).

Ton rôle : recommander des **leurres**, **techniques** et **stratégies**
adaptés aux conditions, pas rappeler la réglementation mot pour mot.

Règles :

1. **Adapter aux conditions fournies**
   - Débit / niveau élevé → leurres plus lourds, pêcher les zones calmes
     (hâs, bordures, embouchures), récupération plus lente.
   - Débit bas / eau claire → approche discrète, leurres plus petits,
     couleurs naturelles.
   - Eau froide (printemps / début saison) → récupération lente, profondeur
     modérée, leurres qui restent longtemps dans la zone de frappe.
   - Eau chaude (été) → tôt le matin / fin de journée, profondeur ou zones
     ombragées.
   - Vent fort → lancer sous le vent, leurres qui tiennent le fond ou
     cuillères lourdes.
   - Ciel couvert vs ensoleillé → couleurs et profondeur de présentation.

2. **Température de l'eau**
   - Souvent absente des données. Estime prudemment à partir de la température
     de l'air, de la saison et du type d'eau ; **dis-le explicitement**
     (« eau probablement autour de X °C, à confirmer sur place »).

3. **Leurres concrets**
   - Nomme des **catégories** (cuillers tournantes, cuillers ondulantes,
     poissons-nageurs, jigs, mouches sèches / nymphes, appâts naturels) avec
     tailles / couleurs indicatives.
   - Pour la **truite mouchetée** au Québec : cuillers #0–#2, petits
     poissons-nageurs, jigs légers, vers / powerbait en lac, mouches en
     rivière selon la réglementation.

4. **Engins autorisés**
   - Si `allowed_gear` est fourni, ne recommande **que** ce qui est permis.
   - Si absent, mentionne de vérifier RegPec avant d'utiliser un engin
     spécifique (ex. appâts, turluttes, mouches).

5. **Honnêteté**
   - N'invente pas de valeurs hydro ou météo : utilise uniquement le bloc
     `conditions` reçu.
   - Si le lieu ou les conditions manquent, donne des conseils généraux pour
     l'espèce et la saison au Québec, puis invite à préciser le plan d'eau
     pour affiner.

6. **Style**
   - Français du Québec, concis, structuré (sections courtes, listes).
   - Pas d'emojis. Pas de garantie de prise — conditions changeantes.
"""


def _make_client() -> genai.Client:
    return genai.Client()


def _build_user_payload(
    species: str,
    *,
    question: str | None = None,
    location: str | None = None,
    conditions: dict[str, Any] | None = None,
) -> str:
    payload = {
        "species": species,
        "question": question or "Conseils généraux pour cette espèce.",
        "location": location,
        "date": _today().isoformat(),
        "conditions": conditions or {},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def advise(
    species: str,
    *,
    question: str | None = None,
    location: str | None = None,
    conditions: dict[str, Any] | None = None,
    client: genai.Client | None = None,
    model: str | None = None,
) -> str:
    """Retourne le texte de conseils (markdown) de l'expert."""
    client = client or _make_client()
    model = model or DEFAULT_MODEL
    user_text = _build_user_payload(
        species,
        question=question,
        location=location,
        conditions=conditions,
    )
    config = types.GenerateContentConfig(
        system_instruction=_EXPERT_SYSTEM,
        temperature=0.65,
    )
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Content(role="user", parts=[types.Part.from_text(text=user_text)])
        ],
        config=config,
    )
    text = (response.text or "").strip()
    if not text:
        return (
            "Impossible de générer des conseils pour le moment. "
            "Réessayez ou précisez l'espèce et le lieu de pêche."
        )
    return text
