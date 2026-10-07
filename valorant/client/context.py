"""
The VALORANT Archipelago client.

Three data sources, from most to least live:
  * the optional companion app (ow-electron + Overwolf GEP) streams the kill feed, so kills, multi-kills, trades
    and clutches count the moment they happen;
  * the Riot Client's local API gives the session state (agent select, in match, menus), used for agent-select
    warnings, match-start announcements and fetching results the moment a match ends;
  * Riot's official match data, which settles every match once published (it replaces live numbers).
"""
import asyncio
import json
import sys
import time
from typing import Any, Callable, Optional

from CommonClient import ClientCommandProcessor, CommonContext, logger
from NetUtils import ClientStatus

from ..data import (
    AGENT_BY_NAME,
    CLASSIC,
    AGENT_BY_UUID,
    AGENT_CODENAMES,
    AGENT_NAMES,
    FILLER_ITEM,
    GOAL_ITEM,
    ITEM_IDS,
    LIVE_WEAPON_IDS,
    LOCATION_KEYS,
    WEAPON_BY_NAME,
    WEAPON_BY_UUID,
    WEAPON_CATEGORIES,
    WEAPON_NAMES,
    WEAPONS,
    describe_short_modes,
    location_id,
    location_name,
    map_display_name,
    queue_display_name,
    short_mode_weight,
)
from .live import LiveTracker
from .riot import REGION_SHARDS, RiotClient, RiotError, RiotNotRunning
from .stats import compute_match_stats, match_overview
from .tracker import ACS_STAT, KD_STAT, PERFORMANCE_STAT, Progress, ShortModes, acs, kd_ratio

DEFAULT_COMPANION_PORT = 43792
RIOT_TICK_S = 1.5
STATE_PROBE_S = 6
PREGAME_POLL_S = 3  # fallback only: with live game events on, agent select needs no polling
HISTORY_INTERVAL_S = 120
MATCH_FETCH_RETRY_S = 4
MATCH_FETCH_TIMEOUT_S = 15 * 60
COMPANION_STATE_INTERVAL_S = 0.5
SHOP_REFRESH_S = 0.5
CATEGORY_LABELS = {"Sidearm": "Sidearms", "SMG": "SMGs", "Shotgun": "Shotguns", "Rifle": "Rifles", "Sniper": "Snipers",
                   "Heavy": "Heavies"}
STAT_FIELDS = ("kills", "deaths", "assists", "trades", "clutches", "aces", "three_ks", "wins", "score", "rounds",
               "performance")

ITEM_NAMES_BY_ID = {item_id: name for name, item_id in ITEM_IDS.items()}


def play_sound(kind: str) -> None:
    """Windows notification sound. Uses ctypes because frozen Archipelago builds don't ship winsound."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # MB_ICONHAND, MB_ICONASTERISK, MB_OK
        ctypes.windll.user32.MessageBeep({"warning": 0x10, "check": 0x40}.get(kind, 0x0))
    except Exception:  # a missing sound must never take the client down
        pass


def kingdom_credits(amount: int) -> str:
    return f"{amount} Kingdom Credit{'' if amount == 1 else 's'}"


def describe_stats(stats: dict) -> str:
    text = "Win" if stats.get("wins") else "Loss"
    if stats.get("performance"):
        text += f", Performance Score {stats['performance']}"
    elif acs(stats):  # matches from before patch 13.06
        text += f", ACS {acs(stats):.0f}"
    text += (f", {stats['kills']}/{stats['deaths']}/{stats['assists']} (K/D {kd_ratio(stats):.2f}), "
             f"{stats['trades']} trades, {stats['clutches']} clutches, {stats['three_ks']} 3Ks, {stats['aces']} aces")
    if stats.get("locked_kills"):
        text += f" - {stats['locked_kills']} kills with locked weapons didn't count"
    return text


class ValorantCommandProcessor(ClientCommandProcessor):
    ctx: "ValorantContext"

    def _cmd_valorant(self) -> bool:
        """Show the Riot Client, current match and companion app status."""
        ctx = self.ctx
        logger.info(f"Riot Client: {ctx.riot_status}")
        state = {"MENUS": "in the menus", "PREGAME": "in agent select", "INGAME": "in a match"}.get(ctx.session_state)
        if state:
            line = f"VALORANT: {state}"
            if ctx.current_match:
                match = ctx.current_match
                line += f" on {match['map']} as {match['agent'] or 'an unknown agent'}"
                problem = ctx.match_problem(match["agent"], match["queue_id"])
                line += f" (doesn't count: {problem})" if problem else " (counts)"
                if not problem and ctx.in_short_mode(match["queue_id"]):
                    short = ctx.short_modes
                    line += f" - {short.percent}% thresholds, {'/'.join(short.thresholds).lower()} count " \
                            f"{short_mode_weight(short.percent)}"
            if ctx.presence and ctx.presence.get("ally_score") is not None and ctx.session_state == "INGAME":
                line += f", score {ctx.presence['ally_score']}-{ctx.presence['enemy_score']}"
            logger.info(line)
        if ctx.companion_clients:
            live = ctx.live
            logger.info("Companion app: connected" + (f", tracking round {live.round}" if live.active else ""))
        else:
            logger.info(f"Companion app: not connected (listening on port {ctx.companion_port}) - stats arrive "
                        f"when each match ends.")
        if ctx.settings:
            logger.info(f"Goal: {ctx.radianite_count()}/{ctx.settings['radianite_required']} Radianite Crystals")
        return True

    def _cmd_unlocks(self) -> bool:
        """List which of this world's agents and weapons you've unlocked."""
        if not self.ctx.settings:
            logger.info("Connect to your Archipelago slot first.")
            return False
        unlocked = self.ctx.unlocked()
        agents = self.ctx.settings["agents"]
        logger.info("Agents unlocked: " + (", ".join(a for a in agents if a in unlocked) or "none"))
        logger.info("Agents locked: " + (", ".join(a for a in agents if a not in unlocked) or "none"))
        if self.ctx.settings["weapon_unlocks"]:
            logger.info("Weapons unlocked: Classic, " + ", ".join(w for w in WEAPON_NAMES if w in unlocked))
            logger.info("Weapons locked: " + (", ".join(w for w in WEAPON_NAMES if w not in unlocked) or "none"))
        else:
            logger.info("Weapons: all allowed in this world.")
        return True

    def _cmd_progress(self, agent: str = "") -> bool:
        """Show your progress towards each check. Optionally pass an agent name."""
        ctx = self.ctx
        if not ctx.settings or not ctx.progress:
            logger.info("Connect to your Archipelago slot first.")
            return False
        agents = ctx.settings["agents"]
        if agent:
            agents = [a for a in agents if a.lower() == agent.lower()]
            if not agents:
                logger.info(f"'{agent}' isn't one of this world's agents: {', '.join(ctx.settings['agents'])}")
                return False
        mode, short = ctx.settings["progress_mode"], ctx.short_modes
        if short.thresholds:
            logger.info(f"Short modes: {describe_short_modes(ctx.settings['short_modes'])}.")
        totals = ctx.progress.totals(mode, ctx.live_extra(), short)
        unlocked = ctx.unlocked()
        for name in agents:
            parts = []
            for stat, tiers in ctx.settings["thresholds"].items():
                if not tiers:
                    continue
                value = totals.get(name, {}).get(stat, 0)
                remaining = [t for t in tiers if value < t]
                # Short-mode kills/assists/trades count extra, so those totals can be fractional: show whole ones.
                shown = (f"{value:.2f}" if stat == KD_STAT else f"{value:.0f}" if stat in (ACS_STAT, PERFORMANCE_STAT)
                         else f"{int(value)}")
                if not remaining:
                    parts.append(f"{stat} {shown} (done)")
                elif stat in short.thresholds:
                    tier = tiers.index(remaining[0])
                    queues = "/".join(short.queues)
                    if mode == "single_match":
                        hint = f"or {short.thresholds[stat][tier]} in one {queues} match"
                    else:
                        hint = (f"{short.needed(value, remaining[0], short=False)} more, "
                                f"or {short.needed(value, remaining[0])} in {queues}")
                    parts.append(f"{stat} {shown} (next {remaining[0]:g}: {hint})")
                else:
                    parts.append(f"{stat} {shown} (next {remaining[0]:g})")
            logger.info(f"{name}{'' if name in unlocked else ' [locked]'}: " + " | ".join(parts))
        return True

    def _cmd_sync(self) -> bool:
        """Look through your recent matches for results right now."""
        self.ctx.next_history_sync = 0
        logger.info("Checking your match history...")
        return True

    def _cmd_region(self, region: str = "") -> bool:
        """Override the auto-detected region: na, eu, ap, kr, latam or br."""
        region = region.lower()
        if region not in REGION_SHARDS:
            logger.info(f"Usage: /region <{'|'.join(REGION_SHARDS)}> (currently: {self.ctx.riot.region or 'unknown'})")
            return False
        self.ctx.riot.set_region(region)
        logger.info(f"Region set to {region}.")
        return True

    def _cmd_sounds(self) -> bool:
        """Toggle sound alerts (agent-select warnings, completed checks, new unlocks)."""
        self.ctx.sounds = not self.ctx.sounds
        logger.info(f"Sound alerts {'on' if self.ctx.sounds else 'off'}.")
        return True

    def _cmd_shop(self) -> bool:
        """Show your Kingdom Credits, rental prices and rented weapons."""
        for line in self.ctx.shop_summary():
            logger.info(line)
        return True

    def _cmd_rent(self, *weapon: str) -> bool:
        """Rent a locked weapon for your next match with Kingdom Credits, e.g. /rent Vandal."""
        asyncio.create_task(self.ctx.rent_weapon(" ".join(weapon)))
        return True

    def _cmd_refund(self, *weapon: str) -> bool:
        """Cancel a weapon rental that hasn't been used yet, e.g. /refund Vandal."""
        asyncio.create_task(self.ctx.refund_rental(" ".join(weapon)))
        return True


class ValorantContext(CommonContext):
    game = "Valorant"
    items_handling = 0b111
    command_processor = ValorantCommandProcessor

    def __init__(self, server_address: Optional[str], password: Optional[str],
                 companion_port: int = DEFAULT_COMPANION_PORT) -> None:
        super().__init__(server_address, password)
        self.riot = RiotClient()
        self.live = LiveTracker(LIVE_WEAPON_IDS, AGENT_CODENAMES)
        self.companion_port = companion_port
        self.companion_clients = 0
        self.companion_sockets: set[Any] = set()
        self.companion_server: Any = None
        self.valorant_tasks: list[asyncio.Task] = []

        self.settings: Optional[dict] = None
        self.progress: Optional[Progress] = None
        self.progress_owner: Optional[tuple] = None
        self.sent_locations: set[int] = set()
        self.sounds = True

        self.riot_status = "Not checked yet"
        self.session_state = ""
        self.presence: Optional[dict] = None
        self.current_match: Optional[dict] = None
        self.pending_matches: dict[str, float] = {}
        self.next_fetch: dict[str, float] = {}
        self.next_history_sync = 0.0
        self.sync_lock = asyncio.Lock()
        self.pregame_id: Optional[str] = None
        self.pregame_selection: tuple = (None, None)
        self.pregame_queue_problem = ""
        self.live_pick_seen = False  # the game events reported your pick in this agent select
        self.last_pregame_poll = 0.0
        self.last_probe = 0.0
        self.probed_state = "MENUS"
        self.live_announced = ""
        self.live_stats_match = ""
        self.last_live_stats: dict = {}
        self.last_companion_state = ""

    # --- Archipelago ----------------------------------------------------------------------------------------

    @property
    def state_key(self) -> str:
        return f"valorant_progress_{self.team}_{self.slot}"

    def make_gui(self):
        base = super().make_gui()  # imports kvui, which has to happen before any kivy import

        from kivy.metrics import dp
        from kivy.uix.scrollview import ScrollView
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.button import MDButton, MDButtonText
        from kivymd.uix.gridlayout import MDGridLayout
        from kivymd.uix.label import MDLabel

        ctx = self

        def text(content: str, **kwargs: Any) -> MDLabel:
            return MDLabel(text=content, adaptive_height=True, **kwargs)

        class ShopView(ScrollView):
            """The Shop tab: spend Kingdom Credits to rent a locked weapon for one match."""

            def __init__(self, **kwargs: Any) -> None:
                super().__init__(do_scroll_x=False, **kwargs)
                self.content = MDBoxLayout(orientation="vertical", adaptive_height=True, padding=dp(16),
                                           spacing=dp(10))
                self.add_widget(self.content)
                self.shown: Optional[dict] = None
                self.next_check = 0.0

            def refresh(self) -> None:
                now = time.monotonic()
                if now < self.next_check:
                    return
                self.next_check = now + SHOP_REFRESH_S
                view = ctx.shop_view()
                if view != self.shown:  # rebuild only when something changed
                    self.shown = view
                    self.render(view)

            def render(self, view: dict) -> None:
                content = self.content
                content.clear_widgets()
                if "message" in view:
                    content.add_widget(text(view["message"]))
                    return
                content.add_widget(text(f"Kingdom Credits: {view['credits']}", font_style="Title", bold=True))
                content.add_widget(text(
                    "Rent a weapon you haven't unlocked for one match: kills with it count, and Strict enforcement "
                    "won't void the match for it. Rented during a match, it counts from the next round that starts "
                    "(never for kills you already made); otherwise it covers your next match that counts. Unused "
                    "rentals can be refunded."))
                if view["current"]:
                    content.add_widget(text(f"Rented for this match: {', '.join(view['current'])}", bold=True))
                for weapon in view["pending"]:
                    row = MDBoxLayout(adaptive_height=True, spacing=dp(8))
                    row.add_widget(text(f"{weapon}: rented for your next match", bold=True))
                    row.add_widget(MDButton(MDButtonText(text="Refund"), style="text",
                                            on_release=lambda *_, w=weapon: asyncio.create_task(ctx.refund_rental(w))))
                    content.add_widget(row)
                for group in view["groups"]:
                    content.add_widget(text(f"{group['label']} - {kingdom_credits(group['price'])} each", bold=True))
                    grid = MDGridLayout(cols=4, adaptive_height=True, spacing=dp(8))
                    for weapon in group["weapons"]:
                        grid.add_widget(MDButton(
                            MDButtonText(text=weapon["name"]), style="outlined",
                            disabled=weapon["rented"] or not weapon["affordable"],
                            on_release=lambda *_, w=weapon["name"]: asyncio.create_task(ctx.rent_weapon(w))))
                    content.add_widget(grid)
                if not view["groups"]:
                    content.add_widget(text("You've unlocked every weapon: there's nothing to rent."))

        class ValorantManager(base):
            base_title = "Archipelago VALORANT Client"

            def build(self):
                layout = super().build()
                self.radianite_label = MDLabel(text="", size_hint_x=None, width=dp(230), halign="center",
                                               valign="center", bold=True)
                self.connect_layout.add_widget(self.radianite_label)
                self.shop_view = ShopView()
                self.add_client_tab("Shop", self.shop_view)
                return layout

            def update_texts(self, dt):
                super().update_texts(dt)
                self.radianite_label.text = self.ctx.radianite_text()
                self.shop_view.refresh()

        return ValorantManager

    def radianite_text(self) -> str:
        if not self.settings or not self.server:
            return "Radianite: -"
        text = f"Radianite: {self.radianite_count()} / {self.settings['radianite_required']}"
        if self.rental_prices is not None and self.progress is not None:
            text += f"   KC: {self.credit_balance()}"
        return text

    async def server_auth(self, password_requested: bool = False) -> None:
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict) -> None:
        if cmd == "Connected":
            self.settings = args["slot_data"]
            owner = (self.seed_name, self.team, self.slot)
            if owner != self.progress_owner:
                self.progress, self.progress_owner = None, owner
                self.live_announced = ""
            self.sent_locations = set()
            asyncio.create_task(self.send_msgs([{"cmd": "Get", "keys": [self.state_key]}]))
            logger.info(f"Agents in this world: {', '.join(self.settings['agents'])}. Type /progress, /unlocks "
                        f"or /valorant for details.")
            if self.short_modes.thresholds:
                logger.info(f"Short modes: {describe_short_modes(self.settings['short_modes'])}.")
        elif cmd == "Retrieved" and self.state_key in args.get("keys", {}):
            self.load_progress(args["keys"][self.state_key])
        elif cmd == "ReceivedItems":
            new_items = self.items_received[args.get("index", 0):]
            if args.get("index", 0) > 0 and self.sounds:
                if any(ITEM_NAMES_BY_ID.get(item.item) in (*AGENT_NAMES, *WEAPON_NAMES) for item in new_items):
                    play_sound("item")
            new_weapons = [ITEM_NAMES_BY_ID[item.item] for item in new_items
                           if ITEM_NAMES_BY_ID.get(item.item) in WEAPON_NAMES]
            if args.get("index", 0) > 0 and new_weapons and self.session_state == "INGAME":
                logger.info(f"Got the {', '.join(new_weapons)}: kills with {'it' if len(new_weapons) == 1 else 'them'} "
                            f"count from the next round that starts.")
            asyncio.create_task(self.after_change(save=self.note_received()))

    def load_progress(self, data: Optional[dict]) -> None:
        stored = Progress(data) if data else None
        if self.progress is None:
            if stored is None:
                logger.info("Tracking starts now: matches that start from this moment on count towards checks.")
            self.progress = stored or Progress(start_ms=int(time.time() * 1000))
        elif stored is not None:
            self.progress.merge(stored)
        self.note_received()
        self.next_history_sync = 0
        asyncio.create_task(self.after_change(save=True))

    def note_received(self) -> bool:
        """Remember when items arrive: weapons only count in rounds that start after you get them."""
        if self.progress is None:
            return False
        return self.progress.note_received(len(self.items_received), int(time.time() * 1000))

    def weapon_received_ms(self) -> dict[str, int]:
        """When each received weapon arrived (0 for weapons received before this was tracked)."""
        times = (self.progress.received_ms if self.progress else None) or []
        now_ms = int(time.time() * 1000)
        received: dict[str, int] = {}
        for index, item in enumerate(self.items_received):
            name = ITEM_NAMES_BY_ID.get(item.item)
            if name in WEAPON_NAMES and name not in received:
                received[name] = times[index] if index < len(times) else now_ms
        return received

    async def save_progress(self) -> None:
        if self.progress is not None:
            await self.send_msgs([{"cmd": "Set", "key": self.state_key, "default": {}, "want_reply": False,
                                   "operations": [{"operation": "replace", "value": self.progress.to_json()}]}])

    @property
    def short_modes(self) -> ShortModes:
        """Lowered Kill/Assist/Trade thresholds for short modes (none before connecting or when the option is off)."""
        return ShortModes((self.settings or {}).get("short_modes"))

    def tracking_ready(self) -> bool:
        return self.settings is not None and self.progress is not None and self.slot is not None

    async def after_change(self, save: bool = False) -> None:
        if not self.tracking_ready():
            return
        if save:
            await self.save_progress()
        await self.update_checks()
        await self.check_goal()

    async def update_checks(self) -> None:
        if not self.tracking_ready():
            return
        done = self.progress.completed(self.settings["thresholds"], self.settings["agents"],
                                       self.settings["progress_mode"], self.live_extra(), self.short_modes)
        new = {}
        for agent, stat, tier in done:
            loc = location_id(agent, stat, tier)
            if loc in self.missing_locations and loc not in self.sent_locations:
                new[loc] = (agent, stat, tier)
        if not new:
            return
        self.sent_locations |= new.keys()
        self.locations_checked |= new.keys()
        await self.check_locations(new.keys())
        for agent, stat, tier in new.values():
            threshold = self.settings["thresholds"][stat][tier - 1]
            logger.info(f"Check complete: {location_name(agent, stat, tier)} ({stat} {threshold:g})")
        if self.sounds:
            play_sound("check")

    async def check_goal(self) -> None:
        if self.finished_game or not self.settings:
            return
        if self.radianite_count() >= self.settings["radianite_required"]:
            await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            self.finished_game = True
            logger.info("You've collected enough Radianite Crystals and reached Radiant. Goal complete!")

    def unlocked(self) -> set[str]:
        return {ITEM_NAMES_BY_ID[item.item] for item in self.items_received if item.item in ITEM_NAMES_BY_ID}

    def radianite_count(self) -> int:
        return sum(1 for item in self.items_received if item.item == ITEM_IDS[GOAL_ITEM])

    # --- rules ----------------------------------------------------------------------------------------------

    def weapon_name_allowed(self, name: str, round_start_ms: Optional[int] = None,
                            rented: Optional[dict[str, int]] = None) -> bool:
        """
        Whether kills with this weapon count in a round that started at `round_start_ms`: you need to have received
        it, or rented it (`rented`: the weapons rented for that match, with when they were bought), before the round
        started. Without a time, received weapons count.
        """
        settings = self.settings
        if not settings or not settings["weapon_unlocks"] or settings["weapon_enforcement"] == "off":
            return True
        if name not in WEAPON_NAMES:
            return True
        received_ms = self.weapon_received_ms().get(name)
        if received_ms is not None and (round_start_ms is None or received_ms < round_start_ms):
            return True
        bought_ms = (rented or {}).get(name)
        return bought_ms is not None and round_start_ms is not None and bought_ms < round_start_ms

    def weapon_uuid_allowed(self, uuid: str, round_start_ms: Optional[int] = None,
                            rented: Optional[dict[str, int]] = None) -> bool:
        weapon = WEAPON_BY_UUID.get(uuid.lower())
        return weapon is None or self.weapon_name_allowed(weapon.name, round_start_ms, rented)

    # --- Kingdom Credits shop -------------------------------------------------------------------------------

    @property
    def rental_prices(self) -> Optional[dict[str, int]]:
        """Kingdom Credits per weapon type, or None when this world has no shop."""
        shop = (self.settings or {}).get("shop")
        return shop["prices"] if shop else None

    def credit_balance(self) -> int:
        received = sum(1 for item in self.items_received if item.item == ITEM_IDS[FILLER_ITEM])
        return received - (self.progress.spent() if self.progress else 0)

    def rental_price(self, weapon: str) -> int:
        return (self.rental_prices or {}).get(WEAPON_BY_NAME[weapon].category, 0)

    def pending_rental_weapons(self) -> list[str]:
        return [rental["weapon"] for rental in self.progress.pending_rentals().values()] if self.progress else []

    def find_weapon(self, text: str) -> Optional[str]:
        text = text.strip().lower()
        return next((name for name in WEAPON_NAMES if name.lower() == text), None)

    def shop_unavailable(self) -> str:
        """Why the shop can't be used right now ("" if it can)."""
        if not self.tracking_ready():
            return "Connect to your Archipelago slot first."
        if self.rental_prices is None:
            return "There's no weapon shop in this world."
        return ""

    def rent_problem(self, weapon: Optional[str]) -> str:
        """Why this weapon can't be rented right now ("" if it can)."""
        unavailable = self.shop_unavailable()
        if unavailable:
            return unavailable
        if weapon is None:
            return f"Name a weapon to rent: {', '.join(WEAPON_NAMES)}."
        if weapon in self.unlocked():
            return f"You've already unlocked the {weapon}."
        if weapon in self.pending_rental_weapons():
            return f"The {weapon} is already rented for your next match."
        if self.current_match and weapon in self.progress.rented_for(self.current_match["id"]):
            return f"The {weapon} is already rented for this match."
        price, balance = self.rental_price(weapon), self.credit_balance()
        if price > balance:
            return f"The {weapon} costs {kingdom_credits(price)} and you have {balance}."
        return ""

    def current_match_counts(self) -> bool:
        match = self.current_match
        return bool(self.session_state == "INGAME" and match and not self.match_problem(match["agent"],
                                                                                         match["queue_id"]))

    async def rent_weapon(self, text: str) -> bool:
        weapon = self.find_weapon(text) if text.strip() else None
        problem = "" if weapon or not text.strip() else f"'{text.strip()}' isn't a weapon."
        problem = problem or self.rent_problem(weapon)
        if problem:
            logger.info(problem)
            return False
        price = self.rental_price(weapon)
        now_ms = int(time.time() * 1000)
        self.progress.rent(weapon, price, now_ms)
        if self.current_match_counts():
            self.progress.bind_rentals(self.current_match["id"], now_ms + 1)
            timing = "from the next round that starts in this match (not for kills you already made)"
        elif self.session_state == "PREGAME":
            timing = "in this match, as long as it counts"
        else:
            timing = "in your next match that counts"
        await self.save_progress()
        logger.info(f"Rented the {weapon} for {kingdom_credits(price)}: kills with it count {timing}. "
                    f"{kingdom_credits(self.credit_balance())} left.")
        self.last_companion_state = ""  # show it in the companion window right away
        return True

    async def refund_rental(self, text: str) -> bool:
        weapon = self.find_weapon(text)
        pending = self.progress.pending_rentals() if self.tracking_ready() else {}
        rental_id = next((key for key, rental in pending.items() if rental["weapon"] == weapon), None)
        if rental_id is None:
            logger.info(f"There's no unused rental of {weapon or repr(text.strip())} to refund.")
            return False
        self.progress.refund(rental_id)
        await self.save_progress()
        logger.info(f"Refunded the {weapon}. You have {kingdom_credits(self.credit_balance())}.")
        self.last_companion_state = ""
        return True

    def use_rentals(self, match_id: str, before_ms: int, agent: Optional[str],
                    queue_id: Optional[str]) -> dict[str, int]:
        """
        Weapons rented for this match, with when they were bought. Unused rentals bought before `before_ms` (the
        match's end, or now while it's running) are used on it if it counts: rentals aren't spent on matches that
        wouldn't count anyway. Kills with them only count after the purchase.
        """
        if not self.progress or not match_id:
            return {}
        if self.rental_prices is not None and before_ms and not self.match_problem(agent, queue_id):
            bound = self.progress.bind_rentals(match_id, before_ms)
            if bound:
                logger.info(f"Using your rental: {', '.join(bound)} count{'s' if len(bound) == 1 else ''} "
                            f"this match.")
        return self.progress.rented_for(match_id)

    def shop_view(self) -> dict:
        """What the Shop tab and /shop show."""
        unavailable = self.shop_unavailable()
        if unavailable:
            return {"message": unavailable}
        prices, balance, unlocked = self.rental_prices, self.credit_balance(), self.unlocked()
        pending = self.pending_rental_weapons()
        groups = []
        for category in WEAPON_CATEGORIES:
            price = prices[category]
            weapons = [{"name": weapon.name, "affordable": price <= balance, "rented": weapon.name in pending}
                       for weapon in WEAPONS if weapon.category == category and weapon.name not in unlocked]
            if weapons:
                groups.append({"category": category, "label": CATEGORY_LABELS[category], "price": price,
                               "weapons": weapons})
        current = sorted(self.progress.rented_for(self.current_match["id"])) if self.current_match else []
        return {"credits": balance, "pending": pending, "current": current, "groups": groups}

    def shop_summary(self) -> list[str]:
        """The shop, as lines for /shop."""
        view = self.shop_view()
        if "message" in view:
            return [view["message"]]
        lines = [f"Kingdom Credits: {view['credits']}. Rent a locked weapon for one match with /rent <weapon>."]
        for group in view["groups"]:
            names = ", ".join(weapon["name"] for weapon in group["weapons"])
            lines.append(f"{group['label']} ({group['price']} each): {names}")
        if not view["groups"]:
            lines.append("You've unlocked every weapon: there's nothing to rent.")
        if view["current"]:
            lines.append(f"Rented for this match: {', '.join(view['current'])}")
        if view["pending"]:
            lines.append(f"Rented for your next match: {', '.join(view['pending'])} (/refund <weapon> to cancel)")
        return lines

    def match_problem(self, agent: Optional[str], queue_id: Optional[str]) -> str:
        """Why a match with this agent and queue wouldn't count ("" if it would)."""
        return self.agent_problem(agent) or self.queue_problem(queue_id)

    def agent_problem(self, agent: Optional[str]) -> str:
        if not self.settings:
            return "not connected to Archipelago"
        if agent is None:
            return "unknown agent"
        if agent not in self.settings["agents"]:
            return f"{agent} isn't one of this world's agents"
        if agent not in self.unlocked():
            return f"{agent} is still locked"
        return ""

    def queue_problem(self, queue_id: Optional[str]) -> str:
        if not self.settings:
            return "not connected to Archipelago"
        if queue_id is None:
            return "unknown game mode"
        queue = queue_display_name(queue_id)
        return "" if queue in self.settings["allowed_queues"] else f"{queue} matches don't count in this world"

    def build_record(self, agent: Optional[str], queue_id: Optional[str], map_name: str, stats: dict, source: str,
                     complete: bool, time_ms: int) -> dict:
        problem = self.match_problem(agent, queue_id)
        if not problem and self.settings["weapon_enforcement"] == "strict" and stats.get("locked_weapons"):
            names = [WEAPON_BY_UUID[w].name if w in WEAPON_BY_UUID else w for w in stats["locked_weapons"]]
            problem = f"you used locked weapons ({', '.join(names)})"
        return {
            "agent": agent or "Unknown", "counted": not problem, "reason": problem, "source": source,
            "complete": complete, "time": time_ms, "queue": queue_display_name(queue_id or ""), "map": map_name,
            "stats": {field: stats.get(field, 0) for field in STAT_FIELDS},
        }

    # --- official match results -----------------------------------------------------------------------------

    async def process_official(self, details: dict, save: bool = True) -> bool:
        """Record an official match result. Returns whether it changed anything."""
        overview = match_overview(details, self.riot.puuid)
        match_id = overview["match_id"]
        if not match_id or not overview["found"] or not self.tracking_ready():
            return False
        if overview["start_ms"] and overview["start_ms"] < self.progress.start_ms:
            return False
        agent = AGENT_BY_UUID.get(overview["agent_uuid"])
        start_ms = overview["start_ms"]
        rented = self.use_rentals(match_id, start_ms + overview["length_ms"], agent.name if agent else None,
                                  overview["queue_id"])

        def allowed(uuid: str, round_start_ms: Optional[int]) -> bool:
            # Without a time, assume the match's start: weapons gained mid-match never cover it.
            return self.weapon_uuid_allowed(uuid, round_start_ms if round_start_ms is not None else start_ms, rented)

        stats = compute_match_stats(details, self.riot.puuid, allowed, self.settings["trade_window_ms"])
        map_name = map_display_name(overview["map"])
        record = self.build_record(agent.name if agent else None, overview["queue_id"], map_name, stats, "official",
                                   True, overview["start_ms"])
        if not self.progress.record(match_id, record):
            return False
        if record["counted"]:
            logger.info(f"Match result - {map_name} as {record['agent']}: {describe_stats(stats)}")
        else:
            logger.info(f"Match on {map_name} as {record['agent']} doesn't count: {record['reason']}.")
        await self.after_change(save=save)
        return True

    async def fetch_pending_matches(self) -> None:
        """Fetch results of matches that just ended, retrying until Riot publishes them."""
        now = time.monotonic()
        for match_id, deadline in list(self.pending_matches.items()):
            if now > deadline or (self.progress and self.progress.has_official(match_id)):
                del self.pending_matches[match_id]
                continue
            if now < self.next_fetch.get(match_id, 0) or not self.tracking_ready():
                continue
            self.next_fetch[match_id] = now + MATCH_FETCH_RETRY_S
            details = await self.call(self.riot.match_details, match_id)
            if details and (details.get("matchInfo") or {}).get("isCompleted", True):
                del self.pending_matches[match_id]
                await self.process_official(details)

    async def sync_history(self) -> None:
        async with self.sync_lock:
            self.next_history_sync = time.monotonic() + HISTORY_INTERVAL_S
            history = await self.call(self.riot.match_history, 0, 20)
            changed = False
            for entry in sorted(history, key=lambda e: e.get("GameStartTime") or 0):
                match_id = entry.get("MatchID")
                if (not match_id or (entry.get("GameStartTime") or 0) < self.progress.start_ms
                        or self.progress.has_official(match_id)):
                    continue
                details = await self.call(self.riot.match_details, match_id)
                if details:
                    changed = await self.process_official(details, save=False) or changed
            if changed:
                await self.save_progress()

    # --- Riot Client (live session state) -------------------------------------------------------------------

    @staticmethod
    async def call(function: Callable, *args: Any) -> Any:
        return await asyncio.to_thread(function, *args)

    async def riot_loop(self) -> None:
        last_problem = ""
        while not self.exit_event.is_set():
            delay = RIOT_TICK_S
            try:
                await self.riot_tick()
                last_problem = ""
            except RiotNotRunning as error:
                self.riot_status, self.session_state, delay = str(error), "", 5
                if last_problem != str(error):
                    logger.info(f"{error} Waiting for it...")
                    last_problem = str(error)
            except RiotError as error:
                self.riot_status = f"error: {error}"
                delay = 60 if error.status == 429 else 10
                if last_problem != str(error):
                    logger.warning(f"Riot API: {error}")
                    last_problem = str(error)
            except Exception as error:  # keep tracking even if one tick blows up
                logger.exception(f"Unexpected error while talking to the Riot Client: {error}")
                delay = 10
            await asyncio.sleep(delay)

    async def riot_tick(self) -> None:
        await self.call(self.riot.ensure_session)
        self.riot_status = f"connected (region: {self.riot.region or 'unknown'})"
        presence = await self.call(self.riot.presence)
        state = (presence or {}).get("state")
        if not state:  # no presence: ask the game servers, but only while VALORANT is actually running
            state = await self.probe_state() if await self.call(self.riot.valorant_running) else ""
        previous, self.session_state, self.presence = self.session_state, state, presence

        if state == "PREGAME":
            await self.watch_pregame(entered=previous != "PREGAME")
        elif previous == "PREGAME":
            self.pregame_id, self.pregame_selection, self.pregame_queue_problem = None, (None, None), ""
            self.live_pick_seen = False
        if state == "INGAME" and (previous != "INGAME" or self.current_match is None):
            await self.on_match_started(presence)
        if previous == "INGAME" and state != "INGAME" and self.current_match:
            self.pending_matches[self.current_match["id"]] = time.monotonic() + MATCH_FETCH_TIMEOUT_S
            logger.info("Match over - grabbing the results as soon as Riot publishes them...")
            self.current_match = None

        await self.fetch_pending_matches()
        if self.tracking_ready() and time.monotonic() >= self.next_history_sync:
            await self.sync_history()

    async def probe_state(self) -> str:
        """Session state from the game servers, for when presence isn't available. Rate limited."""
        if time.monotonic() - self.last_probe >= STATE_PROBE_S:
            self.last_probe = time.monotonic()
            if await self.call(self.riot.coregame_match_id):
                self.probed_state = "INGAME"
            elif await self.call(self.riot.pregame_match_id):
                self.probed_state = "PREGAME"
            else:
                self.probed_state = "MENUS"
        return self.probed_state

    async def watch_pregame(self, entered: bool) -> None:
        """
        Read agent select from Riot: once when it starts (for the game mode), then every few seconds for your pick,
        unless the live game events already report it.
        """
        if not entered and (self.live_pick_seen or time.monotonic() - self.last_pregame_poll < PREGAME_POLL_S):
            return
        self.last_pregame_poll = time.monotonic()
        try:
            await self.read_pregame()
        except RiotError as error:
            if error.status != 404:
                raise
            self.pregame_id = None  # agent select ended (dodge or start)

    async def read_pregame(self) -> None:
        if self.pregame_id is None:
            self.pregame_id = await self.call(self.riot.pregame_match_id)
            if self.pregame_id is None:
                return
            match = await self.call(self.riot.pregame_match, self.pregame_id)
            queue_id = match.get("QueueID")
            if queue_id is None:
                queue_id = (self.presence or {}).get("queue_id")
            if match.get("ProvisioningFlowID") == "CustomGame":
                queue_id = ""
            problem = self.queue_problem(queue_id)
            self.pregame_queue_problem = problem if self.settings else ""
            if problem and self.settings:
                logger.warning(f"Heads up: {problem}.")
                if self.sounds:
                    play_sound("warning")
        else:
            match = await self.call(self.riot.pregame_match, self.pregame_id)

        players = (match.get("AllyTeam") or {}).get("Players") or []
        me = next((p for p in players if str(p.get("Subject", "")).lower() == self.riot.puuid), None)
        if me is None or not self.settings:
            return
        if self.live_pick_seen:
            return  # the game events are faster; don't let an older answer from Riot override them
        agent = AGENT_BY_UUID.get(str(me.get("CharacterID") or "").lower())
        self.set_pregame_selection(agent.name if agent else None, me.get("CharacterSelectionState") or "")

    def in_agent_select(self) -> bool:
        return self.session_state == "PREGAME" or bool(self.companion_clients and self.live.in_agent_select)

    def set_pregame_selection(self, name: Optional[str], state: str) -> None:
        """Warn the moment you hover or lock an agent that doesn't count. `state` is "selected" or "locked"."""
        selection = (name, state)
        if selection == self.pregame_selection or name is None:
            return
        self.pregame_selection = selection
        problem = self.agent_problem(name)
        if problem:
            verb = "locked in" if state == "locked" else "are hovering"
            logger.warning(f"You {verb} {name}, but {problem} - this match won't count!")
            if self.sounds:
                play_sound("warning")
        elif state == "locked":
            logger.info(f"Locked in {name} - this one counts.")

    async def on_match_started(self, presence: Optional[dict]) -> None:
        match_id = await self.call(self.riot.coregame_match_id)
        if not match_id:
            return
        try:
            match = await self.call(self.riot.coregame_match, match_id)
        except RiotError as error:
            if error.status == 404:
                return  # the match is gone already; try again next tick
            raise
        me = next((p for p in match.get("Players") or [] if str(p.get("Subject", "")).lower() == self.riot.puuid), {})
        agent = AGENT_BY_UUID.get(str(me.get("CharacterID") or "").lower())
        queue_id = (match.get("MatchmakingData") or {}).get("QueueID")
        if queue_id is None:
            queue_id = (presence or {}).get("queue_id")
        if match.get("ProvisioningFlow") == "CustomGame":
            queue_id = ""
        self.current_match = {"id": match_id, "agent": agent.name if agent else None, "queue_id": queue_id,
                              "map": map_display_name(match.get("MapID") or "")}
        if not self.settings:
            return
        problem = self.match_problem(self.current_match["agent"], queue_id)
        where = f"{self.current_match['map']} as {self.current_match['agent'] or 'an unknown agent'}"
        if problem:
            logger.warning(f"Match started on {where} - it won't count: {problem}.")
        else:
            # Unused rentals go to this match; kills with them only count after they were bought.
            if self.tracking_ready() and self.use_rentals(match_id, int(time.time() * 1000),
                                                          self.current_match["agent"], queue_id):
                await self.save_progress()
            live = " Live stats are on." if self.companion_clients else ""
            short = self.short_modes
            if self.in_short_mode(queue_id):
                stats = ", ".join(stat.lower() for stat in short.thresholds)
                live = f" {stats.capitalize()} count {short_mode_weight(short.percent)} here.{live}"
            logger.info(f"Match started on {where} ({queue_display_name(queue_id or '')}). Good luck!{live}")

    def in_short_mode(self, queue_id: Optional[str]) -> bool:
        """Whether this queue gets the lowered short-mode thresholds."""
        short = self.short_modes
        return queue_id is not None and bool(short.thresholds) and queue_display_name(queue_id) in short.queues

    # --- companion app ----------------------------------------------------------------------------------

    async def start_companion_server(self) -> None:
        import websockets
        try:
            self.companion_server = await websockets.serve(self.companion_handler, "127.0.0.1", self.companion_port,
                                                        max_size=2 ** 20)
        except OSError as error:
            logger.warning(f"Couldn't listen for the companion app on port {self.companion_port}: {error}")

    async def companion_handler(self, websocket: Any, *_args: Any) -> None:
        self.companion_clients += 1
        self.companion_sockets.add(websocket)
        self.last_companion_state = ""  # make the state loop send a fresh copy to the new companion
        logger.info("Companion app connected: kills, multi-kills, trades and clutches now count the moment "
                    "they happen.")
        try:
            async for raw in websocket:
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(message, dict):
                    changes = self.live.handle(message)
                    if changes:
                        await self.on_live_change(changes)
        except Exception as error:
            logger.debug(f"Companion app connection ended: {error}")
        finally:
            self.companion_clients -= 1
            self.companion_sockets.discard(websocket)
            logger.info("Companion app disconnected.")

    def live_match_id(self) -> str:
        if self.live.match_id:
            return self.live.match_id
        if self.current_match:
            return self.current_match["id"]
        return self.live.pseudo_id

    def live_record(self) -> Optional[dict]:
        """The in-progress match as a record, based on the companion's live numbers."""
        live = self.live
        if not self.tracking_ready() or not live.active or not live.key:
            return None
        if live.started_ms and live.started_ms < self.progress.start_ms:
            return None  # started before tracking began, like official results
        same_match = self.current_match and (not live.match_id or live.match_id == self.current_match["id"])
        agent = self.current_match["agent"] if same_match else None
        queue_id = self.current_match["queue_id"] if same_match else None
        if same_match and self.current_match["queue_id"] is None:
            queue_id = live.queue_guess()
        if not same_match:
            agent, queue_id = live.agent, live.queue_guess()
        rented = self.progress.rented_for(self.current_match["id"] if same_match else self.live_match_id())
        stats = live.stats(lambda name, round_start_ms: self.weapon_name_allowed(name, round_start_ms, rented),
                           self.settings["trade_window_ms"])
        map_name = self.current_match["map"] if same_match else map_display_name(live.map)
        return self.build_record(agent, queue_id, map_name, stats, "live", live.ended, live.started_ms)

    def live_extra(self) -> list[dict]:
        """The live match, if it isn't already stored as a finished match."""
        record = self.live_record()
        if record is None or not self.progress or self.live_match_id() in self.progress.matches:
            return []
        return [record]

    async def on_live_agent_select(self) -> None:
        """Agent select through the game events: instant, and no requests to Riot."""
        if self.live.pick and self.settings and self.in_agent_select():
            agent, locked = self.live.pick
            if not self.live_pick_seen:
                self.live_pick_seen = True
                logger.info(f"Agent select: following your pick through the live game events "
                            f"({'locked in' if locked else 'hovering'} {agent}).")
            self.set_pregame_selection(agent, "locked" if locked else "selected")
        await self.send_companion_state()  # straight to the overlay, which appears, changes or goes away right away

    async def on_live_change(self, changes: set[str]) -> None:
        if "scene" in changes and self.live.in_agent_select and self.live.pick is None:
            self.live_pick_seen = False  # a new agent select
        if changes & {"pick", "scene"}:
            await self.on_live_agent_select()
        record = self.live_record()
        if record is None:
            return
        match_id = self.live_match_id()
        if match_id != self.live_stats_match:
            self.live_stats_match, self.last_live_stats = match_id, {}
        if record["counted"] and match_id != self.live_announced:
            self.live_announced = match_id
            where = f" on {record['map']}" if record["map"] != "Unknown map" else ""
            logger.info(f"Live tracking {record['agent']}{where}.")
        if record["counted"]:
            stats = record["stats"]
            for field, label in (("three_ks", "3K"), ("aces", "ACE"), ("trades", "Trade"), ("clutches", "Clutch")):
                if stats[field] > self.last_live_stats.get(field, 0):
                    logger.info(f"Live: {label}! ({stats[field]} this match)")
            self.last_live_stats = stats
            await self.update_checks()
        if self.live.ended and self.progress.record(match_id, record):
            if record["counted"]:
                where = f"{record['map']} as " if record["map"] != "Unknown map" else ""
                logger.info(f"Live result - {where}{record['agent']}: {describe_stats(record['stats'])} "
                            f"(official numbers replace these once Riot publishes the match)")
            await self.after_change(save=True)

    def pregame_state(self) -> Optional[dict]:
        """What the companion's agent-select overlay shows (None outside agent select)."""
        if not self.in_agent_select() or not self.settings:
            return None
        agent, selection = self.pregame_selection
        unlocked = self.unlocked()
        return {
            "agent": agent,
            "locked": selection == "locked",
            "problem": self.agent_problem(agent) if agent else "",
            "queue_problem": self.pregame_queue_problem,
            "unlocked": [name for name in self.settings["agents"] if name in unlocked],
        }

    def companion_state(self) -> dict:
        """Everything the companion's progress window shows."""
        connected = bool(self.server and self.settings and self.progress and self.slot is not None)
        state: dict[str, Any] = {"kind": "state", "connected": connected}
        if not connected:
            return state
        checked = {LOCATION_KEYS[loc] for loc in self.checked_locations | self.sent_locations if loc in LOCATION_KEYS}
        unlocked = self.unlocked()
        short = self.short_modes
        agents = self.progress.overview(self.settings["thresholds"], self.settings["agents"],
                                        self.settings["progress_mode"], unlocked, checked, self.live_extra(), short)
        for row in agents:
            row["role"] = AGENT_BY_NAME[row["name"]].role
            row["uuid"] = AGENT_BY_NAME[row["name"]].uuid
        weapons_are_items = self.settings.get("weapon_unlocks", True)
        rented = set(self.pending_rental_weapons())
        if self.current_match:
            rented.update(self.progress.rented_for(self.current_match["id"]))
        weapons = [{"name": weapon.name, "uuid": weapon.uuid, "category": weapon.category,
                    "unlocked": weapon is CLASSIC or not weapons_are_items or weapon.name in unlocked,
                    "rented": weapon.name in rented}
                   for weapon in (CLASSIC, *WEAPONS)]
        match = None
        if self.current_match:
            queue_id = self.current_match["queue_id"]
            match = {"agent": self.current_match["agent"], "map": self.current_match["map"],
                     "queue": queue_display_name(queue_id) if queue_id is not None else None,
                     "short": self.in_short_mode(queue_id),
                     "problem": self.match_problem(self.current_match["agent"], queue_id)}
        return {
            **state,
            "pregame": self.pregame_state(),
            "slot": self.player_names.get(self.slot, self.auth or ""),
            "radianite": {"have": self.radianite_count(), "need": self.settings["radianite_required"],
                          "total": self.settings["radianite_total"]},
            "goal": bool(self.finished_game),
            "agents": agents,
            "weapons": {"items": weapons_are_items, "list": weapons},
            "match": match,
            "shop": {"credits": self.credit_balance(), "prices": self.rental_prices} if self.rental_prices else None,
            "short_modes": {"percent": short.percent, "queues": list(short.queues),
                            "weight": short_mode_weight(short.percent),
                            "single_match": self.settings["progress_mode"] == "single_match"}
            if short.thresholds else None,
        }

    async def companion_state_loop(self) -> None:
        """Push the progress window's state to connected companions whenever it changes."""
        self.last_companion_state = ""
        while not self.exit_event.is_set():
            await asyncio.sleep(COMPANION_STATE_INTERVAL_S)
            await self.send_companion_state()

    async def send_companion_state(self) -> None:
        """Send the companion the current state, if it changed since the last one."""
        if not self.companion_sockets:
            return
        try:
            message = json.dumps(self.companion_state())
        except Exception as error:
            logger.debug(f"Couldn't build the companion state: {error}")
            return
        if message == self.last_companion_state:
            return
        self.last_companion_state = message
        for websocket in list(self.companion_sockets):
            try:
                await websocket.send(message)
            except Exception:
                self.companion_sockets.discard(websocket)

    # --- lifecycle ------------------------------------------------------------------------------------------

    def start_valorant_tasks(self) -> None:
        self.valorant_tasks = [
            asyncio.create_task(self.riot_loop(), name="Riot Client loop"),
            asyncio.create_task(self.start_companion_server(), name="Companion app server"),
            asyncio.create_task(self.companion_state_loop(), name="Companion state loop"),
        ]

    async def shutdown(self) -> None:
        for task in self.valorant_tasks:
            task.cancel()
        if self.companion_server is not None:
            self.companion_server.close()
        await super().shutdown()
