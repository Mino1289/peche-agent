"""Règlements de pêche du Québec : sync offline + accès aux JSON locaux."""

from peche.reglements.zones import ZONES, Zone, zone_by_id
from peche.reglements.sync import (
    DATA_DIR,
    ZONES_DIR,
    CACHE_DIR,
    INDEX_PATH,
    BASE_URL,
    sync_zone,
    build_index,
    write_index,
    zone_json_path,
)

__all__ = [
    "ZONES",
    "Zone",
    "zone_by_id",
    "DATA_DIR",
    "ZONES_DIR",
    "CACHE_DIR",
    "INDEX_PATH",
    "BASE_URL",
    "sync_zone",
    "build_index",
    "write_index",
    "zone_json_path",
]
