"""Tests routeur multi-agents."""

from peche.agent.graph.router import route_heuristic, select_agents


def test_route_hydro_simple():
    agents, confident = route_heuristic("Quel est le niveau du Lac Kénogami ?")
    assert "hydro" in agents
    assert confident is True


def test_route_reg_simple():
    agents, confident = route_heuristic("Puis-je pêcher la truite au Lac au Saumon ?")
    assert "regulations" in agents


def test_select_agents_returns_list():
    agents, _ = select_agents("météo à Chicoutimi demain")
    assert isinstance(agents, list)
    assert len(agents) >= 1
