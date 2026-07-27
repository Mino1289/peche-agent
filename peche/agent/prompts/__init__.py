"""Prompts spécialisés par agent."""

from peche.agent.prompts.regulations import REGULATIONS_PROMPT
from peche.agent.prompts.hydro import HYDRO_PROMPT
from peche.agent.prompts.weather import WEATHER_PROMPT
from peche.agent.prompts.fishing import FISHING_PROMPT
from peche.agent.prompts.geomap import GEOMAP_PROMPT
from peche.agent.prompts.synthesize import SYNTHESIZE_PROMPT

AGENT_PROMPTS = {
    "regulations": REGULATIONS_PROMPT,
    "hydro": HYDRO_PROMPT,
    "weather": WEATHER_PROMPT,
    "fishing": FISHING_PROMPT,
    "geomap": GEOMAP_PROMPT,
}
