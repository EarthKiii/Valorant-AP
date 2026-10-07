import unittest

from ..client.tracker import Progress, ShortModes

THRESHOLDS = {"Kills": [10, 25], "Assists": [5], "Trades": [], "Clutches": [1], "Aces": [1], "3Ks": [2], "K/D": [1.5],
              "Wins": [2], "ACS": [200], "Performance": [250, 350]}


def record(agent: str, source: str = "official", counted: bool = True, complete: bool = True,
           queue: str = "Competitive", **stats) -> dict:
    base = {"kills": 0, "deaths": 0, "assists": 0, "trades": 0, "clutches": 0, "aces": 0, "three_ks": 0, "wins": 0,
            "score": 0, "rounds": 0}
    return {"agent": agent, "source": source, "counted": counted, "complete": complete, "queue": queue,
            "stats": {**base, **stats}}


class TestProgress(unittest.TestCase):
    def test_cumulative(self) -> None:
        progress = Progress(start_ms=1)
        progress.record("m1", record("Jett", kills=12, deaths=10, assists=3))
        progress.record("m2", record("Jett", kills=14, deaths=20, assists=3))
        done = set(progress.completed(THRESHOLDS, ["Jett"], "cumulative"))
        self.assertEqual(done, {("Jett", "Kills", 1), ("Jett", "Kills", 2), ("Jett", "Assists", 1)})

    def test_single_match(self) -> None:
        progress = Progress(start_ms=1)
        progress.record("m1", record("Jett", kills=12, deaths=4, three_ks=2))
        progress.record("m2", record("Jett", kills=14, deaths=20))
        done = set(progress.completed(THRESHOLDS, ["Jett"], "single_match"))
        self.assertEqual(done, {("Jett", "Kills", 1), ("Jett", "3Ks", 1), ("Jett", "K/D", 1)})

    def test_wins_always_add_up_and_acs_is_best_match(self) -> None:
        progress = Progress(start_ms=1)
        progress.record("m1", record("Jett", wins=1, score=3900, rounds=20))  # ACS 195
        progress.record("m2", record("Jett", wins=1, score=4410, rounds=21))  # ACS 210
        done = set(progress.completed(THRESHOLDS, ["Jett"], "single_match"))
        self.assertIn(("Jett", "Wins", 1), done)
        self.assertIn(("Jett", "ACS", 1), done)
        self.assertEqual(progress.totals("cumulative")["Jett"]["ACS"], 210)

    def test_performance_score_is_best_finished_match(self) -> None:
        progress = Progress(start_ms=1)
        progress.record("m1", record("Jett", performance=212))
        progress.record("m2", record("Jett", performance=358))
        progress.record("m3", record("Jett", source="live", complete=False, performance=400))  # live has none anyway
        self.assertEqual(progress.totals("cumulative")["Jett"]["Performance"], 358)
        self.assertIn(("Jett", "Performance", 2), set(progress.completed(THRESHOLDS, ["Jett"], "single_match")))
        old = Progress(start_ms=1)
        old.record("m1", record("Jett", kills=1))  # stored before Performance Score existed
        self.assertEqual(old.totals("cumulative")["Jett"]["Performance"], 0)

    def test_live_record_has_no_acs(self) -> None:
        live = record("Jett", source="live", complete=True, wins=1, kills=30)
        totals = Progress(start_ms=1).totals("cumulative", [live])
        self.assertEqual((totals["Jett"]["Wins"], totals["Jett"]["ACS"]), (1, 0))

    def test_uncounted_and_other_agents_ignored(self) -> None:
        progress = Progress(start_ms=1)
        progress.record("m1", record("Jett", counted=False, kills=50))
        progress.record("m2", record("Sage", kills=50))
        self.assertEqual(progress.completed(THRESHOLDS, ["Jett"], "cumulative"), [])

    def test_live_kd_waits_for_match_end(self) -> None:
        progress = Progress(start_ms=1)
        live = record("Jett", source="live", complete=False, kills=10, deaths=1, aces=1)
        done = set(progress.completed(THRESHOLDS, ["Jett"], "cumulative", [live]))
        self.assertIn(("Jett", "Aces", 1), done)
        self.assertNotIn(("Jett", "K/D", 1), done)

    def test_official_replaces_live(self) -> None:
        progress = Progress(start_ms=1)
        self.assertTrue(progress.record("m1", record("Jett", source="live", kills=30)))
        self.assertTrue(progress.record("m1", record("Jett", kills=28)))
        self.assertFalse(progress.record("m1", record("Jett", source="live", kills=30)))
        self.assertEqual(progress.totals("cumulative")["Jett"]["Kills"], 28)

    def test_overview_orders_unlocked_first_and_counts_tiers(self) -> None:
        progress = Progress(start_ms=1)
        progress.record("m1", record("Sage", kills=30, assists=2))
        rows = progress.overview(THRESHOLDS, ["Jett", "Sage", "Omen"], "cumulative", unlocked={"Sage"},
                                 checked={("Jett", "Assists", 1)})
        self.assertEqual([(row["name"], row["unlocked"]) for row in rows],
                         [("Sage", True), ("Jett", False), ("Omen", False)])
        sage = {stat["stat"]: stat for stat in rows[0]["stats"]}
        self.assertEqual((sage["Kills"]["value"], sage["Kills"]["done"]), (30, 2))
        self.assertNotIn("Trades", sage)  # stats without thresholds are left out
        jett = {stat["stat"]: stat for stat in rows[1]["stats"]}
        self.assertEqual(jett["Assists"]["done"], 1)  # already checked on the server (e.g. !collect)

    def test_json_round_trip_and_merge(self) -> None:
        first = Progress(start_ms=500)
        first.record("m1", record("Jett", source="live", kills=5))
        second = Progress(first.to_json())
        second.record("m2", record("Jett", kills=7))
        first.record("m1", record("Jett", kills=6))
        merged = Progress(second.to_json())
        merged.merge(first)
        self.assertEqual(merged.start_ms, 500)
        self.assertEqual(merged.totals("cumulative")["Jett"]["Kills"], 13)


# 75% of THRESHOLDS' Kills and Assists, as the world sends them.
SHORT = ShortModes({"percent": 75, "queues": ["Swiftplay", "Spike Rush"],
                    "thresholds": {"Kills": [8, 19], "Assists": [4]}})


class TestShortModes(unittest.TestCase):
    def done(self, mode: str, *records: dict, short: ShortModes = SHORT) -> set:
        progress = Progress(start_ms=1)
        for index, match in enumerate(records):
            progress.record(f"m{index}", match)
        done = progress.completed(THRESHOLDS, ["Jett"], mode, short_modes=short)
        return {check for check in done if check[1] in ("Kills", "Assists")}  # K/D would be done with 0 deaths

    def test_lowered_thresholds_are_exact(self) -> None:
        self.assertEqual(self.done("cumulative", record("Jett", queue="Spike Rush", kills=7)), set())
        self.assertEqual(self.done("cumulative", record("Jett", queue="Spike Rush", kills=8)), {("Jett", "Kills", 1)})
        self.assertNotIn(("Jett", "Kills", 2), self.done("cumulative", record("Jett", queue="Swiftplay", kills=18)))
        self.assertIn(("Jett", "Kills", 2), self.done("cumulative", record("Jett", queue="Swiftplay", kills=19)))

    def test_modes_mix_proportionally(self) -> None:
        mixed = (record("Jett", kills=15), record("Jett", queue="Swiftplay", kills=8))  # 15 + 8 * 4/3 = 25.67
        self.assertIn(("Jett", "Kills", 2), self.done("cumulative", *mixed))
        self.assertNotIn(("Jett", "Kills", 2), self.done("cumulative", *mixed, short=ShortModes()))

    def test_single_match_uses_the_lowered_threshold_per_match(self) -> None:
        regular, short = record("Jett", kills=9), record("Jett", queue="Spike Rush", kills=7)
        self.assertEqual(self.done("single_match", regular, short), set())
        self.assertEqual(self.done("single_match", record("Jett", queue="Spike Rush", kills=8)), {("Jett", "Kills", 1)})

    def test_other_stats_and_modes_are_unaffected(self) -> None:
        progress = Progress(start_ms=1)
        progress.record("m1", record("Jett", queue="Spike Rush", wins=1, trades=3, three_ks=1))
        progress.record("m2", record("Jett", queue="Deathmatch", kills=9))
        totals = progress.totals("cumulative", short_modes=SHORT)["Jett"]
        self.assertEqual((totals["Wins"], totals["Trades"], totals["3Ks"], totals["Kills"]), (1, 3, 1, 9))

    def test_overview_lists_lowered_tiers_and_what_is_left(self) -> None:
        progress = Progress(start_ms=1)
        progress.record("m1", record("Jett", kills=15))
        stats = {stat["stat"]: stat for stat in progress.overview(THRESHOLDS, ["Jett"], "cumulative", {"Jett"},
                                                                  short_modes=SHORT)[0]["stats"]}
        self.assertEqual(stats["Kills"]["short_tiers"], [8, 19])
        self.assertEqual(stats["Kills"]["short_needed"], 8)  # 15 + 8 * 4/3 >= 25, 15 + 7 * 4/3 < 25
        self.assertEqual(SHORT.needed(stats["Kills"]["value"], 25, short=False), 10)
        self.assertEqual(stats["Assists"]["short_needed"], 4)
        self.assertNotIn("short_tiers", stats["3Ks"])
        single = progress.overview(THRESHOLDS, ["Jett"], "single_match", {"Jett"}, short_modes=SHORT)[0]["stats"]
        self.assertNotIn("short_needed", single[0])  # nothing carries over between matches

    def test_off_when_percent_is_100(self) -> None:
        full = ShortModes({"percent": 100, "queues": ["Swiftplay"], "thresholds": {"Kills": [10]}})
        self.assertEqual(full.thresholds, {})
        self.assertEqual(ShortModes(None).thresholds, {})


class TestRentals(unittest.TestCase):
    def test_rental_is_used_on_the_next_match(self) -> None:
        progress = Progress(start_ms=1)
        progress.rent("Vandal", 4, bought_ms=1000)
        self.assertEqual(progress.spent(), 4)
        self.assertEqual(progress.bind_rentals("before", before_ms=900), [])  # ended before the purchase
        self.assertEqual(progress.bind_rentals("next", before_ms=1500), ["Vandal"])
        self.assertEqual(progress.bind_rentals("after", before_ms=2000), [])  # already used
        self.assertEqual(progress.rented_for("next"), {"Vandal": 1000})  # kills after the purchase count
        self.assertEqual(progress.rented_for("after"), {})
        self.assertEqual(progress.pending_rentals(), {})

    def test_refund_only_unused_rentals(self) -> None:
        progress = Progress(start_ms=1)
        used = progress.rent("Vandal", 4, bought_ms=1000)
        progress.bind_rentals("m1", before_ms=1500)
        unused = progress.rent("Ghost", 1, bought_ms=2000)
        self.assertFalse(progress.refund(used))
        self.assertTrue(progress.refund(unused))
        self.assertFalse(progress.refund(unused))
        self.assertEqual(progress.spent(), 4)

    def test_rentals_survive_json_and_merge(self) -> None:
        first = Progress(start_ms=1)
        bought = first.rent("Vandal", 4, bought_ms=1000)
        refunded = first.rent("Ghost", 1, bought_ms=1600)  # bought after m1 started
        second = Progress(first.to_json())
        first.bind_rentals("m1", before_ms=1500)  # this copy used the Vandal...
        second.refund(refunded)  # ...and that one refunded the Ghost
        second.rent("Odin", 3, bought_ms=1200)
        merged = Progress(second.to_json())
        merged.merge(first)
        self.assertEqual(merged.rented_for("m1"), {"Vandal": 1000})  # a rental used in a match stays paid
        self.assertTrue(merged.rentals[refunded]["refunded"])
        self.assertEqual([r["weapon"] for r in merged.pending_rentals().values()], ["Odin"])
        self.assertEqual(merged.spent(), 7)
        self.assertEqual(merged.rentals[bought]["match"], "m1")


class TestReceivedTimes(unittest.TestCase):
    def test_noted_saved_and_merged(self) -> None:
        progress = Progress(start_ms=1)
        self.assertTrue(progress.note_received(3, now_ms=1000))
        self.assertEqual(progress.received_ms, [0, 0, 0])  # already owned when first noted
        self.assertTrue(progress.note_received(5, now_ms=2000))
        self.assertFalse(progress.note_received(5, now_ms=3000))  # a reconnect resends the same items
        self.assertEqual(progress.received_ms, [0, 0, 0, 2000, 2000])
        other = Progress(progress.to_json())
        other.note_received(6, now_ms=4000)
        other.received_ms[3] = 2500
        progress.merge(other)
        self.assertEqual(progress.received_ms, [0, 0, 0, 2000, 2000, 4000])  # earliest sighting wins
        self.assertIsNone(Progress({"matches": {}}).received_ms)  # older saves have none yet
