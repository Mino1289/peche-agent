"""Entrypoint API : python3 -m peche.api"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("PECHE_HOST", "127.0.0.1")
    port = int(os.environ.get("PECHE_PORT", "8000"))
    uvicorn.run("peche.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
