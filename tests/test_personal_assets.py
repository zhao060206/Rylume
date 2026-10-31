"""Original preservation, model routing, candidate acceptance and export via real HTTP."""
import base64
import io
import time
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw
import pytest

from test_scene_api import studio
import personal_assets


def picture():
    image=Image.new('RGBA',(160,120))
    draw=ImageDraw.Draw(image)
    draw.ellipse((12,12,145,108),fill='#88b5c6',outline='#355e73',width=3)
    draw.ellipse((60,40,100,78),fill='#b78ba5')
    out=io.BytesIO();image.save(out,format='PNG')
    return out.getvalue()


def upload(studio):
    raw=picture()
    code,asset=studio('/api/personal-assets',{'image':'data:image/png;base64,'+base64.b64encode(raw).decode(),
        'label':'自有细胞','domain':'biology','category':'细胞'})
    assert code==200,asset
    return asset,raw


def wait(studio,ident):
    for _ in range(150):
        code,result=studio('/api/personal-assets/'+ident)
        assert code==200,result
        if result['state'] not in personal_assets.ACTIVE:return result
        time.sleep(.03)
    pytest.fail('asset conversion did not terminate')


def test_original_candidate_accept_snapshot_reopen_export_and_archive(studio):
    asset,raw=upload(studio);ident=asset['id'];endpoint='/api/personal-assets/'+ident
    import app_server
    store=personal_assets.manager(app_server.DATA_DIR)
    assert (store.folder(ident)/'original.bin').read_bytes()==raw
    _,initial=studio('/api/scene/catalog');assert not any(a.get('asset_id')==ident for a in initial['assets'])
    _,started=studio(endpoint+'/vectorize',{'use_model':False});assert started['state']=='queued'
    result=wait(studio,ident);assert result['state']=='ready',result
    candidate=result['candidate'];assert candidate['quality']['foreground_similarity']>94
    assert candidate['model_status']=='not_requested'
    code,svg=studio(result['candidate_url']);assert code==200
    assert not any(n.tag.split('}')[-1]=='image' for n in ET.fromstring(svg).iter())
    assert studio(endpoint+'/accept',{'run':'stale'})[0]==400
    assert studio(endpoint+'/accept',{'run':candidate['run']})[0]==200
    _,catalog=studio('/api/scene/catalog');item=next(a for a in catalog['assets'] if a.get('asset_id')==ident)
    assert item['category']=='细胞' and item['personal'] and '_file' not in item
    _,blank=studio('/api/scene/blank',{});job=blank['job_id'];scene_endpoint='/api/jobs/'+job+'/scene'
    _,initial=studio(scene_endpoint)
    code,saved=studio(scene_endpoint,{'base_revision':initial['revision'],'operations':[{'op':'add','object':{
        'id':'my_cell','type':item['type'],'asset_id':ident,'label':'独立文字','x':30,'y':30,'w':32,'h':24}}]},'PATCH')
    assert code==200,saved
    assert 'asset_snapshot' in saved['scene']['objects'][0]
    assert studio(endpoint+'/archive',{})[0]==200
    _,catalog=studio('/api/scene/catalog');assert not any(a.get('asset_id')==ident for a in catalog['assets'])
    _,reopened=studio(scene_endpoint);assert reopened['scene']['objects']==saved['scene']['objects']
    assert '<image' not in reopened['svg'] and '独立文字' in reopened['svg']
    from scene_export import export_scene
    for fmt in ('svg','png','pdf','pptx'):
        output=store.root/('snapshot.'+fmt)
        exported=export_scene(reopened['scene'],fmt,output)
        assert output.stat().st_size>0 and exported['raster_objects']==[]
    assert studio(endpoint+'/restore',{})[0]==200
    assert studio(endpoint+'/metadata',{'label':'改名素材','category':'自定义类别','domain':'chemistry'})[0]==200
    _,catalog=studio('/api/scene/catalog');assert any(a.get('asset_id')==ident and a['domain']=='chemistry' and a['label']=='改名素材' for a in catalog['assets'])


def test_model_analysis_and_comparison_are_separate_and_failures_are_explicit(studio,monkeypatch):
    calls=[]
    def observe(png,config,*,candidate=None):
        calls.append(bool(candidate))
        if candidate:return {'summary':'轮廓和颜色接近原图','warnings':[],'needs_attention':False}
        return {'kind':'flat','summary':'透明底的细胞插画','warnings':[]}
    monkeypatch.setattr(personal_assets,'model_observe',observe)
    asset,_=upload(studio);endpoint='/api/personal-assets/'+asset['id']
    studio(endpoint+'/vectorize',{'use_model':True});result=wait(studio,asset['id'])
    assert calls==[False,True] and result['candidate']['review_status']=='completed'
    studio(endpoint+'/accept',{'run':result['candidate']['run']})
    accepted=result['candidate']['run']
    def unavailable(*args,**kwargs):raise RuntimeError('provider response must never leak credentials')
    monkeypatch.setattr(personal_assets,'model_observe',unavailable)
    studio(endpoint+'/vectorize',{'use_model':True});result=wait(studio,asset['id'])
    assert result['accepted_run']==accepted and result['candidate']['model_status']=='unavailable'
    assert 'provider response' not in str(result)


def test_invalid_image_path_and_cancel_preserve_source(studio,monkeypatch):
    assert studio('/api/personal-assets',{'image':'data:image/svg+xml;base64,xxx'})[0]==400
    assert studio('/api/personal-assets/user_invalid/source.png')[0]==400
    asset,raw=upload(studio);endpoint='/api/personal-assets/'+asset['id']
    import threading
    entered=threading.Event();resume=threading.Event()
    def slow(*args,**kwargs):entered.set();resume.wait(4);return {'summary':'test'}
    monkeypatch.setattr(personal_assets,'model_observe',slow)
    studio(endpoint+'/vectorize',{'use_model':True});assert entered.wait(3)
    studio(endpoint+'/cancel',{});resume.set();result=wait(studio,asset['id'])
    assert result['state']=='cancelled' and result['candidate'] is None
    assert studio(result['source_url'])[0]==200


def test_release_history_is_offline_and_acknowledged_per_version(studio):
    code,notes=studio('/api/release-notes');assert code==200 and notes['unread']
    assert notes['releases'][0]['version']==notes['current_version']=='4.5.0'
    assert notes['releases'][0]['items'] and len(notes['releases'])>=5
    assert studio('/api/release-notes/acknowledge',{'version':'0.0.0'})[0]==400
    assert studio('/api/release-notes/acknowledge',{'version':'4.5.0'})[0]==200
    assert studio('/api/release-notes')[1]['unread'] is False
