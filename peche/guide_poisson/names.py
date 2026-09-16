"""Désinversion toponymique CKAN : « X, Y » → « Y X »."""

from __future__ import annotations


def uninvert_hydronyme(raw: str) -> str:
    s = (raw or "").strip()
    idx = s.rfind(",")
    if idx < 0:
        return s
    head = s[:idx].strip()
    tail = s[idx + 1 :].strip()
    if not head or not tail:
        return s
    return f"{tail} {head}"
