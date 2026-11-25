"""Connector labels sit right beside their own line (step 5 of
docs/修复计划-2026-11-24-排版.md).

04 r1: a 4 mm vertical binding line between EGF and EGFR had its label
"EGF binding" pushed 11 mm away, because the only candidate shifts were
up/down/left/right of the midpoint. Labels now try both sides of the line
along its normal first, labels more than 4 mm off their line are reported as
line-label-detached, and binding partners keep enough room for the two rings
and a visible line between them.
"""
import copy
import math

import pytest

import scene_render
from scene_document import audit_scene, empty_scene, normalize_scene
from scene_render import connection_geometry, label_boxes, layout_scene, line_label_gap, preview_finding_fix
from scene_templates import TEMPLATES, make_template

OLD_OFFSETS = [(0, 0), (0, -4), (0, 4), (0, -8), (0, 8), (-8, 0), (8, 0), (0, -12), (0, 12), (-12, 0), (12, 0),
               (-18, 0), (18, 0), (-24, 0), (24, 0), (-18, 4), (18, 4)]


def _samples(g, n=80):
    c = g['control']
    for i in range(n + 1):
        t = i / n; u = 1 - t
        yield u*u*g['x1'] + 2*u*t*c['x'] + t*t*g['x2'], u*u*g['y1'] + 2*u*t*c['y'] + t*t*g['y2']


def _gap(scene, rid):
    """Distance (mm) from a relation's label box to its own curve, measured independently."""
    r = next(x for x in scene['relations'] if x['id'] == rid)
    b = next(x for x in label_boxes(scene) if x.get('id') == rid)
    return min(math.hypot(max(0, b['x'] - x, x - b['x'] - b['w']), max(0, b['y'] - y, y - b['y'] - b['h']))
               for x, y in _samples(connection_geometry(scene, r)))


def _codes(scene):
    return {(f['code'], tuple(f['object_ids'])) for f in audit_scene(scene)['findings']}


def _binding_04():
    # 04 r10 as saved (studio job j_d5232f5b2fe5): EGF 4 mm above EGFR, its own
    # label moved off to the upper left, and the binding label wider than the
    # line is long.
    scene = empty_scene()
    scene['canvas'].update(width_mm=180, height_mm=120)
    scene['objects'] = [
        {'id': 'egf', 'type': 'ligand', 'label': 'EGF', 'x': 83.5, 'y': 11, 'w': 13, 'h': 9,
         'label_dx': -18, 'label_dy': -10, 'label_user_set': True},
        {'id': 'egfr', 'type': 'receptor', 'label': 'EGFR', 'x': 84.5, 'y': 24, 'w': 11, 'h': 20},
    ]
    scene['relations'] = [{'id': 'r1', 'source': 'egf', 'target': 'egfr', 'type': 'binds', 'label': 'EGF binding'}]
    return normalize_scene(scene)


def test_short_binding_label_hugs_its_line():
    scene = _binding_04()
    assert _gap(scene, 'r1') <= 3
    assert line_label_gap(scene, scene['relations'][0]) == pytest.approx(_gap(scene, 'r1'), abs=.05)


@pytest.mark.parametrize('tid,rid', [('assembly_horizontal', 'e5'), ('signal_vertical', 'e6')])
def test_template_connector_labels_stay_beside_their_line(tid, rid):
    scene = layout_scene(make_template(tid))
    assert _gap(scene, rid) <= 4
    assert not any(c == 'line-label-detached' for c, _ in _codes(scene))


def test_old_placement_is_reported_detached(monkeypatch):
    monkeypatch.setattr(scene_render, '_label_offsets', lambda *a: list(OLD_OFFSETS))
    scene = _binding_04()
    assert _gap(scene, 'r1') > 4
    found = [f for f in audit_scene(scene)['findings'] if f['code'] == 'line-label-detached']
    assert [f['object_ids'] for f in found] == [['r1']]
    assert found[0]['evidence']['distance_mm'] > 4


def test_hand_placed_label_is_never_flagged():
    scene = _binding_04()
    scene['relations'][0]['label_position'] = {'x': 140, 'y': 100}
    assert _gap(scene, 'r1') > 4
    assert not any(c == 'line-label-detached' for c, _ in _codes(scene))


def test_detached_fix_pins_label_back_beside_line(monkeypatch):
    # A far spot ranked first: automatic placement takes it, and the preview
    # must not accept it just because a pinned label is no longer reviewed.
    real = scene_render._label_offsets
    monkeypatch.setattr(scene_render, '_label_offsets', lambda *a: [(0, -14)] + real(*a))
    scene = _binding_04()
    assert _gap(scene, 'r1') > 4
    finding = next(f for f in audit_scene(scene)['findings'] if f['code'] == 'line-label-detached')
    result = preview_finding_fix(scene, finding)
    assert result['changed'], result.get('message')
    fixed = copy.deepcopy(scene)
    fixed['relations'][0]['label_position'] = result['operations'][0]['changes']['label_position']
    assert _gap(fixed, 'r1') <= 4


def test_nucleus_row_leaves_room_for_a_labelled_line():
    # signal_vertical: nuclear STAT -> DNA "transcription" used to be 6.3 mm
    # apart, so the 13 mm label could only sit above both objects.
    scene = layout_scene(make_template('signal_vertical'))
    by_id = {o['id']: o for o in scene['objects']}
    a, b = sorted((by_id['nuclear_stat'], by_id['dna']), key=lambda o: o['x'])
    need = scene_render._measure('transcription', 7 * scene_render.PT_MM) + 3
    assert b['x'] - (a['x'] + a['w']) >= need - .01
    assert a['x'] >= 7 and b['x'] + b['w'] <= scene['canvas']['width_mm'] - 7


def _ligand_bindings():
    for item in TEMPLATES:
        if item.get('family') != 'pathway' or item.get('new_scene_only'):
            continue
        scene = layout_scene(make_template(item['id']))
        by_id = {o['id']: o for o in scene['objects']}
        for r in scene['relations']:
            if r['type'] == 'binds' and by_id[r['source']]['type'] == 'ligand':
                yield item['id'], scene, r


def test_binding_rings_leave_a_visible_line():
    # Two 1 mm rings, each 0.5 mm from its partner: the line shows only when
    # the partners are more than 5 mm apart; plan asks for >= 2 mm of it.
    checked = 0
    for tid, scene, r in _ligand_bindings():
        pts = list(_samples(connection_geometry(scene, r)))
        length = sum(math.dist(p, q) for p, q in zip(pts, pts[1:]))
        gaps = (0 if r.get('source_anchor') else .5) + (0 if r.get('target_anchor') else .5)
        assert length - gaps - 4 >= 2 - .05, (tid, r['id'], round(length, 2))
        checked += 1
    assert checked

def test_line_label_avoids_context_edge():
    """exosome_transfer r2 'release' used to straddle the recipient-cell outline."""
    from scene_storyboards import make_storyboard
    from scene_render import label_boxes, line_label_gap
    s = make_storyboard('exosome_transfer', width_mm=180, height_mm=120)
    if 'objects' not in s:
        s = s['scene']
    r = next(x for x in s['relations'] if x['id'] == 'r2')
    b = next(x for x in label_boxes(s) if x.get('id') == 'r2')
    c = next(o for o in s['objects'] if o['id'] == 'recipient')
    ov = max(0, min(b['x'] + b['w'], c['x'] + c['w']) - max(b['x'], c['x'])) *         max(0, min(b['y'] + b['h'], c['y'] + c['h']) - max(b['y'], c['y']))
    assert ov <= .05 or ov >= b['w'] * b['h'] * .98
    assert line_label_gap(s, r) <= 4
