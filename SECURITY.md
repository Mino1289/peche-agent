# Security

## Reporting

Please open a GitHub issue (or contact the maintainer privately for sensitive reports).

## Secrets

- Never commit `.env` or API keys.
- BYOK keys are stored in the user's browser only; the server does not persist client keys in SQLite.
- Do not log `X-Gemini-Api-Key` headers.

## Deployment

- The API has **no authentication**. Intended for local / trusted networks.
- **MCP** (`/mcp` when `MCP_ENABLED=1`) executes 26 tools with server credentials — keep it on localhost.
- Do not expose port 8000 to the public internet without a reverse proxy and access controls.

## Data

- `data/conversations.db` may contain chat history — gitignored; mount `data/runtime/` as a Docker volume.
