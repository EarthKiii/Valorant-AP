<script>
  import { checksOf, width } from '../lib/format.js';
  import Portrait from '../lib/Portrait.svelte';

  let { agents, selected, playing, onselect } = $props();

  const sorted = $derived([...agents].sort((a, b) => a.name.localeCompare(b.name)));
  const unlocked = $derived(agents.filter((agent) => agent.unlocked).length);
</script>

<section>
  <h2>Agents <span>· {unlocked} / {agents.length} unlocked</span></h2>
  <div class="agent-grid">
    {#each sorted as agent (agent.name)}
      {@const checks = checksOf(agent)}
      <button
        class="tile"
        class:locked={!agent.unlocked}
        class:selected={agent.name === selected}
        class:playing={agent.name === playing}
        title="{agent.name}{agent.unlocked ? '' : ' (locked)'} · {checks.done} / {checks.total} checks"
        onclick={() => onselect(agent.name)}
      >
        <Portrait {agent} lock={!agent.unlocked} />
        <span class="tile-name">{agent.name}</span>
        <div class="bar" class:complete={checks.complete}>
          <div style:width={width(checks.total ? checks.done / checks.total : 0)}></div>
        </div>
      </button>
    {/each}
  </div>
</section>
