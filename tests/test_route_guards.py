"""Route guards: a connector must not run through its own end objects, leave the canvas, or end
right next to another connector's end after sliding past its own label."""
import copy
import math

import scene_render as sr
from scene_document import audit_scene
from scene_templates import make_template

SINGLE = {'width_mm': 90, 'height_mm': 150}


def _codes(scene, code):
    return [f for f in audit_scene(scene)['findings'] if f['code'] == code]


def _rel(scene, rid):
    return next(r for r in scene['relations'] if r['id'] == rid)


def test_line_through_its_own_end_is_reported_and_fixed():
    scene = make_template('signal_horizontal')
    assert not _codes(scene, 'connector-through-end')
    bad = copy.deepcopy(scene)
    _rel(bad, 'e6').update(source_port='e', target_port='e', control={'x': 131.2, 'y': 57.0})
    found = _codes(bad, 'connector-through-end')
    assert found and found[0]['object_ids'][0] == 'e6'
    result = sr.preview_finding_fix(bad, found[0])
    assert result['changed'] and not _codes(result['scene'], 'connector-through-end')


def test_line_leaving_the_canvas_is_reported_and_fixed():
    scene = make_template('network_columns', **SINGLE)
    assert not _codes(scene, 'connector-outside-canvas')
    bad = copy.deepcopy(scene)
    # Far enough left that the bend leaves the canvas whatever ports e3 ends up on.
    _rel(bad, 'e3')['control'] = {'x': -40.0, 'y': 74.0}
    g = sr.connection_geometry(bad, _rel(bad, 'e3'))
    assert min(x for x, _ in sr.connection_samples(g)) < 0, 'test premise: the injected bend must leave the canvas'
    found = _codes(bad, 'connector-outside-canvas')
    assert found and found[0]['object_ids'] == ['e3']
    result = sr.preview_finding_fix(bad, found[0])
    assert result['changed'] and not _codes(result['scene'], 'connector-outside-canvas')


def test_automatic_bend_stays_on_the_canvas():
    scene = make_template('network_columns', **SINGLE)
    g = sr.connection_geometry(scene, _rel(scene, 'e3'))
    W, H = scene['canvas']['width_mm'], scene['canvas']['height_mm']
    assert all(0 <= x <= W and 0 <= y <= H for x, y in sr.connection_samples(g))

def test_slide_past_own_label_keeps_clear_of_other_ends():
    for tid in ('signal_horizontal', 'signal_lipid', 'signal_convergent'):
        scene = make_template(tid)
        e4, e5 = (sr.connection_geometry(scene, _rel(scene, r)) for r in ('e4', 'e5'))
        assert math.dist((e4['x2'], e4['y2']), (e5['x1'], e5['y1'])) >= 1.5, tid


def test_slide_is_skipped_when_both_spots_are_taken():
    o = {'x': 0, 'y': 0, 'w': 10, 'h': 10}
    box = {'x': -6, 'y': 4, 'w': 6, 'h': 2}
    assert sr._clear_own_label(o, 'w', 0, 5, box, taken=[2.5, 7.5]) == (0, 5)
    assert sr._clear_own_label(o, 'w', 0, 5, box, taken=[7.5]) == (0, 2.5)


def test_end_symbol_on_a_label_is_reported_and_fixed():
    scene = make_template('network_columns', **SINGLE)
    assert not _codes(scene, 'connector-symbol-on-label')
    bad = copy.deepcopy(scene)
    _rel(bad, 'e5').update(source_port='s', target_port='s', control={'x': 59.85, 'y': 88.28})
    found = _codes(bad, 'connector-symbol-on-label')
    assert found and found[0]['object_ids'] == ['e5', 'tumor']
    result = sr.preview_finding_fix(bad, found[0])
    assert result['changed'] and not _codes(result['scene'], 'connector-symbol-on-label')
