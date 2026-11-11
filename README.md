# peche-agent

Interactive map and conversational assistant for sport fishing in Quebec.

OpenLayers map (primary UI) + Gemini chat for regulations, weather, hydrometry, tides, and map control. Offline RegPec data bundled; live OGC layers from Quebec open data.

**Français :** [README.fr.md](README.fr.md)

## Quick start (Docker)

```bash
git clone https://github.com/YOUR_USER/peche-agent.git
cd peche-agent
cp .env.example .env   # optional: GEMINI_API_KEY for server-side LLM

docker compose up --build
```

Three containers start by default: **frontend** (port 8000), **backend** (internal API), **mcp** (port 8001).

Open **http://127.0.0.1:8000**

### Bring your own key (BYOK)

If `GEMINI_API_KEY` is not set on the server, open **Assistant → Settings** and paste a free [Google AI Studio](https://aistudio.google.com/app/apikey) key. It stays in your browser (`localStorage`).

## Features

| Layer | Stack |
|-------|--------|
| Front | Vite + TypeScript + OpenLayers |
| API | FastAPI + SSE |
| Agent | Gemini `3.5-flash-lite` (+ fallback `3.1-flash-lite`) |
| Data | RegPec offline + Quebec OGC + SQLite conversations |

- Hybrid map catalog (~30 curated layers + GetCapabilities harvest)
- RegPec zone clip, LiDAR slope filter, user pins shared with chat
- Chat ↔ map sync (`MapState` + SSE `map_action`)
- UI: French default, English toggle (FR \| EN)
- 26 agent tools (+ MCP)

## Local development

```bash
uv pip install --python .venv/bin/python -r requirements.txt
cd web && npm install && npm run build && cd ..
cp .env.example .env

.venv/bin/python -m peche.api          # http://127.0.0.1:8000
cd web && npm run dev                  # hot reload, proxies /api
```

Refresh derived data (optional):

```bash
./scripts/refresh-data.sh
```

## MCP (Cursor, Claude Desktop, custom agents)

Expose Quebec fishing tools to your own agent.

### Option A — stdio (recommended, no HTTP)

```json
{
  "mcpServers": {
    "peche-agent": {
      "command": "/ABS/PATH/.venv/bin/python",
      "args": ["-m", "peche.mcp"],
      "env": {
        "GEMINI_API_KEY": "AIza...",
        "DATA_DIR": "/ABS/PATH/peche-agent/data"
      }
    }
  }
}
```

- **Cursor:** `.cursor/mcp.json` (project) or `~/.cursor/mcp.json`
- **Claude Desktop:** `claude_desktop_config.json` (same `mcpServers` shape)

### Option B — HTTP (Docker MCP container)

With `docker compose up`, MCP is already at **http://127.0.0.1:8001/mcp** (Streamable HTTP).

To mount `/mcp` on the monolithic API (local dev without nginx): `MCP_ENABLED=1` + `python -m peche.api`.

**Security:** MCP has no authentication. Do not expose port 8000 to the public internet without a reverse proxy. MCP uses the **server** `GEMINI_API_KEY`, not the browser BYOK key.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Optional server Gemini key |
| `LLM_MODEL` | `gemini-3.5-flash-lite` | Primary model |
| `LLM_MODEL_FALLBACK` | `gemini-3.1-flash-lite` | Fallback |
| `LLM_THINKING_BUDGET` | `1024` | Budget de réflexion du modèle principal (tracé dans Langfuse) |
| `DATA_DIR` | `./data` | Data root |
| `PECHE_HOST` / `PECHE_PORT` | `127.0.0.1` / `8000` | Bind |
| `MCP_ENABLED` | `0` | Mount `/mcp` on the API |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | — | Enables [Langfuse](https://langfuse.com) tracing (see below); disabled without keys |
| `LANGFUSE_BASE_URL` | — | Langfuse URL for a non-Docker run (`http://localhost:3100` for the local stack) |
| `LANGFUSE_PORT` | `3100` | Host port of the local Langfuse UI |
| `LANGFUSE_TRACING_ENVIRONMENT` | — | Separates `development` / `docker` / `production` traces |
| `LANGFUSE_ENABLED` | `1` | Set `0` to disable tracing and keep the keys |

## LLM tracing (local Langfuse)

Every chat turn is traced (LLM calls, tool calls, map/pin context) in a self-hosted
Langfuse started by the same Docker Compose project — nothing leaves your machine.

```bash
cp .env.example .env                       # contains the local Langfuse keys
docker compose up -d --build   # app + Langfuse (web, worker, Postgres, ClickHouse, Redis, MinIO)
```

Open http://localhost:3100 (default login `admin@peche.local` / `peche-local-admin`, project `peche-agent`).
Running the API outside Docker (`python -m peche.api`) works the same: it reads `LANGFUSE_BASE_URL` from `.env`.
Stop everything with `docker compose down` (add `-v` to wipe traces).

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
cd web && npm run build
```

## Data

See [docs/data.md](docs/data.md). Bundled offline data (~130 MB); `data/cache/` is generated at runtime.

## Docs

- [AGENTS.md](AGENTS.md) — agent onboarding (stack, commands, contracts)
- [docs/map-view.md](docs/map-view.md) — map architecture
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)

## License

MIT — see [LICENSE](LICENSE).
