"""Per-user storage, resumable namespaced import, instance lock and work queues."""
from __future__ import annotations
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_MIGRATION_LOCK=threading.RLock()
_REPLACE_LOCK=threading.RLock()


def _recover_journal(journal):
    """A complete, fsynced journal rolls forward an interrupted replacement."""
    import base64
    try:
        record=json.loads(journal.read_text(encoding='utf8'))
        name=record['name']
        if not isinstance(name,str) or Path(name).name!=name or '/' in name or '\\' in name or name in ('.','..'):
            raise ValueError('Invalid replacement journal target')
        data=base64.b64decode(record['data'],validate=True)
        if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('Incomplete replacement journal')
    except (ValueError,KeyError,TypeError):
        # An incomplete journal was never eligible to overwrite the original.
        return False
    target=journal.parent/name
    with open(_long_path(target),'wb') as handle:
        handle.write(data);handle.flush();os.fsync(handle.fileno())
    if hashlib.sha256(target.read_bytes()).hexdigest()!=record['sha256']:
        raise OSError('Replacement verification failed; recovery journal retained')
    journal.unlink()
    return True


def recover_pending_replacements(root,recursive=True):
    root=Path(root)
    with _REPLACE_LOCK:
        journals=root.rglob('.cfs-replace-*.journal') if recursive else root.glob('.cfs-replace-*.journal')
        for journal in sorted(journals):_recover_journal(journal)


def durable_replace(source,destination):
    """Atomic rename normally; durable recovery on Windows volumes refusing it.

    Some encrypted/redirected Windows directories reject even same-directory
    rename with ERROR_NOT_SAME_DEVICE. Never delete the old file as a workaround.
    A complete journal is synced before writing, verified, then removed. Startup
    recovery and the app's existing writer locks protect this compatibility path.
    """
    import base64
    source,destination=Path(source),Path(destination)
    with _REPLACE_LOCK:
        recover_pending_replacements(destination.parent,recursive=False)
        try:
            for attempt in range(6):
                try:
                    os.replace(_long_path(source),_long_path(destination));return
                except OSError as exc:
                    # Antivirus/indexing and short-lived readers on Windows
                    # can briefly deny a same-directory atomic rename. Keep
                    # both files and retry; never delete the saved original.
                    if getattr(exc,'winerror',None) not in (5,32,33) or attempt==5:raise
                    time.sleep(.02*2**attempt)
        except OSError as exc:
            if getattr(exc,'winerror',None)!=17 and exc.errno!=getattr(__import__('errno'),'EXDEV'):
                raise
        data=source.read_bytes()
        journal=destination.with_name('.cfs-replace-'+str(time.time_ns())+'-'+uuid.uuid4().hex[:8]+'.journal')
        record={'name':destination.name,'data':base64.b64encode(data).decode('ascii'),
                'sha256':hashlib.sha256(data).hexdigest()}
        with open(_long_path(journal),'x',encoding='utf8') as handle:
            json.dump(record,handle);handle.flush();os.fsync(handle.fileno())
        _recover_journal(journal)
        source.unlink(missing_ok=True)


def _discard_stage(stage,parent):
    stage,parent=Path(stage).resolve(),Path(parent).resolve()
    if stage.parent!=parent or not stage.name.startswith('.') or not stage.name.endswith('.import'):
        raise ValueError('Unsafe staging cleanup path')
    if stage.is_dir():shutil.rmtree(stage)
    else:stage.unlink(missing_ok=True)


def get_data_dir(override=None):
    value=override or os.environ.get('CELLFIGURE_DATA_DIR') or os.environ.get('CELL_FIGURE_STUDIO_DATA_DIR')
    path=Path(value) if value else Path(os.environ['LOCALAPPDATA'])/'CellFigureStudio' if os.environ.get('LOCALAPPDATA') else Path.home()/'.cellfigurestudio'
    path=path.expanduser().resolve()
    # Windows can redirect AppData to a long packaged-host directory. The
    # extended form keeps nested immutable backups below Win32 path limits.
    if sys.platform=='win32' and len(str(path))>120:path=Path(_long_path(path))
    path.mkdir(parents=True,exist_ok=True)
    return path


class InstanceLock:
    def __init__(self,path):self.path=Path(path);self.file=None
    def acquire(self):
        if self.file:return self
        self.path.parent.mkdir(parents=True,exist_ok=True)
        handle=self.path.open('a+b')
        try:
            if self.path.stat().st_size==0:handle.write(b' ');handle.flush()
            handle.seek(0)
            if sys.platform=='win32':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            handle.seek(0);handle.truncate();handle.write(str(os.getpid()).encode('ascii'));handle.flush()
        except OSError as exc:
            handle.close();raise RuntimeError('此数据目录已由另一个 Cell Figure Studio 实例打开') from exc
        self.file=handle;return self
    def release(self):
        handle,self.file=self.file,None
        if not handle:return
        try:
            handle.seek(0)
            if sys.platform=='win32':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        finally:handle.close()
    close=release
    def __enter__(self):return self.acquire()
    def __exit__(self,*args):self.release()


def acquire_instance_lock(data_dir):return InstanceLock(Path(data_dir)/'instance.lock').acquire()


def _atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with open(_long_path(temporary),'w',encoding='utf-8') as handle:
            json.dump(value,handle,ensure_ascii=False,indent=2);handle.flush();os.fsync(handle.fileno())
        durable_replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def _snapshot(source,destination):
    """Publish a complete copy only; an existing original backup is immutable."""
    source,destination=Path(source),Path(destination)
    if destination.exists():return
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=destination.with_name('.stage-'+uuid.uuid4().hex[:12]+'.import')
    try:
        if source.is_dir():shutil.copytree(_long_path(source),_long_path(stage))
        else:shutil.copy2(_long_path(source),_long_path(stage))
        os.replace(stage,destination)
    finally:
        _discard_stage(stage,destination.parent)


def _long_path(path):
    value=str(Path(path).absolute())
    if sys.platform=='win32' and not value.startswith('\\\\?\\'):
        return '\\\\?\\UNC\\'+value[2:] if value.startswith('\\\\') else '\\\\?\\'+value
    return value


def _namespace(source):
    slug=re.sub('[^a-z0-9]+','_',source.name.lower()).strip('_')[:24] or 'source'
    digest=hashlib.sha256(str(source).casefold().encode('utf-8')).hexdigest()[:8]
    return slug+'_'+digest


def _rewrite(value,path_map,id_map,key=''):
    if isinstance(value,dict):return {k:_rewrite(v,path_map,id_map,k) for k,v in value.items()}
    if isinstance(value,list):return [_rewrite(v,path_map,id_map,key) for v in value]
    if not isinstance(value,str):return value
    if key in ('id','job_id','revision_of','parent_id','next_job') and value in id_map:return id_map[value]
    normalized=value.replace('\\','/');folded=normalized.casefold()
    for source,target in path_map:
        prefix=str(source).replace('\\','/').rstrip('/')
        if folded==prefix.casefold() or folded.startswith(prefix.casefold()+'/'):
            suffix=normalized[len(prefix):].lstrip('/')
            return str(target/Path(suffix)) if suffix else str(target)
    for old,new in id_map.items():
        if value.startswith('/api/jobs/'+old+'/'):return value.replace('/api/jobs/'+old+'/', '/api/jobs/'+new+'/',1)
    return value


def prepare_data_dir(data_dir,legacy_dirs=()):
    """Import complete jobs with immutable backups and per-item commit records.

    Failed items and jobs still running in 1.x are retried on later startup.
    Originals are never modified, and imports never overwrite existing jobs.
    """
    target=get_data_dir(data_dir)
    for folder in ('studio-jobs','exports','migration-backups'):(target/folder).mkdir(exist_ok=True)
    manifest_path=target/'migration-manifest.json'
    with _MIGRATION_LOCK:
        manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'version':2,'sources':{},'migrated_sources':[]}
        if manifest.get('version')!=2:
            _snapshot(manifest_path,target/'migration-backups'/'migration-manifest-v1.json')
            manifest={'version':2,'sources':{},'migrated_sources':[]}
        def publish():
            manifest['updated_at']=time.time();_atomic_json(manifest_path,manifest)
        for source in dict.fromkeys(Path(p).expanduser().resolve() for p in legacy_dirs):
            if source==target or not source.is_dir():continue
            namespace=_namespace(source);backup=target/'migration-backups'/namespace
            record=manifest['sources'].setdefault(str(source),{'namespace':namespace,'jobs':{},'exports':{},'errors':[]})
            record['errors']=[]
            source_jobs=source/'studio-jobs'
            job_dirs=sorted(p for p in source_jobs.iterdir() if p.is_dir() and not p.name.startswith('.')) if source_jobs.is_dir() else []
            prefix='legacy_'+namespace+'_'
            def imported_id(name):
                safe=re.sub('[^A-Za-z0-9_-]','_',name);limit=64-len(prefix)
                if safe!=name or len(safe)>limit:safe=safe[:limit-9]+'_'+hashlib.sha256(name.encode()).hexdigest()[:8]
                return prefix+safe
            id_map={p.name:imported_id(p.name) for p in job_dirs}
            if len(set(id_map.values()))!=len(id_map):
                id_map={p.name:'legacy_'+namespace+'_'+hashlib.sha256(p.name.encode()).hexdigest()[:16] for p in job_dirs}
            export_root=target/'exports'/('legacy_'+namespace)
            path_map=[(source_jobs/old,target/'studio-jobs'/new) for old,new in id_map.items()]
            path_map.append((source/'exports',export_root))
            path_map.sort(key=lambda pair:len(str(pair[0])),reverse=True)
            config=source/'config.json'
            if config.is_file():
                try:
                    _snapshot(config,backup/'config.json')
                    if not (target/'config.json').exists():_snapshot(backup/'config.json',target/'config.json')
                except OSError as exc:record['errors'].append('config: '+str(exc))
            source_exports=source/'exports'
            if source_exports.is_dir():
                for item in sorted(source_exports.iterdir()):
                    if item.name.startswith('.') or record['exports'].get(item.name,{}).get('status')=='complete':continue
                    try:
                        _snapshot(item,backup/'exports'/item.name)
                        _snapshot(backup/'exports'/item.name,export_root/item.name)
                        record['exports'][item.name]={'status':'complete','path':str(export_root/item.name)}
                    except OSError as exc:record['exports'][item.name]={'status':'failed','error':str(exc)}
                    publish()
            for folder in job_dirs:
                old=folder.name;new=id_map[old];destination=target/'studio-jobs'/new
                previous=record['jobs'].get(old,{})
                if previous.get('status')=='complete' and destination.is_dir():
                    meta_path=destination/'meta.json'
                    meta=json.loads(meta_path.read_text(encoding='utf-8'));changed=False
                    for key in ('next_job','revision_of'):
                        if meta.get(key) in id_map:meta[key]=id_map[meta[key]];changed=True
                    if changed:_atomic_json(meta_path,meta)
                    continue
                try:
                    meta=json.loads((folder/'meta.json').read_text(encoding='utf-8'))
                    if meta.get('status') in ('queued','processing','running'):
                        record['jobs'][old]={'status':'pending_active','new_id':new};publish();continue
                    original=backup/'studio-jobs'/old
                    _snapshot(folder,original)
                    if destination.exists():
                        marker=destination/'.migration-origin.json'
                        if not marker.is_file() or json.loads(marker.read_text(encoding='utf-8'))!={'source':str(source),'job':old}:
                            raise FileExistsError('目标任务已存在，未覆盖: '+new)
                    else:
                        stage=target/'studio-jobs'/('.stage-'+uuid.uuid4().hex[:12]+'.import')
                        try:
                            shutil.copytree(_long_path(original),_long_path(stage))
                            for path in stage.rglob('*.json'):
                                value=json.loads(path.read_text(encoding='utf-8'))
                                _atomic_json(path,_rewrite(value,path_map,id_map))
                            meta_path=stage/'meta.json';meta=json.loads(meta_path.read_text(encoding='utf-8'))
                            meta.update(id=new,migration={'namespace':namespace,'source':str(source),'original_id':old,'backup':str(original)})
                            _atomic_json(meta_path,meta)
                            _atomic_json(stage/'.migration-origin.json',{'source':str(source),'job':old})
                            os.replace(stage,destination)
                        finally:
                            if stage.exists():_discard_stage(stage,target/'studio-jobs')
                    record['jobs'][old]={'status':'complete','new_id':new,'backup':str(original)}
                except (OSError,ValueError,TypeError) as exc:
                    record['jobs'][old]={'status':'failed','new_id':new,'error':str(exc)}
                publish()
            complete=not record['errors'] and all(x['status']=='complete' for x in record['jobs'].values()) and all(x['status']=='complete' for x in record['exports'].values())
            record['status']='complete' if complete else 'pending'
            if complete and str(source) not in manifest['migrated_sources']:manifest['migrated_sources'].append(str(source))
            publish()
        return copy.deepcopy(manifest)


class WorkQueues:
    def __init__(self,max_gen_workers=1,max_export_workers=1):
        self._gen_pool=ThreadPoolExecutor(max_workers=max_gen_workers,thread_name_prefix='scene-gen')
        self._export_pool=ThreadPoolExecutor(max_workers=max_export_workers,thread_name_prefix='scene-export')
    def submit_generation(self,fn,*args,**kwargs):return self._gen_pool.submit(fn,*args,**kwargs)
    def submit_export(self,fn,*args,**kwargs):return self._export_pool.submit(fn,*args,**kwargs)
    def shutdown(self,wait=False):
        self._gen_pool.shutdown(wait=wait,cancel_futures=True);self._export_pool.shutdown(wait=wait,cancel_futures=True)
    def __enter__(self):return self
    def __exit__(self,*args):self.shutdown(wait=True)
