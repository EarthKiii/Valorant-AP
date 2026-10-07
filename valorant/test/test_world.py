from BaseClasses import LocationProgressType

from ..data import GOAL_ITEM, PRIMARY_WEAPON_NAMES, WEAPON_NAMES, describe_short_modes, location_name
from .bases import ValorantTestBase


class TestDefaults(ValorantTestBase):
    def test_item_and_location_counts_match(self) -> None:
        locations = [loc for loc in self.multiworld.get_locations(self.player) if loc.address is not None]
        items = [item for item in self.multiworld.itempool if item.player == self.player]
        self.assertEqual(len(locations), len(items))

    def test_goal_items_present(self) -> None:
        crystals = [item for item in self.multiworld.itempool if item.name == GOAL_ITEM]
        self.assertEqual(len(crystals), self.world.radianite_total)
        self.assertLessEqual(self.world.radianite_required, self.world.radianite_total)

    def test_performance_checks_replace_acs(self) -> None:
        names = {loc.name for loc in self.multiworld.get_locations(self.player)}
        agent = self.world.agents[0]
        self.assertIn(location_name(agent, "Performance", 2), names)
        self.assertNotIn(location_name(agent, "ACS", 1), names)

    def test_aces_excluded_by_default(self) -> None:
        for agent in self.world.agents:
            location = self.multiworld.get_location(location_name(agent, "Aces", 1), self.player)
            self.assertEqual(location.progress_type, LocationProgressType.EXCLUDED)

    def test_slot_data(self) -> None:
        slot_data = self.world.fill_slot_data()
        self.assertEqual(slot_data["agents"], self.world.agents)
        self.assertEqual(slot_data["thresholds"]["Kills"], [10, 15, 20])
        self.assertEqual(slot_data["trade_window_ms"], 5000)
        self.assertEqual(slot_data["thresholds"]["Wins"], [1, 2])
        self.assertEqual(slot_data["thresholds"]["Performance"], [250, 350])
        self.assertEqual(slot_data["thresholds"]["ACS"], [])  # replaced by Performance Score in patch 13.06
        self.assertEqual(slot_data["short_modes"], {  # 75% in short modes by default
            "percent": 75,
            "queues": ["Swiftplay", "Spike Rush"],
            "thresholds": {"Kills": [8, 12, 15], "Assists": [4, 8, 12], "Trades": [2, 4, 8]},
        })
        precollected = {item.name for item in self.multiworld.precollected_items[self.player]}
        self.assertEqual(len(precollected & set(self.world.agents)), 3)  # three starting agents


class TestAgentAndWeaponLogic(ValorantTestBase):
    options = {
        "agent_pool": ["Jett", "Sage"],
        "agent_count": 2,
        "starting_agents": 1,
        "starting_weapons": 0,
    }

    def test_agent_required(self) -> None:
        self.assertEqual(self.world.agents, ["Sage", "Jett"])
        starter = next(name for name in self.world.starting_items if name in self.world.agents)
        other = "Sage" if starter == "Jett" else "Jett"
        self.assertTrue(self.can_reach_location(f"{starter} - Kills Tier 1"))
        self.assertTrue(self.can_reach_location(f"{starter} - Wins Tier 1"))
        self.assertTrue(self.can_reach_location(f"{starter} - Performance Tier 1"))
        self.assertFalse(self.can_reach_location(f"{other} - Kills Tier 1"))
        self.collect_by_name(other)
        self.assertTrue(self.can_reach_location(f"{other} - Kills Tier 1"))

    def test_weapons_required_for_higher_tiers(self) -> None:
        self.collect_by_name(["Jett", "Sage"])
        self.assertFalse(self.can_reach_location("Jett - Kills Tier 2"))
        self.assertFalse(self.can_reach_location("Jett - 3Ks Tier 1"))
        self.collect_by_name("Vandal")
        self.assertTrue(self.can_reach_location("Jett - Kills Tier 2"))
        self.assertTrue(self.can_reach_location("Jett - 3Ks Tier 1"))
        self.assertFalse(self.can_reach_location("Jett - Kills Tier 3"))
        self.collect_by_name("Sheriff")  # sidearms don't count towards weapon logic
        self.assertFalse(self.can_reach_location("Jett - Kills Tier 3"))
        self.collect_by_name("Operator")
        self.assertTrue(self.can_reach_location("Jett - Kills Tier 3"))


class TestForcedStartingAgent(ValorantTestBase):
    # Core precollects start inventory during real generation; the test harness doesn't, so also start with
    # one random agent to keep the generic reachability tests meaningful.
    options = {"agent_pool": ["Sage"], "agent_count": 2, "starting_agents": 2,
               "start_inventory_from_pool": {"Jett": 1}}

    def test_forced_agent_is_included_and_counts_as_starting(self) -> None:
        self.assertEqual(self.world.agents, ["Sage", "Jett"])
        self.assertEqual([name for name in self.world.starting_items if name in self.world.agents], ["Sage"])
        self.assertIn("Jett", [item.name for item in self.multiworld.itempool])  # core removes it from the pool


class TestNoWeapons(ValorantTestBase):
    options = {"weapon_unlocks": False, "agent_count": 3}

    def test_no_weapon_items(self) -> None:
        names = {item.name for item in self.multiworld.itempool}
        self.assertFalse(names & set(WEAPON_NAMES))


class TestTinyWorld(ValorantTestBase):
    """Fewer checks than unlocks: the surplus has to become starting items."""
    options = {
        "agent_count": 1,
        "kill_thresholds": [5],
        "assist_thresholds": [],
        "trade_thresholds": [],
        "clutch_thresholds": [],
        "ace_thresholds": [],
        "three_k_thresholds": [],
        "kd_thresholds": [1.0],
        "win_thresholds": [],
        "performance_thresholds": [],
        "starting_weapons": 0,
    }

    def test_surplus_becomes_start_inventory(self) -> None:
        self.assertEqual(self.world.radianite_total, 1)
        precollected = {item.name for item in self.multiworld.precollected_items[self.player]}
        self.assertTrue(precollected & set(WEAPON_NAMES))


class TestOnlyMultiKillChecks(ValorantTestBase):
    """No weapon-free checks: the world must hand out a starting primary so something is reachable."""
    options = {
        "kill_thresholds": [],
        "assist_thresholds": [],
        "trade_thresholds": [],
        "kd_thresholds": [],
        "win_thresholds": [],
        "performance_thresholds": [],
        "starting_weapons": 0,
        "excluded_stats": [],
    }

    def test_starting_primary_given(self) -> None:
        precollected = {item.name for item in self.multiworld.precollected_items[self.player]}
        self.assertTrue(precollected & set(PRIMARY_WEAPON_NAMES))


class TestSingleMatchKD(ValorantTestBase):
    options = {"progress_mode": "single_match", "kd_thresholds": [2, 1.25, 1.25], "allowed_queues": ["Deathmatch"]}

    def test_thresholds_cleaned(self) -> None:
        self.assertEqual(self.world.thresholds["K/D"], [1.25, 2])
        self.assertEqual(self.world.fill_slot_data()["allowed_queues"], ["Deathmatch"])


class TestShortModes(ValorantTestBase):
    options = {"short_mode_thresholds": 75, "kill_thresholds": [10, 15, 20], "assist_thresholds": [5, 10, 15],
               "trade_thresholds": []}

    def test_lowered_thresholds_in_slot_data(self) -> None:
        self.assertEqual(self.world.fill_slot_data()["short_modes"], {
            "percent": 75,
            "queues": ["Swiftplay", "Spike Rush"],
            "thresholds": {"Kills": [8, 12, 15], "Assists": [4, 8, 12]},
        })

    def test_listed_in_spoiler(self) -> None:
        self.assertEqual(describe_short_modes(self.world.short_modes),
                         "Swiftplay & Spike Rush need 75% of the regular thresholds: Kills 8 / 12 / 15, "
                         "Assists 4 / 8 / 12 (each kill or assist there counts ×1.33)")


class TestShortModesOnlyForAllowedQueues(ValorantTestBase):
    options = {"short_mode_thresholds": 50, "allowed_queues": ["Competitive", "Spike Rush"]}

    def test_only_allowed_short_modes(self) -> None:
        short_modes = self.world.fill_slot_data()["short_modes"]
        self.assertEqual(short_modes["queues"], ["Spike Rush"])
        self.assertEqual(short_modes["thresholds"]["Trades"], [1, 3, 5])


class TestShortModesWithoutShortQueues(ValorantTestBase):
    options = {"short_mode_thresholds": 75, "allowed_queues": ["Competitive"]}

    def test_off(self) -> None:
        self.assertIsNone(self.world.fill_slot_data()["short_modes"])


class TestWeaponShop(ValorantTestBase):
    options = {"rental_prices": {"Rifle": 6, "Sniper": 0}}

    def test_prices_in_slot_data(self) -> None:
        prices = self.world.fill_slot_data()["shop"]["prices"]
        self.assertEqual(prices, {"Sidearm": 2, "SMG": 3, "Shotgun": 3, "Rifle": 6, "Sniper": 0, "Heavy": 4})

    def test_bad_price_is_rejected(self) -> None:
        from Options import OptionError
        from ..options import RentalPrices, clean_rental_prices
        with self.assertRaises(OptionError):
            clean_rental_prices(RentalPrices({"Rifle": -1}), "Tester")


class TestNoShopWithoutEnforcement(ValorantTestBase):
    options = {"weapon_enforcement": "off"}

    def test_off(self) -> None:
        self.assertIsNone(self.world.fill_slot_data()["shop"])
