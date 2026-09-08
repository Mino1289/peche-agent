# peche-agent — Résumé du projet (v1 map-first)

Agent conversationnel québécois d'aide à la pêche sportive, centré sur une
**carte OpenLayers** alimentée par les services OGC publics (Forêt ouverte,
Atlas de l'eau, Vigilance, SmartFaune) + données RegPec offline. Chat Gemini
bidirectionnel avec la carte ; historique qui snapshot l'état MapState.

---

## Architecture

| Couche | Technologie | Fichier clé |
|--------|-------------|-------------|
| **SPA** | Vite + TS + OpenLayers | `web/src/` |
| **API** | FastAPI / SSE | `peche/api/` |
| **LLM** | Gemini 3.5-flash-lite (+ fallback 3.1) | `peche/agent/loop.py` |
| **Outils** | 26 (21 métier + 5 carte) | `peche/tools.py` + `map_tools.py` |
| **Catalogue** | curated + GetCapabilities | `peche/catalog/` |
| **Spatial** | zones pêche, LCE, bassins | `peche/spatial/` |
| **Persistance** | SQLite (msgs + map_state) | `peche/conversations/store.py` |
| **MCP** | stdio / HTTP | `peche/mcp/server.py` |

---

## Interfaces

1. **SPA** (`http://127.0.0.1:8000`) — onglets Carte (couches + carte) et Assistant
2. **API** — `/api/catalog`, `/api/ogc`, `/api/features`, `/api/zones`, `/api/chat`, `/api/hydromet`, `/api/tides`, `/api/conversations`, `/api/health`
3. **MCP** — 26 outils (JSON)

---

## Données

Réutilisées sans re-téléchargement : `data/zones/`, `locations/`, `barrages/`,
`hydromet/`, `tides/`, `iqbp/`, `spatial/lce/`, `spatial/bassins/`,
`regpec_lce_matches.json`.

Nouvelles : `data/catalog/catalog.json`, `data/spatial/zones_peche.geojson`.

Pipeline :

```
./scripts/refresh-data.sh
  ├── coords / hydromet / tides / barrages / lce / bassins / spatial link
  ├── peche.spatial zones-peche
  └── peche.catalog harvest
```

---

## Déploiement

```bash
.venv/bin/python -m peche.api          # UI + API
.venv/bin/python -m peche.mcp          # MCP stdio
docker build -t peche-agent . && docker run -p 8000:8000 --env-file .env peche-agent
```

| Variable | Défaut | Description |
|----------|--------|-------------|
| `GEMINI_API_KEY` | — | Clé Google AI |
| `LLM_MODEL` | `gemini-3.5-flash-lite` | Modèle principal |
| `LLM_MODEL_FALLBACK` | `gemini-3.1-flash-lite` | Repli auto |
| `DATA_DIR` | `./data` | Données |
| `PECHE_HOST` / `PECHE_PORT` | `127.0.0.1` / `8000` | Bind |

---

## Points notables

- **MapState** : contrat unique carte ↔ chat ↔ historique (dont `pins`)
- **Clip zone** : canvas prerender sur polygones RegPec (toutes couches)
- **Pente LiDAR** : filtre colorkey client sur `pente_cpl` (classes A–F)
- **Proxy OGC** : `/api/ogc` + cache disque pour CORS
- Streamlit / Folium / LangGraph retirés en v1
