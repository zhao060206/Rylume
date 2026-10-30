"""Scientific shortcuts must never replace a different requested subject."""
import base64
import io

import pytest
from PIL import Image,ImageDraw

from scientific_intent import intent_contract,mitosis_candidate,phase_sketch
from scene_document import audit_scene,empty_scene,normalize_scene


def phase_reference():
    return {'canvas_mm':[180,120],'reference_purpose':'sketch','reference_contract':{
        'objects':[{'id':'first','label':'Prophase','type':'cell'}, {'id':'second','label':'Metaphase','type':'cell'}],
        'relations':[{'source':'first','target':'second','type':'sequence'}]}}


@pytest.mark.parametrize('text',[
    '植物细胞有丝分裂：前期到中期，不要中心体和星射线',
    '洋葱根尖有丝分裂全周期',
    'Arabidopsis root mitosis cycle',
    'Budding yeast closed mitosis',
    '减数分裂：前期 I 到中期 I',
    '有丝分裂研究的实验流程：培养、固定、免疫染色、成像',
    'The mechanism of spindle assembly during mitosis',
    'Mitosis-inspired robot controller',
    'Chromosome and microtubule interactions during mitosis',
])
def test_special_species_experiments_meiosis_and_regulators_need_semantic_planning(text):
    if text!='Chromosome and microtubule interactions during mitosis':assert phase_sketch(text,phase_reference()) is None
    assert mitosis_candidate(text) is None


def test_excluded_stages_are_not_required_by_the_audit():
    text='有丝分裂：不要间期和前期，只画中期、后期'
    intent=intent_contract(text)
    assert intent['explicit_phases']==['metaphase','anaphase']
    assert set(intent['excluded_phases'])=={'interphase','prophase'}
    value=empty_scene(source_text=text)
    value['generation_contract']={'original_text':text}
    value['objects']=[{'id':key,'type':'cell','label':label,'state':key,'x':x,'y':20,'w':30,'h':30}
        for key,label,x in [('metaphase','Metaphase',20),('anaphase','Anaphase',100)]]
    assert 'missing-scientific-state' not in {f['code'] for f in audit_scene(normalize_scene(value))['findings']}
    value['objects'].append({'id':'excluded','type':'cell','label':'Interphase','state':'interphase','x':60,'y':70,'w':25,'h':25})
    assert 'excluded-scientific-state' in {f['code'] for f in audit_scene(normalize_scene(value))['findings']}


def test_plant_cell_image_request_does_not_force_animal_centrosomes(monkeypatch):
    from figure_assets import illustrate
    import pipeline
    image=Image.new('RGB',(160,160),'white');ImageDraw.Draw(image).rectangle((20,20,140,140),fill='#9cc8ce')
    out=io.BytesIO();image.save(out,'PNG');prompts=[]
    monkeypatch.setattr(pipeline,'generate_raw',lambda prompt,config:(prompts.append(prompt) or out.getvalue()))
    value=empty_scene(source_text='植物细胞前期：无中心体，无星射线，细胞壁完整')
    value['objects']=[{'id':'plant','type':'cell','label':'Prophase','state':'prophase','x':20,'y':20,'w':30,'h':30,
        'visual_description':'Plant cell with a cell wall, no centrosomes and no asters.'}]
    _,result=illustrate(normalize_scene(value),{'original_text':value['source_text']})
    assert result['generated']==1
    assert 'Centrosomes separate outside the nucleus and form asters' not in prompts[0]
    assert 'Plant cell with a cell wall' in prompts[0]


def test_plant_vector_uses_cell_wall_and_cell_plate_and_respects_locked_art():
    from scientific_intent import apply_division_context
    from biology_glyphs import symbol
    value=empty_scene()
    value['objects']=[{'id':'plant','type':'cell','label':'Cytokinesis','state':'cytokinesis'},
                      {'id':'locked','type':'cell','label':'Original','state':'metaphase','locked':True}]
    apply_division_context(value,'高等植物细胞有丝分裂末期与胞质分裂')
    assert value['objects'][0]['state']=='plant_cytokinesis'
    assert value['objects'][1]['state']=='metaphase'
    svg=symbol('cell','#2E6F83',value['objects'][0]['state'])
    assert 'data-feature="cell-wall"' in svg and 'data-feature="cell-plate"' in svg
    assert 'M 50 10 V 90' in svg
    assert symbol('cell','#2E6F83','prophase I')!=symbol('cell','#2E6F83','prophase')


def test_audit_rejects_an_explicitly_negated_activation_and_excluded_object():
    text='EGF activates EGFR. EGFR does not activate AKT. Do not add D.'
    value=empty_scene(source_text=text);value['generation_contract']={'original_text':text}
    value['objects']=[{'id':label,'type':'protein','label':label,'x':x,'y':20,'w':20,'h':20}
                      for label,x in [('EGF',10),('EGFR',50),('AKT',90),('D',130)]]
    value['relations']=[{'id':'good','source':'EGF','target':'EGFR','type':'activates'},
                        {'id':'bad','source':'EGFR','target':'AKT','type':'activates'}]
    findings=audit_scene(normalize_scene(value))['findings']
    assert any(f['code']=='contradicted-relation' and f['object_ids']==['bad'] for f in findings)
    assert not any(f['code']=='contradicted-relation' and f['object_ids']==['good'] for f in findings)
    assert any(f['code']=='excluded-object' and f['object_ids']==['D'] for f in findings)


def test_planner_retries_negation_instead_of_publishing_a_positive_causal_edge(monkeypatch):
    import scene_planner
    calls=[]
    def request(*args,**kwargs):
        calls.append(1)
        return {'objects':[{'id':'EGFR','type':'protein','label':'EGFR','evidence':'EGFR'},
                           {'id':'AKT','type':'protein','label':'AKT','evidence':'AKT'}],
                'relations':[{'id':'r','source':'EGFR','target':'AKT','type':'activates','evidence':'EGFR does not activate AKT'}] if len(calls)==1 else []},0
    monkeypatch.setattr(scene_planner,'_request',request)
    value,_=scene_planner.plan_scene('EGFR does not activate AKT',{'text':{'model':'fake'}})
    assert len(calls)==2 and value['relations']==[]
