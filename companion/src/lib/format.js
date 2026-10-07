// Small helpers shared by the windows.

export const ICON_BASE = 'https://media.valorant-api.com';

export function agentIcon(uuid) {
  return `${ICON_BASE}/agents/${uuid}/displayicon.png`;
}

export function weaponIcon(uuid) {
  return `${ICON_BASE}/weapons/${uuid}/displayicon.png`;
}

export function format(stat, value) {
  if (stat === 'K/D') return value.toFixed(2);
  if (stat === 'ACS' || stat === 'Performance') return String(Math.round(value));
  // Short-mode kills/assists/trades count extra, so those totals can be fractional: show whole ones.
  return String(Math.floor(value + 1e-9));
}

export function checksOf(agent) {
  let done = 0;
  let total = 0;
  for (const stat of agent.stats) {
    done += stat.done;
    total += stat.tiers.length;
  }
  return { done, total, complete: total > 0 && done === total };
}

/** A progress bar width, e.g. "42%". */
export function width(fraction) {
  return `${Math.max(0, Math.min(1, fraction || 0)) * 100}%`;
}
