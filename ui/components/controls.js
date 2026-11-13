/** Native adaptations of BoardUI's MIT button/input/segmented-control patterns.
 * BoardUI © 2026 Mertcan Dundar Esmergul. See THIRD_PARTY_UI.md.
 * Existing canvas controls retain their own listeners and document state.
 */
export function segmentIndex(current, key, count) {
  if (!count) return -1;
  if (key === 'Home') return 0;
  if (key === 'End') return count - 1;
  if (key === 'ArrowRight') return (current + 1) % count;
  if (key === 'ArrowLeft') return (current + count - 1) % count;
  return current;
}

export function enhanceSegments(root, {attribute = 'aria-selected', keyboard = true} = {}) {
  if (!root) return;
  root.classList.add('ui-segments');
  const buttons = [...root.querySelectorAll(':scope > button')];
  let indicator = root.querySelector('.workspace-mode-thumb');
  if (!indicator) {
    indicator = document.createElement('span');
    indicator.setAttribute('aria-hidden', 'true');
    root.prepend(indicator);
  }
  indicator.classList.add('ui-segment-indicator');
  const measure = () => {
    const selected = buttons.find(b => b.getAttribute(attribute) === 'true');
    if (!selected) return;
    indicator.style.transform = `translateX(${selected.offsetLeft}px) scaleX(${selected.offsetWidth})`;
  };
  const resize = new ResizeObserver(measure);
  resize.observe(root);
  for (const button of buttons) resize.observe(button);
  const observer = new MutationObserver(measure);
  observer.observe(root, {subtree: true, attributes: true, attributeFilter: [attribute]});
  if (keyboard) root.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const current = Math.max(0, buttons.findIndex(b => b.getAttribute(attribute) === 'true'));
    const button = buttons[segmentIndex(current, event.key, buttons.length)];
    button.focus(); button.click();
  });
  measure();
  return () => {resize.disconnect(); observer.disconnect();};
}

/** Arrow navigation for native details menus; regular Tab keeps its meaning. */
export function setupMenuKeyboard(root = document) {
  root.addEventListener('keydown', event => {
    const menu = event.target.closest?.('details.app-menu,details.floating-options');
    if (!menu || !['ArrowDown', 'ArrowUp', 'Home', 'End', 'Escape'].includes(event.key)) return;
    if (event.target.matches('input,select,textarea')) return;
    event.preventDefault(); event.stopPropagation();
    const summary = menu.querySelector(':scope > summary');
    if (event.key === 'Escape') {menu.open = false; summary?.focus(); return;}
    menu.open = true;
    const items = [...menu.querySelectorAll('button:not(:disabled),a[href],.document-submenu>summary')].filter(n => n.checkVisibility?.() ?? n.getClientRects().length);
    if (!items.length) return;
    const current = items.indexOf(document.activeElement);
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1
      : current < 0 ? (event.key === 'ArrowUp' ? items.length - 1 : 0)
      : (current + (event.key === 'ArrowUp' ? -1 : 1) + items.length) % items.length;
    items[next].focus();
  });
}

/** A compact options disclosure closes like a normal popup, without losing inputs. */
export function setupOptionsDisclosure(root) {
  if (!root) return;
  const summary=root.querySelector(':scope > summary');
  root.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&root.open){event.preventDefault();event.stopPropagation();root.open=false;summary.focus();}
  });
  document.addEventListener('pointerdown',event=>{if(root.open&&!root.contains(event.target))root.open=false;});
}
