#!/bin/sh
set -e

cd /app
export DATA_DIR="${DATA_DIR:-/app/data}"

exec python -m peche.api
