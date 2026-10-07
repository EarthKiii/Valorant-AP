# VALORANT Setup Guide

## Requirements

- VALORANT on Windows, with the agents you want to use already owned on your account.
- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.4 or newer.
- `valorant.apworld`.
- Optional, for live in-match stats: [Node.js](https://nodejs.org) 22+ and a free Overwolf developer account.

## Installation

1. Double-click `valorant.apworld` (or use **Install APWorld** in the Archipelago Launcher).
2. Restart the Launcher. A **Valorant Client** button appears.

## Creating your options file

In the Launcher, use **Generate Template Options** and edit `Valorant.yaml`. The most important settings:

- `agent_pool`: only the agents you **own**. Any agent you can't pick in-game makes its checks impossible.
- `agent_count`: how many agents (and therefore how many sets of checks) the world has.
- `*_thresholds`: the milestones for each stat. One check per number, per agent; an empty list `[]` removes that
  stat entirely.
- `allowed_queues`: which game modes count.

## Playing

1. Start the Riot Client (and VALORANT).
2. Open the **Valorant Client** from the Launcher and connect to your room (`/connect address:port`, then your
   slot name).
3. Play. Only matches that start **after** your first connection count.

The client's top bar shows how many Radianite Crystals you have and how many you need.

The client finds your account, region and match data through the Riot Client running on your PC. If region
detection fails, set it with `/region na|eu|ap|kr|latam|br`.

### Client commands

| Command             | What it does                                                        |
|---------------------|---------------------------------------------------------------------|
| `/valorant`         | Riot Client, current match and companion app status, goal progress. |
| `/progress [agent]` | Your current numbers and the next threshold for every stat.         |
| `/unlocks`          | Which of this world's agents and weapons you've unlocked.           |
| `/shop`             | Your Kingdom Credits, rental prices and rented weapons.             |
| `/rent <weapon>`    | Rent a locked weapon for your next match (also in the Shop tab).    |
| `/refund <weapon>`  | Cancel a rental you haven't used yet.                               |
| `/sync`             | Check your recent match history right now.                          |
| `/region <region>`  | Override the auto-detected region.                                  |
| `/sounds`           | Toggle sound alerts.                                                |

## Optional: the companion app

The companion app runs next to VALORANT and the client. It's a small app built on Overwolf's ow-electron (without the
Overwolf client) that does three things:

- **Live stats:** it forwards VALORANT's kill feed to the client over `127.0.0.1`, so kills and multi-kills count the
  instant they happen instead of when the match ends.
- **Progress window:** your agents, their progress and your weapons, locked and unlocked.
- **Agent-select overlay** (optional): a warning inside the game when you hover an agent that wouldn't count.

1. Install [Node.js](https://nodejs.org) 22 or newer.
2. Create a free account in the [Overwolf developer console](https://console.overwolf.com) and get your developer
   credentials. Unsigned ow-electron apps only receive game events in dev mode.
3. In the `companion` folder, run `npm install` once.
4. Put your credentials in `companion/.env` (copy `.env.example` if it's missing):

   ```ini
   OW_CLI_EMAIL=you@example.com
   OW_CLI_API_KEY=your-api-key
   ```

5. Start it each session with `npm start` in the `companion` folder. It reads `.env` by itself and opens a progress
   window: your agents as a grid (locked ones grayed out), the selected agent's progress, and your unlocked
   weapons. Closing that window stops the companion; add `SHOW_WINDOW=false` to `companion/.env` to run it without one.
6. Start the Valorant Client. It shows "Companion app connected" once they find each other. Start order doesn't
   matter, and the companion buffers events while the client is closed.

If you changed the client's port with `--companion-port`, add `VALORANT_AP_PORT=<port>` to `companion/.env`.

To start it with a double-click instead, run `npm run pack` once: it builds a self-contained copy in
`companion/dist/VALORANT Companion/` with a **VALORANT Companion** shortcut (see `companion/README.md`).

To install it without Node.js (on another PC, or for a friend), run `npm run sfx`: it builds
`companion/dist/VALORANT Companion Setup.exe`, a single file that installs or updates the companion with Desktop and
Start Menu shortcuts. It contains no credentials, so it's safe to share; each person adds their own Overwolf developer
credentials when the setup opens the settings file.

## Notes

- The client uses the same unofficial, read-only Riot Client endpoints as community tools like VALORANT Rank
  Yoinker. It never touches the game process or its memory.
- Your progress is stored on the Archipelago server, so you can restart the client or switch PCs.
