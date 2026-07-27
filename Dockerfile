FROM python:3.12-slim-bookworm

# toon-format est installé depuis git
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PECHE_HOST=0.0.0.0 \
    PECHE_PORT=8000 \
    PECHE_MCP_HOST=0.0.0.0 \
    PECHE_MCP_PORT=8001 \
    MCP_ENABLED=1

RUN chmod +x /app/scripts/docker-entrypoint.sh

EXPOSE 8000 8001

CMD ["/app/scripts/docker-entrypoint.sh"]