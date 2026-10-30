"""Versioned, data-only discipline packs; installed under the user's data store."""
from __future__ import annotations
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
import xml.etree.ElementTree as ET
from functools import lru_cache
from github_delivery import GitHubDelivery,DeliveryError,Cancelled,checked_zip,version_tuple,REPOSITORY

RESOURCE_TAG='resource-packs-v1'
DOMAIN_TITLES={'biology':'生物学','chemistry':'化学','physics':'物理学','materials':'材料科学',
    'engineering':'工程技术','earth-environment':'地球与环境','computing-math':'计算机与数学','medicine':'医学'}
ID=re.compile(r'^[a-z][a-z0-9_-]{0,79}$')
SAFE_TAGS={'svg','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan'}
SAFE_ATTRS={'viewBox','x','y','x1','y1','x2','y2','cx','cy','r','rx','ry','width','height','d','points','transform',
    'fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','fill-rule','opacity','fill-opacity','stroke-opacity',
    'font-size','font-family','font-weight','text-anchor','dominant-baseline'}
META_KEYS=('asset_id','label','author','author_url','license','license_url','source_url','modifications')
_current=None;_guard=threading.RLock()

@lru_cache(maxsize=512)
def safe_svg(text):
    if not isinstance(text,str) or len(text.encode('utf8'))>256*1024 or re.search(r'<!|<\?',text):
        raise DeliveryError('素材 SVG 大小或格式不合法')
    try:root=ET.fromstring(text)
    except ET.ParseError:raise DeliveryError('素材 SVG 无法解析') from None
    nodes=list(root.iter())
    if len(nodes)>2500 or root.tag.split('}')[-1]!='svg':raise DeliveryError('素材 SVG 结构无效')
    try:
        box=[float(x) for x in root.get('viewBox','').split()]
        if len(box)!=4 or not all(__import__('math').isfinite(x) for x in box) or not all(0<x<=10000 for x in box[2:]):raise ValueError()
    except ValueError:raise DeliveryError('素材 SVG 缺少有效 viewBox') from None
    for node in nodes:
        tag=node.tag.split('}')[-1]
        if tag not in SAFE_TAGS:raise DeliveryError('素材包含不允许的 SVG 元素')
        node.tag=tag
        for attr,value in node.attrib.items():
            if attr not in SAFE_ATTRS or re.search(r'(?i)(url\s*\(|javascript:|https?:|data:|NaN|Infinity)',value):
                raise DeliveryError('素材包含外部引用或不允许的属性')
    root.set('xmlns','http://www.w3.org/2000/svg')
    return ET.tostring(root,encoding='unicode')

def snapshot(value,asset_id):
    if not isinstance(value,dict) or not isinstance(value.get('meta'),dict):raise DeliveryError('素材快照无效')
    meta={k:str(value['meta'].get(k,''))[:1000] for k in META_KEYS}
    if meta['asset_id']!=asset_id:raise DeliveryError('素材快照身份不匹配')
    return {'svg':safe_svg(value.get('svg')),'meta':meta}

def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    with tmp.open('w',encoding='utf8') as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2);handle.flush();os.fsync(handle.fileno())
    from studio_storage import durable_replace
    durable_replace(tmp,path)

def configure(data_dir,**kwargs):
    global _current
    with _guard:
        if _current is None or _current.data_dir!=Path(data_dir).resolve():
            _current=ResourceManager(data_dir,**kwargs)
            _clear_library()
        return _current

def manager():
    global _current
    if _current is None:
        from studio_storage import get_data_dir
        configure(get_data_dir())
    return _current

def _clear_library():
    import scientific_library
    scientific_library.library.cache_clear();scientific_library.glyph.cache_clear()

def reflow_pack_scene(scene,width,height):
    from scene_document import normalize_scene,empty_scene
    canvas=normalize_scene(empty_scene(width_mm=width,height_mm=height))['canvas'];w=canvas['width_mm'];h=canvas['height_mm']
    scene=copy.deepcopy(scene);old=scene['canvas'];scene['canvas']=canvas
    if w<120:
        for i,o in enumerate(scene['objects']):o.update(x=11+(i%2)*(w-35),y=10+(i//2)*(h-30)/max(1,(len(scene['objects'])+1)//2),w=19,h=23)
        if scene['compartments']:
            # Keep the three electrodes in the shared electrolyte; the instrument stays outside.
            for i,o in enumerate(scene['objects'][:3]):o.update(x=6+i*(w-33)/2,y=h*.48)
            scene['objects'][3].update(x=(w-19)/2,y=8)
            scene['compartments'][0].update(x=3,y=h*.36,w=w-6,h=h*.48)
    else:
        for o in scene['objects']:o.update(x=o['x']*w/old['width_mm'],y=o['y']*h/old['height_mm'])
        for c in scene['compartments']:
            for k,scale in [('x',w/old['width_mm']),('w',w/old['width_mm']),('y',h/old['height_mm']),('h',h/old['height_mm'])]:c[k]*=scale
    objs={o['id']:o for o in scene['objects']}
    for r in scene['relations']:
        r.pop('control',None)
        if any(q['source']==r['target'] and q['target']==r['source'] for q in scene['relations']):
            a,b=objs[r['source']],objs[r['target']];dx=b['x']-a['x'];dy=b['y']-a['y'];length=max(1,__import__('math').hypot(dx,dy))
            r['control']={'x':(a['x']+b['x'])/2+9.5-15*dy/length,'y':(a['y']+b['y'])/2+11.5+15*dx/length}
    scene=normalize_scene(scene)
    # Route narrow-paper connectors into separate lanes without shrinking labels.
    if w<120:
        from scene_document import audit_scene
        from scene_render import connection_geometry
        def score(s):return sum(10 if f['severity']=='error' else 1 for f in audit_scene(s)['findings'])
        best=score(scene)
        for _ in range(4):
            if best==0:break
            changed=False
            affected={oid for f in audit_scene(scene)['findings'] for oid in f['object_ids']}
            for edge in scene['relations']:
                if edge['id'] not in affected:continue
                initial=copy.deepcopy(edge.get('control'));g=connection_geometry(scene,edge);center=g['control']
                chosen=initial;local=best
                for dx,dy in [(0,-15),(0,15),(-15,0),(15,0),(0,-28),(0,28),(-28,0),(28,0),(-20,-20),(20,20),(-20,20),(20,-20)]:
                    edge['control']={'x':min(w-3,max(3,center['x']+dx)),'y':min(h-3,max(3,center['y']+dy))}
                    cost=score(scene)
                    if cost<local:local=cost;chosen=copy.deepcopy(edge['control'])
                    if local==0:break
                if chosen is None:edge.pop('control',None)
                else:edge['control']=chosen
                if local<best:best=local;changed=True
            if not changed:break
    return normalize_scene(scene)

class ResourceManager:
    def __init__(self,data_dir,delivery=None,builtin_catalog=None):
        self.data_dir=Path(data_dir).resolve();self.root=self.data_dir/'resources'
        self.delivery=delivery or GitHubDelivery();self.lock=threading.RLock()
        self.executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='resource-download')
        self.tasks={};self.cancels={};self.error='';self.refreshing=False
        self.builtin=Path(builtin_catalog) if builtin_catalog else Path(__file__).parent/'assets/resource-catalog.json'
    def _json(self,path,default):
        try:return json.loads(path.read_text(encoding='utf8'))
        except (OSError,ValueError):return copy.deepcopy(default)
    def installed(self):return self._json(self.root/'installed.json',{})
    def catalog(self):
        d=self._json(self.root/'catalog.json',self._json(self.builtin,{'schema_version':1,'packs':[]}))
        return self.validate_catalog(d)
    @staticmethod
    def validate_catalog(d):
        if not isinstance(d,dict) or d.get('schema_version')!=1 or not isinstance(d.get('packs'),list) or len(d['packs'])>100:raise DeliveryError('资源目录格式不支持')
        seen=set()
        for p in d['packs']:
            if not isinstance(p,dict) or not ID.fullmatch(str(p.get('id',''))) or p['id'] in seen:raise DeliveryError('资源包标识无效')
            seen.add(p['id']);version_tuple(p.get('version'));version_tuple(p.get('min_app_version','3.1.0'))
            if p.get('domain') not in DOMAIN_TITLES or not isinstance(p.get('title'),str) or not 1<=len(p['title'])<=80:raise DeliveryError('资源学科或名称无效')
            if any(not isinstance(p.get(k),int) or not 0<p[k]<=1500 for k in ('asset_count','template_count')):raise DeliveryError('资源计数无效')
            if p.get('asset_name')!=f"rylume-pack-{p['id']}-{p['version']}.zip" or not re.fullmatch('[0-9a-f]{64}',str(p.get('sha256',''))):raise DeliveryError('资源包文件或校验值无效')
            if not isinstance(p.get('size'),int) or not 0<p['size']<100*1024*1024:raise DeliveryError('资源包大小无效')
        return copy.deepcopy(d)
    def status(self):
        from product_identity import PRODUCT_VERSION
        with self.lock:
            installed=self.installed();packs=[]
            for p in self.catalog()['packs']:
                old=installed.get(p['id']);row={**p,'installed_version':old.get('version') if old else None,
                    'compatible':version_tuple(PRODUCT_VERSION)>=version_tuple(p.get('min_app_version','3.1.0')),
                    'task':copy.deepcopy(self.tasks.get(p['id']))}
                row['update_available']=bool(old and version_tuple(p['version'])>version_tuple(old['version']))
                packs.append(row)
            return {'ok':True,'packs':packs,'refreshing':self.refreshing,'error':self.error,'biology_builtin':True}
    def refresh(self):
        with self.lock:
            if self.refreshing:return self.status()
            self.refreshing=True
        def work():
            try:
                raw=self.delivery.read(f'https://github.com/{REPOSITORY}/releases/download/{RESOURCE_TAG}/catalog.json')
                d=self.validate_catalog(json.loads(raw));_write(self.root/'catalog.json',d)
                with self.lock:self.error=''
            except Exception:
                with self.lock:self.error='暂时无法连接 GitHub，已显示本机资源目录；可以重试'
            finally:
                with self.lock:self.refreshing=False
        self.executor.submit(work);return self.status()
    def _set(self,pid,**kwargs):
        with self.lock:self.tasks.setdefault(pid,{}).update(kwargs)
    def install(self,pid):
        from product_identity import PRODUCT_VERSION
        with self.lock:
            p=next((p for p in self.catalog()['packs'] if p['id']==pid),None)
            if not p:raise DeliveryError('资源包不存在')
            if version_tuple(PRODUCT_VERSION)<version_tuple(p.get('min_app_version','3.1.0')):raise DeliveryError('请先更新软件再下载此资源包')
            if self.tasks.get(pid,{}).get('state') in ('queued','downloading','validating','installing'):return self.status()
            cancel=threading.Event();self.cancels[pid]=cancel;self._set(pid,state='queued',progress=0,error='')
            self.executor.submit(self._install,p,cancel)
        return self.status()
    def _install(self,p,cancel):
        pid=p['id'];stage=self.root/'.staging'/uuid.uuid4().hex;archive=self.root/'downloads'/p['asset_name']
        try:
            self._set(pid,state='downloading')
            self.delivery.download(f"https://github.com/{REPOSITORY}/releases/download/{RESOURCE_TAG}/{p['asset_name']}",archive,p['sha256'],
                limit=100*1024*1024,total=p['size'],cancel=cancel,progress=lambda n,t:self._set(pid,downloaded=n,total=t,progress=round(n/max(t,1)*85,1)))
            self._set(pid,state='validating',progress=88)
            checked_zip(archive,stage,max_files=1500,max_bytes=100*1024*1024,allowed_suffixes={'.json','.svg','.txt','.md'})
            manifest=self.validate_pack(stage,p)
            if cancel.is_set():raise Cancelled('下载已取消')
            target=self.root/'packs'/pid/p['version'];target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                # Versions are immutable: a same-version retry only reactivates validated bytes.
                self.validate_pack(target,p)
            else:os.replace(stage,target)
            self._set(pid,state='installing',progress=95)
            with self.lock:
                installed=self.installed();installed[pid]={'version':p['version'],'title':p['title'],'domain':p['domain']}
                _write(self.root/'installed.json',installed);_clear_library()
            self._set(pid,state='installed',progress=100)
        except Cancelled:self._set(pid,state='cancelled',error='下载已取消，已有资源保持可用')
        except Exception as exc:self._set(pid,state='failed',error=str(exc) if isinstance(exc,DeliveryError) else '资源安装未完成，可以重试；原有资源已保留')
        finally:
            if stage.exists() and stage.resolve().is_relative_to((self.root/'.staging').resolve()):shutil.rmtree(stage)
    def validate_pack(self,folder,expected):
        manifest=self._json(folder/'manifest.json',{})
        if manifest.get('schema_version')!=1 or manifest.get('id')!=expected['id'] or manifest.get('version')!=expected['version']:raise DeliveryError('资源包身份与目录不一致')
        assets=manifest.get('assets',[]);templates=manifest.get('templates',[])
        if len(assets)!=expected['asset_count'] or len(templates)!=expected['template_count']:raise DeliveryError('资源数量不完整')
        seen=set()
        for item in assets+templates:
            aid=item.get('id','')
            if not ID.fullmatch(aid) or not aid.startswith(expected['id'].replace('-','_')+'_') or aid in seen:raise DeliveryError('资源对象身份冲突')
            seen.add(aid);file=self.file_path(folder,item['file'])
            if item in assets:safe_svg(file.read_text(encoding='utf8'))
            else:
                scene=json.loads(file.read_text(encoding='utf8'))
                # Scene normalization and snapshots are checked before activation, with a temporary resolver.
                with self.lock:
                    self._validation_assets={a['id']:{**a,'asset_id':a['id'],'_file':str(self.file_path(folder,a['file'])),'domain':expected['domain']} for a in assets}
                    try:
                        _clear_library()
                        from scene_document import normalize_scene
                        normalize_scene(scene)
                    finally:self._validation_assets={};_clear_library()
                safe_svg(self.file_path(folder,item['thumbnail']).read_text(encoding='utf8'))
                if item.get('thumbnail_single'):safe_svg(self.file_path(folder,item['thumbnail_single']).read_text(encoding='utf8'))
        return manifest
    @staticmethod
    def file_path(folder,name):
        if not isinstance(name,str) or '\\' in name or ':' in name or any(p in ('','..','.') for p in name.split('/')):raise DeliveryError('资源文件路径无效')
        path=(folder/name).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():raise DeliveryError('资源文件不存在或越界')
        return path
    def assets(self):
        with self.lock:
            result=dict(getattr(self,'_validation_assets',{}))
            for pid,p in self.installed().items():
                folder=self.root/'packs'/pid/p['version'];manifest=self._json(folder/'manifest.json',{})
                for a in manifest.get('assets',[]):
                    result[a['id']]={**a,'asset_id':a['id'],'_file':str(self.file_path(folder,a['file'])),'domain':p['domain'],
                        'thumbnail':f"/api/resources/file/{pid}/{p['version']}/{a['file']}",'pack_id':pid}
            return result
    def templates(self):
        with self.lock:
            result=[]
            for pid,p in self.installed().items():
                folder=self.root/'packs'/pid/p['version'];manifest=self._json(folder/'manifest.json',{})
                for t in manifest.get('templates',[]):
                    result.append({**t,'_file':str(self.file_path(folder,t['file'])),'pack_id':pid,'domain':p['domain'],
                        'category':p['title'],'library_group':'science','recommended':True,'draft':False,'family':t.get('family','network'),
                        'new_scene_only':True,'example':t['id'],'includes':t.get('includes',[]),'usage':t.get('description',''),
                        'limitations':'用于机制和流程示意；数值与具体实验条件请按研究内容修改。',
                        'thumbnail':f"/api/resources/file/{pid}/{p['version']}/{t['thumbnail']}",
                        'thumbnail_single':f"/api/resources/file/{pid}/{p['version']}/{t.get('thumbnail_single',t['thumbnail'])}"})
            return result
    def template_scene(self,tid,width=None,height=None):
        t=next((t for t in self.templates() if t['id']==tid),None)
        if not t:return None
        from scene_document import normalize_scene
        scene=json.loads(Path(t['_file']).read_text(encoding='utf8'));scene=normalize_scene(scene)
        if width or height:
            scene=reflow_pack_scene(scene,width or scene['canvas']['width_mm'],height or scene['canvas']['height_mm'])
        return scene
    def cancel(self,pid):
        with self.lock:
            if pid in self.cancels:self.cancels[pid].set()
        return self.status()
    def uninstall(self,pid):
        if not ID.fullmatch(pid):raise DeliveryError('资源包标识无效')
        with self.lock:
            if self.tasks.get(pid,{}).get('state') in ('queued','downloading','validating','installing'):raise DeliveryError('请先取消正在进行的下载')
            installed=self.installed();installed.pop(pid,None);_write(self.root/'installed.json',installed);_clear_library();self.tasks.pop(pid,None)
            target=(self.root/'packs'/pid).resolve()
            if not ID.fullmatch(pid) or target.parent!=(self.root/'packs').resolve():raise DeliveryError('资源包路径无效')
            if target.exists():shutil.rmtree(target)
        return self.status()
