"""
Read-only access to VALORANT data through the locally running Riot Client.

Uses the same endpoints as community tools such as VALORANT Rank Yoinker: the Riot Client's local API (found via
its lockfile) for auth and presence, and Riot's "pd"/"glz" servers for match data. Nothing here touches the game
process. Standard library only, so it runs inside Archipelago's bundled Python.
"""
import base64
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", ""))
LOCKFILE = LOCAL_APP_DATA / "Riot Games" / "Riot Client" / "Config" / "lockfile"
SHOOTER_GAME_LOG = LOCAL_APP_DATA / "VALORANT" / "Saved" / "Logs" / "ShooterGame.log"

REGION_SHARDS = {"na": "na", "latam": "na", "br": "na", "eu": "eu", "ap": "ap", "kr": "kr"}
CLIENT_PLATFORM = base64.b64encode(json.dumps({
    "platformType": "PC",
    "platformOS": "Windows",
    "platformOSVersion": "10.0.19042.1.256.64bit",
    "platformChipset": "Unknown",
}).encode()).decode()
TOKEN_LIFETIME_S = 30 * 60

_LOCAL_SSL = ssl.create_default_context()
_LOCAL_SSL.check_hostname = False
_LOCAL_SSL.verify_mode = ssl.CERT_NONE  # the Riot Client serves a self-signed certificate on 127.0.0.1

try:
    import certifi

    _REMOTE_SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _REMOTE_SSL = ssl.create_default_context()


class RiotError(Exception):
    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class RiotNotRunning(RiotError):
    pass


def _request(url: str, headers: dict[str, str], context: ssl.SSLContext, timeout: float = 10) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "ArchipelagoValorant", **headers})
    try:
        with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        raise RiotError(f"HTTP {error.code} for {url}", error.code) from None
    except (urllib.error.URLError, OSError) as error:
        raise RiotError(f"Couldn't reach {url}: {error}") from None
    return json.loads(body) if body else None


def parse_presence(entry: dict) -> Optional[dict]:
    """Decode the VALORANT part of a chat presence (supports the old flat and the newer nested layout)."""
    private = entry.get("private") or ""
    try:
        data = json.loads(base64.b64decode(private + "=" * (-len(private) % 4)))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    match = data.get("matchPresenceData") or {}
    party = data.get("partyPresenceData") or {}

    def pick(key: str, *sources: dict) -> Any:
        for source in (data, *sources):
            if source.get(key) not in (None, ""):
                return source[key]
        return None

    return {
        "state": pick("sessionLoopState", match),
        "queue_id": pick("queueId", match, party),
        "map": pick("matchMap", match),
        "provisioning_flow": pick("provisioningFlow", match),
        "ally_score": pick("partyOwnerMatchScoreAllyTeam", party),
        "enemy_score": pick("partyOwnerMatchScoreEnemyTeam", party),
    }


class RiotClient:
    def __init__(self) -> None:
        self.lockfile: Optional[tuple[str, str]] = None  # (port, password)
        self.puuid = ""
        self.access_token = ""
        self.entitlement = ""
        self.token_time = 0.0
        self.region = ""
        self.shard = ""
        self.region_override = ""
        self.client_version = ""

    # --- session ------------------------------------------------------------------------------------------

    @staticmethod
    def read_lockfile() -> Optional[tuple[str, str]]:
        try:
            _name, _pid, port, password, _protocol = LOCKFILE.read_text().strip().split(":")
        except (OSError, ValueError):
            return None
        return port, password

    def ensure_session(self) -> None:
        """Make sure we have fresh tokens, region and client version. Raises RiotNotRunning if there's no client."""
        lockfile = self.read_lockfile()
        if lockfile is None:
            self.lockfile = None
            self.access_token = ""
            raise RiotNotRunning("The Riot Client isn't running.")
        if lockfile != self.lockfile or time.time() - self.token_time > TOKEN_LIFETIME_S or not self.access_token:
            self.lockfile = lockfile
            tokens = self.local_get("/entitlements/v1/token")
            if not tokens or not tokens.get("accessToken"):
                raise RiotNotRunning("Not logged in to the Riot Client yet.")
            self.access_token = tokens["accessToken"]
            self.entitlement = tokens["token"]
            self.puuid = str(tokens["subject"]).lower()
            self.token_time = time.time()
        if not self.shard:
            self.detect_region()
        if not self.client_version:
            self.detect_client_version()

    def set_region(self, region: str) -> None:
        self.region_override = region
        self.region, self.shard = region, REGION_SHARDS[region]

    def detect_region(self) -> None:
        if self.region_override:
            self.set_region(self.region_override)
            return
        try:
            log = SHOOTER_GAME_LOG.read_text(encoding="utf-8", errors="ignore")
            found = re.search(r"https://glz-(.+?)-1\.(.+?)\.a\.pvp\.net", log)
            if found:
                self.region, self.shard = found.group(1), found.group(2)
                return
        except OSError:
            pass
        # Fall back to the launch arguments of the running game session.
        try:
            sessions = self.local_get("/product-session/v1/external-sessions") or {}
            for session in sessions.values():
                for argument in (session.get("launchConfiguration") or {}).get("arguments") or []:
                    if argument.startswith("-ares-deployment="):
                        self.shard = argument.split("=", 1)[1]
                        self.region = self.shard
                        return
        except RiotError:
            pass

    def detect_client_version(self) -> None:
        try:
            data = _request("https://valorant-api.com/v1/version", {}, _REMOTE_SSL)
            self.client_version = data["data"]["riotClientVersion"]
            return
        except (RiotError, KeyError, TypeError):
            pass
        try:
            log = SHOOTER_GAME_LOG.read_text(encoding="utf-8", errors="ignore")
            found = re.search(r"CI server version: (\S+)", log)
            if found:
                version = found.group(1).split("-")
                if "shipping" not in version:  # release-XX.YY-<build>-<cl> -> release-XX.YY-shipping-<build>-<cl>
                    version.insert(2, "shipping")
                self.client_version = "-".join(version)
        except OSError:
            pass

    # --- raw access ---------------------------------------------------------------------------------------

    def local_get(self, path: str) -> Any:
        if self.lockfile is None:
            raise RiotNotRunning("The Riot Client isn't running.")
        port, password = self.lockfile
        auth = base64.b64encode(f"riot:{password}".encode()).decode()
        try:
            return _request(f"https://127.0.0.1:{port}{path}", {"Authorization": f"Basic {auth}"}, _LOCAL_SSL, 5)
        except RiotError as error:
            if error.status is None:
                raise RiotNotRunning(str(error)) from None
            raise

    def remote_get(self, url: str) -> Any:
        if not self.shard:
            raise RiotError("Unknown region. Launch VALORANT once, or set it with /region.")
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Riot-Entitlements-JWT": self.entitlement,
            "X-Riot-ClientPlatform": CLIENT_PLATFORM,
            "X-Riot-ClientVersion": self.client_version,
        }
        try:
            return _request(url, headers, _REMOTE_SSL)
        except RiotError as error:
            if error.status in (400, 401, 403):
                self.token_time = 0  # stale token: refresh on the next ensure_session()
            raise

    @property
    def pd_url(self) -> str:
        return f"https://pd.{self.shard}.a.pvp.net"

    @property
    def glz_url(self) -> str:
        return f"https://glz-{self.region or self.shard}-1.{self.shard}.a.pvp.net"

    # --- VALORANT data ------------------------------------------------------------------------------------

    def presence(self) -> Optional[dict]:
        data = self.local_get("/chat/v4/presences") or {}
        for entry in data.get("presences") or []:
            if str(entry.get("puuid", "")).lower() == self.puuid and entry.get("product") == "valorant":
                return parse_presence(entry)
        return None

    def valorant_running(self) -> bool:
        sessions = self.local_get("/product-session/v1/external-sessions") or {}
        return any(str(session.get("productId", "")).lower() == "valorant" for session in sessions.values())

    def _current_match_id(self, kind: str) -> Optional[str]:
        try:
            data = self.remote_get(f"{self.glz_url}/{kind}/v1/players/{self.puuid}")
        except RiotError as error:
            if error.status == 404:
                return None
            raise
        return (data or {}).get("MatchID")

    def pregame_match_id(self) -> Optional[str]:
        return self._current_match_id("pregame")

    def pregame_match(self, match_id: str) -> dict:
        return self.remote_get(f"{self.glz_url}/pregame/v1/matches/{match_id}") or {}

    def coregame_match_id(self) -> Optional[str]:
        return self._current_match_id("core-game")

    def coregame_match(self, match_id: str) -> dict:
        return self.remote_get(f"{self.glz_url}/core-game/v1/matches/{match_id}") or {}

    def match_history(self, start: int = 0, end: int = 20) -> list[dict]:
        data = self.remote_get(f"{self.pd_url}/match-history/v1/history/{self.puuid}?startIndex={start}&endIndex={end}")
        return (data or {}).get("History") or []

    def match_details(self, match_id: str) -> Optional[dict]:
        """Full match data, or None if Riot hasn't published it (yet)."""
        try:
            return self.remote_get(f"{self.pd_url}/match-details/v1/matches/{match_id}")
        except RiotError as error:
            if error.status == 404:
                return None
            raise
