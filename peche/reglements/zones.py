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


def display_number(zone: Zone) -> int | None:
    """Numéro affiché (« Zone 28 » → 28), distinct du zone_id RegPec (32)."""
    import re

    m = re.search(r"Zone\s+(\d+)", zone.text)
    return int(m.group(1)) if m else None


def resolve_zone_by_kind(ref: int | str, *, id_kind: str = "auto") -> Zone | None:
    """Résout une référence zone selon le contexte d'appel.

    - ``auto`` (défaut) : numéro affiché prioritaire, sinon id RegPec.
    - ``regpec`` : id RegPec interne uniquement (clic carte, feature).
    - ``display`` : numéro affiché uniquement (filtres utilisateur).
    """
    try:
        n = int(str(ref).strip())
    except (TypeError, ValueError):
        return None

    if id_kind == "regpec":
        return zone_by_id(n)
    if id_kind == "display":
        by_display = [z for z in ZONES if display_number(z) == n]
        if len(by_display) == 1:
            return by_display[0]
        if len(by_display) > 1:
            plain = [
                z
                for z in by_display
                if display_number(z) == n
                and "partie" not in z.text.lower()
                and "nord" not in z.text.lower()
                and "sud" not in z.text.lower()
                and "est" not in z.text.lower()
                and "ouest" not in z.text.lower()
            ]
            return plain[0] if plain else by_display[0]
        return None
    return resolve_zone_ref(n)


def resolve_zone_ref(ref: int | str) -> Zone | None:
    """Résout un numéro utilisateur vers une Zone RegPec.

    Accepte le numéro affiché (28 → Zone 28 / id=32) **ou** l'id RegPec
    interne (32). En cas d'ambiguïté (ex. 1 = affichage et id), retourne
    la zone dont le numéro affiché correspond, sinon celle dont l'id match.
    """
    try:
        n = int(str(ref).strip())
    except (TypeError, ValueError):
        return None

    by_display = [z for z in ZONES if display_number(z) == n]
    if len(by_display) == 1:
        return by_display[0]
    if len(by_display) > 1:
        # Plusieurs parties (ex. 19 nord/sud) — renvoyer la première ; l'UI
        # devra préciser. Préférer celle sans partie si possible.
        plain = [z for z in by_display if display_number(z) == n and "partie" not in z.text.lower() and "nord" not in z.text.lower() and "sud" not in z.text.lower() and "est" not in z.text.lower() and "ouest" not in z.text.lower()]
        return plain[0] if plain else by_display[0]

    return zone_by_id(n)
