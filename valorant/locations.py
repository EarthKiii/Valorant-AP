from BaseClasses import Location

from .data import AGENT_NAMES, MAX_TIERS, STATS, location_name


class ValorantLocation(Location):
    game = "Valorant"


MULTIKILL_STATS = ("Clutches", "Aces", "3Ks")

LOCATION_GROUPS: dict[str, set[str]] = {
    **{agent: {location_name(agent, stat, tier) for stat in STATS for tier in range(1, MAX_TIERS + 1)}
       for agent in AGENT_NAMES},
    **{stat: {location_name(agent, stat, tier) for agent in AGENT_NAMES for tier in range(1, MAX_TIERS + 1)}
       for stat in STATS},
}


def required_primary_weapons(stat: str, tier: int) -> int:
    """Primary weapons the standard weapon logic expects for a given check."""
    return (1 if stat in MULTIKILL_STATS else 0) + tier - 1
