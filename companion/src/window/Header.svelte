<script>
  let { player, radianite, goal, status } = $props();
</script>

<header>
  <div class="title-row">
    <div>
      <h1>VALORANT <span>Archipelago</span></h1>
      <p class="muted">{player}</p>
    </div>
    {#if radianite}
      <div
        class="radianite"
        class:goal={goal || radianite.have >= radianite.need}
        title="{radianite.have} Radianite Crystals collected, {radianite.need} needed to win, {radianite.total} in the pool"
      >
        <span class="gem"></span><span>{radianite.have} / {radianite.need}</span>
      </div>
    {:else}
      <div class="radianite" title="Radianite Crystals collected / needed to win">
        <span class="gem"></span><span>-</span>
      </div>
    {/if}
  </div>
  <ul class="status">
    <li class:on={status.client}>Client</li>
    <li class:on={status.game}>VALORANT</li>
    <li class:on={status.live}>Live stats</li>
  </ul>
</header>
