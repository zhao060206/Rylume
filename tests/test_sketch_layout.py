"""Approximate sketches become measurable layouts without changing their meaning."""
import copy
import base64
import math
from types import SimpleNamespace

import pytest

import figure_generation
from scene_document import SceneError, empty_scene, normalize_scene
from sketch_layout import regularize_sketch
from test_scene_api import studio
from test_generation_core import drawing, finished


def draft(points, **extra):
    scene=empty_scene(source_text='A then B then C then D')
    scene['layout']='process'
    scene['objects']=[{'id':chr(97+i),'type':'cell','label':chr(65+i),
                       'x':x,'y':y,'w':w,'h':h,'rotation':(i-2)*7,
                       'state':'phase_'+str(i),'evidence':chr(65+i)}
                      for i,(x,y,w,h) in enumerate(points)]
    scene['relations']=[{'id':'r'+str(i),'source':scene['objects'][i]['id'],
                         'target':scene['objects'][i+1]['id'],'type':'sequence'}
                        for i in range(len(points)-1)]
    scene.update(extra)
    return normalize_scene(scene)


def centers(scene):
    return [(o['x']+o['w']/2,o['y']+o['h']/2) for o in scene['objects']]


def test_wobbly_row_gets_same_size_baseline_equal_gaps_and_keeps_all_states():
    before=draft([(8,21,18,30),(48,27,34,21),(94,18,20,37),(138,25,27,17)])
    saved=copy.deepcopy(before)
    after,report=regularize_sketch(before,'row')
    assert before==saved, 'The original rough layout must remain available for comparison'
    assert report['fits'] and report['overlaps']==0
    assert { (o['w'],o['h'],o['rotation']) for o in after['objects']}=={(26,26,0)}
    points=centers(after)
    assert len({y for x,y in points})==1
    assert max(points[i+1][0]-points[i][0] for i in range(3))-min(points[i+1][0]-points[i][0] for i in range(3))<.001
    assert [(o['id'],o['label'],o['state']) for o in after['objects']]==[(o['id'],o['label'],o['state']) for o in before['objects']]
    assert [(r['source'],r['target'],r['type']) for r in after['relations']]==[(r['source'],r['target'],r['type']) for r in before['relations']]


def test_two_row_sketch_retains_shared_columns_and_branch_endpoints():
    before=draft([(9,13,20,22),(72,17,28,18),(135,12,22,25),
                  (12,70,26,23),(69,67,30,26),(136,74,23,19)])
    after,report=regularize_sketch(before,'serpentine')
    assert report['fits']
    points=centers(after)
    assert len({p[1] for p in points[:3]})==len({p[1] for p in points[3:]})==1
    assert all(abs(points[i][0]-points[i+3][0])<.001 for i in range(3))


def test_circle_uses_equal_angular_spacing_without_adding_a_closing_edge():
    points=[(90+60*math.cos(a)-12,60+37*math.sin(a)-12,24+(i%2)*5,22+(i%3)*3)
            for i,a in enumerate([0,.9,2.0,3.2,4.0,5.3])]
    before=draft(points)
    after,report=regularize_sketch(before,'cycle')
    assert report['fits'], report
    c=centers(after);cx=sum(x for x,y in c)/len(c);cy=sum(y for x,y in c)/len(c)
    # Equal ellipse angles, rather than equal pixel distances on an ellipse.
    rx=math.sqrt(2*sum((x-cx)**2 for x,y in c)/len(c));ry=math.sqrt(2*sum((y-cy)**2 for x,y in c)/len(c))
    angles=sorted(math.atan2((y-cy)/ry,(x-cx)/rx) for x,y in c)
    gaps=[(angles[(i+1)%len(c)]-angles[i])%math.tau for i in range(len(c))]
    assert max(gaps)-min(gaps)<.001
    assert len(after['relations'])==len(before['relations']), 'A cycle in placement does not authorize a new causal arrow'


def test_locks_independent_text_and_compartments_survive_regularization():
    before=draft([(12,10,23,31),(85,72,31,17)])
    before['objects'][0]['locked']=True
    before['objects'].append({'id':'title','type':'text','label':'Author title','x':15,'y':3,'w':50,'h':7,'rotation':4})
    before=normalize_scene(before)
    after,_=regularize_sketch(before,'row')
    assert after['objects'][0]==before['objects'][0]
    assert after['objects'][-1]==before['objects'][-1]
    assert [(o['id'],o['type']) for o in after['objects']]==[(o['id'],o['type']) for o in before['objects']]


def test_preserve_mode_is_exact_and_regularize_mode_is_separate_preview_identity():
    before=draft([(8,21,18,30),(55,27,34,21),(112,18,20,37)])
    cfg={'original_text':'A then B then C','generation_brief':'A then B then C',
         'canvas_mm':[180,120],'sketch_scene':before,'layout_policy':'preserve'}
    exact=figure_generation.apply_constraints(before,cfg)
    assert exact['objects']==before['objects'] and exact['relations']==before['relations']
    cfg2={**cfg,'layout_policy':'regularize'}
    clean=figure_generation.apply_constraints(before,cfg2)
    assert clean['objects']!=exact['objects']
    assert clean['generation_contract']['layout_policy']=='regularize'
    assert figure_generation.fingerprint(cfg)!=figure_generation.fingerprint(cfg2)


def test_invalid_layout_mode_cannot_silently_change_geometry():
    app=SimpleNamespace(load_config=lambda:{},sanitize_style=lambda value:value)
    with pytest.raises(SceneError,match='智能整理'):
        figure_generation.prepare(app,{'text':'A then B','layout_policy':'whatever'})


def test_crowded_page_reports_limits_and_preserves_font_and_science():
    before=draft([(i%4*8+3,i//4*9+3,6,6) for i in range(24)],canvas={'width_mm':40,'height_mm':40})
    after,report=regularize_sketch(before,'row')
    assert not report['fits'] and any('空间不足' in text for text in after['unresolved'])
    assert all(o['font_size_pt']>=7 for o in after['objects'])
    assert [(r['source'],r['target'],r['type']) for r in after['relations']]==[(r['source'],r['target'],r['type']) for r in before['relations']]


@pytest.mark.parametrize('mode',['vector','image'])
def test_uploaded_rough_sketch_defaults_to_regular_layout_in_both_output_modes(studio,monkeypatch,mode):
    import figure_assets
    import figure_references
    import scene_planner
    import pipeline
    source=draft([(8,21,18,30),(48,27,34,21),(94,18,20,37),(138,25,27,17)])
    contract=figure_references.normalize_contract({'composition':'row','objects':[
        {**o,**{key:o[key]/(180 if key in ('x','w') else 120) for key in ('x','y','w','h')}}
        for o in source['objects']], 'relations':source['relations']})
    monkeypatch.setattr(figure_references,'analyze',lambda *a:(contract,{}))
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(source,{}))
    prompts=[]
    monkeypatch.setattr(pipeline,'generate_raw',lambda prompt,config:(prompts.append(prompt) or drawing()))
    monkeypatch.setattr(figure_assets,'referenced_image',lambda *a,**k:pytest.fail('A rough contour must not be traced into the final illustration'))
    _,reference=studio('/api/references',{'image':'data:image/png;base64,'+base64.b64encode(drawing()).decode(),'purpose':'sketch'})
    body={'text':'A then B then C then D','reference_id':reference['reference_id'],'reference_purpose':'sketch','illustration_mode':mode}
    code,preview=studio('/api/generation/preview',body)
    assert code==200,preview
    assert preview['scene']['generation_contract']['layout_policy']=='regularize'
    code,stale=studio('/api/generate',{**body,'layout_policy':'preserve','preview_id':preview['preview_id']})
    assert code==409 and stale['conflict']
    _,result=studio('/api/generate',{**body,'preview_id':preview['preview_id']})
    job=finished(studio,result['job_id']);assert job['status']=='completed',job
    _,saved=studio('/api/jobs/'+job['id']+'/scene')
    objects=saved['scene']['objects']
    assert len({o['y'] for o in objects})==1
    assert len({(o['w'],o['h']) for o in objects})==1
    assert [(o['x'],o['y']) for o in objects]==[(o['x'],o['y']) for o in preview['scene']['objects']]
    if mode=='image':
        assert len(prompts)==4 and all(o.get('illustration') for o in objects)
        assert saved['svg'].count('<image ')==4
    assert len(saved['scene']['relations'])==3
    # Retrying uses the chosen policy, rather than falling back to copied rough coordinates.
    _,retry=studio('/api/jobs/'+job['id']+'/retry',{})
    retried=finished(studio,retry['job_id']);assert retried['status']=='completed',retried
    _,again=studio('/api/jobs/'+retried['id']+'/scene')
    assert again['scene']['generation_contract']['layout_policy']=='regularize'
    assert [(o['x'],o['y']) for o in again['scene']['objects']]==[(o['x'],o['y']) for o in objects]
