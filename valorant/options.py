from dataclasses import dataclass

from Options import (
    Choice,
    DefaultOnToggle,
    OptionDict,
    OptionError,
    OptionGroup,
    OptionList,
    OptionSet,
    PerGameCommonOptions,
    Range,
    StartInventoryPool,
)

from .data import (
    AGENT_NAMES,
    DEFAULT_RENTAL_PRICES,
    MAX_TIERS,
    OPTION_STATS,
    OTHER_QUEUES,
    PRIMARY_WEAPON_NAMES,
    QUEUES,
    WEAPON_CATEGORIES,
)


class AgentPool(OptionSet):
    """
    Agents that may appear in this world. Only list agents you actually own in VALORANT -
    the game won't let you pick the others, so their checks would be impossible.
    """
    display_name = "Agent Pool"
    valid_keys = AGENT_NAMES
    default = frozenset(AGENT_NAMES)


class AgentCount(Range):
    """
    How many agents (picked at random from the Agent Pool) are part of this world.
    Every agent gets its own set of checks, so this is the main length setting.
    Agents given through Start Inventory are always included.
    """
    display_name = "Agent Count"
    range_start = 1
    range_end = len(AGENT_NAMES)
    default = 6


class StartingAgents(Range):
    """How many of this world's agents you start with unlocked."""
    display_name = "Starting Agents"
    range_start = 1
    range_end = 5
    default = 3


class WeaponUnlocks(DefaultOnToggle):
    """
    Weapons are items. Until you receive a weapon, kills made with it don't count.
    The Classic, the knife and agent abilities are always allowed.
    """
    display_name = "Weapon Unlocks"


class StartingWeapons(Range):
    """How many random primary weapons (SMGs, shotguns, rifles, snipers, heavies) you start with."""
    display_name = "Starting Weapons"
    range_start = 0
    range_end = len(PRIMARY_WEAPON_NAMES)
    default = 1


class WeaponEnforcement(Choice):
    """
    How the client treats weapons you haven't unlocked yet.
    Kills Only: kills made with a locked weapon are ignored (for kills, multi-kills, trades, clutches and K/D).
    Strict: using a locked weapon at all (buying it or getting a kill with it) voids the whole match.
    Off: honor system - nothing is checked.
    """
    display_name = "Weapon Enforcement"
    option_off = 0
    option_kills_only = 1
    option_strict = 2
    default = 1


class WeaponShop(DefaultOnToggle):
    """
    Kingdom Credits (the filler item) become a currency. In the client's Shop tab (or with /rent) you can spend them
    to rent a weapon you haven't unlocked for your next match: kills with it count, and Strict enforcement doesn't
    void the match for it. Only matters with Weapon Unlocks on and Weapon Enforcement not Off.
    """
    display_name = "Weapon Shop"


class RentalPrices(OptionDict):
    """
    Kingdom Credits it costs to rent a weapon for one match, by weapon type: Sidearm, SMG, Shotgun, Rifle, Sniper and
    Heavy (whole numbers from 0 to 99; types left out keep their default price).
    """
    display_name = "Rental Prices"
    valid_keys = WEAPON_CATEGORIES
    default = DEFAULT_RENTAL_PRICES


class WeaponLogic(Choice):
    """
    How many primary weapons the logic expects you to have before a check is "in logic".
    Standard: tier 1 of Kills, Assists, Trades, K/D, Wins and Performance only needs the agent. Each higher tier
    needs one more primary weapon, and Clutches, Aces and 3Ks start at one weapon.
    Relaxed: only the agent is ever required.
    """
    display_name = "Weapon Logic"
    option_relaxed = 0
    option_standard = 1
    default = 1


class ProgressMode(Choice):
    """
    Cumulative: stats add up over every match you play with an agent (25 kills over three matches counts as 25).
    Single Match: each threshold must be reached within one match.
    K/D and Performance Score always use your best single match, and Wins always add up, regardless of this
    setting.
    """
    display_name = "Progress Mode"
    option_cumulative = 0
    option_single_match = 1
    default = 0


class Thresholds(OptionList):
    # One check per value, per agent. Values are cleaned up (sorted, deduplicated) during generation.
    integer = True
    default = ()


class KillThresholds(Thresholds):
    """Kill counts that each send a check, per agent. One check per entry (max 10). Empty list = no kill checks."""
    display_name = "Kill Thresholds"
    default = [10, 15, 20]


class AssistThresholds(Thresholds):
    """Assist counts that each send a check, per agent."""
    display_name = "Assist Thresholds"
    default = [5, 10, 15]


class TradeThresholds(Thresholds):
    """
    Trade counts that each send a check, per agent.
    A trade is killing the enemy who killed one of your teammates, within the Trade Window.
    """
    display_name = "Trade Thresholds"
    default = [2, 5, 10]


class ShortModeThresholds(Range):
    """
    Swiftplay and Spike Rush matches are much shorter than a full game. In those two modes, the Kill, Assist and
    Trade thresholds only need this percentage (rounded up): at 75, a 20-kill check needs 15 kills there.
    100 turns this off. Kills, assists and trades from those modes count extra towards the regular thresholds
    (x1.33 at 75), so mixing modes adds up fairly.
    The lowered thresholds are listed in the spoiler log, in the client and in the companion window.
    """
    display_name = "Short Mode Thresholds (%)"
    range_start = 25
    range_end = 100
    default = 75


class ClutchThresholds(Thresholds):
    """
    Clutch counts that each send a check, per agent.
    A clutch is winning a round after being your team's last player alive.
    """
    display_name = "Clutch Thresholds"
    default = [1, 2]


class AceThresholds(Thresholds):
    """Ace counts (5 kills in one round) that each send a check, per agent."""
    display_name = "Ace Thresholds"
    default = [1]


class ThreeKThresholds(Thresholds):
    """3K counts (rounds where you got 3 or more kills) that each send a check, per agent."""
    display_name = "3K Thresholds"
    default = [1, 2]


class KDThresholds(Thresholds):
    """K/D ratios that each send a check, per agent, when you finish a match at or above them."""
    display_name = "K/D Thresholds"
    integer = False
    default = [1.0, 1.5]


class WinThresholds(Thresholds):
    """Number of matches won with the agent that each send a check. Always counted across matches."""
    display_name = "Win Thresholds"
    default = [1, 2]


class PerformanceThresholds(Thresholds):
    """
    Performance Score values (0-500, on the scoreboard since patch 13.06) that each send a check, per agent, when
    you finish a match at or above them. Rough guide: around 250 is an average game, 350+ is a standout one.
    Only modes with a Performance Score count (Competitive, Unrated, Swiftplay and Premier). The score comes from
    Riot's official match data, so these checks arrive once Riot publishes the match.
    """
    display_name = "Performance Score Thresholds"
    default = [250, 350]


class ExcludedStats(OptionSet):
    """
    Checks for these stats will only ever contain filler, so you never *need* them to finish.
    Valid values: Kills, Assists, Trades, Clutches, Aces, 3Ks, K/D, Wins, Performance
    """
    display_name = "Excluded Stats"
    valid_keys = OPTION_STATS
    default = frozenset({"Aces"})


class AllowedQueues(OptionSet):
    """
    Game modes whose matches count towards checks.
    Valid values: Competitive, Unrated, Swiftplay, Spike Rush, Premier, Deathmatch, Team Deathmatch,
    Escalation, Replication, Skirmish, Custom Games, Other Modes
    Multi-kills, trades and clutches only exist in round-based modes. Modes where everyone plays a generic
    character (e.g. Gauntlet / Ability Draft) never count, since there is no agent to credit.
    """
    display_name = "Allowed Queues"
    valid_keys = (*QUEUES, OTHER_QUEUES)
    default = frozenset({"Competitive", "Unrated", "Swiftplay", "Spike Rush", "Premier"})


class TradeWindow(Range):
    """How many seconds after a teammate dies you have to kill their killer for it to count as a trade."""
    display_name = "Trade Window"
    range_start = 1
    range_end = 10
    default = 5


class RadianiteCount(Range):
    """
    How many Radianite Crystals are shuffled into the item pool. Collect enough of them to win.
    Lowered automatically if the world doesn't have enough checks to hold them.
    """
    display_name = "Radianite Count"
    range_start = 1
    range_end = 100
    default = 15


class RadianiteRequired(Range):
    """Percentage of the Radianite Crystals you need to collect to win."""
    display_name = "Radianite Required (%)"
    range_start = 1
    range_end = 100
    default = 80


@dataclass
class ValorantOptions(PerGameCommonOptions):
    agent_pool: AgentPool
    agent_count: AgentCount
    starting_agents: StartingAgents
    weapon_unlocks: WeaponUnlocks
    starting_weapons: StartingWeapons
    weapon_enforcement: WeaponEnforcement
    weapon_shop: WeaponShop
    rental_prices: RentalPrices
    weapon_logic: WeaponLogic
    progress_mode: ProgressMode
    kill_thresholds: KillThresholds
    assist_thresholds: AssistThresholds
    trade_thresholds: TradeThresholds
    short_mode_thresholds: ShortModeThresholds
    clutch_thresholds: ClutchThresholds
    ace_thresholds: AceThresholds
    three_k_thresholds: ThreeKThresholds
    kd_thresholds: KDThresholds
    win_thresholds: WinThresholds
    performance_thresholds: PerformanceThresholds
    excluded_stats: ExcludedStats
    allowed_queues: AllowedQueues
    trade_window: TradeWindow
    radianite_count: RadianiteCount
    radianite_required: RadianiteRequired
    start_inventory_from_pool: StartInventoryPool


option_groups = [
    OptionGroup("Agents & Weapons", [
        AgentPool, AgentCount, StartingAgents, WeaponUnlocks, StartingWeapons, WeaponEnforcement, WeaponShop,
        RentalPrices, WeaponLogic,
    ]),
    OptionGroup("Checks", [
        ProgressMode, KillThresholds, AssistThresholds, TradeThresholds, ShortModeThresholds, ClutchThresholds,
        AceThresholds, ThreeKThresholds, KDThresholds, WinThresholds, PerformanceThresholds, ExcludedStats,
        AllowedQueues, TradeWindow,
    ]),
    OptionGroup("Goal", [RadianiteCount, RadianiteRequired]),
]


def threshold_options(options: ValorantOptions) -> dict[str, Thresholds]:
    return {
        "Kills": options.kill_thresholds,
        "Assists": options.assist_thresholds,
        "Trades": options.trade_thresholds,
        "Clutches": options.clutch_thresholds,
        "Aces": options.ace_thresholds,
        "3Ks": options.three_k_thresholds,
        "K/D": options.kd_thresholds,
        "Wins": options.win_thresholds,
        "Performance": options.performance_thresholds,
    }


def clean_rental_prices(option: RentalPrices, player_name: str) -> dict[str, int]:
    """Rental prices for every weapon type: the option's values over the defaults, validated."""
    prices = dict(DEFAULT_RENTAL_PRICES)
    for category, raw in option.value.items():
        if isinstance(raw, bool) or not isinstance(raw, int) or not 0 <= raw <= 99:
            raise OptionError(f"{player_name}: Rental Prices for {category} must be a whole number from 0 to 99 "
                              f"(got {raw!r}).")
        prices[category] = raw
    return prices


def clean_thresholds(option: Thresholds, player_name: str) -> list[int | float]:
    """Validate a threshold list and return it sorted and deduplicated."""
    values: set[int | float] = set()
    for raw in option.value:
        try:
            number = float(raw)
        except (TypeError, ValueError):
            raise OptionError(f"{player_name}: {option.display_name} contains '{raw}', which isn't a number.") from None
        if number <= 0:
            raise OptionError(f"{player_name}: {option.display_name} values must be above 0 (got {raw}).")
        if option.integer:
            if not number.is_integer():
                raise OptionError(f"{player_name}: {option.display_name} values must be whole numbers (got {raw}).")
            values.add(int(number))
        else:
            values.add(round(number, 2))
    if len(values) > MAX_TIERS:
        raise OptionError(f"{player_name}: {option.display_name} can have at most {MAX_TIERS} values.")
    return sorted(values)
