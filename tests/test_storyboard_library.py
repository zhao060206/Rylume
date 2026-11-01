"""Scientific identity, context editing and distribution contracts of the new library."""
import copy
import hashlib
import json
import re
from pathlib import Path
import zipfile
import pytest
from scene_templates import TEMPLATES, make_template, apply_template
from scene_document import SceneError, apply_operations, audit_scene
from scene_render import connection_geometry, render_scene
from scene_export import export_scene
from scene_assets import asset_catalog
from scientific_library import library

ROOT=Path(__file__).resolve().parents[1]

def test_library_expansion_has_traceable_originals_and_no_missing_category():
    assert len(library())>=630
    catalog=asset_catalog()
    ids=[a['asset_id'] for c in catalog for a in c['items'] if a.get('asset_id')]
    from scientific_library import available_for_insertion
    assert len(ids)==len(set(ids))==sum(bool(available_for_insertion(a)) for a in library().values())
    assert all(available_for_insertion(library()[aid]) for aid in ids)
    assert all(aid in library() for aid,a in library().items() if a.get('catalog_status')=='quarantined')
    assert len(catalog)>=15
    for a in json.loads((ROOT/'assets/bioicons/manifest.json').read_text(encoding='utf8')):
        aid=a['asset_id']
        assert re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*',aid)
        assert a['license'] in ('CC BY 3.0','CC BY 4.0','CC0 1.0')
        assert hashlib.sha256((ROOT/'assets/bioicons'/f'{aid}.original.svg').read_bytes()).hexdigest()==a['sha256']

def test_distinct_storyboards_are_subjects_with_authored_science():
    boards=[t for t in TEMPLATES if t.get('new_scene_only')]
    assert len(boards)>=28
    assert len({t['example'] for t in boards})==len(boards)
    assert len({t['composition'] for t in boards})>=10
    for t in boards:
        scene=make_template(t['id'])
        assert scene['source_text'] and not audit_scene(scene)['errors']
        assert all(o['evidence'] for o in scene['objects'])
        assert all(r['evidence'] for r in scene['relations'])
        assert '<image' not in render_scene(scene)

def test_scientific_state_morphology_is_explicit():
    scene=make_template('sb_autophagy_flux');byid={o['id']:o for o in scene['objects']}
    assert byid['phago']['state']=='phagophore'
    assert byid['auto']['state']=='autophagosome'
    assert byid['lyso']['state']=='autolysosome'
    scene=make_template('sb_infection_response');byid={o['id']:o for o in scene['objects']}
    assert byid['bacteria']['state']=='bacterium'
    assert byid['lyso']['state']=='phagolysosome'
    assert next(o for o in make_template('sb_lnp_delivery')['objects'] if o['id']=='lnp')['state']=='lnp'

def test_new_subject_cannot_silently_replace_current_scientific_content():
    with pytest.raises(SceneError,match='新建'):
        apply_template(make_template('signal_relay'),'sb_lnp_delivery')
    scene=make_template('sb_lnp_delivery')
    scene=apply_operations(scene,[dict(op='update',id='free',changes=dict(label='Author edited',x=120))])
    refreshed=apply_template(scene,'sb_lnp_delivery','plum')
    assert next(o for o in refreshed['objects'] if o['id']=='free')['label']=='Author edited'
    assert refreshed['objects']==scene['objects']

def test_context_is_editable_and_does_not_deflect_bound_arrows():
    scene=make_template('sb_lnp_delivery');r=next(r for r in scene['relations'] if r['source']=='endo')
    before=connection_geometry(scene,r)
    context=next(o for o in scene['objects'] if o['role']=='context')
    changed=apply_operations(scene,[dict(op='update',id=context['id'],changes=dict(x=0,y=0,w=170,h=110))])
    assert connection_geometry(changed,r)==before
    moved=apply_operations(changed,[dict(op='update',id='free',changes=dict(x=110))])
    assert connection_geometry(moved,r)!=before
    assert not any(f['code']=='overlap' and context['id'] in f['object_ids'] for f in audit_scene(changed)['findings'])
    svg=render_scene(moved)
    assert svg.index('layer-context')<svg.index('layer-relations')<svg.index('layer-objects')

def test_resize_keeps_author_edits_and_bound_topology():
    scene=make_template('sb_lnp_delivery')
    edited=apply_operations(scene,[dict(op='update',id='free',changes=dict(label='Edited RNA',x=120,fill='#645289'))])
    resized=apply_operations(edited,[dict(op='canvas',width_mm=90,height_mm=150,reflow=True)])
    obj=next(o for o in resized['objects'] if o['id']=='free')
    assert obj['label']=='Edited RNA' and obj['fill']=='#645289' and obj['x']==60
    assert resized['requirements']==edited['requirements'] and resized['relations']==edited['relations']
    assert not audit_scene(resized)['errors']

@pytest.mark.parametrize('tid',['sb_lnp_delivery','sb_antigen_synapse','sb_autophagy_flux'])
def test_new_storyboards_export_consistent_editable_shapes(tmp_path,tid):
    scene=make_template(tid)
    for fmt in ('svg','pdf','png','pptx'):
        result=export_scene(scene,fmt,tmp_path/(tid+'.'+fmt))
        assert result['revision']==scene['revision'] and not result['raster_objects']
    with zipfile.ZipFile(tmp_path/(tid+'.pptx')) as z:
        assert not any(p.startswith('ppt/media/') for p in z.namelist())
        slide=z.read('ppt/slides/slide1.xml').decode()
        assert 'custGeom' in slide
