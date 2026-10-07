<script>
  // Shows what the Archipelago client sends: a card for the selected agent, a grid of every agent (grayed with a
  // lock when locked) and the weapons.
  import AgentCard from './AgentCard.svelte';
  import AgentGrid from './AgentGrid.svelte';
  import Header from './Header.svelte';
  import Weapons from './Weapons.svelte';

  // The client resends its whole state on every change, so it's kept raw (no deep proxies): each update is one
  // signal, and Svelte only touches the DOM nodes whose values actually changed.
  let state = $state.raw(null);
  let status = $state.raw({ client: false, game: false, live: false });
  let picked = $state(null); // the agent shown in the card, by name
  let followedMatchAgent = null;

  window.companion.onState((next) => {
    // Follow the agent you're playing whenever a new match starts; otherwise keep the user's pick.
    const playing = (next.match && next.match.agent) || null;
    if (playing && playing !== followedMatchAgent) picked = playing;
    followedMatchAgent = playing;
    state = next;
  });
  window.companion.onStatus((next) => (status = next));

  const ready = $derived(Boolean(status.client && state && state.connected));
  const match = $derived(ready ? state.match : null);
  const selected = $derived(
    ready
      ? state.agents.find((agent) => agent.name === picked)
        || state.agents.find((agent) => agent.unlocked)
        || state.agents[0]
      : null,
  );
  const matchText = $derived.by(() => {
    if (!match) return '';
    const counts = match.problem ? `doesn't count: ${match.problem}` : 'counts';
    const lowered = !match.problem && match.short && state.short_modes
      ? ` · ${match.queue}: ${state.short_modes.percent}% thresholds` : '';
    return `In match: ${match.agent || 'unknown agent'} on ${match.map} · ${counts}${lowered}`;
  });
</script>

<Header
  player={ready ? state.slot : ''}
  radianite={ready ? state.radianite : null}
  goal={ready && state.goal}
  {status}
/>
<main>
  {#if match}
    <p class="match" class:bad={match.problem}>{matchText}</p>
  {/if}
  {#if !ready}
    <p class="empty">
      {status.client ? 'Client running. Connect it to your Archipelago slot.' : 'Waiting for the Archipelago VALORANT client…'}
    </p>
  {:else}
    {#if selected}
      <AgentCard agent={selected} shortModes={state.short_modes} />
    {/if}
    <AgentGrid
      agents={state.agents}
      selected={selected && selected.name}
      playing={match && match.agent}
      onselect={(name) => (picked = name)}
    />
    <Weapons weapons={state.weapons} shop={state.shop} />
  {/if}
</main>
