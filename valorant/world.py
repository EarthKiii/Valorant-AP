import logging
import math
from collections.abc import Mapping
from typing import Any, TextIO

from BaseClasses import ItemClassification, LocationProgressType, Region
from Options import OptionError
from worlds.AutoWorld import World

from .data import (
    AGENT_NAMES,
    FILLER_ITEM,
    GOAL_ITEM,
    ITEM_IDS,
    LOCATION_IDS,
    PRIMARY_WEAPON_NAMES,
    SHORT_MODE_QUEUES,
    SHORT_MODE_STATS,
    STATS,
    WEAPON_NAMES,
    describe_short_modes,
    location_name,
    short_mode_thresholds,
)
from .items import ITEM_GROUPS, ValorantItem, classification_for
from .locations import LOCATION_GROUPS, MULTIKILL_STATS, ValorantLocation, required_primary_weapons
from .options import (
    ValorantOptions,
    WeaponEnforcement,
    WeaponLogic,
    clean_rental_prices,
    clean_thresholds,
    threshold_options,
)
from .web_world import ValorantWebWorld

VICTORY_LOCATION = "Reach Radiant"
VICTORY_EVENT = "Radiant"
SLOT_DATA_VERSION = 1

logger = logging.getLogger("Valorant")


class ValorantWorld(World):
    """
    VALORANT is Riot Games' 5v5 tactical shooter. Agents and weapons are scattered across the multiworld,
    and every kill, assist, trade, clutch, ace, 3K, K/D and Performance Score milestone you reach with an agent in
    real matches sends a check.
    """

    game = "Valorant"
    web = ValorantWebWorld()

    options_dataclass = ValorantOptions
    options: ValorantOptions

    item_name_to_id = ITEM_IDS
    location_name_to_id = LOCATION_IDS
    item_name_groups = ITEM_GROUPS
    location_name_groups = LOCATION_GROUPS

    origin_region_name = "Lobby"

    agents: list[str]
    weapons: list[str]
    starting_items: list[str]
    thresholds: dict[str, list[int | float]]
    short_modes: dict[str, Any] | None
    shop: dict[str, Any] | None
    radianite_total: int
    radianite_required: int

    @property
    def weapons_in_logic(self) -> bool:
        return bool(self.options.weapon_unlocks) and self.options.weapon_logic == WeaponLogic.option_standard

    def generate_early(self) -> None:
        self.thresholds = {stat: [] for stat in STATS}  # legacy stats (ACS) have no option and no checks
        self.thresholds.update({
            stat: clean_thresholds(option, self.player_name)
            for stat, option in threshold_options(self.options).items()
        })
        if not any(self.thresholds.values()):
            raise OptionError(f"{self.player_name}: every threshold list is empty, so there would be no checks.")
        self.short_modes = self.lowered_short_mode_thresholds()
        prices = clean_rental_prices(self.options.rental_prices, self.player_name)
        shop_matters = (self.options.weapon_shop and self.options.weapon_unlocks
                        and self.options.weapon_enforcement != WeaponEnforcement.option_off)
        self.shop = {"prices": prices} if shop_matters else None

        # Agents handed out through Start Inventory are always part of the world and count as starting agents.
        granted = set(self.options.start_inventory.value) | set(self.options.start_inventory_from_pool.value)
        forced = [agent for agent in AGENT_NAMES if agent in granted]
        candidates = [agent for agent in AGENT_NAMES if agent in self.options.agent_pool.value and agent not in forced]
        if not candidates and not forced:
            raise OptionError(f"{self.player_name}: the Agent Pool is empty.")
        self.random.shuffle(candidates)
        extra = max(0, self.options.agent_count.value - len(forced))
        chosen = set(forced) | set(candidates[:extra])
        self.agents = [agent for agent in AGENT_NAMES if agent in chosen]

        startable = [agent for agent in self.agents if agent not in granted]
        wanted = max(0, min(self.options.starting_agents.value, len(self.agents)) - len(forced))
        self.starting_items = self.random.sample(startable, k=min(wanted, len(startable)))

        self.weapons = list(WEAPON_NAMES) if self.options.weapon_unlocks else []
        if self.weapons:
            granted_primaries = [weapon for weapon in PRIMARY_WEAPON_NAMES if weapon in granted]
            wanted = self.options.starting_weapons.value - len(granted_primaries)
            # With weapon logic on and no weapon-free checks, nothing would be reachable without a starting gun.
            weapon_free_checks = any(self.thresholds[stat] for stat in STATS if stat not in MULTIKILL_STATS)
            if self.weapons_in_logic and not weapon_free_checks and not granted_primaries:
                wanted = max(wanted, 1)
            startable = [weapon for weapon in PRIMARY_WEAPON_NAMES if weapon not in granted]
            self.starting_items += self.random.sample(startable, k=max(0, min(wanted, len(startable))))

    def lowered_short_mode_thresholds(self) -> dict[str, Any] | None:
        """The Short Mode Thresholds option's lowered Kill/Assist/Trade thresholds, or None when it's off."""
        percent = self.options.short_mode_thresholds.value
        queues = [queue for queue in SHORT_MODE_QUEUES if queue in self.options.allowed_queues.value]
        thresholds = {stat: short_mode_thresholds(self.thresholds[stat], percent)
                      for stat in SHORT_MODE_STATS if self.thresholds[stat]}
        if percent >= 100 or not queues or not thresholds:
            return None
        return {"percent": percent, "queues": queues, "thresholds": thresholds}

    def create_regions(self) -> None:
        lobby = Region(self.origin_region_name, self.player, self.multiworld)
        self.multiworld.regions.append(lobby)

        excluded = self.options.excluded_stats.value
        for agent in self.agents:
            region = Region(agent, self.player, self.multiworld)
            self.multiworld.regions.append(region)
            lobby.connect(region, f"Play {agent}")
            for stat in STATS:
                for tier in range(1, len(self.thresholds[stat]) + 1):
                    name = location_name(agent, stat, tier)
                    location = ValorantLocation(self.player, name, self.location_name_to_id[name], region)
                    if stat in excluded:
                        location.progress_type = LocationProgressType.EXCLUDED
                    region.locations.append(location)

        victory = ValorantLocation(self.player, VICTORY_LOCATION, None, lobby)
        victory.place_locked_item(ValorantItem(VICTORY_EVENT, ItemClassification.progression, None, self.player))
        lobby.locations.append(victory)

    def create_items(self) -> None:
        for name in self.starting_items:
            self.push_precollected(self.create_item(name))

        # Plain Start Inventory items are already precollected by core; *_from_pool ones get removed by core later.
        already_owned = set(self.options.start_inventory.value) | set(self.starting_items)
        pool = [name for name in self.agents + self.weapons if name not in already_owned]

        slots = len(self.multiworld.get_unfilled_locations(self.player))
        if slots - len(pool) < 1:
            # Not enough checks to hold every unlock plus one crystal: start with the surplus (weapons first).
            surplus = len(pool) - slots + 1
            weapons = [name for name in pool if name in WEAPON_NAMES]
            agents = [name for name in pool if name in AGENT_NAMES]
            self.random.shuffle(weapons)
            self.random.shuffle(agents)
            moved = (weapons + agents)[:surplus]
            for name in moved:
                pool.remove(name)
                self.starting_items.append(name)
                self.push_precollected(self.create_item(name))
            logger.warning(f"{self.player_name}: only {slots} Valorant checks for {len(pool) + surplus} unlocks, "
                           f"so you start with: {', '.join(moved)}")
        room = slots - len(pool)

        excluded = [location for location in self.multiworld.get_unfilled_locations(self.player)
                    if location.progress_type == LocationProgressType.EXCLUDED]
        self.radianite_total = max(1, min(self.options.radianite_count.value, room - len(excluded)))
        filler = room - self.radianite_total
        if filler < len(excluded):
            # Excluded checks may only hold filler; give up some exclusions rather than fail generation.
            self.random.shuffle(excluded)
            for location in excluded[:len(excluded) - filler]:
                location.progress_type = LocationProgressType.DEFAULT
            logger.warning(f"{self.player_name}: not enough filler for every excluded Valorant check, "
                           f"{len(excluded) - filler} of them are no longer excluded.")
        self.radianite_required = max(1, math.ceil(self.radianite_total * self.options.radianite_required.value / 100))

        pool += [GOAL_ITEM] * self.radianite_total + [FILLER_ITEM] * filler
        self.multiworld.itempool += [self.create_item(name) for name in pool]

    def set_rules(self) -> None:
        for agent in self.agents:
            self.get_entrance(f"Play {agent}").access_rule = lambda state, agent=agent: state.has(agent, self.player)
            if not self.weapons_in_logic:
                continue
            for stat in STATS:
                for tier in range(1, len(self.thresholds[stat]) + 1):
                    needed = min(required_primary_weapons(stat, tier), len(PRIMARY_WEAPON_NAMES))
                    if needed:
                        self.get_location(location_name(agent, stat, tier)).access_rule = \
                            lambda state, needed=needed: state.has_from_list(PRIMARY_WEAPON_NAMES, self.player, needed)

        self.get_location(VICTORY_LOCATION).access_rule = \
            lambda state: state.has(GOAL_ITEM, self.player, self.radianite_required)
        self.multiworld.completion_condition[self.player] = lambda state: state.has(VICTORY_EVENT, self.player)

    def create_item(self, name: str) -> ValorantItem:
        return ValorantItem(name, classification_for(name, self.weapons_in_logic), self.item_name_to_id[name],
                            self.player)

    def get_filler_item_name(self) -> str:
        return FILLER_ITEM

    def fill_slot_data(self) -> Mapping[str, Any]:
        return {
            "version": SLOT_DATA_VERSION,
            "agents": self.agents,
            "thresholds": self.thresholds,
            "progress_mode": self.options.progress_mode.current_key,
            "weapon_unlocks": bool(self.options.weapon_unlocks),
            "weapon_enforcement": self.options.weapon_enforcement.current_key,
            "allowed_queues": sorted(self.options.allowed_queues.value),
            "trade_window_ms": self.options.trade_window.value * 1000,
            "radianite_total": self.radianite_total,
            "radianite_required": self.radianite_required,
            "short_modes": self.short_modes,
            "shop": self.shop,
        }

    def write_spoiler_header(self, spoiler_handle: TextIO) -> None:
        spoiler_handle.write(f"Valorant agents ({self.player_name}): {', '.join(self.agents)}\n")
        spoiler_handle.write(f"Radianite Crystals needed: {self.radianite_required}/{self.radianite_total}\n")
        if self.short_modes:
            spoiler_handle.write(f"Short modes: {describe_short_modes(self.short_modes)}\n")
        if self.shop:
            prices = ", ".join(f"{category} {price}" for category, price in self.shop["prices"].items())
            spoiler_handle.write(f"Weapon rentals (Kingdom Credits): {prices}\n")
