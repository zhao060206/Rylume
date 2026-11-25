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
