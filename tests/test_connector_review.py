"""Connector geometry checks in the review (step 6 of docs/修复计划-2026-11-24-排版.md).

The offline audit (tmp/audit_full3.py) measured hooks, detours past the ends,
binding symbols with no line between their discs and lines run through other
objects. The same checks now live in audit_scene, each with a one-click fix
that clears it without adding a new finding.
"""
import copy

import pytest

from scene_document import audit_scene, empty_scene, normalize_scene
from scene_examples import EXAMPLES, make_example
from scene_render import preview_finding_fix
from scene_templates import TEMPLATES, make_template

NEW = {'connector-hook', 'connector-overshoot', 'binds-short', 'line-through-object',
       'connector-through-end', 'connector-outside-canvas', 'connector-symbol-on-label',
       'connector-body-short', 'connector-overlap'}


def _scene(objects, relations):
    scene = empty_scene()
    scene['canvas'].update(width_mm=180, height_mm=120)
    scene['objects'] = objects
    scene['relations'] = relations
    return normalize_scene(scene)


def _obj(oid, x, y, w=16, h=10, typ='protein', **kw):
    return {'id': oid, 'type': typ, 'label': oid.upper(), 'x': x, 'y': y, 'w': w, 'h': h, **kw}


def _findings(scene, code):
    return [f for f in audit_scene(scene)['findings'] if f['code'] == code]


def _fix_clears(scene, finding):
    key = lambda f: (f['code'], tuple(f['object_ids']))
    before = {key(f) for f in audit_scene(scene)['findings']}
    result = preview_finding_fix(scene, finding)
    assert result['changed'], finding
    after = {key(f) for f in result['audit']['findings']}
    assert key(finding) not in after
    assert not after - before, after - before


def test_hook_is_reported_and_fixed():
    # Control 40 mm off a 40 mm chord: the curve bows into a hook (length/chord > 1.4)
    # but stays inside the overshoot slack.
    scene = _scene([_obj('a', 20, 60), _obj('b', 76, 60)],
                   [{'id': 'r', 'source': 'a', 'target': 'b', 'type': 'activates', 'control': {'x': 64, 'y': 25}}])
    found = _findings(scene, 'connector-hook')
    assert found and found[0]['object_ids'] == ['r'] and found[0]['evidence']['ratio'] > 1.4
    _fix_clears(scene, found[0])


def test_overshoot_is_reported_and_fixed():
    # Collinear control far past the target: the line runs out beyond its end.
    scene = _scene([_obj('a', 20, 60), _obj('b', 60, 60)],
                   [{'id': 'r', 'source': 'a', 'target': 'b', 'type': 'activates', 'control': {'x': 150, 'y': 65}}])
    found = _findings(scene, 'connector-overshoot')
    assert found and found[0]['evidence']['overshoot_mm'] > .5
    _fix_clears(scene, found[0])


def test_straight_connector_is_clean():
    scene = _scene([_obj('a', 20, 60), _obj('b', 76, 60)],
                   [{'id': 'r', 'source': 'a', 'target': 'b', 'type': 'activates'}])
    assert not {f['code'] for f in audit_scene(scene)['findings']} & NEW


def test_binds_short_is_reported_and_fixed():
    # 3 mm between ligand and receptor: the two binding discs (5 mm) leave no line.
    scene = _scene([_obj('lig', 83.5, 11, 13, 9, 'ligand'), _obj('rec', 84.5, 23, 11, 20, 'receptor')],
                   [{'id': 'r1', 'source': 'lig', 'target': 'rec', 'type': 'binds'}])
    found = _findings(scene, 'binds-short')
    assert found and found[0]['evidence']['exposed_mm'] < 2
    _fix_clears(scene, found[0])


def test_binds_with_7mm_gap_is_clean():
    scene = _scene([_obj('lig', 83.5, 8, 13, 9, 'ligand'), _obj('rec', 84.5, 24, 11, 20, 'receptor')],
                   [{'id': 'r1', 'source': 'lig', 'target': 'rec', 'type': 'binds'}])
    assert not _findings(scene, 'binds-short')


# A hand-set control collinear with both ends: the line runs straight through C.
# Without it the renderer already bends the line around C on its own.
STRAIGHT = {'x': 73, 'y': 65}


def _through(control=STRAIGHT, **mid):
    rel = {'id': 'r', 'source': 'a', 'target': 'b', 'type': 'activates'}
    if control:
        rel['control'] = dict(control)
    return _scene([_obj('a', 10, 60), _obj('b', 120, 60), _obj('c', 62, 57, 18, 16, **mid)], [rel])


def test_line_through_object_is_reported_and_fixed():
    scene = _through()
    found = _findings(scene, 'line-through-object')
    assert found and found[0]['object_ids'] == ['r', 'c']
    _fix_clears(scene, found[0])


def test_auto_route_already_bends_around_object():
    assert not _findings(_through(control=None), 'line-through-object')


def test_background_objects_are_not_obstacles():
    assert not _findings(_through(role='context'), 'line-through-object')


def test_container_of_an_end_is_not_an_obstacle():
    # The source sits inside a big cell; leaving the cell is not crossing it.
    scene = _scene([_obj('cell', 2, 30, 60, 70, 'cell'), _obj('a', 20, 60), _obj('b', 120, 60)],
                   [{'id': 'r', 'source': 'a', 'target': 'b', 'type': 'activates'}])
    assert not _findings(scene, 'line-through-object')


def test_route_through_allows_the_named_object_only():
    scene = _scene([_obj('a', 10, 60), _obj('b', 120, 60), _obj('c', 40, 57, 14, 16), _obj('d', 85, 57, 14, 16)],
                   [{'id': 'r', 'source': 'a', 'target': 'b', 'type': 'activates', 'route_through': ['c', 'gone'], 'control': dict(STRAIGHT)}])
    assert scene['relations'][0]['route_through'] == ['c']  # unknown ids drop out
    assert [f['object_ids'] for f in _findings(scene, 'line-through-object')] == [['r', 'd']]
    deleted = copy.deepcopy(scene)
    deleted['objects'] = [o for o in deleted['objects'] if o['id'] != 'c']
    assert 'route_through' not in normalize_scene(deleted)['relations'][0]


def test_storyboard_and_flow_fixes():
    barrier = make_template('sb_inflamed_barrier')
    r1 = next(r for r in barrier['relations'] if r['source'] == 'bcargo' and r['target'] == 'leak')
    assert r1.get('route_through') == ['bendo']
    loop = next(r for r in make_template('flow_feedback_control')['relations'] if r['id'] == 'flowlink5')
    assert (loop['source_port'], loop['target_port']) == ('e', 'w') and not loop.get('control')


def _sources():
    for t in TEMPLATES:
        yield 'template:' + t['id'], lambda t=t: make_template(t['id'])
        yield 'narrow:' + t['id'], lambda t=t: make_template(t['id'], width_mm=90, height_mm=150)
    for e in EXAMPLES:
        yield 'example:' + e['id'], lambda e=e: make_example(e['id'])


def test_every_template_and_example_is_clean():
    bad = []
    for name, build in _sources():
        codes = [(f['code'], f['object_ids']) for f in audit_scene(build())['findings'] if f['code'] in NEW]
        if codes:
            bad.append((name, codes))
    assert not bad, bad


# Step 10: a non-binding connector keeps a visible line behind its end symbol.
def test_body_short_is_reported_and_fixed():
    # 3 mm between two proteins: even the smallest arrowhead leaves almost no line.
    scene = _scene([_obj('a', 20, 60), _obj('b', 39, 60)],
                   [{'id': 'r', 'source': 'a', 'target': 'b', 'type': 'activates'}])
    found = _findings(scene, 'connector-body-short')
    assert found and found[0]['object_ids'] == ['r'] and found[0]['evidence']['exposed_mm'] < 1.9
    _fix_clears(scene, found[0])


@pytest.mark.parametrize('kind', ['activates', 'inhibits', 'converts', 'sequence', 'transports'])
def test_short_link_with_7mm_gap_keeps_its_line(kind):
    # 7 mm is enough for every end symbol once the tip gaps and the head shrink.
    scene = _scene([_obj('a', 20, 60), _obj('b', 43, 60)],
                   [{'id': 'r', 'source': 'a', 'target': 'b', 'type': kind}])
    assert not _findings(scene, 'connector-body-short')


def test_binding_lines_are_left_to_binds_short():
    scene = _scene([_obj('lig', 83.5, 11, 13, 9, 'ligand'), _obj('rec', 84.5, 23, 11, 20, 'receptor')],
                   [{'id': 'r1', 'source': 'lig', 'target': 'rec', 'type': 'binds'}])
    assert not _findings(scene, 'connector-body-short')


# Step 11: two connectors must not run together or put an end symbol on each other.
def _overlapping():
    # A vertical link C -> D whose arrowhead lands on the horizontal link A -> B below C.
    return _scene([_obj('a', 20, 60), _obj('b', 120, 60), _obj('c', 62, 25), _obj('d', 62, 67.3)],
                  [{'id': 'r1', 'source': 'a', 'target': 'b', 'type': 'activates'},
                   {'id': 'r2', 'source': 'c', 'target': 'd', 'type': 'activates'}])


def test_connector_overlap_is_reported_and_fixed():
    scene = _overlapping()
    found = _findings(scene, 'connector-overlap')
    assert found and found[0]['object_ids'] == ['r1', 'r2']
    _fix_clears(scene, found[0])


def test_separate_connectors_are_clean():
    scene = _scene([_obj('a', 20, 30), _obj('b', 100, 30), _obj('c', 20, 80), _obj('d', 100, 80)],
                   [{'id': 'r1', 'source': 'a', 'target': 'b', 'type': 'activates'},
                    {'id': 'r2', 'source': 'c', 'target': 'd', 'type': 'inhibits'}])
    assert not _findings(scene, 'connector-overlap')
