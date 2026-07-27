"""Tests pour peche.geocoding."""

import json
from pathlib import Path

from peche import geocoding

FIXTURES = Path(__file__).parent / "fixtures"


def test_geocode_empty():
    assert geocoding.geocode("") == []
    assert geocoding.geocode("   ") == []


def test_geocode_parse_and_cache(monkeypatch, fixtures_dir):
    raw = (fixtures_dir / "nominatim_chicoutimi.json").read_text(encoding="utf-8")
    calls = []

    def fake_fetch(url, **kwargs):
        calls.append(url)
        return raw

    monkeypatch.setattr(geocoding, "fetch_text", fake_fetch)
    geocoding._CACHE.clear()

    hits = geocoding.geocode("Chicoutimi")
    assert len(hits) == 1
    assert hits[0]["display_name"].startswith("Chicoutimi")
    assert abs(hits[0]["lat"] - 48.428) < 0.01

    hits2 = geocoding.geocode("Chicoutimi")
    assert len(calls) == 1
    assert hits2 == hits
