<script>
  // The lowered Swiftplay / Spike Rush thresholds, with what's done, what's next and how much is left.
  let { stats, shortModes } = $props();

  const listed = $derived.by(() => {
    const nouns = stats.map((stat) => stat.stat.toLowerCase());
    const text = nouns.length > 1 ? `${nouns.slice(0, -1).join(', ')} and ${nouns[nouns.length - 1]}` : nouns[0];
    return text[0].toUpperCase() + text.slice(1);
  });

  function need(stat) {
    if (stat.done >= stat.tiers.length) return 'done';
    return shortModes.single_match ? 'in one match' : `${stat.short_needed} more`;
  }
</script>

<div class="short-modes">
  <div class="short-title">
    <span>{shortModes.queues.join(' & ')}</span>
    <span class="short-percent">{shortModes.percent}% thresholds</span>
  </div>
  <div class="short-list">
    {#each stats as stat (stat.stat)}
      <span class="stat-name">{stat.stat}</span>
      <span class="short-tiers">
        {#each stat.short_tiers as value, index (index)}
          <b class:done={index < stat.done} class:next={index === stat.done}>{value}</b>
        {/each}
      </span>
      <span class="short-need" class:done={stat.done >= stat.tiers.length}>{need(stat)}</span>
    {/each}
  </div>
  <p class="short-foot">{listed} there count {shortModes.weight} toward the bars above.</p>
</div>
