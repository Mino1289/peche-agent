# AGENTS.md

Operational guide for coding agents working on **peche-agent**. For product overview, see [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md).

## Stack

| Layer | Location | Notes |
|-------|----------|--------|
| SPA (Vite + TS + OpenLayers) | `web/src/` | Map-first UI; chat is secondary tab |
| API (FastAPI + SSE) | `peche/api/` | Serves SPA from `web/dist/` when built |
| Agent (Gemini) | `peche/agent/` | Tool loop, prompts, BYOK |
| Business tools | `peche/tools.py`, `peche/agent/map_tools.py` | 26+ tools |
| MCP | `peche/mcp/server.py` | stdio or HTTP on `/mcp` when `MCP_ENABLED=1` |
| Catalogue | `peche/catalog/` | **Curated-only** default catalogue |
| Spatial / RegPec | `peche/spatial/`, `peche/reglements/` | Zones, plans, offline rules |
| Derived data | `data/` | See below |

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd web && npm ci && npm run dev          # hot reload; proxies /api → :8000
.venv/bin/python -m peche.api            # http://127.0.0.1:8000 (build web first for prod)

.venv/bin/python -m pytest tests/ -v
cd web && npm run build

./scripts/refresh-data.sh                # locations, hydro, zones, catalogue, …
python3 -m peche.guide_poisson sync      # guide consommation poisson (CKAN)
python3 -m peche.reglements sync         # refresh RegPec zones (optional)
```

## Module map

- `peche/catalog/curated.py` — fishing-first layer definitions (~30 layers)
- `peche/catalog/harvest.py` — writes `data/catalog/catalog.json` (curated only; GetCapabilities dump **not** merged into default UI)
- `peche/catalog/discover.py` — on-demand GetCapabilities search + custom layer validation
- `peche/spatial/` — zones pêche GeoJSON, LCE, plan geometry, point context
- `peche/reglements/` — offline RegPec parser, zone timelines
- `peche/guide_poisson/` — CKAN sync → `data/guide_poisson/index.json`
- `peche/tools.py` — agent/MCP business tools (search plans, regs, weather, hydro, …)

## Data layout

**Committed / stable:** `data/zones/`, `data/spatial/zones_peche.geojson`, `data/guide_poisson/index.json` (after sync), search indexes as documented in README.

**Generated / do not commit:** `data/cache/`, `data/runtime/`, `.env`.

**Refresh pipeline:** `./scripts/refresh-data.sh` (see script for steps).

## Contracts (do not break)

1. **MapState** (`web/src/types.ts`) — shared between map, chat history, and SSE `map_action` events. Includes `center`, `zoom`, `layers`, `zoneFilter`, `pins`.

2. **`GET /api/catalog`** — returns curated catalogue only. Harvested Forêt-ouverte dumps must **not** appear in default groups (`test_catalog_is_curated_only`).

3. **`GET /api/catalog/discover`** + **`POST /api/catalog/validate`** — optional custom layers (front stores in `localStorage`).

4. **`/api/ogc`** — CORS proxy with **host allowlist** (`peche/api/routes/ogc.py`). Never turn this into an open proxy.

5. **Zone clip** — canvas prerender on RegPec zone polygons; all overlay layers respect clip when zone filter active.

6. **Locale** — FR default; switching EN must **not** destroy `MapController` (update chrome + re-render panels only).

7. **BYOK** — Gemini key in browser `localStorage`; optional server `GEMINI_API_KEY`.

## Pitfalls

- Do **not** commit `.env`, API keys, or large raw downloads in `data/cache/`.
- Do **not** merge full GetCapabilities harvest into the default catalogue without an explicit product decision.
- RegPec zone ids (34 zones) ≠ displayed zone numbers; use `resolve_zone_ref` / `zone_by_id`.
- MCP on public deploy: set `MCP_ENABLED=0`.
- GitHub Pages alone cannot host the full app (needs FastAPI for chat, OGC proxy, SQLite). See plan branch `docs/deploy-no-docker`.

## Tests to run before PR

```bash
.venv/bin/python -m pytest tests/ -v
cd web && npm test && npm run build
```

Adding an identifiable map layer = one feature kind in `web/src/featureKinds/` (see [GLOSSARY.md](GLOSSARY.md)).

Key suites: `tests/test_catalog.py`, `tests/test_guide_poisson.py`, `tests/test_map_state.py`, `tests/test_mcp.py`.
