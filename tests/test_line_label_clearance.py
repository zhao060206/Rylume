"""Connector curves clear every label (post-fix review, line-label-overlap trace
in docs/修复计划-2026-11-24-排版.md).

A. A connector label is placed clear of the OTHER connectors: in j_4c53 the
   label "recruitment" of e5 sat on e3 and e4, because label placement only
   avoided objects and object labels.
B. An automatic port covered by its object's own label moves to the label's
   outer edge: in j_eb6f the RAS-GTP and MEK labels sit right under their box,
   so r3/r5 started inside them and no bend could get out. Ports the user set
   (source_anchor/target_anchor) are kept.

Scenes are trimmed from studio jobs j_4c53883883e9/r1 and j_eb6fbc67bc1c/r4
(tests/line_label_clearance_scenes.json, shared with the .mjs test).
"""
import copy
import json
import pathlib

import pytest

from scene_document import audit_scene, empty_scene, normalize_scene
from scene_render import _object_label_boxes, connection_geometry

DATA = json.loads(pathlib.Path(__file__).with_name('line_label_clearance_scenes.json').read_text(encoding='utf-8'))


def _scene(name):
    d = copy.deepcopy(DATA[name])
    s = empty_scene()
    s['canvas'].update(width_mm=d['canvas'][0], height_mm=d['canvas'][1])
    s['objects'] = d['objects']
    s['relations'] = d['relations']
    s['compartments'] = d.get('compartments', [])
    return normalize_scene(s)


def _findings(scene, code):
    return {tuple(f['object_ids']) for f in audit_scene(scene)['findings'] if f['code'] == code}


def _rel(scene, rid):
    return next(r for r in scene['relations'] if r['id'] == rid)


def _inside(box, x, y, m=.2):
    return box['x'] - m < x < box['x'] + box['w'] + m and box['y'] - m < y < box['y'] + box['h'] + m


def test_connector_label_clears_other_connectors():
    scene = _scene('j_4c53')
    rel_ids = {r['id'] for r in scene['relations']}
    on_labels = {p for p in _findings(scene, 'line-label-overlap') if p[1] in rel_ids}
    assert not on_labels, on_labels
    # Still beside its own line.
    assert not any(p == ('e5',) for p in _findings(scene, 'line-label-detached'))


@pytest.mark.parametrize('name,rid,end,oid', [
    ('j_eb6f', 'r3', 's', 'ras'),
    ('j_eb6f', 'r5', 's', 'mek'),
    ('j_eb6f', 'r8', 't', 'pip2'),
    ('j_4c53', 'e3', 't', 'pip3'),
])
def test_line_leaves_from_outside_its_own_label(name, rid, end, oid):
    scene = _scene(name)
    assert (rid, oid) not in _findings(scene, 'line-label-overlap')
    g = connection_geometry(scene, _rel(scene, rid))
    box = next(b for b in _object_label_boxes(scene) if b['id'] == oid)
    x, y = (g['x1'], g['y1']) if end == 's' else (g['x2'], g['y2'])
    assert not _inside(box, x, y), (x, y, box)


def test_only_hand_drawn_overlaps_remain():
    assert _findings(_scene('j_4c53'), 'line-label-overlap') == set()
    # r2 is drawn by hand (relation.control) through the 'a RAS-MAPK' heading.
    assert _findings(_scene('j_eb6f'), 'line-label-overlap') <= {('r2', 'arm_mapk')}


def _stack(**rel):
    s = empty_scene()
    s['canvas'].update(width_mm=100, height_mm=100)
    s['objects'] = [
        {'id': 'a', 'type': 'kinase', 'label': 'RAS', 'x': 20, 'y': 20, 'w': 17, 'h': 10},
        {'id': 'b', 'type': 'kinase', 'label': 'RAF', 'x': 20, 'y': 50, 'w': 17, 'h': 10}]
    s['relations'] = [{'id': 'r', 'source': 'a', 'target': 'b', 'type': 'activates', **rel}]
    return normalize_scene(s)


def test_automatic_port_moves_below_own_label():
    scene = _stack()
    g = connection_geometry(scene, scene['relations'][0])
    box = next(b for b in _object_label_boxes(scene) if b['id'] == 'a')
    assert g['y1'] >= box['y'] + box['h'], (g['y1'], box)
    assert g['x1'] == pytest.approx(28.5)
    assert g['y2'] == pytest.approx(50)


def test_user_anchor_is_kept():
    scene = _stack(source_anchor={'side': 's', 't': .5})
    g = connection_geometry(scene, scene['relations'][0])
    assert (g['x1'], g['y1']) == pytest.approx((28.5, 30))


def test_port_unchanged_when_label_is_elsewhere():
    scene = _stack()
    scene['objects'][0]['label_dx'] = -30
    g = connection_geometry(scene, scene['relations'][0])
    assert g['y1'] == pytest.approx(30)


def test_side_port_slides_along_its_edge():
    # PIP3's label sits 1.5 mm left of its west port: the port slides along the
    # west edge past the label instead of the line ending on the text.
    scene = _scene('j_4c53')
    g = connection_geometry(scene, _rel(scene, 'e3'))
    pip3 = next(o for o in scene['objects'] if o['id'] == 'pip3')
    box = next(b for b in _object_label_boxes(scene) if b['id'] == 'pip3')
    assert g['x2'] == pytest.approx(pip3['x'])
    assert pip3['y'] + .8 <= g['y2'] <= pip3['y'] + pip3['h'] - .8
    assert g['y2'] <= box['y'] - 1 or g['y2'] >= box['y'] + box['h'] + 1, (g['y2'], box)
