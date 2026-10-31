/** Reflow chrome without moving the document's visible center or changing its zoom. */
export function preserveCanvasView(editor, change) {
  const width = editor.host.clientWidth, height = editor.host.clientHeight;
  const offset = editor.scene ? {...editor.offset} : null;
  if (editor.scene) editor.fitMode = false; // A queued resize must not refit and change zoom.
  change();
  if (!editor.scene) return;
  editor.offset.x = offset.x + (editor.host.clientWidth - width) / 2;
  editor.offset.y = offset.y + (editor.host.clientHeight - height) / 2;
  editor.position();
}

export function syncPanelButtons(workspace, root = document) {
  const collapsed = workspace.classList.contains('left-collapsed');
  const assets = root.getElementById('asset-library-dialog');
  for (const b of root.querySelectorAll('[data-tab]')) {
    const expanded = b.dataset?.tab==='assets'&&assets
      ? assets.open&&!assets.classList.contains('is-minimized')
      : !collapsed && b.classList.contains('active');
    b.setAttribute('aria-expanded', String(expanded));
  }
  root.getElementById('toggle-properties')?.setAttribute('aria-pressed', String(!workspace.classList.contains('properties-hidden')));
}
