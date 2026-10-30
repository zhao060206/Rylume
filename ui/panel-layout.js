/** Reflow chrome without moving the document's visible center or changing its zoom. */
export function preserveCanvasView(editor, change) {
  const width = editor.host.clientWidth, height = editor.host.clientHeight;
  if (editor.scene) editor.fitMode = false; // A queued resize must not refit and change zoom.
  change();
  if (!editor.scene) return;
  editor.offset.x += (editor.host.clientWidth - width) / 2;
  editor.offset.y += (editor.host.clientHeight - height) / 2;
  editor.position();
}

export function syncPanelButtons(workspace, root = document) {
  const collapsed = workspace.classList.contains('left-collapsed');
  for (const b of root.querySelectorAll('[data-tab]')) {
    const expanded = !collapsed && b.classList.contains('active');
    b.setAttribute('aria-expanded', String(expanded));
  }
  root.getElementById('toggle-properties')?.setAttribute('aria-pressed', String(!workspace.classList.contains('properties-hidden')));
}
