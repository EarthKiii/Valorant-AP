import unittest

from ..client.stats import compute_match_stats, match_overview
from ..data import WEAPON_BY_NAME, map_display_name, queue_display_name

ME = "a1"
VANDAL = WEAPON_BY_NAME["Vandal"].uuid.upper()  # Riot sometimes sends upper-case UUIDs
PHANTOM = WEAPON_BY_NAME["Phantom"].uuid


def kill(round_number: int, time: int, killer: str, victim: str, weapon: str | None = VANDAL) -> dict:
    damage = {"damageType": "Weapon", "damageItem": weapon} if weapon else {"damageType": "Ability",
                                                                          "damageItem": "Ultimate"}
    return {"round": round_number, "roundTime": time, "killer": killer, "victim": victim, "finishingDamage": damage}


def make_match(kills: list[dict], winners: list[str], deaths: int = 2) -> dict:
    players = [{"subject": f"a{i}", "teamId": "Blue", "characterId": "add6443a-41bd-e414-f6ad-e58d267f4e95",
                "stats": {"kills": 99, "deaths": deaths if i == 1 else 0, "assists": 4, "score": 50 * len(winners),
                          "roundsPlayed": len(winners)}} for i in range(1, 6)]
    players += [{"subject": f"e{i}", "teamId": "Red", "characterId": "x", "stats": {}} for i in range(1, 6)]
    return {
        "matchInfo": {"matchId": "m1", "queueID": "competitive", "mapId": "/Game/Maps/Bonsai/Bonsai",
                      "gameStartMillis": 1000, "isCompleted": True},
        "players": players,
        "roundResults": [{"roundNum": n, "winningTeam": team,
                          "playerStats": [{"subject": p["subject"], "economy": {"weapon": VANDAL}} for p in players]}
                         for n, team in enumerate(winners)],
        "teams": [{"teamId": "Blue", "won": winners.count("Blue") > winners.count("Red")},
                  {"teamId": "Red", "won": winners.count("Red") > winners.count("Blue")}],
        "kills": kills,
    }


# Round 0: a trade and a 3K (one of the kills is an ability kill).
# Round 1: all four teammates die, then we kill all five enemies: ace, 3K and clutch.
ROUND_0 = [
    kill(0, 1000, "e1", "a2"),
    kill(0, 3000, ME, "e1"),
    kill(0, 4000, ME, "e2", PHANTOM),
    kill(0, 5000, ME, "e3", None),
]
ROUND_1 = [kill(1, 1000 * n, f"e{n}", f"a{n + 1}") for n in range(1, 5)]
ROUND_1 += [kill(1, 10000 + 1000 * n, ME, victim) for n, victim in enumerate(["e5", "e1", "e2", "e3", "e4"])]


class TestQueueNames(unittest.TestCase):
    def test_queue_ids_seen_in_real_matches(self) -> None:
        self.assertEqual(queue_display_name("unrated"), "Unrated")
        self.assertEqual(queue_display_name("premier-seasonmatch"), "Premier")
        self.assertEqual(queue_display_name("skirmish2v2"), "Skirmish")
        self.assertEqual(queue_display_name(""), "Custom Games")
        self.assertEqual(queue_display_name("abilitydraftarena"), "Other Modes")
        self.assertEqual(map_display_name("/Game/Maps/Duel/Duel_Platform/Skirmish_D"), "Skirmish D")


class TestComputeMatchStats(unittest.TestCase):
    def test_full_match(self) -> None:
        stats = compute_match_stats(make_match(ROUND_0 + ROUND_1, ["Blue", "Blue"]), "A1")
        self.assertEqual(stats["kills"], 8)
        self.assertEqual(stats["deaths"], 2)
        self.assertEqual(stats["assists"], 4)
        self.assertEqual(stats["trades"], 1)
        self.assertEqual(stats["three_ks"], 2)
        self.assertEqual(stats["aces"], 1)
        self.assertEqual(stats["clutches"], 1)
        self.assertEqual(stats["locked_kills"], 0)

    def test_locked_weapon_kills_are_dropped(self) -> None:
        phantom_locked = lambda uuid, _when: uuid != PHANTOM
        stats = compute_match_stats(make_match(ROUND_0 + ROUND_1, ["Blue", "Blue"]), ME, phantom_locked)
        self.assertEqual(stats["kills"], 7)
        self.assertEqual(stats["three_ks"], 1)  # round 0 is down to two kills
        self.assertEqual(stats["trades"], 1)
        self.assertEqual(stats["locked_kills"], 1)
        self.assertEqual(stats["locked_weapons"], [PHANTOM])

    def test_carried_locked_weapon_is_reported(self) -> None:
        vandal_locked = lambda uuid, _when: uuid != VANDAL.lower()
        stats = compute_match_stats(make_match([], ["Blue", "Red"]), ME, vandal_locked)
        self.assertEqual(stats["locked_weapons"], [VANDAL.lower()])

    def test_lost_round_is_not_a_clutch(self) -> None:
        stats = compute_match_stats(make_match(ROUND_0 + ROUND_1, ["Blue", "Red"]), ME)
        self.assertEqual(stats["clutches"], 0)
        self.assertEqual(stats["aces"], 1)

    def test_teamkills_and_slow_revenge(self) -> None:
        kills = [kill(0, 1000, ME, "a2"), kill(0, 2000, "e1", "a3"), kill(0, 9000, ME, "e1")]
        stats = compute_match_stats(make_match(kills, ["Blue", "Blue"]), ME, trade_window_ms=5000)
        self.assertEqual(stats["kills"], 1)
        self.assertEqual(stats["trades"], 0)

    def test_single_round_modes_have_no_multikills(self) -> None:
        kills = [kill(0, 1000 * n, ME, f"e{n}") for n in range(1, 6)]
        stats = compute_match_stats(make_match(kills, ["Blue"]), ME)
        self.assertEqual(stats["kills"], 5)
        self.assertEqual((stats["aces"], stats["three_ks"], stats["clutches"]), (0, 0, 0))

    def test_official_api_format(self) -> None:
        """VAL-MATCH-V1 nests kills per round and uses timeSinceRoundStartMillis."""
        match = make_match([], ["Blue", "Blue"])
        del match["kills"]
        for entry in ROUND_0 + ROUND_1:
            converted = {k: v for k, v in entry.items() if k not in ("round", "roundTime")}
            converted["timeSinceRoundStartMillis"] = entry["roundTime"]
            stats_entry = next(p for p in match["roundResults"][entry["round"]]["playerStats"]
                               if p["subject"] == entry["killer"])
            stats_entry.setdefault("kills", []).append(converted)
        stats = compute_match_stats(match, ME)
        self.assertEqual((stats["kills"], stats["trades"], stats["aces"], stats["clutches"]), (8, 1, 1, 1))

    def test_win_and_combat_score(self) -> None:
        won = compute_match_stats(make_match([], ["Blue", "Blue", "Red"]), ME)
        self.assertEqual((won["wins"], won["score"], won["rounds"]), (1, 150, 3))
        lost = compute_match_stats(make_match([], ["Red", "Red", "Blue"]), ME)
        self.assertEqual(lost["wins"], 0)

    def test_performance_score(self) -> None:
        match = make_match([], ["Blue", "Blue"])
        self.assertEqual(compute_match_stats(match, ME)["performance"], 0)  # before patch 13.06
        # Shaped like Riot's 13.06 data: the score sits under a placeholder key next to its sub-scores.
        match["players"][0]["scores"] = {"TempValueF": 357.5, "TempValueG": 382.5, "TempValueH": 288.4,
                                         "TempValueA": 196.1, "TempValueL": {"TempValueO": "merit"}}
        self.assertEqual(compute_match_stats(match, ME)["performance"], 358)  # rounded like the scoreboard
        for broken in (None, "358", 9000, -1, True):
            match["players"][0]["scores"] = {"TempValueF": broken}
            self.assertEqual(compute_match_stats(match, ME)["performance"], 0)

    def test_unknown_player(self) -> None:
        self.assertIsNone(compute_match_stats(make_match([], ["Blue"]), "nobody"))

    def test_overview(self) -> None:
        overview = match_overview(make_match([], ["Blue"]), ME)
        self.assertEqual(overview["match_id"], "m1")
        self.assertEqual(overview["queue_id"], "competitive")
        self.assertEqual(overview["agent_uuid"], "add6443a-41bd-e414-f6ad-e58d267f4e95")
        self.assertTrue(overview["found"])


class TestRoundStarts(unittest.TestCase):
    def test_weapons_are_checked_at_the_start_of_their_round(self) -> None:
        kills = [dict(kill(0, 4000, ME, "e1"), gameTime=9000), dict(kill(0, 6000, ME, "e2"), gameTime=11000),
                 dict(kill(1, 2500, ME, "e3"), gameTime=40000)]
        match = make_match(kills, ["Blue", "Blue"])
        match["matchInfo"]["gameLengthMillis"] = 60000
        seen = []
        compute_match_stats(match, ME, lambda uuid, round_start: seen.append(round_start) or True)
        # gameStartMillis is 1000: round 0 started at 1000 + 9000 - 4000, round 1 at 1000 + 40000 - 2500
        self.assertEqual(sorted(set(seen)), [6000, 38500])
