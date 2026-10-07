<script>
  import { checksOf, width } from '../lib/format.js';
  import Portrait from '../lib/Portrait.svelte';
  import ShortModes from './ShortModes.svelte';
  import StatRow from './StatRow.svelte';

  let { agent, shortModes } = $props();

  const checks = $derived(checksOf(agent));
  // Same pip column width on every row, so the bars line up.
  const tiers = $derived(Math.max(1, ...agent.stats.map((stat) => stat.tiers.length)));
  const shortStats = $derived(shortModes ? agent.stats.filter((stat) => stat.short_tiers) : []);
</script>

<article class="agent-card" class:locked={!agent.unlocked}>
  <div class="card-head">
    <Portrait {agent} big />
    <div class="card-info">
      <div class="card-title"><span>{agent.name}</span><span class="role">{agent.role || ''}</span></div>
      <div class="card-sub">
        {checks.done} / {checks.total} checks{#if !agent.unlocked}<span class="locked-pill">Locked</span>{/if}
      </div>
      <div class="bar" class:complete={checks.complete}>
        <div style:width={width(checks.total ? checks.done / checks.total : 0)}></div>
      </div>
    </div>
  </div>
  {#if !agent.unlocked}
    <p class="card-note">Find {agent.name} in the multiworld to start earning these checks.</p>
  {/if}
  <div class="stats" style:--tiers={tiers}>
    {#each agent.stats as stat (stat.stat)}
      <StatRow {stat} {shortModes} />
    {/each}
  </div>
  {#if shortStats.length}
    <ShortModes stats={shortStats} {shortModes} />
  {/if}
</article>
