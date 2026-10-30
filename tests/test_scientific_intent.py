import copy
import json
import pytest
from scientific_intent import intent_contract,phase_tokens,mitosis_candidate,canonical_phase
from scene_document import audit_scene
import scene_planner


def test_temporal_cycle_is_not_engineering_control_or_materials_cell():
    assert intent_contract('真核细胞有丝分裂全周期闭环流线图')['layout_kind']=='process'
    for text in ('fuel cell life cycle assessment','electrochemical cell feedback controller','电池生命周期评价'):
        assert intent_contract(text)['domain']=='engineering'
    assert intent_contract('EGFR activates AKT in a cell')['domain']=='biology'
    assert canonical_phase('Prometaphase')=='prometaphase'
    assert phase_tokens('前中期 → 中期 → 后期')==['prometaphase','metaphase','anaphase']


def test_short_subject_gets_a_disclosed_scientific_candidate_not_empty_boxes():
    text='生成一张真核细胞有丝分裂的流程图'
    candidate=mitosis_candidate(text)
    assert len(candidate['objects'])==6
    assert candidate['source_text']==text
    assert all(o['evidence_source']=='knowledge' and 'openstax.org' in o['evidence_ref'] for o in candidate['objects'])
    assert candidate['unresolved'] and candidate['provenance']['knowledge_sources']
    assert len({o['y'] for o in candidate['objects']})==2
    assert [o['x'] for o in candidate['objects'][:3]]==sorted(o['x'] for o in candidate['objects'][:3])
    assert [o['x'] for o in candidate['objects'][3:]]==sorted((o['x'] for o in candidate['objects'][3:]),reverse=True)
    assert not [f for f in audit_scene(candidate)['findings'] if f['severity']=='error']
    assert mitosis_candidate('有丝分裂：前期、中期、后期') is None
    assert mitosis_candidate('减数分裂全过程') is None
    assert mitosis_candidate('非经典有丝分裂') is None


def test_full_cycle_candidate_has_actual_division_states_and_disclosed_next_generation():
    candidate=mitosis_candidate('真核细胞有丝分裂全周期闭环流线图')
    assert len(candidate['objects'])==7
    assert candidate['relations'][-1]['label']=='Next cycle' and not candidate['relations'][-1]['indirect']
    assert all(r['type']=='sequence' for r in candidate['relations'])
    assert any('子代' in t for t in candidate['unresolved'])


def test_reference_planning_receives_pixels_and_enhanced_brief_but_keeps_original(monkeypatch):
    calls=[]
    def request(config,messages,**kw):
        calls.append((config,messages))
        return {'title':'A then B','layout':'process','objects':[
            {'id':'a','type':'cell','label':'Interphase','state':'Interphase','evidence':'Interphase'},
            {'id':'b','type':'cell','label':'Prophase','state':'Prophase','evidence':'Prophase'}],
            'relations':[{'id':'ab','source':'a','target':'b','type':'sequence','evidence':'Interphase to Prophase'}]},0
    monkeypatch.setattr(scene_planner,'_request',request)
    text='Interphase to Prophase'
    config={'text':{'model':'text'},'vision':{'base_url':'https://offline.invalid','model':'vision'},
            'generation_brief':'两行蛇形排布','reference_id':'ref_fake','reference_purpose':'sketch',
            'reference_image_data_url':'data:image/png;base64,TEST','reference_contract':{'objects':[]}}
    result,_=scene_planner.plan_scene(text,config)
    assert calls[0][0]['text']['model']=='vision'
    content=calls[0][1][1]['content'];assert content[1]['type']=='image_url'
    assert '两行蛇形排布' in content[0]['text']
    assert result['source_text']==text and result['objects'][1]['state']=='prophase'


def test_known_phase_sketch_preserves_labels_and_reference_evidence_without_semantic_guess(monkeypatch):
    monkeypatch.setattr(scene_planner,'_request',lambda *a,**k:pytest.fail('Known phase sketch should not replan its identities'))
    config={'canvas_mm':[180,120],'reference_id':'ref_test','reference_purpose':'sketch','reference_contract':{
        'objects':[{'id':'p1','label':'间期','type':'process'},{'id':'p2','label':'前期','type':'process'}],
        'relations':[{'source':'p1','target':'p2','type':'sequence'}]}}
    value,meta=scene_planner.plan_scene('保持我的两个细胞位置',config)
    assert [o['state'] for o in value['objects']]==['interphase','prophase']
    assert all(o['evidence_source']=='reference_image' for o in value['objects'])
    assert value['relations'][0]['type']=='sequence'


def test_independent_audit_detects_missing_phases_and_foreign_mechanisms():
    value=mitosis_candidate('有丝分裂全周期闭环')
    value['source_text']='有丝分裂：前期、中期、后期'
    value['generation_contract']={'original_text':value['source_text']}
    value['objects']=[o for o in value['objects'] if o['state']!='metaphase']
    ids={o['id'] for o in value['objects']}
    value['relations']=[r for r in value['relations'] if r['source'] in ids and r['target'] in ids]
    value['requirements']={'objects':list(ids),'relations':[]}
    value['title']='LATENT physical priors'
    codes={f['code'] for f in audit_scene(value)['findings']}
    assert 'missing-scientific-state' in codes and 'unsupported-mechanism' in codes


def test_project_stages_and_molecular_names_never_become_cell_phases():
    from scientific_intent import labeled_cell_phase,phase_sketch
    from figure_generation import apply_constraints
    from scene_document import empty_scene,normalize_scene
    for label in ('Signal kinase','Apoptosis regulator','S','G2 sensor','前期调研','中期开发','后期测试','Prophase kinase'):
        assert labeled_cell_phase(label,biological_context=True)==''
    assert labeled_cell_phase('前期')==''
    assert labeled_cell_phase('细胞 2（前中期）')=='prometaphase'
    assert labeled_cell_phase('Prophase cell')=='prophase'
    value=empty_scene()
    value['objects']=[{'id':'n'+str(i),'type':'process','label':label,'x':10+i*40,'y':20,'w':20,'h':20}
                      for i,label in enumerate(('Signal kinase','前期调研','Prophase kinase'))]
    value=normalize_scene(value)
    config={'original_text':'按草稿细化科研流程图','generation_brief':'按草稿细化科研流程图',
            'sketch_scene':value,'canvas_mm':[180,120]}
    result=apply_constraints(value,config)
    assert all(o['type']=='process' and not o['state'] for o in result['objects'])
    assert phase_sketch(config['original_text'],config) is None


def test_sketch_phase_matching_does_not_confuse_metaphase_with_prometaphase():
    from figure_generation import apply_constraints
    from scene_document import empty_scene,normalize_scene
    sketch=empty_scene()
    sketch['objects']=[{'id':'n'+str(i),'type':'process','label':label,'x':10+i*60,'y':20,'w':30,'h':30}
                       for i,label in enumerate(('前中期','中期'))]
    sketch=normalize_scene(sketch)
    model=empty_scene()
    model['objects']=[{'id':'meta','type':'cell','label':'Metaphase','state':'metaphase'},
                      {'id':'prometa','type':'cell','label':'Prometaphase','state':'prometaphase'}]
    result=apply_constraints(normalize_scene(model),{'original_text':'按细胞草稿生成','generation_brief':'按细胞草稿生成',
        'sketch_scene':sketch,'canvas_mm':[180,120]})
    assert [o['state'] for o in result['objects']]==['prometaphase','metaphase']
    assert [o['label'] for o in result['objects']]==['Prometaphase','Metaphase']


def test_planning_and_audit_do_not_treat_a_phase_regulator_as_a_cell(monkeypatch):
    def request(*args,**kwargs):
        return {'objects':[{'id':'regulator','type':'process','label':'Prophase kinase','evidence':'Prophase kinase'}]},0
    monkeypatch.setattr(scene_planner,'_request',request)
    text='A Prophase kinase participates in mitosis.'
    value,_=scene_planner.plan_scene(text,{'text':{'model':'fake'}})
    assert value['objects'][0]['type']=='process'
    value['generation_contract']={'original_text':text}
    codes={f['code'] for f in audit_scene(value)['findings']}
    assert 'phase-morphology' not in codes
    assert 'missing-scientific-state' in codes
