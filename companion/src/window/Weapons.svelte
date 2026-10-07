<script>
  import { weaponIcon } from '../lib/format.js';
  import LockBadge from '../lib/LockBadge.svelte';

  const CATEGORIES = [
    ['Sidearm', 'Sidearms'], ['SMG', 'SMGs'], ['Shotgun', 'Shotguns'],
    ['Rifle', 'Rifles'], ['Sniper', 'Snipers'], ['Heavy', 'Heavies'],
  ];

  let { weapons, shop } = $props();

  const groups = $derived(
    CATEGORIES.map(([category, label]) => ({ label, list: weapons.list.filter((weapon) => weapon.category === category) }))
      .filter((group) => group.list.length),
  );
  const items = $derived(weapons.list.filter((weapon) => weapon.name !== 'Classic'));
  const unlocked = $derived(items.filter((weapon) => weapon.unlocked).length);
  let missingIcons = $state({}); // offline on first launch: hide the broken image, keep the name
</script>

<section>
  <h2>
    Weapons <span>{weapons.items ? `· ${unlocked} / ${items.length} unlocked` : ''}</span>
    {#if shop}<span class="credits" title="Kingdom Credits: rent a locked weapon for one match in the client's Shop tab">· {shop.credits} KC</span>{/if}
  </h2>
  {#if !weapons.items}
    <p class="note">Weapons aren't items in this world: every gun counts.</p>
  {/if}
  <div class="weapons">
    {#each groups as group (group.label)}
      <div class="weapon-group">
        <div class="weapon-group-name">{group.label}</div>
        <div class="weapon-list">
          {#each group.list as weapon (weapon.name)}
            <div
              class="weapon"
              class:locked={!weapon.unlocked && !weapon.rented}
              class:rented={!weapon.unlocked && weapon.rented}
              title={weapon.name === 'Classic' ? 'Classic (always available)'
                : weapon.unlocked ? weapon.name
                : weapon.rented ? `${weapon.name} (rented for one match)` : `${weapon.name} (locked)`}
            >
              <img
                src={weaponIcon(weapon.uuid)}
                alt=""
                hidden={missingIcons[weapon.uuid]}
                onerror={() => (missingIcons[weapon.uuid] = true)}
              />
              <span>{weapon.name}</span>
              {#if !weapon.unlocked && weapon.rented}<span class="rented-tag">Rented</span>
              {:else if !weapon.unlocked}<LockBadge />{/if}
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</section>
