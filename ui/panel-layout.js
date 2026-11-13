/** Reflow chrome without moving the document's visible center or changing its zoom. */
export function preserveCanvasView(editor, change) {
  const width = editor.host.clientWidth, height = editor.host.clientHeight;
  const offset = editor.scene ? {...editor.offset} : null;
  const canvas=editor.scene?.canvas;
  // Dragging an object exits fit mode, even when the entire page still fits.
  // Keep that overview visible when an inspector takes part of its space.
  const fitted=!!editor.fitMode || !!(canvas && canvas.width_mm*96/25.4*editor.zoom <= width && canvas.height_mm*96/25.4*editor.zoom <= height);
  change();
  if (!editor.scene) return;
  if(fitted&&editor.fit){editor.fit();return;}
  editor.fitMode=false;
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
