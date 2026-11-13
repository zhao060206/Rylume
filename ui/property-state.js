/** Keep a numeric edit from collapsing the inspector on every scene update. */
const states = new WeakMap();
export function preservePropertyState(parent, key, render) {
  const same = states.get(parent) === key;
  const opened = same ? new Set([...parent.querySelectorAll('details[open]')].map(n => n.querySelector('summary')?.textContent)) : new Set();
  const scroll = parent.scrollTop;
  const active = parent.ownerDocument.activeElement;
  const label = same && parent.contains(active) ? active.getAttribute('aria-label') : null;
  render();
  states.set(parent, key);
  for (const n of parent.querySelectorAll('details')) n.open = opened.has(n.querySelector('summary')?.textContent);
  if (label) [...parent.querySelectorAll('input,select')].find(n => n.getAttribute('aria-label') === label)?.focus({preventScroll:true});
  if (same) parent.scrollTop = scroll;
}
