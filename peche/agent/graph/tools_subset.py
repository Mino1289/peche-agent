"""Sous-ensembles d'outils par agent."""

from __future__ import annotations

AGENT_TOOLS: dict[str, set[str]] = {
    "regulations": {"list_zones", "search_plans", "get_reglements"},
    "hydro": {
        "search_stations",
        "get_hydromet",
        "get_hydromet_for_waterbody",
        "get_hydromet_at_plan",
        "get_water_levels",
        "get_iqbp",
        "search_barrages",
        "get_barrages_at_plan",
        "search_plans",
    },
    "weather": {
        "get_weather",
        "get_weather_at_plan",
        "get_weather_at_place",
        "search_tide_stations",
        "get_tides",
        "get_tides_at_place",
        "get_tides_at_plan",
        "get_water_levels",
        "search_plans",
    },
    "fishing": {"get_fishing_advice", "search_plans", "get_reglements"},
    "geomap": {"search_plans", "get_map_context", "get_reglements"},
}
