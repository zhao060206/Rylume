"""Real user journeys through HTTP; models are replaced at the transport boundary."""
import base64
import copy
import io
import json
import time
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw
import pytest

import app_server
import scene_planner
from scene_document import empty_scene, normalize_scene
from test_scene_api import studio


def drawing():
    image = Image.new('RGB',(160,140),'white')
    draw=ImageDraw.Draw(image)
    draw.ellipse((20,10,135,125),fill='#9cc8ce',outline='#29596c',width=3)
    draw.ellipse((60,40,100,80),fill='#a259a8')
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


def scene():
    value=empty_scene(source_text='A then B');value['layout']='process'
    value['objects']=[{'id':ident,'type':'cell','label':ident.upper(),'x':x,'y':20,'w':25,'h':25,
                       'evidence':ident.upper()} for ident,x in [('a',15),('b',110)]]
    value['relations']=[{'id':'ab','source':'a','target':'b','type':'sequence'}]
    value['requirements']={'objects':['a','b'],'relations':['ab']}
    return normalize_scene(value)


def finished(studio,jid):
    for _ in range(250):
        code,job=studio('/api/jobs/'+jid)
        assert code==200
        if job['status'] in ('completed','failed','cancelled'):
            return job
        time.sleep(.02)
    pytest.fail('job did not finish')


def test_image_generation_uses_same_editable_document_and_exports(studio,monkeypatch):
    calls=[]
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(scene(),{}))
    import pipeline
    monkeypatch.setattr(pipeline,'generate_raw',lambda prompt,config:(calls.append(prompt) or drawing()))
    code,result=studio('/api/generate',{'text':'A then B','illustration_mode':'image'})
    assert code==200,result
    job=finished(studio,result['job_id']);assert job['status']=='completed',job
    assert job['scene_engine']=='v2' and job['illustration_result']['generated']==2
    assert len(calls)==2
    assert all('no labels, no text, no arrows' in prompt for prompt in calls)
    endpoint=f"/api/jobs/{job['id']}/scene"
    _,document=studio(endpoint);assert all(o.get('illustration') for o in document['scene']['objects'])
    assert document['svg'].count('<image ')==2 and 'data-object-id="a"' in document['svg']
    # Move an actual generated cell and its label; reload the document.
    code,moved=studio(endpoint,{'base_revision':document['revision'],'operations':[
        {'op':'update','id':'a','changes':{'x':28,'label':'A edited','label_dx':3}},
        {'op':'update_relation','id':'ab','changes':{'label':'editable arrow label','type':'transports','label_position':{'x':72,'y':54}}}]},'PATCH')
    assert code==200,moved
    _,reloaded=studio(endpoint);assert reloaded['scene']['objects'][0]['x']==28
    assert reloaded['scene']['relations'][0]['source']=='a'
    assert reloaded['scene']['relations'][0]['type']=='transports'
    assert reloaded['scene']['relations'][0]['label_position']=={'x':72,'y':54}
    assert 'editable arrow label' in reloaded['svg']
    from scene_render import connection_geometry
    assert connection_geometry(reloaded['scene'],reloaded['scene']['relations'][0])!=connection_geometry(document['scene'],document['scene']['relations'][0])
    for fmt in ('svg','pdf','png','pptx'):
        code,out=studio(f"/api/jobs/{job['id']}/save-as",{'format':fmt,'revision':moved['revision']})
        assert code==200,out
        assert out['revision']==moved['revision'] and out['raster_objects']==['A edited','B']
        assert Path(out['path']).stat().st_size>100
        if fmt=='pptx':
            with zipfile.ZipFile(out['path']) as z:
                xml=z.read('ppt/slides/slide1.xml').decode()
                assert 'A edited' in xml and 'editable arrow label' in xml and '<p:pic>' in xml and '<p:sp>' in xml
    # A failed/absent image service cannot erase the committed vector draft.
    _,draft=studio(f"/api/jobs/{job['id']}/scene")
    assert draft['scene']['generation_contract']['original_text']=='A then B'


def test_reference_pixels_and_object_positions_survive_upload_to_generation(studio,monkeypatch):
    import pipeline
    observed=[]
    contract={'summary':'两行蛇形草稿','composition':'serpentine','objects':[
        {'id':'a','label':'A','type':'cell','x':.12,'y':.15,'w':.2,'h':.2},
        {'id':'b','label':'B','type':'cell','x':.62,'y':.60,'w':.2,'h':.2}],
        'relations':[{'source':'a','target':'b','type':'sequence'}]}
    def transport(url,key,payload,**kw):
        observed.append(payload)
        return {'choices':[{'message':{'content':json.dumps(contract)}}]}
    monkeypatch.setattr(pipeline,'_post_json',transport)
    # Configure a harmless local transport name; actual network is intercepted.
    config=app_server.load_config();config['vision']={'base_url':'https://offline.invalid/v1','model':'spy'};app_server.save_config(config)
    image='data:image/png;base64,'+base64.b64encode(drawing()).decode()
    code,reference=studio('/api/references',{'image':image,'purpose':'sketch'})
    assert code==200 and reference['analysis_status']=='ready'
    assert any(x['type']=='image_url' for x in observed[0]['messages'][0]['content'])
    code,pixels=studio(reference['preview_url']);assert code==200 and pixels.startswith(b'\x89PNG')
    captured=[]
    def plan(text,config,**kw):
        captured.append(config);return scene(),{}
    monkeypatch.setattr(scene_planner,'plan_scene',plan)
    code,result=studio('/api/generate',{'text':'A then B','reference_id':reference['reference_id'],'reference_purpose':'sketch','layout_policy':'preserve'})
    assert code==200,result
    job=finished(studio,result['job_id']);assert job['status']=='completed',job
    _,doc=studio(f"/api/jobs/{job['id']}/scene")
    assert captured[0]['reference_image_data_url'].startswith('data:image/png;base64,')
    assert doc['scene']['objects'][0]['x']==pytest.approx(.12*180)
    assert doc['scene']['objects'][1]['y']==pytest.approx(.60*120)
    assert doc['scene']['generation_contract']['reference_id']==reference['reference_id']


def test_preview_is_reused_and_stale_inputs_are_rejected(studio,monkeypatch):
    calls=[]
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(calls.append(1) or scene(),{}))
    body={'text':'A then B','illustration_mode':'vector'}
    code,preview=studio('/api/generation/preview',body);assert code==200,preview
    assert len(calls)==1
    code,stale=studio('/api/generate',{**body,'text':'A activates C','preview_id':preview['preview_id']})
    assert code==409 and stale['conflict']
    code,result=studio('/api/generate',{**body,'preview_id':preview['preview_id'],'request_id':'preview-reuse'})
    assert code==200,result
    job=finished(studio,result['job_id']);assert job['status']=='completed',job
    assert len(calls)==1
    _,again=studio('/api/generate',{**body,'preview_id':preview['preview_id'],'request_id':'preview-reuse'})
    assert again['job_id']==job['id']


def test_current_canvas_geometry_topology_and_original_remain_intact(studio,monkeypatch):
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(scene(),{}))
    _,first=studio('/api/generate',{'text':'A then B'})
    source=finished(studio,first['job_id']);endpoint=f"/api/jobs/{source['id']}/scene"
    _,old=studio(endpoint)
    _,moved=studio(endpoint,{'base_revision':old['revision'],'operations':[
        {'op':'update','id':'a','changes':{'x':41,'y':12,'label_dx':8}},
        {'op':'update_relation','id':'ab','changes':{'source_anchor':{'side':'s','t':.23}}}]},'PATCH')
    body={'text':'按我的草稿优化形态','sketch_job_id':source['id'],'base_revision':moved['revision']}
    _,result=studio('/api/generate',body);job=finished(studio,result['job_id'])
    assert job['status']=='completed',job
    _,new=studio(f"/api/jobs/{job['id']}/scene")
    assert new['scene']['objects'][0]['x']==41 and new['scene']['objects'][0]['label_dx']==8
    assert new['scene']['relations']==moved['scene']['relations']
    _,unchanged=studio(endpoint);assert unchanged['revision']==moved['revision']
    assert unchanged['scene']==moved['scene']
    code,_=studio('/api/generate',{**body,'base_revision':1});assert code==409


def test_disconnected_image_service_leaves_reopenable_vector_draft(studio,monkeypatch):
    import pipeline
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(scene(),{}))
    monkeypatch.setattr(pipeline,'generate_raw',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('offline')))
    _,result=studio('/api/generate',{'text':'A then B','illustration_mode':'image'})
    job=finished(studio,result['job_id'])
    assert job['status']=='completed' and job['illustration_result']['state']=='partial'
    _,doc=studio(f"/api/jobs/{job['id']}/scene")
    assert len(doc['scene']['objects'])==2 and '<image ' not in doc['svg']
    assert any('图像服务' in x for x in doc['scene']['unresolved'])
    assert job['author_state']=='pending' and job['visual_state']=='unverified'


def test_reference_transport_uses_real_edit_request(monkeypatch):
    from figure_assets import referenced_image
    import urllib.request
    seen=[]
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return json.dumps({'data':[{'b64_json':base64.b64encode(drawing()).decode()}]}).encode()
    def send(request,**kw):seen.append(request);return Reply()
    monkeypatch.setattr(urllib.request,'urlopen',send)
    image='data:image/png;base64,'+base64.b64encode(drawing()).decode()
    raw=referenced_image('one cell',{'image':{'base_url':'https://offline.invalid/v1','model':'test'}},image)
    assert raw.startswith(b'\x89PNG') and seen[0].full_url.endswith('/images/edits')
    assert b'filename="reference.png"' in seen[0].data and drawing() in seen[0].data


def test_raster_document_rejects_external_urls_and_traversal(studio):
    from scene_document import SceneError
    value=scene();value['objects'][0]['illustration']={'data':'https://untrusted.invalid/image.png'}
    with pytest.raises(SceneError):normalize_scene(value)
    code,_=studio('/api/generate',{'text':'x','reference_id':'../config.json'});assert code==400


def test_selected_redraw_preserves_other_objects_and_original_version(studio,monkeypatch):
    import pipeline
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(scene(),{}))
    monkeypatch.setattr(pipeline,'generate_raw',lambda *a,**k:drawing())
    _,first=studio('/api/generate',{'text':'A then B','illustration_mode':'image'})
    original=finished(studio,first['job_id']);endpoint=f"/api/jobs/{original['id']}/scene"
    _,before=studio(endpoint)
    calls=[]
    def changed(prompt,config):
        calls.append(prompt)
        image=Image.open(io.BytesIO(drawing())).convert('RGB')
        ImageDraw.Draw(image).ellipse((50,35,100,90),fill='#a72640')
        out=io.BytesIO();image.save(out,'PNG');return out.getvalue()
    monkeypatch.setattr(pipeline,'generate_raw',changed)
    import figure_assets
    def edit_existing(prompt,config,image):
        assert image==before['scene']['objects'][0]['illustration']['data']
        return changed(prompt,config)
    monkeypatch.setattr(figure_assets,'referenced_image',edit_existing)
    code,res=studio(f"/api/jobs/{original['id']}/redraw",{'base_revision':before['revision'],'target_ids':['a'],'instruction':'深红色细胞核'})
    assert code==200,res
    child=finished(studio,res['job_id']);assert child['status']=='completed',child
    _,after=studio(f"/api/jobs/{child['id']}/scene")
    assert len(calls)==1 and '深红色细胞核' in calls[0]
    assert after['scene']['objects'][1]==before['scene']['objects'][1]
    assert after['scene']['relations']==before['scene']['relations']
    assert after['scene']['objects'][0]['illustration']['sha256']!=before['scene']['objects'][0]['illustration']['sha256']
    _,untouched=studio(endpoint);assert untouched['scene']==before['scene']
    # Changing scientific state must not leave the old raster visible.
    code,state=studio(f"/api/jobs/{child['id']}/scene",{'base_revision':after['revision'],'operations':[
        {'op':'update','id':'a','changes':{'state':'metaphase'}}]},'PATCH')
    assert code==200,state
    assert 'illustration' not in state['scene']['objects'][0]
    assert state['svg'].count('<image ')==1


def test_cancel_after_draft_commit_retains_reopenable_scene(studio,monkeypatch):
    import pipeline
    monkeypatch.setattr(scene_planner,'plan_scene',lambda *a,**k:(scene(),{}))
    def cancelled(*a,**k):
        active=next(j for j in app_server.JOBS.values() if j.get('status')=='processing')
        active['cancel_requested']=True
        return drawing()
    monkeypatch.setattr(pipeline,'generate_raw',cancelled)
    _,res=studio('/api/generate',{'text':'A then B','illustration_mode':'image'})
    job=finished(studio,res['job_id']);assert job['status']=='cancelled' and job['scene_revision']==1
    code,doc=studio(f"/api/jobs/{job['id']}/scene");assert code==200 and len(doc['scene']['objects'])==2


def test_reference_is_cropped_per_object_and_sketch_cannot_add_external_nodes():
    from figure_assets import object_reference
    from figure_generation import apply_constraints
    image=Image.new('RGB',(500,250),'white');draw=ImageDraw.Draw(image)
    draw.ellipse((30,30,170,170),fill='red');draw.ellipse((320,30,460,170),fill='blue')
    out=io.BytesIO();image.save(out,'PNG')
    ref={'coordinates':'normalized','objects':[
        {'id':'a','label':'A','type':'cell','x':.05,'y':.1,'w':.3,'h':.6},
        {'id':'b','label':'B','type':'cell','x':.63,'y':.1,'w':.3,'h':.6}],
        'relations':[{'source':'a','target':'b','type':'sequence'}]}
    config={'original_text':'A then B','generation_brief':'A then B','canvas_mm':[180,120],
            'reference_image_data_url':'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode(),
            'reference_purpose':'sketch','reference_contract':ref}
    crop=object_reference(config,{'id':'a','label':'A'})
    cropped=Image.open(io.BytesIO(base64.b64decode(crop.partition(',')[2])))
    assert cropped.width<200 and cropped.getpixel((cropped.width//2,cropped.height//2))==(255,0,0)
    value=scene();value['objects'].append({'id':'extra_nucleus','type':'nucleus','label':'Nucleus'})
    result=apply_constraints(value,config)
    assert [o['id'] for o in result['objects']]==['a','b']
    assert result['relations'][0]['type']=='sequence'


def test_single_cell_request_does_not_leak_whole_figure_and_rejects_duplicate_cells(monkeypatch):
    from figure_assets import illustrate,image_asset,validate_object_count
    from scene_document import SceneError
    image=Image.new('RGB',(300,140),'white');draw=ImageDraw.Draw(image)
    draw.ellipse((10,15,125,125),fill='#5c9ab7');draw.ellipse((170,15,285,125),fill='#5c9ab7')
    out=io.BytesIO();image.save(out,'PNG')
    with pytest.raises(SceneError):validate_object_count(image_asset(out.getvalue()),{'type':'cell','state':'interphase'})
    import pipeline
    prompts=[]
    def single(prompt,config):prompts.append(prompt);return drawing()
    monkeypatch.setattr(pipeline,'generate_raw',single)
    value=scene();value['source_text']='Draw TWO cells for the entire figure, before and after'
    value,result=illustrate(value,{'generation_brief':value['source_text']})
    assert result['generated']==2
    assert all('Draw TWO cells' not in prompt for prompt in prompts)
    assert all('ONE isolated' in prompt for prompt in prompts)
