import asyncio
import json
import sys
import unittest
from unittest import mock

from NetUtils import NetworkItem

from ..client.context import ValorantCommandProcessor, ValorantContext, play_sound
from ..client.tracker import Progress
from ..data import DEFAULT_RENTAL_PRICES, ITEM_IDS, location_id
from .test_stats import VANDAL, kill, make_match


class TestFrozenBuildCompatibility(unittest.TestCase):
    def test_sounds_work_without_winsound(self) -> None:
        """Frozen Archipelago builds don't ship winsound; sound alerts must not depend on it."""
        with mock.patch.dict(sys.modules, {"winsound": None}):
            for kind in ("warning", "check", "item"):
                play_sound(kind)


class TestCompanionState(unittest.TestCase):
    def test_state_for_progress_window(self) -> None:
        async def build() -> dict:
            ctx = ValorantContext(None, None)
            ctx.slot, ctx.team, ctx.server = 1, 0, object()
            ctx.player_names = {1: "Jonas"}
            ctx.settings = {"agents": ["Jett", "Sage"], "thresholds": {"Kills": [10, 25], "Wins": [1]},
                            "progress_mode": "cumulative", "radianite_total": 10, "radianite_required": 8}
            ctx.progress = Progress(start_ms=1)
            ctx.progress.record("m1", {"agent": "Jett", "counted": True, "source": "official", "complete": True,
                                       "stats": {"kills": 12, "wins": 1}})
            ctx.items_received = [NetworkItem(ITEM_IDS[name], 0, 1, 0)
                                  for name in ("Jett", "Radianite Crystal", "Radianite Crystal")]
            ctx.checked_locations = {location_id("Sage", "Kills", 1)}
            state = ctx.companion_state()
            ctx.server = None  # only a stand-in for "connected"
            await ctx.shutdown()
            return state

        state = asyncio.run(build())
        json.dumps(state)  # must be sendable as-is
        self.assertTrue(state["connected"])
        self.assertEqual(state["slot"], "Jonas")
        self.assertEqual(state["radianite"], {"have": 2, "need": 8, "total": 10})
        jett, sage = state["agents"]
        self.assertEqual((jett["name"], jett["unlocked"], jett["role"]), ("Jett", True, "Duelist"))
        self.assertEqual([(stat["stat"], stat["value"], stat["done"]) for stat in jett["stats"]],
                         [("Kills", 12, 1), ("Wins", 1, 1)])
        self.assertEqual((sage["unlocked"], sage["stats"][0]["done"]), (False, 1))
        self.assertEqual(jett["uuid"], "add6443a-41bd-e414-f6ad-e58d267f4e95")
        weapons = {weapon["name"]: weapon for weapon in state["weapons"]["list"]}
        self.assertTrue(state["weapons"]["items"])
        self.assertEqual(len(weapons), 20)  # the Classic plus every weapon item
        self.assertTrue(weapons["Classic"]["unlocked"])
        self.assertFalse(weapons["Vandal"]["unlocked"])

    def test_short_modes(self) -> None:
        async def build() -> tuple[dict, list[str]]:
            ctx = ValorantContext(None, None)
            ctx.slot, ctx.team, ctx.server = 1, 0, object()
            ctx.settings = {"agents": ["Jett"], "thresholds": {"Kills": [10, 25], "Wins": [1]},
                            "progress_mode": "cumulative", "radianite_total": 10, "radianite_required": 8,
                            "allowed_queues": ["Competitive", "Spike Rush"],
                            "short_modes": {"percent": 75, "queues": ["Spike Rush"],
                                            "thresholds": {"Kills": [8, 19]}}}
            ctx.progress = Progress(start_ms=1)
            ctx.progress.record("m1", {"agent": "Jett", "counted": True, "source": "official", "complete": True,
                                       "queue": "Spike Rush", "stats": {"kills": 13}})
            ctx.items_received = [NetworkItem(ITEM_IDS["Jett"], 0, 1, 0)]
            ctx.current_match = {"id": "m2", "agent": "Jett", "queue_id": "spikerush", "map": "Ascent"}
            state = ctx.companion_state()
            with self.assertLogs("Client", "INFO") as logs:
                ValorantCommandProcessor(ctx)._cmd_progress()
            ctx.server = None
            await ctx.shutdown()
            return state, logs.output

        state, logs = asyncio.run(build())
        json.dumps(state)
        self.assertEqual(state["short_modes"], {"percent": 75, "queues": ["Spike Rush"], "weight": "×1.33",
                                                "single_match": False})
        self.assertEqual((state["match"]["queue"], state["match"]["short"]), ("Spike Rush", True))
        kills = state["agents"][0]["stats"][0]
        # 13 Spike Rush kills count as 17.33 towards 25: 6 more there, or 8 in other modes
        self.assertEqual((kills["done"], kills["short_tiers"], kills["short_needed"]), (1, [8, 19], 6))
        self.assertIn("Spike Rush need 75% of the regular thresholds: Kills 8 / 19", logs[0])
        self.assertIn("Jett: Kills 17 (next 25: 8 more, or 6 in Spike Rush)", logs[1])

    def test_agent_select_overlay(self) -> None:
        async def build() -> list:
            ctx = ValorantContext(None, None)
            ctx.slot, ctx.team, ctx.server = 1, 0, object()
            ctx.settings = {"agents": ["Jett", "Sage", "Omen"], "thresholds": {"Kills": [10]},
                            "progress_mode": "cumulative", "radianite_total": 10, "radianite_required": 8,
                            "allowed_queues": ["Unrated"]}
            ctx.progress = Progress(start_ms=1)
            ctx.items_received = [NetworkItem(ITEM_IDS[name], 0, 1, 0) for name in ("Jett", "Omen")]
            states = [ctx.companion_state()["pregame"]]  # in the menus
            ctx.session_state, ctx.pregame_id = "PREGAME", "p1"
            states.append(ctx.companion_state()["pregame"])  # nothing hovered yet
            for selection in (("Sage", "selected"), ("Reyna", "locked"), ("Jett", "selected")):
                ctx.pregame_selection = selection
                states.append(ctx.companion_state()["pregame"])
            ctx.server = None
            await ctx.shutdown()
            return states

        menus, empty, sage, reyna, jett = asyncio.run(build())
        self.assertIsNone(menus)
        self.assertEqual(empty, {"agent": None, "locked": False, "problem": "", "queue_problem": "",
                                 "unlocked": ["Jett", "Omen"]})
        self.assertEqual((sage["agent"], sage["locked"], sage["problem"]), ("Sage", False, "Sage is still locked"))
        self.assertEqual((reyna["locked"], reyna["problem"]), (True, "Reyna isn't one of this world's agents"))
        self.assertEqual(jett["problem"], "")

    def test_agent_select_from_game_events(self) -> None:
        """The overlay follows your pick from the live game events, and Riot isn't polled for it any more."""
        sent: list[dict] = []

        class Companion:
            async def send(self, message: str) -> None:
                sent.append(json.loads(message)["pregame"])

        async def run() -> tuple:
            ctx = ValorantContext(None, None)
            ctx.slot, ctx.team, ctx.server = 1, 0, object()
            ctx.settings = {"agents": ["Jett", "Sage"], "thresholds": {"Kills": [10]}, "progress_mode": "cumulative",
                            "radianite_total": 10, "radianite_required": 8, "allowed_queues": ["Unrated"]}
            ctx.progress = Progress(start_ms=1)
            ctx.items_received = [NetworkItem(ITEM_IDS["Jett"], 0, 1, 0)]
            ctx.companion_clients, ctx.companion_sockets = 1, {Companion()}

            async def feed(feature: str, key: str, value) -> None:
                await ctx.on_live_change(ctx.live.handle({"kind": "info", "feature": feature, "key": key,
                                                          "value": value}))

            def me(character: str, locked: bool) -> str:
                return json.dumps({"name": "Me#1", "character": character, "locked": locked, "local": True})

            await feed("game_info", "scene", "CharacterSelectPersistentLevel")
            await feed("match_info", "roster_0", me("Sage", False))
            await feed("match_info", "roster_0", me("Jett", True))
            ctx.session_state = "PREGAME"
            with mock.patch.object(ctx, "read_pregame", new=mock.AsyncMock()) as read_pregame:
                await ctx.watch_pregame(entered=False)
            ctx.server, ctx.companion_sockets = None, set()
            await ctx.shutdown()
            return read_pregame, ctx.pregame_selection

        with self.assertLogs("Client", "INFO") as logs:
            read_pregame, selection = asyncio.run(run())
        empty, sage, jett = sent
        self.assertEqual((empty["agent"], empty["unlocked"]), (None, ["Jett"]))
        self.assertEqual((sage["agent"], sage["locked"], sage["problem"]), ("Sage", False, "Sage is still locked"))
        self.assertEqual((jett["agent"], jett["locked"], jett["problem"]), ("Jett", True, ""))
        self.assertEqual(selection, ("Jett", "locked"))
        read_pregame.assert_not_called()
        self.assertTrue(any("following your pick through the live game events (hovering Sage)" in line
                            for line in logs.output))
        self.assertTrue(any("You are hovering Sage, but Sage is still locked" in line for line in logs.output))

    def test_state_before_connecting(self) -> None:
        async def build() -> dict:
            ctx = ValorantContext(None, None)
            state = ctx.companion_state()
            await ctx.shutdown()
            return state

        self.assertEqual(asyncio.run(build()), {"kind": "state", "connected": False})


class TestWeaponShop(unittest.TestCase):
    def make_context(self, credits: int) -> ValorantContext:
        ctx = ValorantContext(None, None)
        ctx.slot, ctx.team = 1, 0
        ctx.riot.puuid = "a1"
        ctx.send_msgs = mock.AsyncMock()  # no server: saving progress and sending checks go nowhere
        ctx.settings = {"agents": ["Jett"], "thresholds": {"Kills": [1]}, "progress_mode": "cumulative",
                        "radianite_total": 10, "radianite_required": 8, "allowed_queues": ["Competitive"],
                        "weapon_unlocks": True, "weapon_enforcement": "strict", "trade_window_ms": 5000,
                        "shop": {"prices": dict(DEFAULT_RENTAL_PRICES)}}
        ctx.progress = Progress(start_ms=1)
        ctx.items_received = [NetworkItem(ITEM_IDS["Jett"], 0, 1, 0)] + \
            [NetworkItem(ITEM_IDS["Kingdom Credits"], 0, 1, 0)] * credits
        return ctx

    def test_buying_and_refunding(self) -> None:
        async def run() -> list:
            ctx = self.make_context(credits=7)
            results = [await ctx.rent_weapon("vandal"), ctx.credit_balance(),
                       await ctx.rent_weapon("Vandal"),  # already rented
                       await ctx.rent_weapon("Operator"),  # 5 credits, only 2 left
                       await ctx.rent_weapon("Laser"),  # not a weapon
                       await ctx.rent_weapon("Ghost"), ctx.credit_balance(),
                       ctx.shop_view(),
                       await ctx.refund_rental("ghost"), ctx.credit_balance()]
            await ctx.shutdown()
            return results

        with self.assertLogs("Client", "INFO") as logs:
            (rented, after_vandal, twice, too_expensive, unknown, ghost, after_ghost, view, refunded,
             after_refund) = asyncio.run(run())
        self.assertEqual((rented, after_vandal, twice, too_expensive, unknown), (True, 2, False, False, False))
        self.assertEqual((ghost, after_ghost, refunded, after_refund), (True, 0, True, 2))
        self.assertTrue(any("The Operator costs 5 Kingdom Credits and you have 2." in line for line in logs.output))
        rifles = next(group for group in view["groups"] if group["category"] == "Rifle")
        vandal = next(weapon for weapon in rifles["weapons"] if weapon["name"] == "Vandal")
        self.assertEqual((rifles["price"], vandal["rented"], view["pending"]), (5, True, ["Vandal", "Ghost"]))

    def test_rented_weapon_counts_for_one_match(self) -> None:
        async def run() -> dict:
            ctx = self.make_context(credits=5)
            ctx.progress.rent("Vandal", 5, bought_ms=500)
            kills = [kill(0, 1000, "a1", "e1", VANDAL), kill(1, 1000, "a1", "e2", VANDAL)]
            first = make_match(kills, ["Blue", "Blue"])  # starts at 1000, after the purchase
            second = make_match(kills, ["Blue", "Blue"])
            second["matchInfo"].update({"matchId": "m2", "gameStartMillis": 2000})
            await ctx.process_official(first)
            await ctx.process_official(second)
            state = dict(ctx.progress.matches)
            await ctx.shutdown()
            return state

        with self.assertLogs("Client", "INFO"):
            matches = asyncio.run(run())
        self.assertTrue(matches["m1"]["counted"])  # strict mode doesn't void the match for the rented Vandal
        self.assertEqual(matches["m1"]["stats"]["kills"], 2)
        self.assertFalse(matches["m2"]["counted"])  # the rental was used up: the Vandal is locked again
        self.assertIn("locked weapons (Vandal)", matches["m2"]["reason"])
