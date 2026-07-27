"""Tests pour peche.encoding."""

from peche.encoding import _slim_hydro_for_llm, to_toon, wrap_tool_result


def test_slim_hydro_removes_series():
    payload = {
        "station_id": "061001",
        "history": {
            "unit": "m",
            "series": [{"t": "2026-01-01", "v": 100}],
            "source": "test",
        },
    }
    slim = _slim_hydro_for_llm(payload)
    assert "series" not in slim["history"]
    assert slim["history"]["source"] == "test"


def test_slim_hydro_recurses_stations():
    payload = {
        "stations": [
            {
                "station_id": "061001",
                "history": {"series": [1, 2, 3], "meta": "ok"},
            }
        ]
    }
    slim = _slim_hydro_for_llm(payload)
    assert "series" not in slim["stations"][0]["history"]


def test_wrap_tool_result_shape():
    out = wrap_tool_result("search_plans", {"candidates": []})
    assert "toon" in out
    assert isinstance(out["toon"], str)
    assert len(out["toon"]) > 0


def test_wrap_tool_result_slims_hydro():
    out = wrap_tool_result(
        "get_hydromet_for_waterbody",
        {"stations": [{"history": {"series": [1]}}]},
    )
    assert "series" not in out["toon"]


def test_to_toon_returns_string():
    s = to_toon({"a": 1, "b": "test"})
    assert isinstance(s, str)
