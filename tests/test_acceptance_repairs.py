import copy

import pytest

import pipeline
from scene_document import audit_scene, empty_scene, normalize_scene
from scene_render import layout_scene, preview_finding_fix


def test_containment_layout_and_check_use_same_parent():
    scene=empty_scene();scene['objects']=[{'id':'n','type':'nucleus','label':'Nucleus'},
        {'id':'dna','type':'dna','label':'Chromatin','parent_id':'n'},
        {'id':'pore','type':'nuclear_pore','label':'Pore','parent_id':'n','placement':'boundary'}]
    scene=layout_scene(scene);n,dna,pore=scene['objects']
    assert n['x']<=dna['x'] and dna['x']+dna['w']<=n['x']+n['w']
    assert not [f for f in audit_scene(scene)['findings'] if f['code']=='containment']
    dna['x']=170
    assert any(f['code']=='containment' and f['object_ids']==['dna','n'] for f in audit_scene(scene)['findings'])


def test_explicit_connector_crossing_a_text_is_detected():
    scene=empty_scene();scene['objects']=[
        {'id':'a','type':'protein','label':'A','x':10,'y':40,'w':10,'h':10},
        {'id':'b','type':'protein','label':'B','x':140,'y':40,'w':10,'h':10},
        {'id':'word','type':'text','label':'Important text','x':68,'y':39,'w':35,'h':3}]
    scene['relations']=[{'id':'edge','source':'a','target':'b','type':'sequence','control':{'x':85,'y':45}}]
    found=audit_scene(scene)['findings']
    assert any(f['code']=='line-label-overlap' and f['object_ids']==['edge','word'] for f in found)


def test_layout_fix_cannot_pass_by_detaching_a_label():
    scene=empty_scene();scene['objects']=[
        {'id':'reads','type':'protein','label':'Reads','x':15,'y':30,'w':12,'h':10,'label_dx':80},
        {'id':'qc','type':'protein','label':'QC / align','x':95,'y':30,'w':15,'h':10}]
    scene=normalize_scene(scene)
    findings=audit_scene(scene)['findings'];assert any(f['code']=='label-detached' for f in findings)
    overlap=next(f for f in findings if f['code']=='label-overlap')
    result=preview_finding_fix(scene,overlap)
    if result['changed']:
        old={(f['code'],tuple(f['object_ids'])) for f in findings}
        assert not {(f['code'],tuple(f['object_ids'])) for f in result['audit']['findings']}-old
    assert scene['objects'][0]['label_dx']==80


def test_prompt_optimization_rejects_invented_instrument(monkeypatch):
    monkeypatch.setattr(pipeline,'_chat',lambda *a,**k:'收集样本，加入 1.5mL 离心管，再进行检测。')
    monkeypatch.setattr(pipeline,'chat_json',lambda *a,**k:{'equivalent':False,'reason':'新增容器和体积'})
    with pytest.raises(RuntimeError,match='原意核对'):
        pipeline.optimize_brief('收集样本，然后检测。',{'text':{'base_url':'http://test','model':'test'}})


def test_prompt_optimization_keeps_named_markers_and_number(monkeypatch):
    monkeypatch.setattr(pipeline,'_chat',lambda *a,**k:'EGFR 1 到 AKT 2；沿水平排列，保留两条标签。')
    monkeypatch.setattr(pipeline,'chat_json',lambda *a,**k:{'equivalent':True})
    config={'text':{'base_url':'http://test','model':'test'}}
    assert 'AKT 2' in pipeline.optimize_brief('EGFR 1 到 AKT 2',config)
    with pytest.raises(RuntimeError,match='原意核对'):pipeline.optimize_brief('EGFR 1 到 AKT 3',config)


def test_parent_move_carries_contents_once_and_keeps_explicit_child_position():
    from scene_document import apply_operations
    scene=empty_scene();scene['objects']=[
        dict(id='n',type='nucleus',label='N',x=10,y=10,w=60,h=60),
        dict(id='dna',type='dna',label='DNA',parent_id='n',x=25,y=25,w=20,h=10)]
    scene=normalize_scene(scene)
    moved=apply_operations(scene,[dict(op='update',id='n',changes={'x':20})])
    assert moved['objects'][1]['x']==35
    explicit=apply_operations(scene,[dict(op='update',id='n',changes={'x':20}),dict(op='update',id='dna',changes={'x':35})])
    assert explicit==moved


def test_single_nucleus_does_not_create_a_second_nuclear_compartment():
    from scene_planner import reconcile_containment
    scene=empty_scene();scene['compartments']=[dict(id='nuclear_space',kind='nucleus',label='Nucleus')]
    scene['objects']=[dict(id='n',type='nucleus',label='Nucleus',compartment='nuclear_space'),
        dict(id='dna',type='dna',label='Chromatin',parent_id='n',compartment='nuclear_space')]
    scene=layout_scene(reconcile_containment(scene))
    assert not scene['compartments'] and scene['objects'][0]['h']==28
