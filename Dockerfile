# Stage 1 — build SPA
FROM node:22-alpine AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2 — static SPA + reverse proxy to API
FROM nginx:1.27-alpine AS frontend

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /web/dist /usr/share/nginx/html

EXPOSE 80

# Stage 3 — Python API + MCP (default image for CI / docker run)
FROM python:3.12-slim-bookworm AS backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    PECHE_HOST=0.0.0.0 \
    PECHE_PORT=8000 \
    MCP_ENABLED=0 \
    LLM_MODEL=gemini-3.5-flash-lite \
    LLM_MODEL_FALLBACK=gemini-3.1-flash-lite

RUN chmod +x /app/scripts/docker-entrypoint.sh /app/scripts/docker-entrypoint-mcp.sh

EXPOSE 8000

CMD ["/app/scripts/docker-entrypoint.sh"]
