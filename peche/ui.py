"""`python3 -m peche.ui` — lance Streamlit sur l'app de chat."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from streamlit.web import cli as stcli


def main() -> int:
    app = Path(__file__).with_name("streamlit_app.py")
    host = os.environ.get("PECHE_HOST", "127.0.0.1")
    port = os.environ.get("PECHE_PORT", "8501")
    sys.argv = [
        "streamlit",
        "run",
        str(app),
        "--server.address",
        host,
        "--server.port",
        port,
        "--browser.gatherUsageStats",
        "false",
    ]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
