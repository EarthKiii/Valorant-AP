# VALORANT Archipelago Companion

Optional app that runs next to VALORANT and the Archipelago client. It does three things:

- **Live stats:** lets the client count kills, 3Ks, aces, trades and clutches the moment they happen, instead of when
  the match ends.
- **Progress window:** your agents, their progress and your weapons (below).
- **Agent-select overlay:** an optional warning inside the game when you hover an agent that wouldn't count.

It's a small [ow-electron](https://www.npmjs.com/package/@overwolf/ow-electron) app, without the Overwolf client.
It loads Overwolf's game events package (the same feed Overwolf-based trackers use) and forwards VALORANT's events
as JSON to the client on `ws://127.0.0.1:43792`. All stat logic lives in the client. It also loads Overwolf's overlay
package for the optional agent-select overlay below.

It also shows a progress window fed by the client:

- your Radianite count and the match you're in;
- a card with the selected agent's progress: a bar per stat toward its next tier. It follows the agent you're
  playing, and you can click any agent in the grid to see theirs;
- a grid of every agent in your world (grayed with a lock until unlocked);
- every weapon, grouped like the buy menu (grayed with a lock until unlocked).

Agent and weapon icons come from valorant-api.com and are cached after the first load. Closing the window stops
the companion. Set `SHOW_WINDOW=false` in `.env` to run it headless instead, which uses less memory.

## Agent-select overlay (optional)

During agent select, a small note sits at the top center of the game:

- the agents you've unlocked, until you hover one;
- a red warning when the agent you hover or lock in wouldn't count (still locked, or not in your world), or when
  the game mode doesn't count;
- a green "counts" once you're on an agent that does.

It's drawn inside the game by Overwolf's overlay package (the same way Overwolf apps show in-game windows), so it
works in exclusive Fullscreen too. Mouse and keyboard go straight through to the game, and the note itself only
exists during agent select.

- `SHOW_OVERLAY=false` in `.env` turns it off. The overlay package then never attaches to VALORANT, so there's no
  in-game cost at all. When it's on, the package attaches when VALORANT starts and stays attached until it closes.
- `OVERLAY_TOP` moves it up or down (percent of the game's height, default 12).
- Start the companion before VALORANT if you can. If the game is already running, the companion asks the overlay to attach
  late, which should also work.
- Needs the same Overwolf developer credentials as the game events. The log says "In-game overlay attached to
  VALORANT" once it's ready. If VALORANT runs as administrator, the overlay stays off.
- It needs the client connected to your slot. Your pick comes from the live game events the moment it changes, with
  no requests to Riot. Without live events (e.g. missing credentials), the client asks Riot every 3 seconds instead.
  The client's log says which one it's using in each agent select.

## Setup

1. Install [Node.js](https://nodejs.org) 22+.
2. Get free developer credentials from the [Overwolf developer console](https://console.overwolf.com). Without
   them the companion still starts, but game events stay off ("invalid verification" in the log).
3. `npm install`
4. Put your credentials in `.env` (copy `.env.example` if it's missing):

   ```ini
   OW_CLI_EMAIL=you@example.com
   OW_CLI_API_KEY=your-api-key
   ```

   A dev token works too: set `OW_DEV_KEY` instead. If you started the client with a different `--companion-port`,
   set `VALORANT_AP_PORT` to match. `.env` is git-ignored.

## Run

```powershell
npm start
```

`npm start` builds the window, reads `.env` and launches the companion under ow-electron with those variables, so you
never have to set them in your shell. Variables already set in your shell take precedence over `.env`.

## Working on the window

The window is written in [Svelte](https://svelte.dev) 5 (`src/window/`, shared pieces in `src/lib/`).
`scripts/build.mjs` compiles it with esbuild into `renderer/build/` (one minified `.js` and `.css`), which
`renderer/window.html` loads. Svelte compiles each component into direct DOM updates: when the client sends new
progress, only the numbers and bars that changed are touched.

- `npm run build` builds once. `npm start` and `npm run pack` do it for you.
- `npm run watch` rebuilds on every save. Press Ctrl+R in the window to reload it.
- `npm run build -- --analyze` lists what's in the bundle, biggest first.

Styles are global, in `src/window/styles.css`. Styles inside a component (`<style>` blocks) are written to the
built `.css` file too, because the window's Content Security Policy only allows stylesheets shipped with the app.
For the same reason, set inline styles with `style:` directives (e.g. `style:width={...}`), not `style="..."`.

## Pack it

```powershell
npm run pack
```

This builds `dist/VALORANT Companion/`, a self-contained copy (about 360 MB, mostly the Electron runtime) that runs
without Node or npm. Double-click the **VALORANT Companion** shortcut in that folder to start it, or put that shortcut
on your desktop. Its settings and credentials are in `app\.env` (copied from your `.env` when you pack), so keep the
folder to yourself.

- Run `npm run pack` again after updating the companion.
- The shortcut stores the folder's full path. If you move the folder, use `Start VALORANT Companion.cmd` inside it, or
  pack again.

## Setup exe

```powershell
npm run sfx
```

This packs the companion and wraps it in one self-extracting file, `dist/VALORANT Companion Setup.exe` (about
145 MB), built with the C# compiler that ships with Windows. Running it:

- installs to `%LOCALAPPDATA%\Programs\VALORANT Companion` (no admin rights needed) and creates shortcuts on the
  Desktop and in the Start Menu;
- updates an existing install in place: the old files are replaced, but `app\.env` (settings and credentials) is
  kept. If the companion is running, it asks you to close it first;
- opens `app\.env` in Notepad if it has no Overwolf credentials yet, then offers to start the companion.

It never contains your credentials: your `app\.env` is swapped for the blank `.env.example`, so the file is safe to
share. Each person needs their own Overwolf developer credentials. It isn't signed, so Windows SmartScreen may warn
on the first run (**More info** → **Run anyway**).

`/dir=<folder>` installs somewhere else, and `/quiet` skips every dialog, shortcut and launch.

The app itself stays unpackaged on purpose; the setup just extracts it. Overwolf only enables dev mode, and with it
live game events, for apps that aren't packaged. A packaged build would need Overwolf's approval and signing, and
Overwolf doesn't approve private helper apps like this one.
