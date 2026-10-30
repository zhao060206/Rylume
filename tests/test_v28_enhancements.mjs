import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const source = await readFile(new URL('../ui/canvas-editor.js', import.meta.url), 'utf8');
const { SceneEditor, legendOperations, hitObjects } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

// 1. Verify SceneEditor prototype has bringToFront, sendToBack, openContextMenu
assert.equal(typeof SceneEditor.prototype.bringToFront, 'function', 'bringToFront must be a function');
assert.equal(typeof SceneEditor.prototype.sendToBack, 'function', 'sendToBack must be a function');
assert.equal(typeof SceneEditor.prototype.openContextMenu, 'function', 'openContextMenu must be a function');

// 2. Test bringToFront and sendToBack reordering logic
const scene = {
  canvas: { width_mm: 180, height_mm: 120 },
  objects: [
    { id: 'o1', type: 'protein', label: 'A', x: 10, y: 10, w: 20, h: 10, visible: true },
    { id: 'o2', type: 'protein', label: 'B', x: 40, y: 10, w: 20, h: 10, visible: true },
    { id: 'o3', type: 'protein', label: 'C', x: 70, y: 10, w: 20, h: 10, visible: true }
  ],
  relations: [
    { id: 'r1', source: 'o1', target: 'o2', type: 'activates' }
  ]
};

const editor = Object.create(SceneEditor.prototype);
let recordedOps = [];
Object.assign(editor, {
  doc: structuredClone(scene),
  selected: new Set(['o1']),
  applyOperations(ops, label) {
    recordedOps.push({ ops, label });
    // Apply reorder
    if (ops[0]?.op === 'reorder') {
      const map = new Map(this.doc.objects.map(o => [o.id, o]));
      this.doc.objects = ops[0].ids.map(id => map.get(id)).filter(Boolean);
    }
  }
});

editor.bringToFront();
assert.equal(recordedOps.length, 1);
assert.deepEqual(editor.doc.objects.map(o => o.id), ['o2', 'o3', 'o1'], 'o1 should be moved to front');

editor.selected = new Set(['o3']);
editor.sendToBack();
assert.equal(recordedOps.length, 2);
assert.deepEqual(editor.doc.objects.map(o => o.id), ['o3', 'o2', 'o1'], 'o3 should be moved to back');

// 3. Test legend generation
const legendOps = legendOperations(scene, () => 'leg_1');
assert.ok(legendOps.length > 0, 'legendOperations should create legend items');
assert.ok(legendOps.some(op => op.op === 'add' && op.object.state === 'legend_activates'), 'must have legend_activates');

console.log('All v28 frontend enhancement checks passed!');
