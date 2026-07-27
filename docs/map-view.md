# Carte interactive — peche-agent

## Objectif

Visualiser sur une carte :

- Stations hydrométriques Vigilance (niveau / débit)
- Barrages CEHQ (répertoire officiel, ~6000 points)
- Stations marées SHC
- Plan d'eau RegPec sélectionné (contexte chat)
- Météo locale au point

## v1 — implémenté

Module [`peche/map_view.py`](../peche/map_view.py) + onglet **Carte** dans l'UI Streamlit (pleine page, 720 px).

Couches v1 :

| Couche | Source | Statut |
|--------|--------|--------|
| Stations hydro (toutes) | `data/hydromet/stations.json` | OK |
| Barrages CEHQ | `data/barrages/barrages.json` (~6000) | OK — `MarkerCluster` + points rouges |
| Marées SHC | `data/tides/stations.json` (IWLS) | OK |
| Pin plan d'eau | coords RegPec (`data/locations/`) | OK |
| Météo (popup) | outil météo chat ou `get_weather` | OK |
| Lacs / rivières LCE | `data/spatial/lce/` | OK — viewport zoom ≥ 10 |
| Bassins hydrographiques | `data/spatial/bassins/` | OK — niveau selon zoom |
| Lien RegPec ↔ LCE | `data/spatial/regpec_lce_matches.json` | OK — match + segments DMS |
| Règlements (popup pin) | `get_reglements` | OK — espèces en vigueur |

### Sync avec le chat

L'onglet Carte lit `st.session_state.messages` via `map_context_from_messages()` :

1. Outils plan (`get_weather_at_plan`, `get_hydromet_for_waterbody`, `get_barrages_at_plan`, etc.) → pin RegPec
2. Sinon `search_plans` → premier candidat
3. Sinon lieu libre (`get_weather_at_place`, etc.) → centrage sans pin
4. Météo : réutilise le dernier résultat météo du chat, ou appelle `get_weather` sur le pin (cache 15 min)

Priorité : outil le plus récent en premier (parcours inverse des messages).

## Limitations — règlements sur carte

Les règlements RegPec sont des **segments textuels** avec coordonnées ponctuelles (DMS dans le libellé), pas des polygones GeoJSON.

| Approche | Faisabilité |
|----------|-------------|
| Marqueurs par segment (point DMS) | Réaliste — v2 |
| Contours des 34 zones | Données MFFP à sourcer |
| Tracé de rivière (ligne) | OSM / NHN — gros chantier |

Recommandation : carte v1 = stations + barrages + pin du plan recherché ; pas de découpage réglementaire vectoriel.

## Évolutions possibles

- Couleur des stations selon `etat` Vigilance.
- Export GPX des stations proches d'un plan.
- Agent MCP `get_map_context` (voir [multi-agent](multi-agent.md)).
