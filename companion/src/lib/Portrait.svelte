<script>
  // An agent's icon, with their initials when it can't load (e.g. offline on first launch).
  import { agentIcon } from './format.js';
  import LockBadge from './LockBadge.svelte';

  let { agent, big = false, lock = false } = $props();

  const src = $derived(agentIcon(agent.uuid));
  let failed = $state('');
</script>

<span class="portrait" class:big class:no-icon={failed === src} data-initials={agent.name.slice(0, 2).toUpperCase()}>
  <img {src} alt="" onerror={() => (failed = src)} />
  {#if lock}<LockBadge />{/if}
</span>
