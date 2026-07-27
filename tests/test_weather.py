"""Tests pour peche.weather."""

import json
from pathlib import Path

from peche import weather

FIXTURES = Path(__file__).parent / "fixtures"


def test_cache_key_rounding():
    k1 = weather._cache_key(48.428, -71.068)
    k2 = weather._cache_key(48.421, -71.061)
    assert k1 == k2


def test_parse_feature(fixtures_dir):
    feature = json.loads(
        (fixtures_dir / "geom_et_feature.json").read_text(encoding="utf-8")
    )
    out = weather._parse_feature(feature, 48.43, -71.07)
    assert out["ville"] == "Chicoutimi"
    assert float(out["temperature_c"]) == 18.5
    assert out["distance_km"] is not None


def test_get_weather_cache_hit(monkeypatch, fixtures_dir):
    feature = json.loads(
        (fixtures_dir / "geom_et_feature.json").read_text(encoding="utf-8")
    )
    payload = {"type": "FeatureCollection", "features": [feature]}

    call_count = 0

    def fake_fetch(url, **kwargs):
        nonlocal call_count
        call_count += 1
        return json.dumps(payload)

    monkeypatch.setattr(weather, "fetch_text", fake_fetch)
    weather._CACHE.clear()

    r1 = weather.get_weather(48.43, -71.07)
    r2 = weather.get_weather(48.43, -71.07)
    assert call_count == 1
    assert r2.get("_cache") == "hit"
    assert r1["temperature_c"] == r2["temperature_c"]
