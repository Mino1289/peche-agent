"""Parse compact zone expressions: ``21,23,25-28`` or ``*``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from peche.reglements.zones import ZONES, display_number, zone_by_id


@dataclass(frozen=True, slots=True)
class ZoneExprAll:
    kind: Literal["all"] = "all"


@dataclass(frozen=True, slots=True)
class ZoneExprList:
    kind: Literal["list"] = "list"
    values: tuple[int, ...] = ()


ZoneExpr = ZoneExprAll | ZoneExprList


def parse_zone_expr(raw: str | None) -> ZoneExpr:
    """Parse ``a,b,d-f`` or ``*``. Empty string → all."""
    if raw is None:
        return ZoneExprAll()
    s = str(raw).strip()
    if not s or s == "*":
        return ZoneExprAll()

    values: set[int] = set()
    for token in (t.strip() for t in s.split(",") if t.strip()):
        if token == "*":
            return ZoneExprAll()
        if "-" in token:
            parts = token.split("-", 1)
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                raise ValueError(f"Plage invalide : {token!r}")
            try:
                a = int(parts[0].strip())
                b = int(parts[1].strip())
            except ValueError as exc:
                raise ValueError(f"Plage invalide : {token!r}") from exc
            lo, hi = min(a, b), max(a, b)
            values.update(range(lo, hi + 1))
        else:
            try:
                values.add(int(token))
            except ValueError as exc:
                raise ValueError(f"Jeton invalide : {token!r}") from exc

    if not values:
        return ZoneExprAll()
    return ZoneExprList(values=tuple(sorted(values)))


def resolve_zone_ids_for_expr(expr: ZoneExpr) -> list[int] | None:
    """Expand display/regpec refs to unique RegPec ``zone_id`` values.

    Returns ``None`` when the expression means « all zones ».
    """
    if isinstance(expr, ZoneExprAll):
        return None
    ids: set[int] = set()
    for n in expr.values:
        by_display = [z for z in ZONES if display_number(z) == n]
        if by_display:
            for z in by_display:
                ids.add(z.value)
            continue
        z = zone_by_id(n)
        if z:
            ids.add(z.value)
    return sorted(ids)


def zone_filter_active(raw: str | None) -> bool:
    """True when a non-empty, non-`*` filter is set."""
    expr = parse_zone_expr(raw)
    return isinstance(expr, ZoneExprList) and bool(expr.values)
