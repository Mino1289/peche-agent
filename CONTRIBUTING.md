# Contributing

Thanks for your interest in peche-agent!

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
cp .env.example .env
```

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
cd web && npm run build
```

## Pull requests

- Keep changes focused; include tests when touching Python logic.
- Run `pytest` and `npm run build` before opening a PR.
- Do not commit `.env`, `data/cache/`, or `data/runtime/`.

For domain context (Quebec fishing regulations, data sources), see [README.fr.md](README.fr.md).
