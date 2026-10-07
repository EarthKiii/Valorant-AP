"""
Builds live, in-match stats from the game events the companion app forwards (Overwolf GEP via ow-electron).

Companion messages look like {"kind": "info" | "event" | "snapshot" | "game_exit", "feature": ..., "key": ...,
"value": ..., "ts": <ms>}. Pure Python with no Archipelago imports.
"""
import json
import time
from collections import Counter
from typing import Any, Callable, NamedTuple, Optional

ALWAYS_ALLOWED_WEAPONS = {"Classic", "Knife"}
AGENT_SELECT_SCENE = "characterselectpersistentlevel"
NON_ROUND_MODES = {"deathmatch", "team_deathmatch"}
GAME_MODE_QUEUES = {
    "quickbomb": "spikerush",
    "swift": "swiftplay",
    "swiftplay": "swiftplay",
    "deathmatch": "deathmatch",
    "team_deathmatch": "hurm",
    "escalation": "ggteam",
}


def _player_name(value: Any) -> str:
    """'Doom #5339' / 'Doom#5339' / 'Doom' -> 'doom'."""
    return str(value or "").split("#")[0].strip().casefold()


def _parse(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _flag(value: Any) -> bool:
    return value.strip().lower() == "true" if isinstance(value, str) else bool(value)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


class LiveKill(NamedTuple):
    round: int
    ts: int
    victim: str
    weapon: Optional[str]  # weapon name, or None for abilities and unknown weapons


class LiveTracker:
    def __init__(self, live_weapon_ids: dict[str, str], agent_codenames: dict[str, str]) -> None:
        self.weapon_names = {key.lower(): name for key, name in live_weapon_ids.items()}
        self.agent_codenames = {key.lower(): name for key, name in agent_codenames.items()}
        self.agent_names = {name.lower(): name for name in agent_codenames.values()}
        self.my_name = ""
        self.my_puuid = ""
        self.agent: Optional[str] = None
        self.scene = ""  # the game's current screen, e.g. agent select
        self.pick: Optional[tuple[str, bool]] = None  # your agent-select pick: (agent, locked in)
        self.last_message_ms = 0
        self.reset_match()

    def reset_match(self, match_id: str = "") -> None:
        self.match_id = match_id
        self.pseudo_id = ""
        self.started_ms = 0
        self.active = False
        self.ended = False
        self.outcome = ""
        self.game_mode: dict = {}
        self.map = ""
        self.round = 0
        self.round_phase = ""
        self.score = (0, 0)
        self.my_kills: list[LiveKill] = []
        self.ally_deaths: list[tuple[int, int, str]] = []  # (round, ts, killer) - enemies killing our teammates
        self.clutch_rounds: set[int] = set()
        self.won_rounds: set[int] = set()
        self.kill_counter = 0
        self.deaths = 0
        self.assists = 0
        self.scoreboard: dict[str, dict] = {}
        self._recent_feed: dict[str, int] = {}
        self._allies_alive = 5
        self._enemies_alive = 5
        self._me_alive = True

    @property
    def in_agent_select(self) -> bool:
        return self.scene.lower() == AGENT_SELECT_SCENE

    def agent_name(self, value: Any) -> Optional[str]:
        """An agent from the game events, which may use its name ("Jett"), codename ("Wushu") or ID ("Wushu_PC_C")."""
        text = str(value or "").lower().removesuffix("_pc_c")
        return self.agent_codenames.get(text) or self.agent_names.get(text)

    @property
    def key(self) -> str:
        """Riot match ID when known, otherwise the companion's own ID for this match."""
        return self.match_id or self.pseudo_id

    def queue_guess(self) -> Optional[str]:
        """Riot queue ID guessed from the live game mode (None when unknown, e.g. the Range)."""
        if not self.game_mode:
            return None
        if _flag(self.game_mode.get("custom")):
            return ""
        mode = str(self.game_mode.get("mode", "")).lower().replace(" ", "")
        if mode == "bomb":
            return "competitive" if str(self.game_mode.get("ranked")) == "1" else "unrated"
        return GAME_MODE_QUEUES.get(mode)

    # --- message handling ---------------------------------------------------------------------------------

    def handle(self, message: dict) -> set[str]:
        """Apply one companion message and return tags for what changed (e.g. {"kill"}, {"match_end"})."""
        kind = message.get("kind")
        ts = _int(message.get("ts")) or int(time.time() * 1000)
        self.last_message_ms = ts
        if kind == "snapshot":
            return self._snapshot(message.get("value"), ts)
        if kind == "game_exit":
            self.scene, self.pick = "", None
            return {"game_exit"}
        feature, key, value = message.get("feature"), str(message.get("key") or ""), message.get("value")
        if kind == "event":
            changes = self._event(key, value, ts)
        elif kind == "info":
            changes = self._info(feature, key, value, ts)
        else:
            return set()
        if self.active and not self.started_ms:
            self.started_ms = ts
        return changes

    def _snapshot(self, value: Any, ts: int) -> set[str]:
        info = _parse(value)
        if isinstance(info, dict) and isinstance(info.get("info"), dict):
            info = info["info"]
        changes: set[str] = set()
        if isinstance(info, dict):
            for feature, entries in info.items():
                if isinstance(entries, dict):
                    for key, entry in entries.items():
                        if key != "kill_feed":  # a snapshot's kill feed is old news
                            changes |= self._info(feature, key, entry, ts)
        return changes

    def _event(self, key: str, value: Any, ts: int) -> set[str]:
        if key == "match_start":
            # The match ID may arrive just before this event; keep it unless it belongs to a match we already played.
            fresh = not self.my_kills and self.round == 0 and not self.ended
            match_id, pseudo_id = (self.match_id, self.pseudo_id) if fresh else ("", "")
            self.reset_match(match_id)
            self.pseudo_id = pseudo_id
            self.active = True
            return {"match_start"}
        if key == "match_end":
            self.ended = True
            return {"match_end"}
        if key == "kill_feed":
            return self._kill_feed(value, ts)
        if key == "kill":
            self.kill_counter = max(self.kill_counter, _int(value))
            return {"stats"}
        if key == "death":
            self.deaths = max(self.deaths, _int(value))
            return {"stats"}
        if key == "assist":
            self.assists = max(self.assists, _int(value))
            return {"stats"}
        return set()

    def _info(self, feature: Any, key: str, value: Any, ts: int) -> set[str]:
        if feature == "me":
            if key == "player_name":
                self.my_name = _player_name(value)
            elif key == "player_id":
                self.my_puuid = str(value or "").lower()
            elif key == "agent":
                codename = str(value or "").lower().removesuffix("_pc_c")
                self.agent = self.agent_codenames.get(codename, self.agent)
                return {"agent"}
            return set()
        if feature == "game_info" and key == "scene":
            scene = str(value or "")
            if scene.lower() == AGENT_SELECT_SCENE and not self.in_agent_select:
                self.pick = None  # a new agent select
            changed = scene != self.scene
            self.scene = scene
            return {"scene"} if changed else set()
        if feature == "kill":
            if key == "kills":
                self.kill_counter = _int(value)
            elif key == "assists":
                self.assists = _int(value)
            return {"stats"}
        if feature == "death":
            if key == "deaths":
                self.deaths = _int(value)
            return {"stats"}
        if feature != "match_info":
            return set()

        if key == "match_id" and value:
            if value != self.match_id and (self.match_id or self.ended):
                self.reset_match()
            self.match_id = str(value)
            self.active = True
            return {"match_start"}
        if key == "pseudo_match_id" and value:
            if value != self.pseudo_id and (self.pseudo_id or self.ended):
                self.reset_match()
            self.pseudo_id = str(value)
            self.active = True
            return {"match_start"}
        if key == "round_number":
            number = _int(value)
            if number != self.round:
                self._new_round(number)
                return {"round"}
            return set()
        if key == "round_phase":
            self.round_phase = str(value or "")
            if self.round_phase == "game_end":
                self.ended = True
                return {"match_end"}
            return set()
        if key == "score":
            score = _parse(value)
            if isinstance(score, dict):
                won, lost = _int(score.get("won")), _int(score.get("lost"))
                changes = set()
                if won > self.score[0] and self.round:
                    self.won_rounds.add(self.round)
                    changes.add("round_won")
                self.score = (won, lost)
                return changes
            return set()
        if key == "match_outcome" and value:
            self.ended = True
            self.outcome = str(value).lower()
            return {"match_end"}
        if key == "game_mode":
            mode = _parse(value)
            self.game_mode = mode if isinstance(mode, dict) else {"mode": str(mode)}
            return {"mode"}
        if key == "map":
            self.map = str(value or "")
            return set()
        if key == "kill_feed":
            return self._kill_feed(value, ts)
        if key.startswith("scoreboard_"):
            return self._scoreboard(key, value)
        if key.startswith("roster_"):
            entry = _parse(value)
            if isinstance(entry, dict) and _flag(entry.get("local")):
                self.my_name = self.my_name or _player_name(entry.get("name"))
                self.my_puuid = self.my_puuid or str(entry.get("player_id") or "").lower()
                # In agent select, "character" is the agent you're on and "locked" whether you've locked it in.
                agent = self.agent_name(entry.get("character"))
                pick = (agent, _flag(entry.get("locked"))) if agent else None
                if pick and pick != self.pick:
                    self.pick = pick
                    return {"pick"}
        return set()

    def _scoreboard(self, key: str, value: Any) -> set[str]:
        entry = _parse(value)
        if not isinstance(entry, dict):
            return set()
        self.scoreboard[key] = entry
        changes: set[str] = set()
        if _flag(entry.get("is_local")):
            self.my_name = self.my_name or _player_name(entry.get("name"))
            self.kill_counter = max(self.kill_counter, _int(entry.get("kills")))
            self.deaths = _int(entry.get("deaths"), self.deaths)
            self.assists = _int(entry.get("assists"), self.assists)
            changes.add("stats")
        if self.round_phase == "combat" and self._scoreboard_clutch():
            changes.add("clutch_chance")
        return changes

    def _scoreboard_clutch(self) -> bool:
        """Clutch situation according to the scoreboard's alive flags."""
        local = next((e for e in self.scoreboard.values() if _flag(e.get("is_local"))), None)
        if local is None or not _flag(local.get("alive")):
            return False
        others = [e for e in self.scoreboard.values() if e is not local]
        allies_alive = sum(1 for e in others if _flag(e.get("teammate")) and _flag(e.get("alive")))
        enemies_alive = sum(1 for e in others if not _flag(e.get("teammate")) and _flag(e.get("alive")))
        return self._mark_clutch() if allies_alive == 0 and enemies_alive > 0 else False

    def _new_round(self, number: int) -> None:
        self.round = number
        allies = sum(1 for e in self.scoreboard.values() if _flag(e.get("teammate")) or _flag(e.get("is_local")))
        enemies = len(self.scoreboard) - allies
        self._allies_alive = allies or 5
        self._enemies_alive = enemies or 5
        self._me_alive = True

    def _kill_feed(self, value: Any, ts: int) -> set[str]:
        # GEP reports each kill both as an info update and as an event; count it once.
        raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
        self._recent_feed = {k: t for k, t in self._recent_feed.items() if ts - t < 3000}
        if raw in self._recent_feed:
            return set()
        self._recent_feed[raw] = ts

        entry = _parse(value)
        if not isinstance(entry, dict):
            return set()
        self.active = True
        attacker, victim = _player_name(entry.get("attacker")), _player_name(entry.get("victim"))
        victim_is_ally = _flag(entry.get("is_victim_teammate"))
        attacker_is_ally = _flag(entry.get("is_attacker_teammate"))
        changes = {"feed"}

        if self.my_name and victim == self.my_name:
            self._me_alive = False
            self._allies_alive -= 1
        elif victim_is_ally:
            self._allies_alive -= 1
        else:
            self._enemies_alive -= 1

        if self.my_name and attacker == self.my_name and not victim_is_ally:
            weapon = self.weapon_names.get(str(entry.get("weapon") or "").lower())
            self.my_kills.append(LiveKill(self.round, ts, victim, weapon))
            changes.add("kill")
        elif victim_is_ally and not attacker_is_ally and victim != self.my_name:
            self.ally_deaths.append((self.round, ts, attacker))

        if self._me_alive and self._allies_alive <= 1 and self._enemies_alive > 0 and self._mark_clutch():
            changes.add("clutch_chance")
        return changes

    def _mark_clutch(self) -> bool:
        if self.round in self.clutch_rounds:
            return False
        self.clutch_rounds.add(self.round)
        return True

    # --- results ------------------------------------------------------------------------------------------

    def _weapon_ok(self, weapon: Optional[str], weapon_allowed: Callable[[str], bool]) -> bool:
        return weapon is None or weapon in ALWAYS_ALLOWED_WEAPONS or weapon_allowed(weapon)

    def stats(self, weapon_allowed: Callable[[str], bool] = lambda _name: True, trade_window_ms: int = 5000) -> dict:
        """Current stats for this match, in the same shape as the official ones (minus score, which GEP lacks)."""
        valid = [kill for kill in self.my_kills if self._weapon_ok(kill.weapon, weapon_allowed)]
        locked = [kill for kill in self.my_kills if not self._weapon_ok(kill.weapon, weapon_allowed)]
        kills = len(valid)
        if not self.my_kills and self.kill_counter:
            kills = self.kill_counter  # we couldn't recognise ourselves in the kill feed; use the plain counter

        round_based = str(self.game_mode.get("mode", "")).lower() not in NON_ROUND_MODES
        per_round = Counter(kill.round for kill in valid)
        locked_rounds = {kill.round for kill in locked}
        trades = sum(
            1 for kill in valid
            if any(r == kill.round and killer == kill.victim and 0 <= kill.ts - t <= trade_window_ms
                   for r, t, killer in self.ally_deaths)
        )
        clutches = len({r for r in self.clutch_rounds if r in self.won_rounds and r not in locked_rounds})
        return {
            "kills": kills,
            "deaths": self.deaths,
            "assists": self.assists,
            "trades": trades if round_based else 0,
            "clutches": clutches if round_based else 0,
            "aces": sum(1 for n in per_round.values() if n >= 5) if round_based else 0,
            "three_ks": sum(1 for n in per_round.values() if n >= 3) if round_based else 0,
            "wins": 1 if self.outcome == "victory" else 0,
            "locked_kills": len(locked),
            "locked_weapons": sorted({kill.weapon for kill in locked if kill.weapon}),
        }
