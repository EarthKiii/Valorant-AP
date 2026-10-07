"""
Keeps every match result for one slot and turns them into completed checks.

A match record looks like:
    {"agent": "Jett", "counted": True, "reason": "", "source": "official" | "live",
     "complete": True, "time": 1712345678000, "queue": "Competitive", "map": "Ascent",
     "stats": {"kills": 21, "deaths": 14, "wins": 1, "score": 4830, "rounds": 21, "performance": 312, ...}}

Live records (from the companion app) are replaced by the official record for the same match once
Riot publishes it. Pure Python with no Archipelago imports.
"""
import uuid
from typing import Iterable, Optional

COUNT_STATS = {
    "Kills": "kills",
    "Assists": "assists",
    "Trades": "trades",
    "Clutches": "clutches",
    "Aces": "aces",
    "3Ks": "three_ks",
    "Wins": "wins",
}
ALWAYS_SUMMED = {"Wins"}  # a single match can't hold more than one win
KD_STAT = "K/D"
ACS_STAT = "ACS"  # only in worlds generated before patch 13.06 replaced ACS with Performance Score
PERFORMANCE_STAT = "Performance"
BEST_MATCH_STATS = (KD_STAT, ACS_STAT, PERFORMANCE_STAT)


def kd_ratio(stats: dict) -> float:
    return round(stats.get("kills", 0) / max(1, stats.get("deaths", 0)), 2)


def acs(stats: dict) -> float | None:
    """Average Combat Score, or None when the match has no score data (e.g. live numbers)."""
    rounds = stats.get("rounds", 0)
    return round(stats.get("score", 0) / rounds, 1) if rounds and stats.get("score") else None


class ShortModes:
    """
    Lowered thresholds for short modes (the slot data's "short_modes", None when off). A short-mode match counts
    100/percent times towards the regular thresholds, so playing only short modes needs `percent`% of each one
    (rounded up), and mixing modes adds up proportionally.
    """

    def __init__(self, data: Optional[dict] = None) -> None:
        data = data or {}
        self.percent: int = int(data.get("percent") or 100)
        self.queues: tuple[str, ...] = tuple(data.get("queues") or ())
        self.thresholds: dict[str, list[int]] = dict(data.get("thresholds") or {}) if self.percent < 100 else {}

    def weight(self, stat: str, queue: Optional[str]) -> int:
        """
        Integer weight for a match's value: 100 in short modes and `percent` elsewhere, later divided by `percent`.
        Integers keep sums exact, so a lowered threshold is reached at exactly the right count.
        """
        if stat not in self.thresholds:
            return 1
        return 100 if queue in self.queues else self.percent

    def needed(self, value: float, threshold: float, short: bool = True) -> int:
        """How many more of a stat it takes to bring `value` to `threshold`, in short modes or in other modes."""
        missing = round(threshold * self.percent) - round(value * self.percent)
        return max(0, -(-missing // (100 if short else self.percent)))


class Progress:
    def __init__(self, data: Optional[dict] = None, start_ms: int = 0) -> None:
        data = data or {}
        self.start_ms: int = int(data.get("start_ms") or start_ms)
        self.matches: dict[str, dict] = dict(data.get("matches") or {})
        # Weapon rentals bought with Kingdom Credits, by id:
        # {"weapon": "Vandal", "price": 4, "bought_ms": ..., "match": None | match id, "refunded": bool}
        self.rentals: dict[str, dict] = {key: dict(value) for key, value in (data.get("rentals") or {}).items()}
        # When each received item arrived (Unix ms), by its position in the received-items list; None until noted.
        received = data.get("received")
        self.received_ms: Optional[list[int]] = [int(ms) for ms in received] if received is not None else None

    def to_json(self) -> dict:
        return {"version": 1, "start_ms": self.start_ms, "matches": self.matches, "rentals": self.rentals,
                "received": self.received_ms}

    def note_received(self, count: int, now_ms: int) -> bool:
        """
        Record when newly received items arrived. The first time this runs, items already received count as received
        long ago, so slots tracked before this existed keep counting their weapons. Returns whether anything changed.
        """
        if self.received_ms is None:
            self.received_ms = [0] * count
            return True
        if len(self.received_ms) < count:
            self.received_ms += [now_ms] * (count - len(self.received_ms))
            return True
        return False

    def has_official(self, match_id: str) -> bool:
        return self.matches.get(match_id, {}).get("source") == "official"

    def record(self, match_id: str, record: dict) -> bool:
        """Store a match result. Official results always win over live ones. Returns whether anything changed."""
        if record.get("source") != "official" and self.has_official(match_id):
            return False
        if self.matches.get(match_id) == record:
            return False
        self.matches[match_id] = record
        return True

    def totals(self, mode: str, extra: Iterable[dict] = (),
               short_modes: Optional[ShortModes] = None) -> dict[str, dict[str, float]]:
        """
        Per-agent stat values: summed over matches ("cumulative") or the best single match ("single_match").
        Wins are always summed; K/D, ACS and Performance Score are always the best of any finished match.
        With short modes on, their kills/assists/trades are weighted, so those values can be fractional.
        """
        short_modes = short_modes or ShortModes()
        totals: dict[str, dict[str, float]] = {}
        for record in [*self.matches.values(), *extra]:
            if not record.get("counted"):
                continue
            agent_totals = totals.setdefault(record["agent"], {stat: 0 for stat in (*COUNT_STATS, *BEST_MATCH_STATS)})
            stats = record.get("stats") or {}
            for stat, field in COUNT_STATS.items():
                value = stats.get(field, 0) * short_modes.weight(stat, record.get("queue"))
                if mode == "single_match" and stat not in ALWAYS_SUMMED:
                    agent_totals[stat] = max(agent_totals[stat], value)
                else:
                    agent_totals[stat] += value
            if record.get("complete", True):
                agent_totals[KD_STAT] = max(agent_totals[KD_STAT], kd_ratio(stats))
                agent_totals[ACS_STAT] = max(agent_totals[ACS_STAT], acs(stats) or 0)
                agent_totals[PERFORMANCE_STAT] = max(agent_totals[PERFORMANCE_STAT], stats.get("performance") or 0)
        for agent_totals in totals.values():
            for stat in short_modes.thresholds:
                agent_totals[stat] /= short_modes.percent
        return totals

    def completed(self, thresholds: dict[str, list], agents: Iterable[str], mode: str,
                  extra: Iterable[dict] = (), short_modes: Optional[ShortModes] = None) -> list[tuple[str, str, int]]:
        """Every (agent, stat, tier) whose threshold has been reached."""
        totals = self.totals(mode, extra, short_modes)
        done = []
        for agent in agents:
            values = totals.get(agent)
            if not values:
                continue
            for stat, tiers in thresholds.items():
                for tier, threshold in enumerate(tiers, start=1):
                    if values.get(stat, 0) >= threshold:
                        done.append((agent, stat, tier))
        return done

    def overview(self, thresholds: dict[str, list], agents: Iterable[str], mode: str, unlocked: set[str],
                 checked: set[tuple[str, str, int]] = frozenset(), extra: Iterable[dict] = (),
                 short_modes: Optional[ShortModes] = None) -> list[dict]:
        """
        Per-agent progress for display: unlocked agents first, then locked ones (each group in world order).
        A tier counts as done if its threshold is reached or the server already has the check (e.g. !collect).
        Stats with lowered short-mode thresholds also get "short_tiers" and, when progress adds up across
        matches, "short_needed": how many more a short mode needs for the next tier.
        """
        short_modes = short_modes or ShortModes()
        totals = self.totals(mode, extra, short_modes)
        rows = []
        for agent in agents:
            values = totals.get(agent, {})
            stats = []
            for stat, tiers in thresholds.items():
                if not tiers:
                    continue
                value = values.get(stat, 0)
                done = sum(1 for tier, threshold in enumerate(tiers, start=1)
                           if value >= threshold or (agent, stat, tier) in checked)
                entry = {"stat": stat, "value": value, "tiers": list(tiers), "done": done}
                if stat in short_modes.thresholds:
                    entry["short_tiers"] = list(short_modes.thresholds[stat])
                    if mode != "single_match":
                        entry["short_needed"] = short_modes.needed(value, tiers[done]) if done < len(tiers) else 0
                stats.append(entry)
            rows.append({"name": agent, "unlocked": agent in unlocked, "stats": stats})
        rows.sort(key=lambda row: not row["unlocked"])
        return rows

    def merge(self, other: "Progress") -> None:
        """Fold in results from another copy of this slot's progress (e.g. after a reconnect)."""
        self.start_ms = min(filter(None, (self.start_ms, other.start_ms)), default=0)
        for match_id, record in other.matches.items():
            mine = self.matches.get(match_id)
            if mine is None or (record.get("source") == "official" and mine.get("source") != "official"):
                self.matches[match_id] = record
        if other.received_ms is not None:
            mine = self.received_ms or []
            earliest = [min(a, b) for a, b in zip(mine, other.received_ms)]
            longer = mine if len(mine) > len(other.received_ms) else other.received_ms
            self.received_ms = earliest + longer[len(earliest):]
        for rental_id, rental in other.rentals.items():
            mine = self.rentals.get(rental_id)
            if mine is None:
                self.rentals[rental_id] = dict(rental)
                continue
            if mine.get("match") is None and rental.get("match") is not None:
                mine["match"], mine["refunded"] = rental["match"], False  # used: it can't have been refunded
            elif rental.get("refunded") and mine.get("match") is None:
                mine["refunded"] = True

    # --- weapon rentals (the Kingdom Credits shop) ---------------------------------------------------------------
    # A rental is used on the first counted match still running when it's bought (or starting after), and counts from
    # the first round that starts after the purchase: rented between rounds, it covers the rest of that match.

    def rent(self, weapon: str, price: int, bought_ms: int) -> str:
        rental_id = uuid.uuid4().hex
        self.rentals[rental_id] = {"weapon": weapon, "price": price, "bought_ms": bought_ms, "match": None,
                                   "refunded": False}
        return rental_id

    def spent(self) -> int:
        """Kingdom Credits spent on rentals (refunds excluded)."""
        return sum(rental["price"] for rental in self.rentals.values() if not rental.get("refunded"))

    def pending_rentals(self) -> dict[str, dict]:
        """Rentals still waiting for their match, oldest first."""
        waiting = [(rental_id, rental) for rental_id, rental in self.rentals.items()
                   if rental.get("match") is None and not rental.get("refunded")]
        return dict(sorted(waiting, key=lambda item: item[1]["bought_ms"]))

    def refund(self, rental_id: str) -> bool:
        """Cancel a rental that hasn't been used yet. Returns whether it was refunded."""
        if rental_id not in self.pending_rentals():
            return False
        self.rentals[rental_id]["refunded"] = True
        return True

    def bind_rentals(self, match_id: str, before_ms: int) -> list[str]:
        """Use every unused rental bought before `before_ms` on this match. Returns the newly covered weapons."""
        bound = []
        for rental in self.pending_rentals().values():
            if rental["bought_ms"] < before_ms:
                rental["match"] = match_id
                bound.append(rental["weapon"])
        return bound

    def rented_for(self, match_id: Optional[str]) -> dict[str, int]:
        """Weapons rented for this match, with when they were bought: they count in rounds that start later."""
        rented: dict[str, int] = {}
        for rental in self.rentals.values():
            if match_id and rental.get("match") == match_id and not rental.get("refunded"):
                rented[rental["weapon"]] = min(rental["bought_ms"], rented.get(rental["weapon"], rental["bought_ms"]))
        return rented
