"""Téléchargement de ressources Données Québec (CKAN)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

from peche.fetch import fetch_bytes, fetch_text

CKAN_API = "https://www.donneesquebec.ca/recherche/api/3/action"


def package_show(package_id: str) -> dict[str, Any]:
    url = f"{CKAN_API}/package_show?id={quote(package_id)}"
    payload = json.loads(fetch_text(url))
    if not payload.get("success"):
        raise RuntimeError(f"CKAN package_show failed for {package_id}")
    return payload["result"]


def resource_url(package_id: str, *, format_hint: str = "SQLite") -> str:
    """Retourne l'URL de téléchargement d'une ressource (SQLite par défaut)."""
    pkg = package_show(package_id)
    hint = format_hint.lower()
    for res in pkg.get("resources", []):
        fmt = (res.get("format") or "").lower()
        name = (res.get("name") or "").lower()
        if hint in fmt or hint in name:
            url = res.get("url")
            if url:
                return url
    for res in pkg.get("resources", []):
        url = res.get("url")
        if url:
            return url
    raise RuntimeError(f"Aucune ressource pour {package_id}")


def download_zip_resource(
    package_id: str,
    *,
    format_hint: str = "SQLite",
    cache_path: Path,
    timeout: float = 180.0,
) -> Path:
    """Télécharge une archive zip CKAN et extrait le fichier .sqlite."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    url = resource_url(package_id, format_hint=format_hint)
    data = fetch_bytes(url, timeout=timeout)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        sqlite_names = [n for n in zf.namelist() if n.lower().endswith(".sqlite")]
        if not sqlite_names:
            raise RuntimeError(f"Pas de .sqlite dans l'archive {package_id}")
        name = sqlite_names[0]
        cache_path.write_bytes(zf.read(name))
    return cache_path
