#!/bin/sh
set -e

if [ "${MCP_ENABLED:-1}" = "1" ]; then
  python -m peche.mcp --transport http \
    --host "${PECHE_MCP_HOST:-0.0.0.0}" \
    --port "${PECHE_MCP_PORT:-8001}" &
fi

exec python -m peche.ui
