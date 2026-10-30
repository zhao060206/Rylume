import copy
import hashlib
import io
import json
from pathlib import Path
import stat
import threading
import time
import zipfile
import pytest
from github_delivery import GitHubDelivery,DeliveryError,Cancelled,checked_zip,trusted_url,version_tuple
from resource_packs import configure,safe_svg,_write
from app_updates import UpdateManager,acknowledge

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture(autouse=True)
def isolated_library():
    import resource_packs
    old=resource_packs._current
    yield
    resource_packs._current=old;resource_packs._clear_library()
def wait(fn,terminal,timeout=10):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=fn()
        if terminal(value):return value
        time.sleep(.02)
    raise AssertionError('Background operation timed out: '+str(fn()))

def pack_fixture(tmp_path,pid='chemistry'):
    folder=ROOT/'resource-packs'/pid
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
    file=tmp_path/'fixture.zip'
    with zipfile.ZipFile(file,'w',zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob('*'):
            if p.is_file():z.write(p,p.relative_to(folder))
    row=next(p for p in json.loads((ROOT/'assets/resource-catalog.json').read_text(encoding='utf8'))['packs'] if p['id']==pid)
    row={**row,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'size':file.stat().st_size}
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps({'schema_version':1,'packs':[row]}),encoding='utf8')
    return file,catalog,row

class LocalDelivery:
    def __init__(self,file,read=None):self.file=file;self.read_value=read;self.downloads=0;self.fail=False
    def read(self,*a,**kw):
        if self.fail:raise OSError('offline')
        return json.dumps(self.read_value).encode()
    def download(self,url,dest,sha256,**kw):
        self.downloads+=1
        if kw.get('cancel') and kw['cancel'].is_set():raise Cancelled()
        raw=self.file.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha256:raise DeliveryError('SHA-256 mismatch')
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        if kw.get('progress'):kw['progress'](len(raw),len(raw))
        return dest

def installed(tmp_path,pid='chemistry'):
    file,catalog,row=pack_fixture(tmp_path,pid)
    delivery=LocalDelivery(file);m=configure(tmp_path/'data',delivery=delivery,builtin_catalog=catalog)
    m.install(pid);result=wait(m.status,lambda s:s['packs'][0].get('task',{}).get('state') in ('installed','failed'))
    assert result['packs'][0]['task']['state']=='installed',result
    return m,delivery

def test_install_uninstall_and_portable_scene_roundtrip(tmp_path):
    from scene_render import render_scene
    from scene_document import normalize_scene
    from scene_export import export_scene
    m,_=installed(tmp_path);template=m.templates()[0];scene=m.template_scene(template['id'])
    assert scene['objects'] and all(o['asset_snapshot'] for o in scene['objects'])
    before=render_scene(scene);m.uninstall('chemistry');assert not m.assets()
    reopened=normalize_scene(json.loads(json.dumps(scene)));assert render_scene(reopened)==before
    out=tmp_path/'portable.pptx';export_scene(reopened,'pptx',out)
    with zipfile.ZipFile(out) as z:
        assert not any(p.startswith('ppt/media/') for p in z.namelist())
        assert b'custGeom' in z.read('ppt/slides/slide1.xml')

def test_install_is_deduplicated_and_offline_catalog_survives(tmp_path):
    m,d=installed(tmp_path);m.refresh();wait(m.status,lambda s:not s['refreshing'])
    assert m.status()['packs'][0]['installed_version']=='1.0.0'
    assert m.status()['error']

def test_bad_digest_preserves_installed_pack(tmp_path):
    m,d=installed(tmp_path);m.catalog=lambda:{'schema_version':1,'packs':[{**m.validate_catalog(json.loads(m.builtin.read_text()))['packs'][0],'sha256':'0'*64,'version':'1.0.1','asset_name':'rylume-pack-chemistry-1.0.1.zip'}]}
    m.install('chemistry');s=wait(m.status,lambda s:s['packs'][0]['task']['state']=='failed')
    assert s['packs'][0]['installed_version']=='1.0.0' and m.assets()

@pytest.mark.parametrize('text',[
 '<svg viewBox="0 0 100 100"><script>alert(1)</script></svg>',
 '<svg viewBox="0 0 100 100"><image href="file:///config.json"/></svg>',
 '<svg viewBox="0 0 100 100"><path onclick="alert(1)" d="M0 0"/></svg>',
 '<svg viewBox="0 0 100 100"><rect fill="url(https://evil.test/a)"/></svg>',
 '<!DOCTYPE svg [<!ENTITY foo SYSTEM "file:///config.json">]><svg viewBox="0 0 100 100"/>',
 '<svg viewBox="0 0 NaN 100"/>'])
def test_untrusted_artwork_is_rejected(text):
    with pytest.raises(DeliveryError):safe_svg(text)

@pytest.mark.parametrize('name',['../escape','/absolute','C:/Windows/a','assets\\evil.svg','assets/NUL.txt','assets/a:stream','assets/a.'])
def test_zip_slip_windows_paths_rejected_before_extract(tmp_path,name):
    file=tmp_path/'evil.zip'
    with zipfile.ZipFile(file,'w') as z:
        info=zipfile.ZipInfo();info.filename=name;z.writestr(info,'bad')
    with pytest.raises(DeliveryError):checked_zip(file,tmp_path/'stage')
    assert not (tmp_path/'stage').exists()

def test_zip_case_collision_symlink_and_file_directory_conflict(tmp_path):
    for index,entries in enumerate([['assets/A.svg','assets/a.svg'],['a','a/b']]):
        file=tmp_path/f'bad{index}.zip'
        with zipfile.ZipFile(file,'w') as z:
            for p in entries:z.writestr(p,'x')
        with pytest.raises(DeliveryError):checked_zip(file,tmp_path/f'stage{index}')
    file=tmp_path/'link.zip'
    with zipfile.ZipFile(file,'w') as z:
        info=zipfile.ZipInfo('link');info.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(info,'../../config.json')
    with pytest.raises(DeliveryError):checked_zip(file,tmp_path/'link-stage')

@pytest.mark.parametrize('url',['http://github.com/zhao060206/Rylume/a','https://github.com/other/repo/a','https://github.com.evil.test/a','https://api.github.com/user','https://u:x@github.com/zhao060206/Rylume/a','https://github.com:8443/zhao060206/Rylume/a'])
def test_remote_origin_boundary(url):
    with pytest.raises(DeliveryError):trusted_url(url)

def test_semantic_versions_and_prerelease():
    assert version_tuple('v3.10.0')>version_tuple('3.9.9')
    for v in ('3.1','v3.2.0-beta','latest','1.2.3.4'):
        with pytest.raises(DeliveryError):version_tuple(v)

def release_fixture(tmp_path):
    file=tmp_path/'app.zip'
    with zipfile.ZipFile(file,'w') as z:
        z.writestr('Rylume/Rylume.exe',b'MZfixture')
        z.writestr('Rylume/_internal/python313.dll','fixture')
        z.writestr('Rylume/_internal/ui/canvas-studio.html','fixture')
    asset={'name':'Rylume-3.1.0-Windows-x64.zip','size':file.stat().st_size,'digest':'sha256:'+hashlib.sha256(file.read_bytes()).hexdigest(),'browser_download_url':'https://github.com/zhao060206/Rylume/releases/download/v3.1.0/Rylume-3.1.0-Windows-x64.zip'}
    release={'tag_name':'v3.1.0','draft':False,'prerelease':False,'body':'Release notes','assets':[asset]}
    return file,release

def test_update_download_and_source_mode_never_replaces_interpreter(tmp_path):
    file,release=release_fixture(tmp_path);m=UpdateManager(tmp_path/'data',current_version='3.0.0',frozen=False,delivery=LocalDelivery(file,release))
    m.check();assert wait(m.status,lambda s:s['state']!='checking')['state']=='available'
    m.download();ready=wait(m.status,lambda s:s['state'] in ('ready','failed'))
    assert ready['state']=='ready' and not ready['can_apply']
    with pytest.raises(DeliveryError,match='源码版'):m.apply()

def test_update_digest_failure_and_missing_asset_never_stages(tmp_path):
    file,release=release_fixture(tmp_path);release['assets'][0]['digest']='sha256:'+'0'*64
    m=UpdateManager(tmp_path/'data',current_version='3.0.0',delivery=LocalDelivery(file,release));m.check();wait(m.status,lambda s:s['state']=='available');m.download()
    assert wait(m.status,lambda s:s['state']=='failed')['state']=='failed' and m.stage is None
    release['assets']=[];m.check();assert wait(m.status,lambda s:s['state']=='failed')['error']

def test_update_plan_and_health_are_confined_to_separate_data(tmp_path,monkeypatch):
    import app_updates
    file,release=release_fixture(tmp_path);target=tmp_path/'portable/Rylume';target.mkdir(parents=True);(target/'Rylume.exe').write_text('old')
    calls=[];m=UpdateManager(tmp_path/'data',install_dir=target,current_version='3.0.0',frozen=True,delivery=LocalDelivery(file,release),launcher=lambda *a,**kw:calls.append((a,kw)))
    m.check();wait(m.status,lambda s:s['state']=='available');m.download();wait(m.status,lambda s:s['state']=='ready')
    monkeypatch.setattr(app_updates.sys,'platform','win32')
    m.apply(['--data-dir',str(tmp_path/'data'),'--no-migrate']);assert calls
    planpath=next((m.root/'apply').glob('*/plan.json'));plan=json.loads(planpath.read_text())
    assert plan['install_dir']==str(target.resolve()) and plan['data_dir']==str((tmp_path/'data').resolve())
    assert '-File' in calls[0][0][0] and 'api_key' not in planpath.read_text()
    acknowledge(tmp_path/'data',planpath,plan['nonce']);assert Path(plan['health_file']).is_file()
    with pytest.raises(DeliveryError):acknowledge(tmp_path/'wrong-data',planpath,plan['nonce'])

def test_all_discipline_templates_are_portable_and_have_distinct_mechanisms(tmp_path):
    from scene_document import normalize_scene,audit_scene
    from scene_render import render_scene
    for folder in sorted((ROOT/'resource-packs').iterdir()):
        manifest=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
        assert len(manifest['assets'])>=18 and len(manifest['templates'])>=4
        geometries=[]
        for a in manifest['assets']:assert '<svg' in safe_svg((folder/a['file']).read_text(encoding='utf8'))
        for t in manifest['templates']:
            scene=normalize_scene(json.loads((folder/t['file']).read_text(encoding='utf8')))
            assert not audit_scene(scene)['errors'];assert all(o.get('asset_snapshot') for o in scene['objects'])
            assert '<image' not in render_scene(scene)
            geometries.append((tuple(o['asset_id'] for o in scene['objects']),tuple((r['source'],r['target'],r['label']) for r in scene['relations'])))
        assert len(set(geometries))==len(geometries)
