<script>
  import { format, width } from '../lib/format.js';

  let { stat, shortModes } = $props();

  const complete = $derived(stat.done >= stat.tiers.length);
  const target = $derived(complete ? stat.tiers[stat.tiers.length - 1] : stat.tiers[stat.done]);
  const title = $derived.by(() => {
    let text = `${stat.stat} tiers: ${stat.tiers.map((tier) => format(stat.stat, tier)).join(', ')}`;
    if (stat.short_tiers && shortModes) {
      text += `\n${shortModes.queues.join(' & ')}: ${stat.short_tiers.join(', ')}`
        + ` (each one there counts ${shortModes.weight})`;
    }
    return text;
  });
</script>

<div class="stat" class:complete {title}>
  <span class="stat-name">{stat.stat}</span>
  <div class="bar"><div style:width={width(complete ? 1 : stat.value / target)}></div></div>
  <span class="value">
    {format(stat.stat, stat.value)}{#if !complete}<small>{` / ${format(stat.stat, target)}`}</small>{/if}
  </span>
  <span class="pips">
    {#each stat.tiers as _, index (index)}<i class:done={index < stat.done}></i>{/each}
  </span>
</div>
