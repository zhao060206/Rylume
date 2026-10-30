import time
from pathlib import Path
import app_server
import desktop_delivery
from test_scene_api import studio
from test_delivery import pack_fixture,LocalDelivery,wait
from resource_packs import configure
from app_updates import UpdateManager

def test_downloaded_pack_enters_catalog_and_survives_uninstall_in_documents(studio,tmp_path):
    file,catalog,row=pack_fixture(tmp_path)
    manager=configure(app_server.DATA_DIR,delivery=LocalDelivery(file),builtin_catalog=catalog)
    code,result=studio('/api/resources/install',{'id':'chemistry'});assert code==200
    wait(manager.status,lambda s:s['packs'][0]['task']['state']=='installed')
    code,catalog=studio('/api/scene/catalog');assert code==200
    assert next(d for d in catalog['asset_domains'] if d['id']=='chemistry')['available']
    assets=[a for a in catalog['assets'] if a.get('domain')=='chemistry'];assert len(assets)==row['asset_count']
    assert all('_file' not in a for a in assets)
    templates=[t for t in catalog['templates'] if t.get('pack_id')=='chemistry'];assert len(templates)==4
    code,thumbnail=studio(assets[0]['thumbnail']);assert code==200 and b'<svg' in thumbnail
    code,new=studio('/api/scene/example',{'template':templates[0]['id'],'canvas_mm':[90,150]});assert code==200,new
    endpoint='/api/jobs/'+new['job_id'];_,before=studio(endpoint+'/scene')
    assert before['scene']['canvas']['width_mm']==90 and all(o['asset_snapshot'] for o in before['scene']['objects'])
    assert before['audit']['warnings']==0
    code,_=studio('/api/resources/uninstall',{'id':'chemistry'});assert code==200
    _,after=studio(endpoint+'/scene');assert before['svg']==after['svg']
    code,imported=studio('/api/scene/import',{'scene':after['scene']});assert code==200
    for fmt in ('svg','pdf','png','pptx'):
        code,result=studio(endpoint+'/save-as',{'format':fmt,'revision':1});assert code==200,result
        assert result['revision']==1 and Path(result['path']).is_file()
    code,_=studio(assets[0]['thumbnail']);assert code==400

def test_update_endpoints_report_available_without_touching_source(studio,tmp_path,monkeypatch):
    from test_delivery import release_fixture
    file,release=release_fixture(tmp_path)
    manager=UpdateManager(app_server.DATA_DIR,current_version='3.0.0',frozen=False,delivery=LocalDelivery(file,release))
    monkeypatch.setattr(desktop_delivery,'_updater',manager)
    assert studio('/api/updates/check',{})[0]==200
    assert wait(manager.status,lambda s:s['state']=='available')['latest_version']==app_server.PRODUCT_VERSION
    assert studio('/api/updates/download',{})[0]==200
    assert wait(manager.status,lambda s:s['state']=='ready')['can_apply'] is False
    code,error=studio('/api/updates/apply',{});assert code==400 and error['error']
