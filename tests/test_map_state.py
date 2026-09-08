"""Tests MapState / map_tools."""

from peche.agent import map_tools
from peche.agent.schemas import TOOLS


def test_map_tools_registered():
    for name in (
        "set_map_view",
        "toggle_layers",
        "set_layer_filter",
        "filter_by_zone",
        "highlight_features",
    ):
        assert name in TOOLS
    assert "save_map_preset" not in TOOLS


def test_map_actions_emit_and_drain():
    map_tools.clear_map_actions()
    r = map_tools.set_map_view(center=[-71.2, 46.8], zoom=10)
    assert r["ok"] is True
    r2 = map_tools.toggle_layers(show=["lidar_pentes"], hide=["grhq_flow"])
    assert r2["ok"] is True
    r3 = map_tools.filter_by_zone(zone_id=19)
    assert r3["ok"] is True
    actions = map_tools.drain_map_actions()
    assert len(actions) == 3
    assert actions[0]["action"] == "set_view"
    assert actions[1]["action"] == "toggle_layers"
    assert actions[2]["action"] == "filter_by_zone"
    assert map_tools.drain_map_actions() == []


def test_set_layer_filter_colorkey():
    map_tools.clear_map_actions()
    r = map_tools.set_layer_filter("zones_chasse", {"No_zone": "28"})
    assert r["ok"]
    actions = map_tools.drain_map_actions()
    assert actions[0]["filters"]["No_zone"] == "28"


def test_append_exchange_with_map_state(tmp_db):
    cid = tmp_db.create_conversation()
    state = {
        "center": [-71.0, 46.8],
        "zoom": 9,
        "bbox": [-72, 46, -70, 48],
        "basemap": "fond_quebec",
        "layers": [],
        "zoneFilter": {"zoneId": 19},
        "pins": [{"id": "p1", "lon": -71.2, "lat": 46.8, "label": "Quai", "source": "user"}],
    }
    tmp_db.append_exchange(
        cid,
        "Montre la zone 18",
        "Voici la zone.",
        tools_log=[{"name": "filter_by_zone", "args": {"zone_id": 19}}],
        map_state=state,
        user_map_state={"center": [-71.0, 46.8], "zoom": 6, "bbox": [0, 0, 1, 1], "basemap": "fond_quebec", "layers": []},
    )
    msgs = tmp_db.load_messages(cid)
    assert msgs[0]["map_state"]["zoom"] == 6
    assert msgs[1]["map_state"]["zoneFilter"]["zoneId"] == 19
    assert msgs[1]["map_state"]["pins"][0]["label"] == "Quai"
