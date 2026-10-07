# VALORANT for Archipelago

An [Archipelago](https://archipelago.gg) world for VALORANT. Agents and weapons are items; every kill, assist,
trade, clutch, ace, 3K, K/D, win and Performance Score milestone you hit with an agent in real matches is a check. Collect enough
Radianite Crystals to win.

VALORANT can't be modded, so nothing touches the game. A client watches your matches through the Riot Client
running on your PC and decides what counts (unlocked agent? unlocked weapons? allowed game mode?).

## What's in here

| Path               | What it is                                                                                                         |
|--------------------|--------------------------------------------------------------------------------------------------------------------|
| `valorant/`        | The APWorld: items, locations, options, logic, docs, tests and the client.                                         |
| `valorant/client/` | The Archipelago client (`Valorant Client` in the Launcher).                                                        |
| `companion/`       | Optional companion app (ow-electron): live in-match checks, a progress window and an in-game agent-select overlay. |
| `Valorant.yaml`    | Example options file with every option documented.                                                                 |
| `build_apworld.py` | Packages `valorant/` into `valorant.apworld`.                                                                      |
| `patchnotes/`      | What changed in each version, one file per version.                                                                |

Player-facing docs: [game page](valorant/docs/en_Valorant.md) and [setup guide](valorant/docs/setup_en.md).

## Quick start

```powershell
python build_apworld.py          # -> valorant.apworld
```

1. Install `valorant.apworld` into Archipelago (double-click it, or **Install APWorld** in the Launcher).
2. Edit `Valorant.yaml` (set `agent_pool` to the agents you own), generate, and host as usual.
3. Start VALORANT, open **Valorant Client** in the Launcher and connect.
4. Optional, for checks mid-match: run the companion app (see [setup guide](valorant/docs/setup_en.md#optional-the-companion-app)).

## How the data flows

| When             | Source                                                  | Used for                                                                                   |
|------------------|---------------------------------------------------------|--------------------------------------------------------------------------------------------|
| Agent select     | Live game events (companion), else the pregame endpoint | Warning (with a sound, and on the companion's overlay) if you hover/lock a locked agent    |
| Match start      | Riot Client presence → core-game endpoint               | "This match counts / doesn't count" announcement                                           |
| During the match | Companion app (Overwolf GEP kill feed)                  | Kills, 3Ks, aces, trades, clutches counted as they happen; wins and K/D at the final round |
| Match end        | Riot match-details endpoint                             | Official stats (incl. Performance Score), fetched within seconds; replaces live numbers    |
| Every 2 minutes  | Riot match-history endpoint                             | Catches anything missed (client closed, etc.)                                              |

Progress is stored in the Archipelago server's data storage, so the client can be restarted at any time.

## Options at a glance

- **Agent Pool / Agent Count / Starting Agents:** which agents can appear, how many do, and how many you start with.
- **Weapon Unlocks / Starting Weapons / Weapon Enforcement / Weapon Logic:** weapons as items, how strictly locked
  weapons are treated, and how many primaries the logic expects for higher tiers.
- **Weapon Shop / Rental Prices:** spend Kingdom Credits (the filler item) in the client's Shop tab to rent a locked
  weapon for one match, priced by weapon type.
- **Progress Mode:** cumulative across matches (default) or within a single match. Wins always add up; K/D and
  Performance Score always use your best match.
- **Kill/Assist/Trade/Clutch/Ace/3K/K/D/Win/Performance Score Thresholds:** one check per value, per agent (up to 10 each).
- **Short Mode Thresholds (%):** Swiftplay and Spike Rush only need this percentage of the Kill, Assist and Trade
  thresholds (100 = off). The lowered values are listed in the spoiler log, the client and the companion window.
- **Excluded Stats:** stats whose checks only hold filler (Aces by default, since they're rare).
- **Allowed Queues:** which modes count. **Trade Window:** seconds allowed for a trade.
- **Radianite Count / Radianite Required (%):** the goal.

## Development

The world and client were tested against Archipelago 0.6.8 from source:

```powershell
# from an Archipelago source checkout, with this repo's valorant/ folder linked or copied into worlds/
python -m pytest worlds/valorant/test
```

The tests cover generation under several option sets, the agent and weapon logic, and the match analysis (both
Riot data formats, trades, clutches, multi-kills, locked weapons). They also cover progress tracking and the live
event tracker.

Agents and weapons are listed in `valorant/data.py` with their Riot UUIDs from
[valorant-api.com](https://valorant-api.com). IDs are derived from list position, so new agents and weapons must be
**appended**, never inserted.

### Releasing

Every world version gets a GitHub release tagged `v<version>`, with `valorant.apworld` and the example
`Valorant.yaml` attached ([workflow](.github/workflows/release.yml)):

1. Bump `world_version` in `valorant/archipelago.json`.
2. Add `patchnotes/<version>.md`; it becomes the release's description.
3. Push to `main`. The workflow builds the `.apworld`, creates the tag and publishes the release.

Pushing a tag yourself (`git tag v0.6.2` then `git push origin v0.6.2`) works too, as long as it matches the world
version. Versions that already have a release are skipped.

## Caveats

- The Riot endpoints used are unofficial (the same ones used by tools like VALORANT Rank Yoinker). They're read-only
  and never touch the game, but Riot could change them at any time.
- The client can't stop you from picking a locked agent or buying a locked gun; it just doesn't count the match or
  kills.
- The companion app relies on Overwolf's game events package. Running it unsigned needs free Overwolf developer
  credentials. The kill feed's IDs for the newest weapons (Bandit, Warden) aren't documented, so kills with them
  count live and get corrected by the official match data.
