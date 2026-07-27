"""Catalogue des 34 zones de pêche du Québec.

Les valeurs `value` correspondent aux IDs utilisés par RegPec dans l'URL
`?id_zone=...`. Quelques zones ont des IDs non séquentiels (19 nord/sud A/B).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Zone:
    value: int
    text: str


ZONES: list[Zone] = [
    Zone(1, "Zone 1"),
    Zone(2, "Zone 2"),
    Zone(3, "Zone 3"),
    Zone(4, "Zone 4"),
    Zone(5, "Zone 5"),
    Zone(6, "Zone 6"),
    Zone(7, "Zone 7"),
    Zone(8, "Zone 8"),
    Zone(9, "Zone 9"),
    Zone(10, "Zone 10"),
    Zone(11, "Zone 11"),
    Zone(12, "Zone 12"),
    Zone(13, "Zone 13 est"),
    Zone(14, "Zone 13 ouest"),
    Zone(15, "Zone 14"),
    Zone(16, "Zone 15"),
    Zone(17, "Zone 16"),
    Zone(18, "Zone 17"),
    Zone(19, "Zone 18"),
    Zone(3063, "Zone 19 nord"),
    Zone(2652, "Zone 19 sud - partie A"),
    Zone(2653, "Zone 19 sud - partie B"),
    Zone(22, "Zone 20"),
    Zone(23, "Zone 21"),
    Zone(24, "Zone 22 nord"),
    Zone(25, "Zone 22 sud"),
    Zone(26, "Zone 23 nord"),
    Zone(27, "Zone 23 sud"),
    Zone(28, "Zone 24"),
    Zone(29, "Zone 25"),
    Zone(30, "Zone 26"),
    Zone(31, "Zone 27"),
    Zone(32, "Zone 28"),
    Zone(33, "Zone 29"),
]


def zone_by_id(zone_id: int) -> Zone | None:
    for zone in ZONES:
        if zone.value == zone_id:
            return zone
    return None
