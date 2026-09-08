# Stage 1 — build SPA
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2 — Python API + static SPA
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=web /web/dist /app/web/dist

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    PECHE_HOST=0.0.0.0 \
    PECHE_PORT=8000 \
    MCP_ENABLED=0 \
    LLM_MODEL=gemini-3.5-flash-lite \
    LLM_MODEL_FALLBACK=gemini-3.1-flash-lite

RUN chmod +x /app/scripts/docker-entrypoint.sh

EXPOSE 8000

CMD ["/app/scripts/docker-entrypoint.sh"]
