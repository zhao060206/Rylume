"""Object labels stay attached to their shape and inside the right compartment.

Step 2 of docs/修复计划-2026-11-24-排版.md: ligand labels hug the shape,
membrane-protein labels sit beside the object at membrane height instead of
falling into the cytoplasm, detached labels are reported, and labels the user
placed by hand are never moved or flagged.
"""
import math

import pytest

from scene_document import apply_operations, audit_scene, normalize_scene
from scene_examples import make_example
from scene_render import _object_label_boxes, layout_scene, preview_finding_fix

MEMBRANE = ('membrane', 'plasma_membrane')


def _gap(o, b):
    return math.hypot(max(0, o['x'] - b['x'] - b['w'], b['x'] - o['x'] - o['w']),
                      max(0, o['y'] - b['y'] - b['h'], b['y'] - o['y'] - o['h']))


def _kind(scene, o):
    return {c['id']: c['kind'] for c in scene['compartments']}.get(o.get('compartment'), '')


def _laid(name='egfr'):
    scene = make_example(name, layout=False)
    for o in scene['objects']:
        o['label_dx'] = 0
        o['label_dy'] = 0
    return normalize_scene(layout_scene(scene, force=True))


def _boxes(scene):
    return {b['id']: b for b in _object_label_boxes(layout_scene(scene))}


def _ligands(scene):
    found = [o for o in scene['objects'] if o['type'] == 'ligand' and _kind(scene, o) == 'extracellular' and o['label']]
    assert found, 'example needs an extracellular ligand'
    return found


def _membrane_objects(scene):
    found = [o for o in scene['objects'] if _kind(scene, o) in MEMBRANE and o['label']]
    assert found, 'example needs a membrane object'
    return found


@pytest.mark.parametrize('name', ['egfr', 'jak_stat'])
def test_ligand_label_hugs_its_shape(name):
    scene = _laid(name)
    boxes = _boxes(scene)
    for o in _ligands(scene):
        box = boxes[o['id']]
        assert _gap(o, box) <= 3, (o['id'], _gap(o, box))
        centre = box['y'] + box['h'] / 2
        assert o['y'] <= centre <= o['y'] + o['h'], 'label should sit beside the ligand, not above it'


@pytest.mark.parametrize('name', ['egfr', 'jak_stat'])
def test_membrane_label_does_not_fall_into_cytoplasm(name):
    scene = _laid(name)
    boxes = _boxes(scene)
    comps = {c['id']: c for c in scene['compartments']}
    for o in _membrane_objects(scene):
        band = comps[o['compartment']]
        box = boxes[o['id']]
        centre = box['y'] + box['h'] / 2
        assert centre <= band['y'] + band['h'] + .01, (o['id'], centre, band)
        assert _gap(o, box) <= 3, (o['id'], _gap(o, box))
    codes = {f['code'] for f in audit_scene(scene)['findings']}
    assert 'label-wrong-compartment' not in codes
    assert 'label-detached' not in codes


def test_old_fixed_ligand_offset_is_reported_detached():
    scene = _laid()
    ligand = _ligands(scene)[0]
    ligand['label_dx'] = -ligand['w'] - 5
    ligand['label_dy'] = -ligand['h'] - 1
    findings = audit_scene(normalize_scene(scene))['findings']
    assert any(f['code'] == 'label-detached' and ligand['id'] in f['object_ids'] for f in findings)


def test_membrane_label_below_object_is_wrong_compartment():
    scene = _laid()
    target = _membrane_objects(scene)[0]
    target['label_dx'] = 0
    target['label_dy'] = .5  # default below-object placement, i.e. in the cytoplasm
    findings = audit_scene(normalize_scene(scene))['findings']
    assert any(f['code'] == 'label-wrong-compartment' and target['id'] in f['object_ids'] for f in findings)


def test_detached_fix_restores_hugging_label():
    scene = _laid()
    ligand = _ligands(scene)[0]
    ligand['label_dx'] = -ligand['w'] - 5
    ligand['label_dy'] = -ligand['h'] - 1
    scene = normalize_scene(scene)
    finding = next(f for f in audit_scene(scene)['findings'] if f['code'] == 'label-detached' and ligand['id'] in f['object_ids'])
    result = preview_finding_fix(scene, finding)
    assert result['changed']
    assert not any(f['code'] == 'label-detached' and ligand['id'] in f['object_ids'] for f in result['audit']['findings'])


def test_user_placed_label_is_kept_and_not_flagged():
    scene = _laid()
    ligand = _ligands(scene)[0]
    moved = apply_operations(scene, [{'op': 'update', 'id': ligand['id'], 'changes': {'label_dx': 40, 'label_dy': 30}}])
    moved = moved['scene'] if isinstance(moved, dict) and 'scene' in moved and 'objects' not in moved else moved
    obj = next(o for o in moved['objects'] if o['id'] == ligand['id'])
    assert obj.get('label_user_set') is True
    relaid = normalize_scene(layout_scene(moved, force=True))
    obj = next(o for o in relaid['objects'] if o['id'] == ligand['id'])
    assert (obj['label_dx'], obj['label_dy']) == (40, 30)
    assert obj.get('label_user_set') is True
    findings = audit_scene(relaid)['findings']
    assert not any(f['code'] in ('label-detached', 'label-wrong-compartment') and ligand['id'] in f['object_ids'] for f in findings)


@pytest.mark.parametrize('name', ['egfr', 'jak_stat'])
def test_example_as_shipped_keeps_ligand_label_beside_shape(name):
    scene = make_example(name)
    boxes = _boxes(scene)
    for o in _ligands(scene):
        box = boxes[o['id']]
        assert _gap(o, box) <= 3, (o['id'], _gap(o, box))
        assert o['y'] <= box['y'] + box['h'] / 2 <= o['y'] + o['h']
    codes = {f['code'] for f in audit_scene(scene)['findings']}
    assert not codes & {'label-detached', 'label-wrong-compartment'}, codes


def test_wrong_compartment_fix_tries_every_side():
    scene = _laid()
    target = _membrane_objects(scene)[0]
    target['label_dx'] = 0
    target['label_dy'] = .5
    scene = normalize_scene(scene)
    finding = next(f for f in audit_scene(scene)['findings'] if f['code'] == 'label-wrong-compartment' and target['id'] in f['object_ids'])
    result = preview_finding_fix(scene, finding)
    assert result['changed']
    assert not any(f['code'] == 'label-wrong-compartment' and target['id'] in f['object_ids'] for f in result['audit']['findings'])
    obj = next(o for o in result['scene']['objects'] if o['id'] == target['id'])
    assert not obj.get('label_user_set')
