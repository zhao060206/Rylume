"""Connector routing must bend around obstacles, never overshoot past its ends.

Regression for the 2026-11-24 check: a vertical MEK->ERK arrow whose straight
line crossed MEK's own label was routed via a collinear control point 60 mm
above, so it looked like an arrow coming out of the membrane.
"""
import math

import pytest

from scene_document import empty_scene
import scene_render
from scene_render import connection_geometry


def _samples(g, n=60):
    x1, y1, x2, y2 = g['x1'], g['y1'], g['x2'], g['y2']
    cx, cy = g['control']['x'], g['control']['y']
    for i in range(n + 1):
        t = i / n; u = 1 - t
        yield u*u*x1 + 2*u*t*cx + t*t*x2, u*u*y1 + 2*u*t*cy + t*t*y2


def _overshoot(g):
    """How far (mm) the curve leaves the endpoints' box, beyond a small slack."""
    chord = math.hypot(g['x2'] - g['x1'], g['y2'] - g['y1'])
    slack = max(6.0, 0.6 * chord)
    lo_x, hi_x = min(g['x1'], g['x2']) - slack, max(g['x1'], g['x2']) + slack
    lo_y, hi_y = min(g['y1'], g['y2']) - slack, max(g['y1'], g['y2']) + slack
    worst = 0.0
    for x, y in _samples(g):
        worst = max(worst, lo_x - x, x - hi_x, lo_y - y, y - hi_y)
    return worst


def _vertical_pair():
    scene = empty_scene()
    scene['canvas'].update(width_mm=180, height_mm=120)
    # MEK above ERK, same centre x; MEK's label sits between them on the line.
    scene['objects'] = [
        {'id': 'mek', 'type': 'kinase', 'label': 'MEK', 'x': 132, 'y': 50, 'w': 17, 'h': 10},
        {'id': 'erk', 'type': 'kinase', 'label': 'ERK', 'x': 132, 'y': 67, 'w': 17, 'h': 10},
    ]
    rel = {'id': 'r5', 'source': 'mek', 'target': 'erk', 'type': 'activates'}
    scene['relations'] = [rel]
    return scene, rel


def test_vertical_connector_bends_sideways_instead_of_overshooting():
    scene, rel = _vertical_pair()
    g = connection_geometry(scene, rel)
    assert _overshoot(g) <= 0, g['path']
    # The bend is perpendicular to the chord, not along it.
    assert abs(g['control']['x'] - g['x1']) > 1 or g['control']['y'] == pytest.approx((g['y1'] + g['y2']) / 2), g['path']


def test_unobstructed_connector_stays_straight():
    scene, rel = _vertical_pair()
    scene['objects'][0]['label'] = ''  # nothing in the way any more
    g = connection_geometry(scene, rel)
    assert g['control']['x'] == pytest.approx((g['x1'] + g['x2']) / 2)
    assert g['control']['y'] == pytest.approx((g['y1'] + g['y2']) / 2)


@pytest.mark.parametrize('name', ['egfr', 'jak_stat'])
def test_example_connectors_never_overshoot(name):
    from scene_examples import make_example
    scene = make_example(name)
    for rel in scene['relations']:
        if rel.get('control') or rel.get('callout'):
            continue
        g = connection_geometry(scene, rel)
        assert _overshoot(g) <= 0, (rel['id'], g['path'])


def _ratio(g):
    """Curve length over chord: 1.0 is straight; the offline audit calls > 1.4 a hook."""
    pts = list(_samples(g))
    chord = math.hypot(g['x2'] - g['x1'], g['y2'] - g['y1'])
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) / chord


def _strictly_inside(p, o, m=.4):
    return o['x'] + m < p[0] < o['x'] + o['w'] - m and o['y'] + m < p[1] < o['y'] + o['h'] - m


def _contains(o, e, tol=.5):
    return (o['x'] <= e['x'] + tol and o['y'] <= e['y'] + tol
            and o['x'] + o['w'] >= e['x'] + e['w'] - tol and o['y'] + o['h'] >= e['y'] + e['h'] - tol)


def test_endpoint_objects_own_labels_do_not_bend_the_connector():
    # 04 r5: MEK's label sits right under MEK, where the s port leaves. The line
    # has to leave there anyway, so dodging that label only bends it into a hook.
    scene, rel = _vertical_pair()
    g = connection_geometry(scene, rel)
    assert _ratio(g) < 1.2, g['path']


@pytest.mark.parametrize('tid', ['signal_lipid', 'signal_horizontal'])
def test_template_connector_does_not_cross_other_objects(tid):
    # full3: PIP3 -> AKT ran straight through mTOR, because crossing an object
    # cost 1 per sample and touching a label cost 8.
    from scene_templates import make_template
    scene = scene_render.layout_scene(make_template(tid))
    by_id = {o['id']: o for o in scene['objects']}
    rel = next(r for r in scene['relations'] if r['id'] == 'e5')
    g = connection_geometry(scene, rel)
    pts = list(_samples(g))
    ends = [by_id[rel['source']], by_id[rel['target']]]
    crossed = [o['id'] for o in scene['objects']
               if o.get('visible', True) and o.get('role') != 'context' and o not in ends
               and not any(_contains(o, e) for e in ends) and sum(_strictly_inside(p, o) for p in pts) >= 2]
    assert not crossed, (crossed, g['path'])


def _fan_scene():
    # RAS at the bottom; EGFR comes in from the upper right and RAF leaves to the
    # upper left, so both connectors use RAS's n side (04: r2 end and r3 start).
    scene = empty_scene()
    scene['canvas'].update(width_mm=180, height_mm=120)
    scene['objects'] = [
        {'id': 'egfr', 'type': 'kinase', 'label': '', 'x': 90, 'y': 10, 'w': 17, 'h': 10},
        {'id': 'ras', 'type': 'kinase', 'label': '', 'x': 60, 'y': 60, 'w': 17, 'h': 10},
        {'id': 'raf', 'type': 'kinase', 'label': '', 'x': 30, 'y': 10, 'w': 17, 'h': 10},
    ]
    scene['relations'] = [
        {'id': 'r2', 'source': 'egfr', 'target': 'ras', 'type': 'activates'},
        {'id': 'r3', 'source': 'ras', 'target': 'raf', 'type': 'activates'},
    ]
    return scene


def test_endpoints_sharing_a_side_are_spread_apart_without_crossing():
    scene = _fan_scene()
    into = connection_geometry(scene, scene['relations'][0])
    out = connection_geometry(scene, scene['relations'][1])
    a, b = (into['x2'], into['y2']), (out['x1'], out['y1'])
    assert math.dist(a, b) >= 3, (a, b)
    # Both stay on RAS's top edge, ordered like the far ends (EGFR right, RAF left).
    assert a[1] == pytest.approx(60) and b[1] == pytest.approx(60), (a, b)
    assert 60 < b[0] < a[0] < 77, (a, b)


def test_single_connector_on_a_side_stays_centred():
    scene = _fan_scene()
    scene['relations'] = scene['relations'][:1]
    g = connection_geometry(scene, scene['relations'][0])
    assert (g['x2'], g['y2']) == pytest.approx((68.5, 60))
