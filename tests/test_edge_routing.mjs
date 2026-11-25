// The editor's edgeGeometry must route connectors the same way as
// scene_render.connection_geometry (tests/test_connection_routing.py).
import test from 'node:test';
import assert from 'node:assert/strict';
import {edgeGeometry} from '../ui/canvas-editor.js';

const canvas = {width_mm: 180, height_mm: 120};

function samples(g, n = 60) {
  const out = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, u = 1 - t;
    out.push([u * u * g.start.x + 2 * u * t * g.control.x + t * t * g.end.x,
              u * u * g.start.y + 2 * u * t * g.control.y + t * t * g.end.y]);
  }
  return out;
}

function ratio(g) {
  const pts = samples(g);
  let len = 0;
  for (let i = 1; i < pts.length; i++) len += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  return len / Math.hypot(g.end.x - g.start.x, g.end.y - g.start.y);
}

function overshoot(g) {
  const chord = Math.hypot(g.end.x - g.start.x, g.end.y - g.start.y), slack = Math.max(6, .6 * chord);
  const lx = Math.min(g.start.x, g.end.x) - slack, hx = Math.max(g.start.x, g.end.x) + slack;
  const ly = Math.min(g.start.y, g.end.y) - slack, hy = Math.max(g.start.y, g.end.y) + slack;
  return Math.max(...samples(g).map(([x, y]) => Math.max(lx - x, x - hx, ly - y, y - hy)));
}

const obj = (id, label, x, y) => ({id, type: 'kinase', label, x, y, w: 17, h: 10, visible: true});

test('an endpoint object\'s own label does not bend the connector', () => {
  const scene = {canvas, objects: [obj('mek', 'MEK', 132, 50), obj('erk', 'ERK', 132, 67)],
    relations: [{id: 'r5', source: 'mek', target: 'erk', type: 'activates'}]};
  const g = edgeGeometry(scene, scene.relations[0]);
  assert.ok(ratio(g) < 1.2, g.path);
  assert.ok(overshoot(g) <= 0, g.path);
});

test('endpoints sharing a side are spread apart without crossing', () => {
  const scene = {canvas, objects: [obj('egfr', '', 90, 10), obj('ras', '', 60, 60), obj('raf', '', 30, 10)],
    relations: [{id: 'r2', source: 'egfr', target: 'ras', type: 'activates'},
                {id: 'r3', source: 'ras', target: 'raf', type: 'activates'}]};
  const a = edgeGeometry(scene, scene.relations[0]).end, b = edgeGeometry(scene, scene.relations[1]).start;
  assert.ok(Math.hypot(a.x - b.x, a.y - b.y) >= 3, JSON.stringify({a, b}));
  assert.ok(Math.abs(a.y - 60) < 1e-6 && Math.abs(b.y - 60) < 1e-6, JSON.stringify({a, b}));
  assert.ok(60 < b.x && b.x < a.x && a.x < 77, JSON.stringify({a, b}));
});

test('a single connector on a side stays centred', () => {
  const scene = {canvas, objects: [obj('egfr', '', 90, 10), obj('ras', '', 60, 60)],
    relations: [{id: 'r2', source: 'egfr', target: 'ras', type: 'activates'}]};
  const e = edgeGeometry(scene, scene.relations[0]).end;
  assert.ok(Math.abs(e.x - 68.5) < 1e-6 && Math.abs(e.y - 60) < 1e-6, JSON.stringify(e));
});
