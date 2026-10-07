"""
Turns a Riot match-details payload into the numbers the checks are based on.

Pure Python with no Archipelago imports, so it can be tested in isolation.
Handles both the client "PVP" format (kills carry roundTime/gameTime) and the official
VAL-MATCH-V1 format (timeSinceRoundStartMillis/timeSinceGameStartMillis).
"""
from collections import defaultdict
from typing import Any, Callable, Optional

# Called with a lowercase weapon UUID and when the round it was used in started (Unix ms, None if unknown); returns
# whether kills with that weapon count in that round.
WeaponFilter = Callable[[str, Optional[int]], bool]

COUNT_FIELDS = ("kills", "deaths", "assists", "trades", "clutches", "aces", "three_ks", "wins", "score", "rounds")

# Riot's match data carries the Performance Score (0-500, the scoreboard metric since patch 13.06) only under a
# placeholder key in the player's "scores", so it's read defensively: anything missing or out of range counts as none.
PERFORMANCE_KEY = "TempValueF"
PERFORMANCE_MAX = 500


def performance_score(player: dict) -> int:
    """The player's Performance Score, rounded like the scoreboard shows it (0 when the match has none)."""
    value = (player.get("scores") or {}).get(PERFORMANCE_KEY)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= PERFORMANCE_MAX:
        return 0
    return int(value + 0.5)


def _lower(value: Any) -> str:
    return str(value or "").lower()


def _kill_time(kill: dict) -> int:
    for key in ("roundTime", "timeSinceRoundStartMillis", "gameTime", "timeSinceGameStartMillis"):
        if kill.get(key) is not None:
            return int(kill[key])
    return 0


def _game_time(kill: dict) -> Optional[int]:
    """Milliseconds from the start of the match to the kill."""
    for key in ("gameTime", "timeSinceGameStartMillis"):
        if kill.get(key) is not None:
            return int(kill[key])
    return None


def _round_time(kill: dict) -> Optional[int]:
    """Milliseconds from the start of the kill's round (its combat phase) to the kill."""
    for key in ("roundTime", "timeSinceRoundStartMillis"):
        if kill.get(key) is not None:
            return int(kill[key])
    return None


def _collect_kills(match: dict) -> list[dict]:
    """Every kill in the match, tagged with its round and sorted chronologically."""
    kills: list[dict] = []
    if match.get("kills"):
        kills = [dict(kill, round=int(kill.get("round", 0))) for kill in match["kills"]]
    else:
        for index, round_result in enumerate(match.get("roundResults") or []):
            round_number = int(round_result.get("roundNum", index))
            for player_stats in round_result.get("playerStats") or []:
                kills += [dict(kill, round=int(kill.get("round", round_number)))
                          for kill in player_stats.get("kills") or []]
    kills.sort(key=lambda kill: (kill["round"], _kill_time(kill)))
    return kills


def kill_weapon(kill: dict) -> Optional[str]:
    """UUID of the gun that made a kill; None for abilities, melee, the spike, fall damage..."""
    damage = kill.get("finishingDamage") or {}
    if _lower(damage.get("damageType")) != "weapon":
        return None
    return _lower(damage.get("damageItem")) or None


def match_overview(match: dict, puuid: str) -> dict:
    """The bits of a match the client needs before deciding whether it counts."""
    info = match.get("matchInfo") or {}
    me = find_player(match, puuid) or {}
    return {
        "match_id": info.get("matchId") or info.get("matchID") or "",
        "queue_id": _lower(info.get("queueID", info.get("queueId"))),
        "map": info.get("mapId") or "",
        "start_ms": int(info.get("gameStartMillis") or 0),
        "length_ms": int(info.get("gameLengthMillis") or 0),
        "completed": bool(info.get("isCompleted", True)),
        "agent_uuid": _lower(me.get("characterId")),
        "found": bool(me),
    }


def find_player(match: dict, puuid: str) -> Optional[dict]:
    puuid = _lower(puuid)
    return next((p for p in match.get("players") or [] if _lower(p.get("subject", p.get("puuid"))) == puuid), None)


def compute_match_stats(
    match: dict,
    puuid: str,
    weapon_allowed: WeaponFilter = lambda _uuid, _when: True,
    trade_window_ms: int = 5000,
) -> Optional[dict]:
    """
    Per-match stats for one player (`wins` is 1 if their team won, `score`/`rounds` give the ACS, `performance` is
    the Performance Score).
    Kills made with a weapon rejected by `weapon_allowed` are left out of
    every stat (kills, multi-kills, trades, and the clutch for that round) and reported in `locked_kills`.
    `locked_weapons` lists every locked weapon the player killed with or carried into a round. Weapons are checked
    at the start of the round they were used in (worked out from the kills' times).
    """
    me = find_player(match, puuid)
    if me is None:
        return None
    puuid = _lower(puuid)
    team_of = {_lower(p.get("subject", p.get("puuid"))): p.get("teamId") for p in match.get("players") or []}
    my_team = me.get("teamId")
    round_results = match.get("roundResults") or []
    # Deathmatch and friends are a single "round": multi-kills, trades and clutches are meaningless there.
    round_based = len(round_results) >= 2
    info = match.get("matchInfo") or {}
    start_ms = int(info.get("gameStartMillis") or 0)
    end_ms = start_ms + int(info.get("gameLengthMillis") or 0) if start_ms and info.get("gameLengthMillis") else None

    def at(game_time: Optional[int]) -> Optional[int]:
        return start_ms + game_time if start_ms and game_time is not None else None

    kills_by_round: dict[int, list[dict]] = defaultdict(list)
    for kill in _collect_kills(match):
        kills_by_round[kill["round"]].append(kill)
    # When each round started: a kill's time in the match minus its time in the round. Rounds without timed kills
    # fall back to the match's end for carried weapons: that only affects Strict enforcement, as they have no kills.
    round_starts: dict[int, Optional[int]] = {}
    for number, kills in kills_by_round.items():
        starts = [_game_time(kill) - _round_time(kill) for kill in kills
                  if _game_time(kill) is not None and _round_time(kill) is not None]
        round_starts[number] = at(min(starts)) if starts else None

    winners: dict[int, Any] = {}
    participants: dict[int, set[str]] = {}
    locked_weapons: set[str] = set()
    for index, round_result in enumerate(round_results):
        round_number = int(round_result.get("roundNum", index))
        winners[round_number] = round_result.get("winningTeam")
        participants[round_number] = set()
        for player_stats in round_result.get("playerStats") or []:
            subject = _lower(player_stats.get("subject", player_stats.get("puuid")))
            participants[round_number].add(subject)
            if subject == puuid:
                carried = _lower((player_stats.get("economy") or {}).get("weapon"))
                if carried and not weapon_allowed(carried, round_starts.get(round_number) or end_ms):
                    locked_weapons.add(carried)

    stats = {field: 0 for field in COUNT_FIELDS}
    stats["locked_kills"] = 0
    counted_any_kill_event = False

    for round_number, round_kills in sorted(kills_by_round.items()):
        mine = [k for k in round_kills
                if _lower(k.get("killer")) == puuid
                and _lower(k.get("victim")) != puuid
                and team_of.get(_lower(k.get("victim"))) != my_team]
        valid = []
        for kill in mine:
            weapon = kill_weapon(kill)
            if weapon and not weapon_allowed(weapon, round_starts.get(round_number) or at(_game_time(kill))):
                locked_weapons.add(weapon)
                stats["locked_kills"] += 1
            else:
                valid.append(kill)
        counted_any_kill_event = counted_any_kill_event or bool(mine)
        stats["kills"] += len(valid)
        if not round_based:
            continue

        if len(valid) >= 3:
            stats["three_ks"] += 1
        if len(valid) >= 5:
            stats["aces"] += 1

        # A trade: killing the enemy who killed a teammate of ours, shortly after they did it.
        for kill in valid:
            victim, time = _lower(kill.get("victim")), _kill_time(kill)
            if any(_lower(other.get("killer")) == victim
                   and _lower(other.get("victim")) != puuid
                   and team_of.get(_lower(other.get("victim"))) == my_team
                   and 0 <= time - _kill_time(other) <= trade_window_ms
                   for other in round_kills):
                stats["trades"] += 1

        # A clutch: being the last one alive on our team (with enemies left) in a round we win.
        people = participants.get(round_number) or set(team_of)
        allies = {p for p in people if team_of.get(p) == my_team} | {puuid}
        enemies = {p for p in people if p in team_of and team_of[p] != my_team}
        in_clutch = len(allies) == 1 and bool(enemies)
        for kill in round_kills:
            victim = _lower(kill.get("victim"))
            allies.discard(victim)
            enemies.discard(victim)
            if allies == {puuid} and enemies:
                in_clutch = True
        if in_clutch and winners.get(round_number) == my_team and len(valid) == len(mine):
            stats["clutches"] += 1

    player_stats = me.get("stats") or {}
    stats["deaths"] = int(player_stats.get("deaths") or 0)
    stats["assists"] = int(player_stats.get("assists") or 0)
    stats["score"] = int(player_stats.get("score") or 0)
    stats["rounds"] = int(player_stats.get("roundsPlayed") or len(round_results))
    stats["performance"] = performance_score(me)
    my_team_result = next((t for t in match.get("teams") or [] if t.get("teamId") == my_team), {})
    stats["wins"] = 1 if my_team_result.get("won") else 0
    if not counted_any_kill_event and not stats["locked_kills"]:
        # No kill events available for us (rare); fall back to the scoreboard number.
        stats["kills"] = int(player_stats.get("kills") or 0)
    stats["locked_weapons"] = sorted(locked_weapons)
    return stats
