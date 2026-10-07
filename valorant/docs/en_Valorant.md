# VALORANT

## What does randomization do to this game?

VALORANT itself is never modified (its anti-cheat wouldn't allow it). Instead, the VALORANT client watches the
matches you play and decides what counts:

- **Agents are items.** A match only counts if you played an agent you've unlocked. Lock in a locked agent during
  agent select and the client warns you (with a sound) right away.
- **Weapons are items.** The Classic, the knife and agent abilities are always allowed. Kills with a weapon you
  haven't unlocked don't count (or, with Weapon Enforcement set to Strict, void the whole match).
- **Checks are stat milestones per agent:** Kills, Assists, Trades, Clutches, Aces, 3Ks, K/D, Wins and Performance Score,
  each
  with configurable thresholds (e.g. "Jett - Kills Tier 2" = 15 kills as Jett by default).

## What is the goal?

Collect enough Radianite Crystals to reach Radiant. How many exist and how many you need are set in your options.

## What items can appear in other players' worlds?

Agents, weapons, Radianite Crystals and Kingdom Credits (filler).

## What are Kingdom Credits for?

With **Weapon Shop** on (the default), they're a currency. In the client's **Shop** tab, or with `/rent <weapon>`,
you can rent a weapon you haven't unlocked for one match: kills with it count, and Strict enforcement doesn't void the
match for it. Prices depend on the weapon type (**Rental Prices**: Sidearm 2, SMG 3, Shotgun 3, Heavy 4, Rifle 5,
Sniper 5 by default).

A rental is used on one match that counts (played with an unlocked agent in an allowed mode), and like a weapon you
receive, it counts from the next round that starts:

- rent in the menus or in agent select, and it covers your whole next match;
- rent between rounds, and it covers the rest of the match you're in; rent mid-round, and it starts with the next
  round. Kills you already made with that weapon never count. With Strict enforcement, having used it before renting
  still voids the match.

Unused rentals can be refunded (`/refund <weapon>` or the Shop tab). Rentals don't change what's in logic: the logic
only ever expects weapons you've unlocked.

## What happens when I receive an item?

It takes effect right away, even in the middle of a match:

- **Weapons** count from the next round that starts: one you receive between rounds counts for the round about to
  start, and one you receive mid-round from the round after. Kills made with it before it arrived never count. The
  client goes by when it saw the item arrive, so a weapon received while the client was closed counts from the next
  time you connect.
- **Agents:** a match counts as long as you've unlocked the agent before it ends.

The client plays a sound for new unlocks.

## How are the stats defined?

| Stat        | Definition                                                                                                   |
|-------------|--------------------------------------------------------------------------------------------------------------|
| Kills       | Enemies you killed (teamkills don't count).                                                                  |
| Assists     | Assists as reported by the game.                                                                             |
| Trades      | Killing the enemy who just killed a teammate, within the Trade Window (default 5 seconds).                   |
| Clutches    | Your team wins a round after you were your team's last player alive with enemies remaining.                  |
| Aces        | Rounds where you got 5 kills.                                                                                |
| 3Ks         | Rounds where you got 3 or more kills (an ace is also a 3K).                                                  |
| K/D         | Kills divided by deaths at the end of a match (0 deaths counts as 1).                                        |
| Wins        | Matches your team won.                                                                                       |
| Performance | Performance Score (0-500) of a match, as shown on the scoreboard (Competitive, Unrated, Swiftplay, Premier). |

With **Progress Mode: Cumulative** (default) stats add up across all your matches with that agent; with
**Single Match** each threshold has to be reached within one match. K/D and Performance Score always use your
best single match, and Wins always add up across matches.
Multi-kills, trades and clutches only exist in round-based modes (not in Deathmatch or Team Deathmatch).

**Short Mode Thresholds** lowers the Kill, Assist and Trade thresholds in Swiftplay and Spike Rush, which are much
shorter than a full match. At 75, a 20-kill check needs only 15 kills there (rounded up). Each kill, assist or trade
in those modes counts ×1.33 towards the regular thresholds, so matches in different modes add up fairly. The lowered
thresholds are listed in the spoiler log, when the client connects, in `/progress` and in the companion window's agent
card.

## How live is it?

- **Always live:** agent-select warnings, whether the match you just started will count, and fetching your results
  the moment the match ends (checks arrive seconds after Riot publishes the match).
- **Live during the match (optional):** run the companion app and kills, 3Ks, aces, trades and clutches count
  the instant they happen, and K/D and Wins the moment the match ends. Performance Score isn't in the live feed, so
  those checks arrive once Riot publishes the match. Riot's official match data still settles every match afterwards and
  replaces the live numbers.

## Which matches count?

Only matches that start after you first connect the client to your slot, in a game mode listed in Allowed Queues
(Competitive, Unrated, Swiftplay, Spike Rush and Premier by default; Skirmish and others can be added), played as
one of this world's agents that you've unlocked. Modes where everyone plays a generic character, like Gauntlet
(Ability Draft), never count because there's no agent to credit.
