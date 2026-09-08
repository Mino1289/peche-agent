# peche-agent

Carte interactive et assistant conversationnel pour la pêche sportive au Québec.

Carte OpenLayers (UI principale) + chat Gemini pour règlements, météo, hydrométrie, marées et pilotage de la carte. Données RegPec hors ligne incluses ; couches OGC publiques du Québec.

**English:** [README.md](README.md)

## Démarrage rapide (Docker)

```bash
git clone https://github.com/VOTRE_USER/peche-agent.git
cd peche-agent
cp .env.example .env   # optionnel : GEMINI_API_KEY côté serveur

docker compose up --build
```

Ouvrir **http://127.0.0.1:8000**

### Clé personnelle (BYOK)

Si `GEMINI_API_KEY` n'est pas définie sur le serveur, ouvrez **Assistant → Paramètres** et collez une clé gratuite [Google AI Studio](https://aistudio.google.com/app/apikey). Elle reste dans votre navigateur.

## Fonctionnalités

| Couche | Techno |
|--------|--------|
| Front | Vite + TypeScript + OpenLayers |
| API | FastAPI + SSE |
| Agent | Gemini `3.5-flash-lite` (+ repli `3.1-flash-lite`) |
| Données | RegPec offline + OGC QC + SQLite |

- Catalogue hybride (~30 couches curées + GetCapabilities)
- Clip zone RegPec, filtre pente LiDAR, points utilisateur partagés avec le chat
- Sync chat ↔ carte (`MapState` + `map_action` SSE)
- UI : français par défaut, bascule EN (FR \| EN)
- 26 outils agent (+ MCP)

## Développement local

```bash
uv pip install --python .venv/bin/python -r requirements.txt
cd web && npm install && npm run build && cd ..
cp .env.example .env

.venv/bin/python -m peche.api
cd web && npm run dev
```

Données dérivées :

```bash
./scripts/refresh-data.sh
```

## MCP (Cursor, Claude Desktop, agents custom)

### Option A — stdio (recommandé)

```json
{
  "mcpServers": {
    "peche-agent": {
      "command": "/CHEMIN/.venv/bin/python",
      "args": ["-m", "peche.mcp"],
      "env": {
        "GEMINI_API_KEY": "AIza...",
        "DATA_DIR": "/CHEMIN/peche-agent/data"
      }
    }
  }
}
```

- **Cursor :** `.cursor/mcp.json`
- **Claude Desktop :** `claude_desktop_config.json`

### Option B — HTTP sur le même port que l'UI

```bash
MCP_ENABLED=1 docker compose up
```

URL : **http://127.0.0.1:8000/mcp**

**Sécurité :** le MCP n'a pas d'authentification. Ne pas exposer le port 8000 sur Internet sans reverse-proxy. Le MCP utilise la clé **serveur**, pas le BYOK navigateur.

## Variables d'environnement

Voir [README.md](README.md) (tableau EN).

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

## Données

Voir [docs/data.md](docs/data.md).

## Licence

MIT — voir [LICENSE](LICENSE).
