# peche-agent

Agent conversationnel pour la pêche au Québec : règlements officiels (offline) +
météo, hydrométrie et marées en direct, exposé via Streamlit, API SSE et MCP.

## Setup rapide

```bash
# 1. venv
uv pip install --python .venv/bin/python -r requirements.txt

# 2. config
cp .env.example .env   # renseigner GEMINI_API_KEY

# 3. données dérivées (régénération complète)
./scripts/refresh-data.sh
```

Ou étape par étape :

```bash
python3 -m peche.reglements sync              # zones (nécessite cache/réseau)
python3 -m peche.coords extract --build-index # locations + search_index.json
python3 -m peche.hydromet sync-stations
python3 -m peche.hydromet match --all
```

Lancer l'UI **avec le venv** (sinon `folium` et autres deps peuvent manquer) :

```bash
.venv/bin/python -m peche.ui
```

## Lancer le chat (Streamlit)

```bash
python3 -m peche.ui    # http://127.0.0.1:8501
```

Fonctionnalités UI (onglets **Chat**, **Historique**, **Carte**) :
- historique des conversations persisté (SQLite),
- graphiques hydro multi-stations (ex. barrages Lac Kénogami),
- carte pleine page : hydro Vigilance, barrages CEHQ (~6000), marées SHC, pin plan + météo du chat (Folium),
- debug des appels d'outils sous chaque réponse.

## Serveur MCP (Cursor / clients MCP)

Expose les **17 outils** via stdio (dev local) ou HTTP streamable (Docker) :

```bash
python3 -m peche.mcp                         # stdio
python3 -m peche.mcp --transport http        # http://127.0.0.1:8001/mcp
```

**Cursor — stdio** (`.cursor/mcp.json`) :

```json
{
  "mcpServers": {
    "peche-agent": {
      "command": "/chemin/vers/peche-agent/.venv/bin/python",
      "args": ["-m", "peche.mcp"],
      "cwd": "/chemin/vers/peche-agent"
    }
  }
}
```

**Cursor — HTTP** (conteneur Docker, port `8001` exposé) :

```json
{
  "mcpServers": {
    "peche-agent": {
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

Avec Docker Compose, le MCP démarre automatiquement avec l'UI (`scripts/docker-entrypoint.sh`).
Désactiver : `MCP_ENABLED=0`.

## API HTTP

```bash
python3 -m peche.server     # http://127.0.0.1:8000
```

| Route | Description |
|-------|-------------|
| `POST /api/chat` | SSE — `{ message, session_id? }` |
| `GET /api/conversations` | Liste des conversations |
| `GET /api/conversations/{id}` | Messages d'une conversation |
| `DELETE /api/conversations/{id}` | Supprimer |
| `POST /api/reset` | Effacer toutes les conversations |
| `GET /api/health` | État des données et config |

## Outils de l'agent

| Outil | Quand |
|---|---|
| `search_plans` | trouver un plan d'eau (Ste/Sainte, segments) |
| `get_hydromet_for_waterbody` | **niveau/débit multi-stations** pour un lac/rivière |
| `get_hydromet_at_plan` | hydro station primaire (legacy) |
| `get_reglements` | règlements en vigueur |
| `get_weather*` / `get_tides*` / `get_water_levels` | conditions live |
| `get_fishing_advice` | conseils techniques (sous-agent) |

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

Suite offline (pytest) : normalisation, dates, parser RegPec, hydrométrie, barrages, marées, météo (mock), recherche de plans, conversations SQLite, health API, MCP.

## Documentation

- [Architecture multi-agents](docs/multi-agent.md)
- [Carte interactive](docs/map-view.md)

## Docker et données

L'image (`Dockerfile`) copie le dépôt dans `/app` via `COPY . .`.

| Élément | Comportement |
|---------|----------------|
| `data/zones/`, `data/locations/`, `data/hydromet/`, `data/barrages/`, `data/tides/`, `data/search_index.json` | **Inclus dans l'image** au moment du `docker build` |
| `data/cache/` | **Exclu** (`.dockerignore`) — le sync RegPec retélécharge si absent |
| `data/conversations.db` | **Exclu** (`.gitignore`) — non persisté sauf volume monté |

Pour des données à jour dans Docker :

```bash
# Option A — reconstruire l'image après refresh local
./scripts/refresh-data.sh
docker build -t peche-agent .
docker run -p 8501:8501 --env-file .env peche-agent

# Option B — monter le dossier data depuis l'hôte
docker run -p 8501:8501 --env-file .env -v "$(pwd)/data:/app/data" peche-agent
```

Après ajout de dépendances (`folium`, `mcp`, etc.), **reconstruire** l'image Docker.

## Provider LLM

`google-genai` (Gemini) — modèle via `LLM_MODEL` dans `.env`.
