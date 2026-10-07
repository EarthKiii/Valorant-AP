from BaseClasses import Item, ItemClassification

from .data import AGENTS, FILLER_ITEM, GOAL_ITEM, WEAPONS, PRIMARY_CATEGORIES


class ValorantItem(Item):
    game = "Valorant"


ROLE_GROUPS = {"Duelist": "Duelists", "Initiator": "Initiators", "Controller": "Controllers", "Sentinel": "Sentinels"}
CATEGORY_GROUPS = {
    "Sidearm": "Sidearms", "SMG": "SMGs", "Shotgun": "Shotguns", "Rifle": "Rifles", "Sniper": "Snipers",
    "Heavy": "Heavy Weapons",
}

ITEM_GROUPS: dict[str, set[str]] = {
    "Agents": {agent.name for agent in AGENTS},
    "Weapons": {weapon.name for weapon in WEAPONS},
    "Primary Weapons": {weapon.name for weapon in WEAPONS if weapon.category in PRIMARY_CATEGORIES},
    **{group: {a.name for a in AGENTS if a.role == role} for role, group in ROLE_GROUPS.items()},
    **{group: {w.name for w in WEAPONS if w.category == category} for category, group in CATEGORY_GROUPS.items()},
}


def classification_for(name: str, weapons_in_logic: bool) -> ItemClassification:
    if name == GOAL_ITEM:
        return ItemClassification.progression_skip_balancing
    if name == FILLER_ITEM:
        return ItemClassification.filler
    if name in ITEM_GROUPS["Agents"]:
        return ItemClassification.progression
    if name in ITEM_GROUPS["Primary Weapons"] and weapons_in_logic:
        return ItemClassification.progression
    return ItemClassification.useful
