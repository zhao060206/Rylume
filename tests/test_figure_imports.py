"""Figure import through real HTTP: candidates, edits, reopen, template and export."""
import base64
import copy
import io
import json
import threading
import time
from pathlib import Path

from PIL import Image
import pytest

import figure_imports as imports
from scene_document import SceneError
from test_scene_api import studio

SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
<rect x="20" y="60" width="100" height="50" fill="#DDEBEB" stroke="#315D69"/>
<text x="45" y="90" font-size="18" fill="#334455">Input</text>
<line x1="120" y1="85" x2="250" y2="85" stroke="#315D69" stroke-width="2"/>
<rect x="250" y="60" width="120" height="50" fill="#EDF0DD"/>
<text x="275" y="90" font-size="18">Output</text></svg>'''


def png():
    out=io.BytesIO();Image.new('RGB',(400,200),'white').save(out,format='PNG');return out.getvalue()


def observation():
    return {'objects':[
        {'id':'a','kind':'rectangle','x':.05,'y':.3,'w':.25,'h':.25,'fill':'#DDEBEB'},
        {'id':'t1','kind':'text','label':'Input','x':.1,'y':.35,'w':.15,'h':.15},
        {'id':'b','kind':'rectangle','x':.6,'y':.3,'w':.3,'h':.25},
        {'id':'t2','kind':'text','label':'Output','x':.65,'y':.35,'w':.2,'h':.15},
        {'id':'detail','kind':'illustration','x':.4,'y':.8,'w':.1,'h':.1}],
        'relations':[{'source':'a','target':'b','type':'sequence','source_anchor':[1,.5],'target_anchor':[0,.5]}],
        'warnings':['Figure caption is not included.']}


def upload(studio,raw=SVG,name='Diagram.svg',page=1):
    status,row=studio('/api/figure-imports',{'name':name,'data':base64.b64encode(raw).decode(),'page':page})
    assert status==200,row
    return row


def ready(studio,ident):
    for _ in range(250):
        _,row=studio('/api/figure-imports/'+ident)
        if row['state'] not in imports.ACTIVE:return row
        time.sleep(.02)
    pytest.fail('figure import did not finish')


def test_native_import_edit_reopen_export_template_and_idempotent_accept(studio):
    row=upload(studio);endpoint='/api/figure-imports/'+row['id']
    _,before=studio('/api/jobs')
    code,_=studio(endpoint+'/convert',{'mode':'native'});assert code==200
    row=ready(studio,row['id']);assert row['state']=='ready',row
    _,after=studio('/api/jobs');assert before==after  # conversion cannot create a document
    _,candidate=studio(endpoint+'/candidate');assert candidate['report']['texts']==2
    assert candidate['report']['image_blocks']==0 and '<image' not in candidate['svg']
    assert 'Input' in candidate['svg'] and 'Output' in candidate['svg']
    code,_=studio(endpoint+'/accept',{'run':'stale'});assert code==409
    code,result=studio(endpoint+'/accept',{'run':candidate['run']});assert code==200,result
    _,again=studio(endpoint+'/accept',{'run':candidate['run']});assert again['job_id']==result['job_id']
    job=result['job_id'];api='/api/jobs/'+job+'/scene'
    _,scene=studio(api);assert len(scene['scene']['objects'])==5
    target=next(o for o in scene['scene']['objects'] if o['label']=='Input')
    code,edited=studio(api,{'base_revision':1,'operations':[{'op':'update','id':target['id'],
        'changes':{'x':target['x']+5,'label':'Revised input','w':80,'fill':'#AA2211'}}]},'PATCH')
    assert code==200,edited
    assert 'Revised input' in edited['svg'] and '#AA2211' in edited['svg']
    _,reopened=studio(api);assert reopened['scene']==edited['scene']
    code,template=studio('/api/personal-templates',{'job_id':job,'base_revision':2,'title':'My workflow'})
    assert code==200,template
    code,_=studio('/api/personal-templates',{'job_id':job,'base_revision':1});assert code==409
    code,new=studio('/api/personal-templates/'+template['id']+'/use',{});assert code==200
    assert new['job_id']!=job
    _,cloned=studio('/api/jobs/'+new['job_id']+'/scene')
    assert cloned['scene']['objects']==edited['scene']['objects']
    assert cloned['revision']==1 and cloned['scene']['title']=='My workflow'
    for fmt in ('svg','png','pdf','pptx'):
        code,exported=studio('/api/jobs/'+new['job_id']+'/save-as',{'format':fmt,'revision':1})
        assert code==200,exported
        assert Path(exported['path']).is_file()
    import app_server
    assert (imports.manager(app_server.DATA_DIR).folder(row['id'])/'original.bin').read_bytes()==SVG
    assert imports.ImportStore(app_server.DATA_DIR).template_list()[0]['id']==template['id']


def test_ai_reconstruction_independent_text_crops_and_bound_arrows(studio,monkeypatch):
    monkeypatch.setattr(imports,'observe',lambda *args:observation())
    row=upload(studio,png(),'Paper.png');endpoint='/api/figure-imports/'+row['id']
    studio(endpoint+'/convert',{'mode':'ai'});row=ready(studio,row['id']);assert row['state']=='ready',row
    _,candidate=studio(endpoint+'/candidate');assert candidate['report']['image_blocks']==1
    assert candidate['report']['connections']==1 and candidate['report']['author_confirmed'] is False
    _,result=studio(endpoint+'/accept',{'run':candidate['run']});api='/api/jobs/'+result['job_id']+'/scene'
    _,first=studio(api)
    from scene_render import connection_geometry
    original=connection_geometry(first['scene'],first['scene']['relations'][0])
    _,updated=studio(api,{'base_revision':1,'operations':[{'op':'update','id':'a','changes':{'x':18}}]},'PATCH')
    moved=connection_geometry(updated['scene'],updated['scene']['relations'][0])
    assert original['x1']!=moved['x1']
    assert original['x2']==moved['x2'] and original['y2']==moved['y2']
    _,reopened=studio(api);assert reopened['scene']['objects']==updated['scene']['objects']


def test_cancel_retry_and_failure_keep_original_and_never_publish(studio,monkeypatch):
    entered=threading.Event();resume=threading.Event();calls=[]
    def observe(*args):
        calls.append(1);entered.set();resume.wait(5);return observation()
    monkeypatch.setattr(imports,'observe',observe)
    row=upload(studio,png(),'cancel.png');ep='/api/figure-imports/'+row['id']
    studio(ep+'/convert',{'mode':'ai'});assert entered.wait(2)
    _,repeat=studio(ep+'/convert',{'mode':'ai'});assert len(calls)==1
    studio(ep+'/cancel',{});resume.set();row=ready(studio,row['id']);assert row['state']=='cancelled'
    code,_=studio(ep+'/accept',{'run':repeat['run']});assert code==409
    monkeypatch.setattr(imports,'observe',lambda *a: (_ for _ in ()).throw(RuntimeError('secret provider payload')))
    studio(ep+'/convert',{'mode':'ai'});row=ready(studio,row['id']);assert row['state']=='failed'
    assert 'secret' not in row['message']
    code,source=studio(ep+'/source.png');assert code==200 and source==png()
    monkeypatch.setattr(imports,'observe',lambda *a:observation())
    studio(ep+'/convert',{'mode':'ai'});assert ready(studio,row['id'])['state']=='ready'


def test_missing_model_returns_actionable_failure_without_fake_success(studio):
    row=upload(studio,png(),'needs-model.png');studio('/api/figure-imports/'+row['id']+'/convert',{'mode':'ai'})
    row=ready(studio,row['id']);assert row['state']=='failed' and '模型' in row['message']


@pytest.mark.parametrize('body',[
    '<script>alert(1)</script>','<image href="https://bad.test/a.png"/>',
    '<foreignObject/>','<rect width="50" height="50" onload="alert(1)"/>',
    '<rect fill="url(https://bad.test/a.svg)"/>',
])
def test_untrusted_svg_is_rejected_before_rendering(body):
    raw=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'+body+'</svg>').encode()
    with pytest.raises(SceneError):imports.decode_file({'name':'attack.svg','data':base64.b64encode(raw).decode()})


def test_complex_native_svg_is_not_silently_truncated():
    raw=SVG.replace(b'<rect ',b'<defs><linearGradient id="gradient"/></defs><rect ',1)
    with pytest.raises(SceneError,match='AI'):imports.native_svg(raw,'gradient.svg')


@pytest.mark.parametrize('change', ['duplicate','endpoint','nan','whole-image','invented-mechanism'])
def test_invalid_reconstruction_is_not_marked_ready(change):
    value=observation()
    if change=='duplicate':value['objects'][1]['id']='a'
    if change=='endpoint':value['relations'][0]['target']='absent'
    if change=='nan':value['objects'][0]['x']=float('nan')
    if change=='whole-image':value['objects']=[dict(id='whole',kind='illustration',x=0,y=0,w=1,h=1)];value['relations']=[]
    if change=='invented-mechanism':value['relations'][0]['type']='activates'
    with pytest.raises(SceneError):imports.reconstruct(value,png(),'x.png')


def test_pdf_page_selection_and_out_of_range():
    import fitz
    doc=fitz.open();doc.new_page(width=400,height=200);doc.new_page(width=200,height=400)
    raw=doc.tobytes();body={'name':'paper.pdf','data':base64.b64encode(raw).decode(),'page':2}
    _,_,pixels,page,pages=imports.decode_file(body)
    image=Image.open(io.BytesIO(pixels));assert image.height>image.width and page==2 and pages==2
    with pytest.raises(SceneError,match='2'):imports.decode_file({**body,'page':3})


def test_vision_falls_back_to_text_without_leaking_credentials(monkeypatch):
    import pipeline
    calls=[]
    def post(endpoint,key,body,**kwargs):
        calls.append((endpoint,key,body));return {'choices':[{'message':{'content':json.dumps(observation())}}]}
    monkeypatch.setattr(pipeline,'_post_json',post)
    imports.observe(png(),{'text':{'model':'reader','base_url':'https://configured.example/v1','api_key':'private-test'}})
    assert calls[0][2]['model']=='reader'
    assert calls[0][2]['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')


def test_interrupted_import_can_be_recovered_after_restart(tmp_path):
    store=imports.ImportStore(tmp_path);row=store.upload({'name':'x.png','data':base64.b64encode(png()).decode()})
    meta=store.read(row['id']);meta['state']='recognizing';imports._write(store.folder(row['id'])/'meta.json',meta)
    recovered=imports.ImportStore(tmp_path).read(row['id']);assert recovered['state']=='interrupted'
