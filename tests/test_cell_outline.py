"""process_cell: the review checks each stage against the drawn cell outline.

Formation and transport belong inside the cell, membrane fusion on the membrane and release outside.
The outline is decoration in the SVG, so before this check a stage dragged out of the cell went unnoticed.
"""
import copy

import pytest

import scene_render as sr
from scene_document import audit_scene
from scene_templates import make_template

SIZES = [{}, {'width_mm': 90, 'height_mm': 150}, {'width_mm': 120, 'height_mm': 150}, {'width_mm': 180, 'height_mm': 90}]
CODE = 'cell-outline-placement'


def _codes(scene):
    return [f for f in audit_scene(scene)['findings'] if f['code'] == CODE]


def _moved(scene, state, dx, dy):
    bad = copy.deepcopy(scene)
    cw, ch = bad['canvas']['width_mm'], bad['canvas']['height_mm']
    o = next(x for x in bad['objects'] if x['state'] == state)
    o['x'] = min(max(0, o['x'] + dx), cw - o['w'])
    o['y'] = min(max(0, o['y'] + dy), ch - o['h'])
    return bad, o['id']


@pytest.mark.parametrize('size', SIZES)
def test_default_layout_matches_the_outline(size):
    assert not _codes(make_template('process_cell', **size))


@pytest.mark.parametrize('size', SIZES)
@pytest.mark.parametrize('state,expected', [('biogenesis', 'inside'), ('released', 'outside'), ('fusion', 'boundary')])
def test_misplaced_stage_is_reported(size, state, expected):
    scene = make_template('process_cell', **size)
    cw, ch = scene['canvas']['width_mm'], scene['canvas']['height_mm']
    shift = {'biogenesis': (0, ch * .55), 'released': (-cw * .45, -ch * .35), 'fusion': (-cw * .3, -ch * .15)}[state]
    bad, oid = _moved(scene, state, *shift)
    found = _codes(bad)
    assert [f['object_ids'] for f in found] == [[oid]]
    assert found[0]['evidence']['expected'] == expected


def test_fix_moves_only_that_stage_back():
    scene = make_template('process_cell')
    bad, oid = _moved(scene, 'biogenesis', 0, scene['canvas']['height_mm'] * .55)
    finding = _codes(bad)[0]
    key = lambda f: (f['code'], tuple(f['object_ids']))
    before = {key(f) for f in audit_scene(bad)['findings']}
    result = sr.preview_finding_fix(bad, finding)
    assert result['changed']
    assert {op['id'] for op in result['operations']} == {oid}
    after = {key(f) for f in result['audit']['findings']}
    assert key(finding) not in after and not after - before


def test_other_templates_are_not_checked():
    scene = make_template('process_vertical')
    o = scene['objects'][0]
    o['state'] = 'biogenesis'
    assert not _codes(scene)


def test_outline_drawing_is_unchanged():
    svg = sr.render_scene(make_template('process_cell'))
    assert 'M 10 31 C 14 6 89 6 115 25 C 140 43 139 62 130 82 C 111 91 35 93 13 76 C 3 62 1 44 10 31 Z' in svg
