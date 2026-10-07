import json
import unittest

from ..client.live import LiveTracker
from ..data import AGENT_CODENAMES, LIVE_WEAPON_IDS


def info(feature: str, key: str, value, ts: int = 0) -> dict:
    return {"kind": "info", "feature": feature, "category": feature, "key": key, "value": value, "ts": ts}


def event(feature: str, key: str, value, ts: int = 0) -> dict:
    return {"kind": "event", "feature": feature, "key": key, "value": value, "ts": ts}


def feed(attacker: str, victim: str, ally_attacker: bool, ally_victim: bool, weapon: str = "TX_Hud_Volcano") -> str:
    return json.dumps({"attacker": attacker, "victim": victim, "is_attacker_teammate": ally_attacker,
                       "is_victim_teammate": ally_victim, "weapon": weapon, "ult": "", "headshot": False})


class TestLiveTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.live = LiveTracker(LIVE_WEAPON_IDS, AGENT_CODENAMES)
        self.send(info("me", "player_name", "Doom#5339"))
        self.send(info("me", "agent", "Wushu_PC_C"))
        self.send(event("match_info", "match_start", ""))
        self.send(info("match_info", "match_id", "riot-match-1"))
        self.send(info("match_info", "game_mode", json.dumps({"mode": "bomb", "custom": False, "ranked": "1"})))
        for index in range(10):
            entry = {"name": "Doom #5339" if index == 0 else f"P{index} #TAG", "teammate": index < 5,
                     "is_local": index == 0, "alive": True, "kills": 0, "deaths": 0, "assists": 0}
            self.send(info("match_info", f"scoreboard_{index}", json.dumps(entry)))

    def send(self, message: dict) -> set[str]:
        return self.live.handle(message)

    def kill_feed(self, ts: int, *args, both: bool = False) -> set[str]:
        changes = self.send(event("match_info", "kill_feed", feed(*args), ts))
        if both:  # GEP sends each kill as an event *and* an info update
            changes |= self.send(info("match_info", "kill_feed", feed(*args), ts + 5))
        return changes

    def test_identity_and_queue(self) -> None:
        self.assertEqual(self.live.agent, "Jett")
        self.assertEqual(self.live.my_name, "doom")
        self.assertEqual(self.live.key, "riot-match-1")
        self.assertEqual(self.live.queue_guess(), "competitive")

    def test_trade_3k_ace_and_clutch(self) -> None:
        self.send(info("match_info", "round_number", "1"))
        self.send(info("match_info", "round_phase", "combat"))
        for n in range(1, 5):  # all four teammates die
            self.kill_feed(1000 * n, f"P{n + 4}", f"P{n}", False, True, both=True)
        self.assertIn("kill", self.kill_feed(4500, "Doom", "P8", True, False, both=True))  # trade: P8 just killed P4
        for n, victim in enumerate(["P5", "P6", "P7", "P9"]):
            self.kill_feed(10000 + 1000 * n, "Doom", victim, True, False)
        self.send(info("match_info", "score", json.dumps({"won": 1, "lost": 0})))

        stats = self.live.stats()
        self.assertEqual(stats["kills"], 5)
        self.assertEqual((stats["trades"], stats["three_ks"], stats["aces"], stats["clutches"]), (1, 1, 1, 1))

    def test_lost_round_no_clutch_and_locked_weapon(self) -> None:
        self.send(info("match_info", "round_number", "1"))
        for n in range(1, 5):
            self.kill_feed(1000 * n, f"P{n + 4}", f"P{n}", False, True)
        self.kill_feed(6000, "Doom", "P5", True, False, "TX_Hud_Operator")
        self.kill_feed(7000, "Doom", "P6", True, False, "TX_Hud_Pistol_Glock_S")  # Classic is always fine
        self.send(info("match_info", "score", json.dumps({"won": 0, "lost": 1})))
        stats = self.live.stats(weapon_allowed=lambda name, _when: name != "Operator")
        self.assertEqual(stats["kills"], 1)
        self.assertEqual(stats["locked_kills"], 1)
        self.assertEqual(stats["locked_weapons"], ["Operator"])
        self.assertEqual(stats["clutches"], 0)

    def test_counters_and_match_end(self) -> None:
        self.send(info("kill", "assists", 3))
        self.send(info("death", "deaths", 2))
        self.send(event("kill", "kill", 4))
        self.assertEqual(self.live.stats()["wins"], 0)
        self.assertIn("match_end", self.send(info("match_info", "match_outcome", "victory")))
        stats = self.live.stats()
        self.assertEqual((stats["kills"], stats["deaths"], stats["assists"]), (4, 2, 3))  # nothing attributed: counter
        self.assertEqual(stats["wins"], 1)
        self.assertTrue(self.live.ended)

    def test_new_match_resets(self) -> None:
        self.kill_feed(1000, "Doom", "P5", True, False)
        self.send(info("match_info", "match_outcome", "defeat"))
        self.send(info("match_info", "match_id", "riot-match-2"))
        self.assertEqual(self.live.key, "riot-match-2")
        self.assertFalse(self.live.ended)
        self.assertEqual(self.live.stats()["kills"], 0)

    def test_deathmatch_has_no_multikills(self) -> None:
        self.send(info("match_info", "game_mode", json.dumps({"mode": "Deathmatch", "custom": False})))
        for n in range(5):
            self.kill_feed(1000 * n, "Doom", f"P{n + 5}", True, False)
        stats = self.live.stats()
        self.assertEqual((stats["kills"], stats["aces"], stats["three_ks"]), (5, 0, 0))
        self.assertEqual(self.live.queue_guess(), "deathmatch")


class TestAgentSelect(unittest.TestCase):
    def test_pick_from_roster(self) -> None:
        live = LiveTracker(LIVE_WEAPON_IDS, AGENT_CODENAMES)
        self.assertEqual(live.handle(info("game_info", "scene", "CharacterSelectPersistentLevel")), {"scene"})
        self.assertTrue(live.in_agent_select)

        def roster(character: str, locked: str, local: str = "true") -> set:
            entry = {"name": "Me#1", "character": character, "locked": locked, "local": local, "teammate": "true"}
            return live.handle(info("match_info", "roster_3", json.dumps(entry)))

        self.assertEqual(roster("Sage", "false", local="false"), set())  # a teammate
        self.assertIsNone(live.pick)
        self.assertEqual(roster("Omen", "false"), {"pick"})  # hovering, by name
        self.assertEqual(live.pick, ("Omen", False))
        self.assertEqual(roster("Omen", "false"), set())
        self.assertEqual(roster("Wushu", "false"), {"pick"})  # by codename
        self.assertEqual(roster("Wushu_PC_C", "true"), {"pick"})  # by ID, locked in
        self.assertEqual(live.pick, ("Jett", True))
        self.assertEqual(roster("", "false"), set())  # nothing picked: keep the last pick

        live.handle(info("game_info", "scene", "MainMenu"))
        self.assertFalse(live.in_agent_select)
        live.handle(info("game_info", "scene", "CharacterSelectPersistentLevel"))
        self.assertIsNone(live.pick)  # a new agent select starts empty
        live.handle({"kind": "game_exit"})
        self.assertEqual((live.scene, live.pick), ("", None))


class TestLiveRoundStarts(unittest.TestCase):
    def test_weapons_are_checked_at_the_start_of_combat(self) -> None:
        live = LiveTracker(LIVE_WEAPON_IDS, AGENT_CODENAMES)
        live.handle(info("me", "player_name", "Doom"))
        live.handle(event("match_info", "match_start", "", ts=1000))
        live.handle(info("match_info", "round_number", "1", ts=2000))
        live.handle(info("match_info", "round_phase", "combat", ts=32000))
        feed_entry = {"attacker": "Doom", "victim": "P6", "is_attacker_teammate": True, "is_victim_teammate": False,
                      "weapon": "TX_Hud_Volcano"}
        live.handle(info("match_info", "kill_feed", json.dumps(feed_entry), ts=40000))
        seen = []
        live.stats(lambda name, round_start: seen.append((name, round_start)) or True)
        self.assertEqual(seen, [("Vandal", 32000)])
