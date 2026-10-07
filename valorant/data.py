"""
Static VALORANT data shared by the world and the client.

Item and location IDs are derived from the *position* of agents and weapons in these tuples,
so only ever append new entries to the end - never reorder or remove existing ones.
UUIDs come from https://valorant-api.com and match the IDs Riot uses in match data.
"""
from typing import NamedTuple

BASE_ID = 0x56414C00  # "VAL\0"


class Agent(NamedTuple):
    name: str
    uuid: str
    role: str
    starter: bool  # one of the free agents every account owns


class Weapon(NamedTuple):
    name: str
    uuid: str
    category: str


AGENTS: tuple[Agent, ...] = (
    Agent("Brimstone", "9f0d8ba9-4140-b941-57d3-a7ad57c6b417", "Controller", True),
    Agent("Phoenix", "eb93336a-449b-9c1b-0a54-a891f7921d69", "Duelist", True),
    Agent("Sage", "569fdd95-4d10-43ab-ca70-79becc718b46", "Sentinel", True),
    Agent("Sova", "320b2a48-4d9b-a075-30f1-1f93a9b638fa", "Initiator", True),
    Agent("Jett", "add6443a-41bd-e414-f6ad-e58d267f4e95", "Duelist", True),
    Agent("Viper", "707eab51-4836-f488-046a-cda6bf494859", "Controller", False),
    Agent("Cypher", "117ed9e3-49f3-6512-3ccf-0cada7e3823b", "Sentinel", False),
    Agent("Reyna", "a3bfb853-43b2-7238-a4f1-ad90e9e46bcc", "Duelist", False),
    Agent("Killjoy", "1e58de9c-4950-5125-93e9-a0aee9f98746", "Sentinel", False),
    Agent("Breach", "5f8d3a7f-467b-97f3-062c-13acf203c006", "Initiator", False),
    Agent("Omen", "8e253930-4c05-31dd-1b6c-968525494517", "Controller", False),
    Agent("Raze", "f94c3b30-42be-e959-889c-5aa313dba261", "Duelist", False),
    Agent("Skye", "6f2a04ca-43e0-be17-7f36-b3908627744d", "Initiator", False),
    Agent("Yoru", "7f94d92c-4234-0a36-9646-3a87eb8b5c89", "Duelist", False),
    Agent("Astra", "41fb69c1-4189-7b37-f117-bcaf1e96f1bf", "Controller", False),
    Agent("KAY/O", "601dbbe7-43ce-be57-2a40-4abd24953621", "Initiator", False),
    Agent("Chamber", "22697a3d-45bf-8dd7-4fec-84a9e28c69d7", "Sentinel", False),
    Agent("Neon", "bb2a4828-46eb-8cd1-e765-15848195d751", "Duelist", False),
    Agent("Fade", "dade69b4-4f5a-8528-247b-219e5a1facd6", "Initiator", False),
    Agent("Harbor", "95b78ed7-4637-86d9-7e41-71ba8c293152", "Controller", False),
    Agent("Gekko", "e370fa57-4757-3604-3648-499e1f642d3f", "Initiator", False),
    Agent("Deadlock", "cc8b64c8-4b25-4ff9-6e7f-37b4da43d235", "Sentinel", False),
    Agent("Iso", "0e38b510-41a8-5780-5e8f-568b2a4f2d6c", "Duelist", False),
    Agent("Clove", "1dbf2edd-4729-0984-3115-daa5eed44993", "Controller", False),
    Agent("Vyse", "efba5359-4016-a1e5-7626-b1ae76895940", "Sentinel", False),
    Agent("Tejo", "b444168c-4e35-8076-db47-ef9bf368f384", "Initiator", False),
    Agent("Waylay", "df1cb487-4902-002e-5c17-d28e83e78588", "Duelist", False),
    Agent("Veto", "92eeef5d-43b5-1d4a-8d03-b3927a09034b", "Sentinel", False),
    Agent("Miks", "7c8a4701-4de6-9355-b254-e09bc2a34b72", "Controller", False),
)

# The Classic and the knife are always available and are therefore not items.
WEAPONS: tuple[Weapon, ...] = (
    Weapon("Shorty", "42da8ccc-40d5-affc-beec-15aa47b42eda", "Sidearm"),
    Weapon("Frenzy", "44d4e95c-4157-0037-81b2-17841bf2e8e3", "Sidearm"),
    Weapon("Ghost", "1baa85b4-4c70-1284-64bb-6481dfc3bb4e", "Sidearm"),
    Weapon("Bandit", "410b2e0b-4ceb-1321-1727-20858f7f3477", "Sidearm"),
    Weapon("Sheriff", "e336c6b8-418d-9340-d77f-7a9e4cfe0702", "Sidearm"),
    Weapon("Stinger", "f7e1b454-4ad4-1063-ec0a-159e56b58941", "SMG"),
    Weapon("Spectre", "462080d1-4035-2937-7c09-27aa2a5c27a7", "SMG"),
    Weapon("Bucky", "910be174-449b-c412-ab22-d0873436b21b", "Shotgun"),
    Weapon("Judge", "ec845bf4-4f79-ddda-a3da-0db3774b2794", "Shotgun"),
    Weapon("Bulldog", "ae3de142-4d85-2547-dd26-4e90bed35cf7", "Rifle"),
    Weapon("Guardian", "4ade7faa-4cf1-8376-95ef-39884480959b", "Rifle"),
    Weapon("Phantom", "ee8e8d15-496b-07ac-e5f6-8fae5d4c7b1a", "Rifle"),
    Weapon("Vandal", "9c82e19d-4575-0200-1a81-3eacf00cf872", "Rifle"),
    Weapon("Warden", "8db0a1bf-4a50-832a-4566-faaaa6d250ca", "Rifle"),
    Weapon("Marshal", "c4883e50-4494-202c-3ec3-6b8a9284f00b", "Sniper"),
    Weapon("Outlaw", "5f0aaf7a-4289-3998-d5ff-eb9a5cf7ef5c", "Sniper"),
    Weapon("Operator", "a03b24d3-4319-996d-0f8c-94bbfba1dfc7", "Sniper"),
    Weapon("Ares", "55d8a0f4-4274-ca67-fe2c-06ab45efdf58", "Heavy"),
    Weapon("Odin", "63e6c2b6-4a8e-869c-3d4c-e38355226584", "Heavy"),
)

CLASSIC = Weapon("Classic", "29a0cfab-485b-f5d5-779a-b59f85e204a8", "Sidearm")  # always available, never an item

PRIMARY_CATEGORIES = ("SMG", "Shotgun", "Rifle", "Sniper", "Heavy")
WEAPON_CATEGORIES = ("Sidearm", *PRIMARY_CATEGORIES)
# Kingdom Credits it costs to rent a weapon for one match, by weapon type (Rental Prices option).
DEFAULT_RENTAL_PRICES = {"Sidearm": 2, "SMG": 3, "Shotgun": 3, "Rifle": 5, "Sniper": 5, "Heavy": 4}

AGENT_NAMES: tuple[str, ...] = tuple(agent.name for agent in AGENTS)
WEAPON_NAMES: tuple[str, ...] = tuple(weapon.name for weapon in WEAPONS)
PRIMARY_WEAPON_NAMES: tuple[str, ...] = tuple(w.name for w in WEAPONS if w.category in PRIMARY_CATEGORIES)

AGENT_BY_NAME = {agent.name: agent for agent in AGENTS}
AGENT_BY_UUID = {agent.uuid: agent for agent in AGENTS}
WEAPON_BY_NAME = {weapon.name: weapon for weapon in WEAPONS}
WEAPON_BY_UUID = {weapon.uuid: weapon for weapon in WEAPONS}

# Stats tracked per agent. The order is part of the location ID scheme (append only; 10 stats fill an agent's IDs).
STATS: tuple[str, ...] = (
    "Kills", "Assists", "Trades", "Clutches", "Aces", "3Ks", "K/D", "Wins", "ACS", "Performance",
)
# VALORANT stopped showing ACS in patch 13.06 (Performance Score replaced it). New worlds have no ACS checks; the
# client still tracks it for worlds generated before.
LEGACY_STATS = ("ACS",)
OPTION_STATS = tuple(stat for stat in STATS if stat not in LEGACY_STATS)
MAX_TIERS = 10

# Name of the field in a match record that feeds each stat.
STAT_FIELDS = {
    "Kills": "kills",
    "Assists": "assists",
    "Trades": "trades",
    "Clutches": "clutches",
    "Aces": "aces",
    "3Ks": "three_ks",
    "K/D": "kd",
    "Wins": "wins",
    "ACS": "acs",
    "Performance": "performance",
}

GOAL_ITEM = "Radianite Crystal"
FILLER_ITEM = "Kingdom Credits"

ITEM_IDS: dict[str, int] = {
    **{agent.name: BASE_ID + index for index, agent in enumerate(AGENTS)},
    **{weapon.name: BASE_ID + 100 + index for index, weapon in enumerate(WEAPONS)},
    GOAL_ITEM: BASE_ID + 200,
    FILLER_ITEM: BASE_ID + 201,
}


def location_name(agent: str, stat: str, tier: int) -> str:
    return f"{agent} - {stat} Tier {tier}"


def location_id(agent: str, stat: str, tier: int) -> int:
    return BASE_ID + 1000 + AGENT_NAMES.index(agent) * 100 + STATS.index(stat) * 10 + (tier - 1)


LOCATION_IDS: dict[str, int] = {
    location_name(agent, stat, tier): location_id(agent, stat, tier)
    for agent in AGENT_NAMES
    for stat in STATS
    for tier in range(1, MAX_TIERS + 1)
}
LOCATION_KEYS: dict[int, tuple[str, str, int]] = {
    location_id(agent, stat, tier): (agent, stat, tier)
    for agent in AGENT_NAMES
    for stat in STATS
    for tier in range(1, MAX_TIERS + 1)
}

# Queue options: display name -> predicate on Riot's queue ID.
QUEUES: dict[str, str] = {
    "Competitive": "competitive",
    "Unrated": "unrated",
    "Swiftplay": "swiftplay",
    "Spike Rush": "spikerush",
    "Premier": "premier",
    "Deathmatch": "deathmatch",
    "Team Deathmatch": "hurm",
    "Escalation": "ggteam",
    "Replication": "onefa",
    "Skirmish": "skirmish",
    "Custom Games": "",
}
OTHER_QUEUES = "Other Modes"


def queue_display_name(queue_id: str) -> str:
    queue_id = (queue_id or "").lower()
    for display, riot_id in QUEUES.items():
        # Some queue IDs carry suffixes ("premier-seasonmatch", "skirmish2v2").
        if queue_id == riot_id or (riot_id and queue_id.startswith(riot_id)):
            return display
    return OTHER_QUEUES


# Short modes, whose Kill, Assist and Trade thresholds the Short Mode Thresholds option can lower.
SHORT_MODE_QUEUES = ("Swiftplay", "Spike Rush")
SHORT_MODE_STATS = ("Kills", "Assists", "Trades")


def short_mode_thresholds(thresholds: list[int], percent: int) -> list[int]:
    """`percent`% of each threshold, rounded up."""
    return [-(-threshold * percent // 100) for threshold in thresholds]


def short_mode_weight(percent: int) -> str:
    """How much one kill, assist or trade in a short mode counts towards the regular thresholds, e.g. "×1.33"."""
    return f"×{100 / percent:.2f}".rstrip("0").rstrip(".")


def describe_short_modes(short_modes: dict) -> str:
    """The lowered thresholds in one line, e.g. for the spoiler log and the client."""
    stats = list(short_modes["thresholds"])
    tiers = ", ".join(f"{stat} {' / '.join(map(str, values))}" for stat, values in short_modes["thresholds"].items())
    nouns = [stat[:-1].lower() for stat in stats]
    each = ", ".join(nouns[:-1]) + " or " + nouns[-1] if len(nouns) > 1 else nouns[0]
    return (f"{' & '.join(short_modes['queues'])} need {short_modes['percent']}% of the regular thresholds: {tiers} "
            f"(each {each} there counts {short_mode_weight(short_modes['percent'])})")


MAP_NAMES = {
    "Ascent": "Ascent", "Bonsai": "Split", "Canyon": "Fracture", "Duality": "Bind", "Foxtrot": "Breeze",
    "Infinity": "Abyss", "Jam": "Lotus", "Juliett": "Sunset", "Pitt": "Pearl", "Plummet": "Summit",
    "Port": "Icebox", "Rook": "Corrode", "Triad": "Haven", "HURM_Alley": "District", "HURM_Bowl": "Kasbah",
    "HURM_Helix": "Drift", "HURM_HighTide": "Glitch", "HURM_Yard": "Piazza", "Range": "The Range",
    "RangeV2": "The Range",
    "AbilityDraft": "Gauntlet", "Skirmish_A": "Skirmish A", "Skirmish_B": "Skirmish B", "Skirmish_C": "Skirmish C",
    "Skirmish_D": "Skirmish D", "Skirmish_E": "Skirmish E",
}


def map_display_name(map_path: str) -> str:
    """'/Game/Maps/Bonsai/Bonsai' -> 'Split'."""
    key = (map_path or "").rstrip("/").rsplit("/", 1)[-1]
    return MAP_NAMES.get(key, key or "Unknown map")


# --- Companion app (Overwolf GEP) identifiers --------------------------------------------------------------

# Agent codenames as reported by the live feed ("Wushu_PC_C" -> Jett).
AGENT_CODENAMES = {
    "Sarge": "Brimstone", "Phoenix": "Phoenix", "Thorne": "Sage", "Hunter": "Sova", "Wushu": "Jett",
    "Pandemic": "Viper", "Gumshoe": "Cypher", "Vampire": "Reyna", "Killjoy": "Killjoy", "Breach": "Breach",
    "Wraith": "Omen", "Clay": "Raze", "Guide": "Skye", "Stealth": "Yoru", "Rift": "Astra", "Grenadier": "KAY/O",
    "Deadeye": "Chamber", "Sprinter": "Neon", "BountyHunter": "Fade", "Mage": "Harbor", "Aggrobot": "Gekko",
    "Cable": "Deadlock", "Sequoia": "Iso", "Smonk": "Clove", "Nox": "Vyse", "Cashew": "Tejo", "Terra": "Waylay",
    "Pine": "Veto", "Iris": "Miks",
}

# Kill-feed weapon IDs. Anything not listed (abilities, newer guns) is treated as allowed during the match;
# the official match data, which uses UUIDs, settles it afterwards.
LIVE_WEAPON_IDS = {
    "TX_Hud_Pistol_Glock_S": "Classic", "TX_Hud_Pistol_SawedOff_S": "Shorty", "TX_Hud_AutoPistol": "Frenzy",
    "TX_Hud_Pistol_Luger_S": "Ghost", "TX_Hud_Pistol_Revolver_S": "Sheriff", "TX_Hud_Pump": "Bucky",
    "TX_Hud_Shotguns_Spas12_S": "Judge", "TX_Hud_Vector": "Stinger", "TX_Hud_SMG_MP5_S": "Spectre",
    "TX_Hud_Burst": "Bulldog", "TX_Hud_DMR": "Guardian", "TX_Hud_Assault_AR10A2_S": "Phantom",
    "TX_Hud_Volcano": "Vandal", "TX_Hud_Sniper_BoltAction_S": "Marshal", "TX_Hud_Operator": "Operator",
    "TX_Hud_DoubleSniper": "Outlaw", "TX_Hud_LMG": "Ares", "TX_Hud_HMG": "Odin", "TX_Hud_Knife_Standard_S": "Knife",
}
