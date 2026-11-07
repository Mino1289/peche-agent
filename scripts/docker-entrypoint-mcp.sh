#!/bin/sh
set -e

cd /app
export DATA_DIR="${DATA_DIR:-/app/data}"

exec python -m peche.mcp --transport http --host 0.0.0.0 --port "${PECHE_MCP_PORT:-8001}"
