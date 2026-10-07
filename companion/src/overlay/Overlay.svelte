<script>
  // Agent select: warns when the agent you hover or lock in (or the mode) wouldn't count, and otherwise confirms it.
  let pregame = $state.raw(null);
  window.companion.onPregame((next) => (pregame = next));

  const view = $derived.by(() => {
    if (!pregame) return null;
    const { agent, locked, problem, queue_problem: queueProblem, unlocked } = pregame;
    if (queueProblem) return { kind: 'warn', title: "This match won't count", detail: queueProblem };
    if (agent && problem) {
      return locked
        ? { kind: 'warn', title: `You locked in ${agent}`, detail: `${problem}: this match won't count.` }
        : { kind: 'warn', title: problem, detail: "This match won't count. Pick an unlocked agent." };
    }
    if (agent) return { kind: 'ok', title: locked ? `Locked in ${agent}: this one counts` : `${agent} counts`, detail: '' };
    return { kind: 'info', title: 'Unlocked agents', detail: unlocked.join(', ') || 'none yet' };
  });
</script>

{#if view}
  <div class="pill {view.kind}">
    <svg class="icon" viewBox="0 0 16 16" aria-hidden="true">
      {#if view.kind === 'warn'}
        <path d="M8 1.5 15.5 14.5H.5L8 1.5zm-.9 5v4h1.8v-4H7.1zm0 5.2v1.7h1.8v-1.7H7.1z" />
      {:else}
        <path d="M6.4 11.2 2.9 7.7 1.5 9.1l4.9 4.9 8.1-8.1-1.4-1.4z" />
      {/if}
    </svg>
    <div class="text">
      <span class="title">{view.title}</span>
      {#if view.detail}<span class="detail">{view.detail}</span>{/if}
    </div>
  </div>
{/if}
