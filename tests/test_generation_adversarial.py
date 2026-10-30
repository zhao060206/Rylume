"""Adversarial generation journeys: identity, intent, references and concurrent edits."""
import base64
import copy
import io
import threading
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

import app_server
import figure_assets
import figure_generation
import figure_references
import scene_planner
from scene_document import SceneError, empty_scene, normalize_scene
from test_scene_api import studio
from test_generation_core import finished


def pair():
    value=empty_scene(source_text='A then B')
    value['objects']=[{'id':ident,'type':'process','label':ident.upper(),'x':x,'y':20,'w':25,'h':25}
                      for ident,x in [('a',15),('b',110)]]
    value['relations']=[{'id':'ab','source':'a','target':'b','type':'sequence'}]
    return normalize_scene(value)


def pixels(transparent=False):
    image=Image.new('RGBA',(160,140),(0,0,0,0) if transparent else 'white')
    draw=ImageDraw.Draw(image)
    draw.ellipse((20,10,135,125),fill='#9cc8ce',outline='#29596c',width=3)
    out=io.BytesIO();image.save(out,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()


def configuration(**extra):
    return {'original_text':'按草稿生成','generation_brief':'按草稿生成','canvas_mm':[180,120],**extra}


def test_preview_and_idempotency_fingerprint_include_actual_draft_and_redraw_content():
    first=configuration(draft_source_id='client_draft',draft_source_revision=1,sketch_scene=pair())
    changed=copy.deepcopy(first);changed['sketch_scene']['objects'][0]['x']=57
    assert figure_generation.fingerprint(first)!=figure_generation.fingerprint(changed)
    first=configuration(prepared_scene=pair(),redraw_ids=['a'],redraw_instruction='核变红')
    changed=copy.deepcopy(first);changed['prepared_scene']['objects'][0]['label']='Another entity'
    assert figure_generation.fingerprint(first)!=figure_generation.fingerprint(changed)


def test_sketch_protects_locked_objects_and_independent_text():
    sketch=pair()
    sketch['objects'][0].update(locked=True,fill='#abcdef')
    sketch['objects'][1].update(type='text',label='Author supplied title')
    proposal=pair()
    for obj in proposal['objects']:obj.update(type='cell',label='Unrequested replacement')
    result=figure_generation.apply_constraints(proposal,configuration(sketch_scene=sketch))
    assert result['objects']==sketch['objects']


def test_equal_counts_do_not_authorize_guessing_molecule_identity_by_list_position():
    sketch=pair();proposal=pair()
    for i,obj in enumerate(proposal['objects']):obj.update(id='unrelated_'+str(i),label='Unrelated '+str(i),type='cell')
    proposal['relations']=[]
    result=figure_generation.apply_constraints(normalize_scene(proposal),configuration(sketch_scene=sketch))
    assert result['objects']==sketch['objects']
    assert result['unresolved'], 'Unmatched identities must be disclosed instead of silently assigned by order'


def test_reference_sketch_with_no_observed_edges_cannot_invent_causal_arrows():
    ref={'objects':[{'id':obj['id'],'label':obj['label'],'x':obj['x']/180,'y':.2,'w':.15,'h':.2}
                    for obj in pair()['objects']], 'relations':[]}
    proposal=pair();proposal['relations'][0]['type']='activates'
    result=figure_generation.apply_constraints(proposal,configuration(reference_id='ref_example',reference_purpose='sketch',reference_contract=ref))
    assert result['relations']==[]


def test_reference_ids_are_unique_and_relations_never_point_to_discarded_objects():
    contract=figure_references.normalize_contract({'objects':[
        {'id':'ref_n2','label':'First'},{'id':'ref_n2','label':'Second'},
        {'id':'discard','x':'bad'},{'id':'valid','label':'Valid'}],
        'relations':[{'source':'discard','target':'valid','type':'sequence'}]})
    ids=[o['id'] for o in contract['objects']]
    assert len(ids)==len(set(ids))
    assert all(r['source'] in ids and r['target'] in ids for r in contract['relations'])


def test_transparent_reference_is_composited_against_paper_not_turned_black():
    raw,size=figure_references._png(pixels(transparent=True))
    with Image.open(io.BytesIO(raw)) as image:assert image.getpixel((0,0))==(255,255,255)


def test_selected_redraw_edits_the_current_object_pixels(monkeypatch):
    value=pair();value['objects'][0]['illustration']=figure_assets.image_asset(base64.b64decode(pixels().partition(',')[2]))
    expected=value['objects'][0]['illustration']['data']
    observed=[]
    monkeypatch.setattr(figure_assets,'referenced_image',lambda prompt,config,image:(observed.append(image) or base64.b64decode(pixels().partition(',')[2])))
    import pipeline
    monkeypatch.setattr(pipeline,'generate_raw',lambda *a,**k:pytest.fail('Redraw must see the existing illustration'))
    result,metadata=figure_assets.illustrate(value,configuration(redraw_ids=['a'],redraw_instruction='Change only the outline'))
    assert observed==[expected]
    assert metadata['generated']==1


def test_whole_figure_evidence_is_not_repeated_inside_every_object_prompt(monkeypatch):
    value=pair()
    value['objects'][0]['evidence']='Draw TWO cells in different stages and connect them with an arrow.'
    calls=[]
    import pipeline
    monkeypatch.setattr(pipeline,'generate_raw',lambda prompt,config:(calls.append(prompt) or base64.b64decode(pixels().partition(',')[2])))
    figure_assets.illustrate(value,configuration())
    assert len(calls)==2
    assert all('Draw TWO cells' not in prompt for prompt in calls)


def test_generation_checkpoint_cannot_overwrite_an_edit_saved_during_model_call(studio,monkeypatch):
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(pair(),{}))
    entered=threading.Event();resume=threading.Event()
    import pipeline
    def image(*args,**kwargs):
        entered.set()
        assert resume.wait(8)
        return base64.b64decode(pixels().partition(',')[2])
    monkeypatch.setattr(pipeline,'generate_raw',image)
    _,result=studio('/api/generate',{'text':'A then B','illustration_mode':'image'})
    try:
        assert entered.wait(6)
        endpoint='/api/jobs/'+result['job_id']+'/scene'
        _,before=studio(endpoint)
        code,saved=studio(endpoint,{'base_revision':before['revision'],'operations':[
            {'op':'update','id':'a','changes':{'x':53,'label':'Author edit during generation'}}]},'PATCH')
        assert code==200
    finally:
        resume.set()
    job=finished(studio,result['job_id'])
    _,after=studio(endpoint)
    assert after['scene']['objects'][0]['x']==53
    assert after['scene']['objects'][0]['label']=='Author edit during generation'
    assert after['revision']>=saved['revision']


def test_retry_preserves_image_mode_original_brief_and_draft_snapshot(studio,monkeypatch):
    seen=[]
    monkeypatch.setattr(scene_planner,'plan_scene',lambda text,config,**k:(seen.append(copy.deepcopy(config)) or pair(),{}))
    import pipeline
    monkeypatch.setattr(pipeline,'generate_raw',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('offline')))
    draft=pair();draft['objects'][0]['x']=62
    _,first=studio('/api/generate',{'text':'增强排版说明','original_text':'A then B','illustration_mode':'image',
        'draft_scene':draft,'dpi':600})
    original=finished(studio,first['job_id'])
    code,result=studio('/api/jobs/'+original['id']+'/retry',{})
    assert code==200,result
    retried=finished(studio,result['job_id'])
    assert retried['illustration_mode']=='image'
    assert seen[-1]['generation_brief']=='增强排版说明' and seen[-1]['original_text']=='A then B'
    _,after=studio('/api/jobs/'+retried['id']+'/scene')
    assert after['scene']['objects'][0]['x']==62


@pytest.mark.parametrize('dpi',['not a number',True,float('inf'),300.5])
def test_invalid_dpi_returns_a_domain_error(dpi):
    app=SimpleNamespace(load_config=lambda:{},sanitize_style=lambda value:value)
    with pytest.raises(SceneError):figure_generation.prepare(app,{'text':'A then B','dpi':dpi})


def test_known_scientific_contradiction_retains_draft_but_is_not_completed(studio,monkeypatch):
    proposal=pair();proposal['relations'][0]['type']='activates'
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(proposal,{}))
    _,result=studio('/api/generate',{'text':'A does not activate B'})
    job=finished(studio,result['job_id'])
    assert job['status']=='failed' and job['scene_revision']==1
    code,saved=studio('/api/jobs/'+job['id']+'/scene')
    assert code==200 and len(saved['scene']['objects'])==2
    assert any(f['code']=='contradicted-relation' for f in saved['audit']['findings'])


def test_generation_input_snapshot_never_stores_provider_config(studio,monkeypatch):
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(pair(),{}))
    fixture_credential='local-fixture-credential'
    config=app_server.load_config();config['image']={'base_url':'https://offline.invalid','model':'fake','api_key':fixture_credential}
    app_server.save_config(config)
    _,result=studio('/api/generate',{'text':'A then B'})
    job=finished(studio,result['job_id'])
    saved=(app_server.JOBS_DIR/job['id']/'generation-input.json').read_text(encoding='utf8')
    assert fixture_credential not in saved and 'base_url' not in saved and 'api_key' not in saved


def test_no_edit_endpoint_keeps_the_existing_illustration_on_failed_redraw(studio,monkeypatch):
    import pipeline
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(pair(),{}))
    monkeypatch.setattr(pipeline,'generate_raw',lambda *a,**k:base64.b64decode(pixels().partition(',')[2]))
    _,first=studio('/api/generate',{'text':'A then B','illustration_mode':'image'})
    original=finished(studio,first['job_id']);_,before=studio('/api/jobs/'+original['id']+'/scene')
    monkeypatch.setattr(figure_assets,'referenced_image',lambda *a,**k:(_ for _ in ()).throw(SceneError('当前服务不支持参考图重绘')))
    _,result=studio('/api/jobs/'+original['id']+'/redraw',{'base_revision':before['revision'],'target_ids':['a'],'instruction':'只改轮廓'})
    child=finished(studio,result['job_id']);_,after=studio('/api/jobs/'+child['id']+'/scene')
    assert child['illustration_result']['generated']==0
    assert after['scene']['objects']==before['scene']['objects']


def test_large_valid_draft_is_not_rejected_by_its_generated_requirement_metadata():
    value=empty_scene(width_mm=900,height_mm=500)
    value['objects']=[{'id':'m'+str(i),'type':'protein','label':'Protein '+str(i),'x':10+(i%20)*40,'y':10+(i//20)*50,'w':20,'h':20}
                      for i in range(120)]
    value=normalize_scene(value)
    result=figure_generation.apply_constraints(value,configuration(sketch_scene=value))
    assert len(result['objects'])==120


def test_ai_edit_does_not_send_embedded_image_bytes_as_text_and_respects_locks(monkeypatch):
    value=pair();value['objects'][0]['illustration']=figure_assets.image_asset(base64.b64decode(pixels().partition(',')[2]))
    observed=[]
    def request(config,messages,**kwargs):
        observed.append(str(messages))
        return {'operations':[{'op':'update','id':'a','changes':{'label':'Updated label'}}]},0
    monkeypatch.setattr(scene_planner,'_request',request)
    result=scene_planner.propose_revision(value,'修改文字',['a'],{})
    assert result['operations']
    assert not any('data:image/png;base64' in message for message in observed)
    value['objects'][0]['locked']=True
    with pytest.raises(SceneError):scene_planner.propose_revision(value,'修改文字',['a'],{})
    with pytest.raises(SceneError):scene_planner.propose_revision(value,'修改文字','a',{})
