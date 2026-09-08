# Carte interactive — peche-agent v1 (map-first)

## Objectif

La **carte OpenLayers** est l'élément principal. Le chat Gemini et l'historique
servent à piloter et contextualiser la visualisation.

## Architecture

```
Browser (web/)  →  FastAPI (peche/api)  →  domain Python + OGC publics
```

- SPA : Vite + TypeScript + OpenLayers (`web/`)
- API : `/api/catalog`, `/api/ogc`, `/api/features`, `/api/zones`, `/api/chat` (SSE),
  `/api/hydromet`, `/api/tides`, `/api/conversations`, `/api/health`
- Agent unique Gemini (`gemini-3.5-flash-lite`, fallback `gemini-3.1-flash-lite`)
  avec outils métier + outils carte (`set_map_view`, `toggle_layers`, …)

## Couches

Catalogue hybride :

1. **Curated (~30)** — fishing-first avec filtres (`peche/catalog/curated.py`)
2. **Harvested** — GetCapabilities des services Forêt ouverte / Atlas de l'eau /
   SmartFaune (`python3 -m peche.catalog harvest`)

Basemaps : Fond Québec (XYZ) + Imagerie Continue (WMTS).

### Filtres

| Mécanisme | Couches |
|-----------|---------|
| `cql` | GeoServer faune (TFS, zones chasse, habitats…) |
| `arcgis` | Atlas de l'eau (Guide poisson, IQBP…) |
| `local` | Vigilance, barrages, marées, plans RegPec |
| `colorkey` | `pente_cpl` — 6 classes A–F côté client |
| clip zone | **toutes** les couches via polygone RegPec |

### Zones de pêche

Polygones issus de `SmartFaunePub:Zone_chasse_da3_sefaq`, mappés aux 34 ids
RegPec : `python3 -m peche.spatial zones-peche` → `data/spatial/zones_peche.geojson`.

## MapState

```ts
type MapState = {
  center: [lon, lat]; zoom; bbox;
  basemap; layers: [{id, visible, opacity, filters?}];
  zoneFilter?: { zoneId };
  pins?: [{ id, lon, lat, label? }];
};
```

- Chat → agent : `map_state` dans `POST /api/chat`, injecté au prompt (TOON)
- Agent → carte : événements SSE `map_action`
- Historique : `messages.map_state_json` ; clic message = rewind carte
- UI : onglets Carte | Assistant ; points utilisateur dans `pins`

## Lancer

```bash
# API + SPA (après npm run build dans web/)
.venv/bin/python -m peche.api   # http://127.0.0.1:8000

# Dev front
cd web && npm run dev           # proxy /api → :8000
```

## Données réutilisées (pas de re-téléchargement massif)

Conservées : `data/zones/`, `locations/`, `barrages/`, `hydromet/`, `tides/`,
`iqbp/`, `spatial/lce/`, `spatial/bassins/`, `regpec_lce_matches.json`.

LCE/bassins restent l'index offline de l'agent ; le rendu carte passe par les
WMS GRHQ / Bassins.
