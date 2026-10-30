"""Contracts for honest discovery and scientific semantics, not template counts."""
import time
from pathlib import Path
import pytest
from scene_templates import TEMPLATES, make_template
from scene_render import render_scene
from scene_document import apply_operations, audit_scene
from test_scene_api import studio

ROOT = Path(__file__).resolve().parents[1]


def test_composition_variants_are_not_presented_as_new_science():
    byid = {t['id']: t for t in TEMPLATES}
    for t in TEMPLATES:
        assert t['usage'] and t['includes'] and t['limitations']
        if t['library_group'] == 'layout':
            assert not t['recommended']
        if t['variant_of']:
            assert t['id'] in byid[t['variant_of']]['variants']
            assert not t['recommended']


@pytest.mark.parametrize('size', [(180, 120), (90, 150)])
def test_egfr_reaction_has_substrate_product_and_preserves_them_when_edited(size):
    s = make_template('sb_mapk_branch', width_mm=size[0], height_mm=size[1])
    objects = {o['id']: o for o in s['objects']}
    assert {'egf', 'egfr', 'ras', 'raf', 'mek', 'erk', 'pi3k', 'pip2', 'pip3', 'akt'} <= objects.keys()
    assert any(r['source'] == 'pip2' and r['target'] == 'pip3' and r['type'] == 'converts' for r in s['relations'])
    assert not any(r['source'] == 'pi3k' and r['type'] == 'converts' for r in s['relations'])
    edited = apply_operations(s, [dict(op='update', id='pip2', changes={'x': objects['pip2']['x']-1})])
    assert edited['relations'] == s['relations']
    assert not audit_scene(s)['errors']


def test_a_catalyst_or_template_is_never_consumed_as_its_product():
    for tid, ids in [('sb_sting_traffic', {'cgas'}), ('sb_lnp_delivery', {'free'}),
                     ('sb_socs_feedback', {'dna'}), ('sb_translation_route', {'dna', 'rib'})]:
        s = make_template(tid)
        assert not any(r['source'] in ids and r['type'] == 'converts' for r in s['relations'])
    s = make_template('sb_autophagy_flux')
    assert {'phago', 'auto', 'lysosome', 'lyso'} <= {o['id'] for o in s['objects']}
    assert all(r['type'] == 'sequence' for r in s['relations'])


def test_actual_preview_matches_new_document_without_creating_or_modifying_jobs(studio):
    _, catalog = studio('/api/scene/catalog')
    t = next(t for t in catalog['templates'] if t['id'] == 'sb_mapk_branch')
    _, before = studio('/api/jobs')
    for path, size in [(t['thumbnail'], (180, 120)), (t['thumbnail_single'], (90, 150))]:
        status, actual = studio(path)
        assert status == 200
        assert actual.decode('utf8') == render_scene(make_template(t['id'], width_mm=size[0], height_mm=size[1]))
    _, after = studio('/api/jobs')
    assert before == after
    status, created = studio('/api/scene/example', {'template': t['id'], 'canvas_mm': [90, 150]})
    assert status == 200
    base = '/api/jobs/' + created['job_id']
    for _ in range(100):
        _, job = studio(base)
        if job['status'] in ('completed', 'failed'): break
        time.sleep(.02)
    assert job['status'] == 'completed'
    _, doc = studio(base + '/scene')
    assert render_scene(doc['scene']) == render_scene(make_template(t['id'], width_mm=90, height_mm=150))
