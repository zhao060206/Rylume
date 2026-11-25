// The editor places connector labels like scene_render.connection_geometry:
// beside the line along its normal first (tests/test_line_label_placement.py).
import test from 'node:test';
import assert from 'node:assert/strict';
import {edgeGeometry} from '../ui/canvas-editor.js';

const canvas = {width_mm: 180, height_mm: 120};
const H = 7 * 25.4 / 72;

function samples(g, n = 80) {
  const out = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, u = 1 - t;
    out.push([u * u * g.start.x + 2 * u * t * g.control.x + t * t * g.end.x,
              u * u * g.start.y + 2 * u * t * g.control.y + t * t * g.end.y]);
  }
  return out;
}

// Label box as rendered: centred on label.x, baseline at label.y.
function gap(g, width) {
  const x = g.label.x - width / 2, y = g.label.y - H * .8;
  return Math.min(...samples(g).map(([px, py]) => Math.hypot(Math.max(0, x - px, px - x - width), Math.max(0, y - py, py - y - H))));
}

// 04 r10: EGF 4 mm above EGFR, EGF's own label moved away to the upper left.
const scene04 = () => ({canvas,
  objects: [
    {id: 'egf', type: 'ligand', label: 'EGF', x: 83.5, y: 11, w: 13, h: 9, label_dx: -18, label_dy: -10, visible: true},
    {id: 'egfr', type: 'receptor', label: 'EGFR', x: 84.5, y: 24, w: 11, h: 20, visible: true}],
  relations: [{id: 'r1', source: 'egf', target: 'egfr', type: 'binds', label: 'EGF binding'}]});

test('a short binding line keeps its label right beside it', () => {
  const scene = scene04();
  const g = edgeGeometry(scene, scene.relations[0]);
  assert.ok(g.label, JSON.stringify(Object.keys(g)));
  // "EGF binding" at 7 pt is ~13.7 mm wide; anything under that is generous.
  assert.ok(gap(g, 13) <= 3, JSON.stringify(g.label));
  // Beside the line, not on it: the label does not cover the line.
  assert.ok(gap(g, 13) > 0, JSON.stringify(g.label));
});

test('a horizontal line puts its label above, a hand-placed one is kept', () => {
  const scene = {canvas,
    objects: [{id: 'a', type: 'kinase', label: '', x: 20, y: 50, w: 17, h: 10, visible: true},
              {id: 'b', type: 'kinase', label: '', x: 90, y: 50, w: 17, h: 10, visible: true}],
    relations: [{id: 'r', source: 'a', target: 'b', type: 'activates', label: 'phosphorylation'}]};
  const g = edgeGeometry(scene, scene.relations[0]);
  assert.ok(g.label.y < 55, JSON.stringify(g.label));
  assert.ok(gap(g, 20) <= 3, JSON.stringify(g.label));
  scene.relations[0].label_position = {x: 150, y: 100};
  const kept = edgeGeometry(scene, scene.relations[0]);
  assert.deepEqual([kept.label.x, kept.label.y], [150, 100]);
});
