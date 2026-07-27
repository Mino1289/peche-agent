"""Parsing des périodes de règlements en français.

Les libellés RegPec ressemblent à :
    "Période Du 1 er avril 2026 au 31 mars 2027"
    "Période Du 15 mai 2026 au 10 septembre 2026 - Autres espèces"
    "Du 20 décembre 2026 au 31 mars 2027"

On extrait `(start: date, end: date)` et on expose `period_includes(text, day)`
pour filtrer les règlements en vigueur à une date donnée.

Si une période n'est pas parsable (cas rare), on considère qu'elle peut
s'appliquer (`True`) plutôt que de la masquer silencieusement — l'agent peut
toujours mentionner la chaîne brute si nécessaire.
"""

from __future__ import annotations

import re
from datetime import date

MONTHS_FR: dict[str, int] = {
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
}

_MONTH_GROUP = "|".join(sorted(MONTHS_FR.keys(), key=len, reverse=True))
_PERIOD_RE = re.compile(
    rf"""
    [Dd]u\s+
    (?P<d1>\d{{1,2}})\s*(?:er|ère|ème|e)?\s+
    (?P<m1>{_MONTH_GROUP})\s+
    (?P<y1>\d{{4}})\s+
    au\s+
    (?P<d2>\d{{1,2}})\s*(?:er|ère|ème|e)?\s+
    (?P<m2>{_MONTH_GROUP})\s+
    (?P<y2>\d{{4}})
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_period_range(text: str) -> tuple[date, date] | None:
    """Extrait `(start, end)` depuis une chaîne de période FR, ou None."""
    if not text:
        return None
    m = _PERIOD_RE.search(text)
    if not m:
        return None
    try:
        start = date(int(m["y1"]), MONTHS_FR[m["m1"].lower()], int(m["d1"]))
        end = date(int(m["y2"]), MONTHS_FR[m["m2"].lower()], int(m["d2"]))
    except (ValueError, KeyError):
        return None
    return start, end


def period_includes(text: str, day: date) -> bool:
    """`True` si `day` tombe dans la période, ou si la période n'est pas parsable."""
    rng = parse_period_range(text)
    if rng is None:
        return True
    start, end = rng
    return start <= day <= end


def today() -> date:
    """`date.today()` exposée pour permettre le mock dans les tests."""
    return date.today()
