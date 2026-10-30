"""Persistent figure annotations and isolated AI candidate jobs.

An AI run never moves HEAD. Apply and rollback publish new immutable revisions.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs
from scene_document import SceneError, RevisionConflict
from studio_storage import _atomic_json, recover_pending_replacements

_SESSION=uuid.uuid4().hex
_ACTIVE={}
_ACTIVE_LOCK=threading.RLock()
_ACTIONS='annotations|annotation-enhance|annotation-runs|annotation-cancel|annotation-apply|annotation-rollback'


def _read(path,default):
    recover_pending_replacements(path.parent,recursive=False)
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else copy.deepcopy(default)


def _notes(repo):
    return _read(repo.root/'figure-annotations.json',{'annotation_revision':0,'notes':[]})


def _run_path(repo,run_id):
    if not isinstance(run_id,str) or not re.fullmatch(r'a_[a-f0-9]{16}',run_id):raise SceneError('批注任务标识无效')
    return repo.root/'annotation-runs'/(run_id+'.json')


def _run(repo,run_id):
    path=_run_path(repo,run_id)
    if not path.exists():raise FileNotFoundError('批注任务不存在')
    run=_read(path,{})
    # Reconcile an interrupted apply/rollback after HEAD was committed. The
    # original revision remains available even if the process stopped before
    # the run's metadata was written.
    for pending_key,published_key in (('pending_apply','applied_revision'),('pending_rollback','rollback_revision')):
        pending=run.get(pending_key)
        if pending:
            head=repo.read()
            if head['revision']>=pending['revision']:
                published=repo.read(pending['revision'])
                if _scene_digest(published)==pending['scene_digest']:run[published_key]=pending['revision']
            run.pop(pending_key,None);_atomic_json(path,run)
    if run.get('status') in ('queued','running') and run.get('session')!=_SESSION:
        run.update(status='interrupted',message='上次修改因程序退出而中断。原图与批注已保留，可重新提交。',finished_at=time.time())
        _atomic_json(path,run)
    return run


def _scene_digest(scene):
    snapshot=copy.deepcopy(scene);snapshot['revision']=0
    return hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def _public_run(run,full=False):
    fields=('id','status','stage','message','created_at','finished_at','base_revision','annotation_revision',
            'applied_revision','rollback_revision','round','max_rounds','error')
    result={k:copy.deepcopy(run[k]) for k in fields if k in run}
    if full:
        result.update({k:copy.deepcopy(run[k]) for k in ('notes','candidate','before_svg') if k in run})
    elif run.get('candidate'):
        result['checks']=copy.deepcopy(run['candidate'].get('checks',[]))
    return result


def _runs(repo,limit=40):
    folder=repo.root/'annotation-runs'
    paths=sorted(folder.glob('a_*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if limit is not None:paths=paths[:limit]
    return [_run(repo,p.stem) for p in paths]


def _recovery(repo,runs=None):
    records=runs if runs is not None else _runs(repo,limit=None)
    applied=[r for r in records if r.get('applied_revision') and not r.get('rollback_revision')]
    if not applied:return None
    latest=max(applied,key=lambda r:r['applied_revision'])
    return {'run_id':latest['id'],'before_revision':latest['base_revision'],
            'applied_revision':latest['applied_revision'],'can_rollback':True}


def _document(repo):
    notes=_notes(repo);runs=_runs(repo)
    return {'ok':True,**notes,'runs':[_public_run(r) for r in runs],'recovery':_recovery(repo)}


def _revision(body,key='base_revision',zero=False):
    value=body.get(key)
    if isinstance(value,bool) or not isinstance(value,int) or value<(0 if zero else 1):raise SceneError('请提供有效的'+key)
    return value


def _start(app,job,repo,body):
    from annotation_planner import normalize_notes, propose_annotations
    from scene_service import queues
    from scene_render import render_scene
    request_id=str(body.get('request_id') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,100}',request_id):raise SceneError('请提供有效的重复提交标识')
    with repo.lock:
        scene=repo.read();notes_doc=_notes(repo)
        base=_revision(body);note_revision=_revision(body,'annotation_revision',zero=True)
        if base!=scene['revision']:raise RevisionConflict('图版已变化，请先保存最新图版再提交批注')
        if note_revision!=notes_doc['annotation_revision']:raise RevisionConflict('批注已变化，请先保存最新批注')
        notes=normalize_notes(scene,notes_doc['notes'])
        if not notes:raise SceneError('请先添加至少一条批注')
        fingerprint=hashlib.sha256(json.dumps([base,note_revision,notes],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        prior=_runs(repo,limit=None)
        for old in prior:
            if old.get('request_id')==request_id:
                if old.get('fingerprint')!=fingerprint:raise RevisionConflict('相同提交标识不能用于不同批注')
                return _public_run(old,True)
        if any(r['status'] in ('queued','running') for r in prior):raise RevisionConflict('这张图已有批注修改任务，请先等待或取消')
        run_id='a_'+uuid.uuid4().hex[:16];path=_run_path(repo,run_id)
        run={'id':run_id,'status':'queued','stage':'queued','message':'已排队；当前图版保持原样',
             'created_at':time.time(),'base_revision':base,'annotation_revision':note_revision,'notes':notes,
             'request_id':request_id,'fingerprint':fingerprint,'session':_SESSION,'max_rounds':3,'round':0,
             'before_svg':render_scene(scene)}
        _atomic_json(path,run)
        cancelled=threading.Event();key=(str(repo.root),run_id)
        with _ACTIVE_LOCK:_ACTIVE[key]={'cancelled':cancelled}
        config=copy.deepcopy(app.load_config())
        def progress(*args,**kwargs):
            event=args[0] if args and isinstance(args[0],dict) else kwargs
            if args and isinstance(args[0],str):event={**event,'stage':args[0],'message':str(args[1]) if len(args)>1 else ''}
            with repo.lock:
                current=_run(repo,run_id)
                if cancelled.is_set() or current['status']=='cancelled':raise InterruptedError('批注修改已取消')
                current.update(status='running',**{k:v for k,v in event.items() if k in ('stage','message','round','max_rounds')})
                _atomic_json(path,current)
        def worker():
            try:
                if cancelled.is_set():raise InterruptedError('已取消')
                progress(stage='planning',message='正在逐项理解批注并规划修改')
                candidate=propose_annotations(copy.deepcopy(scene),copy.deepcopy(notes),config,
                    on_progress=progress,cancelled=cancelled.is_set,max_rounds=3)
                with repo.lock:
                    current=_run(repo,run_id)
                    if cancelled.is_set() or current['status']=='cancelled':raise InterruptedError('已取消')
                    current.update(status='completed',stage='completed',message='候选已生成，请对比并查看每处核验结果',
                                   candidate=candidate,finished_at=time.time(),round=candidate.get('rounds',1))
                    _atomic_json(path,current)
            except InterruptedError:
                with repo.lock:
                    current=_run(repo,run_id);current.update(status='cancelled',stage='cancelled',message='已取消；原图与批注均保留',finished_at=time.time());_atomic_json(path,current)
            except Exception as exc:
                with repo.lock:
                    current=_run(repo,run_id)
                    if current['status']!='cancelled':
                        current.update(status='failed',stage='failed',error=app._friendly_error(exc),message='修改未完成，原图与批注均保留',finished_at=time.time());_atomic_json(path,current)
            finally:
                with _ACTIVE_LOCK:_ACTIVE.pop(key,None)
        future=queues().submit_generation(worker)
        with _ACTIVE_LOCK:
            if key in _ACTIVE:_ACTIVE[key]['future']=future
        return _public_run(run,True)


def dispatch(handler,method,path,app):
    match=re.fullmatch(r'/api/jobs/([A-Za-z0-9_-]+)/('+_ACTIONS+r')',path)
    if not match:return False
    from scene_service import repository, _is_scene, _publish, payload
    try:
        job_id,action=match.groups();job=app.JOBS.get(job_id)
        if not job:handler._json(404,{'ok':False,'error':'图版不存在'});return True
        if not _is_scene(job) or not job.get('scene_revision'):
            raise SceneError('此图尚无可编辑场景，请先创建可编辑副本再批注')
        repo=repository(app,job_id);body=handler._body() if method in ('POST','PUT','PATCH') else {}
        if action=='annotations':
            with repo.lock:
                if method in ('PUT','PATCH'):
                    from annotation_planner import normalize_notes
                    doc=_notes(repo)
                    if _revision(body,'base_annotation_revision',zero=True)!=doc['annotation_revision']:raise RevisionConflict('批注已被其他操作更新，本地文字已保留，请重新载入后合并')
                    notes=normalize_notes(repo.read(),body.get('notes'),draft=True)
                    # An identical save is idempotent and does not stale an existing candidate.
                    if notes!=doc['notes']:
                        doc={'annotation_revision':doc['annotation_revision']+1,'notes':notes,'scene_revision':repo.read()['revision'],'updated_at':time.time()}
                        _atomic_json(repo.root/'figure-annotations.json',doc)
                elif method!='GET':raise SceneError('不支持的批注操作')
                result=_document(repo)
            handler._json(200,result);return True
        if action=='annotation-enhance' and method=='POST':
            from annotation_planner import enhance_annotation_instruction
            instruction=str(body.get('instruction') or '').strip()
            if not instruction or len(instruction)>2000:raise SceneError('请输入 1–2000 字的批注要求')
            result=enhance_annotation_instruction(instruction,app.load_config());handler._json(200,{'ok':True,**result});return True
        if action=='annotation-runs':
            if method=='POST':run=_start(app,job,repo,body)
            elif method=='GET':
                query=parse_qs(handler.path.split('?',1)[1] if '?' in handler.path else '')
                run_id=(query.get('run_id') or [''])[0]
                with repo.lock:
                    if not run_id:handler._json(200,{'ok':True,'runs':[_public_run(r) for r in _runs(repo)]});return True
                    run=_public_run(_run(repo,run_id),True)
            else:raise SceneError('不支持的任务操作')
            handler._json(200,{'ok':True,'run':run});return True
        if action=='annotation-cancel' and method=='POST':
            with repo.lock:
                run_id=body.get('run_id');run=_run(repo,run_id)
                if run['status'] in ('queued','running'):
                    key=(str(repo.root),run_id)
                    with _ACTIVE_LOCK:
                        active=_ACTIVE.get(key)
                        if active:
                            active['cancelled'].set()
                            if active.get('future') and active['future'].cancel():_ACTIVE.pop(key,None)
                    run.update(status='cancelled',stage='cancelled',message='已取消；当前模型请求结束后停止，候选不会应用',finished_at=time.time())
                    _atomic_json(_run_path(repo,run_id),run)
            handler._json(200,{'ok':True,'run':_public_run(run,True)});return True
        if action=='annotation-apply' and method=='POST':
            with repo.lock:
                current=repo.read();run=_run(repo,body.get('run_id'))
                if _revision(body)!=current['revision'] or run['base_revision']!=current['revision']:raise RevisionConflict('图版已变化，请保留当前版本并重新生成候选')
                if _notes(repo)['annotation_revision']!=run['annotation_revision']:raise RevisionConflict('批注要求已变化，请按最新批注重新生成')
                candidate=run.get('candidate') or {}
                if run['status']!='completed' or not candidate.get('can_apply') or not candidate.get('operations') or run.get('applied_revision'):raise SceneError('这个候选尚不能应用，请查看核验结果或重新生成')
                # Revalidate the stored operation list rather than trusting a client scene.
                from annotation_planner import validate_candidate_operations
                proposed=validate_candidate_operations(current,run['notes'],candidate['operations'])
                run['pending_apply']={'revision':current['revision']+1,'scene_digest':_scene_digest(proposed)}
                _atomic_json(_run_path(repo,run['id']),run)
                result=repo.commit(proposed,current['revision']);_publish(app,job,result)
                run.pop('pending_apply',None);run.update(applied_revision=result['revision'],applied_at=time.time());_atomic_json(_run_path(repo,run['id']),run)
                handler._json(200,{'ok':True,**result,'recovery':_recovery(repo)})
            return True
        if action=='annotation-rollback' and method=='POST':
            with repo.lock:
                current=repo.read()
                if _revision(body)!=current['revision']:raise RevisionConflict('图版已变化，请刷新后再恢复')
                recovery=_recovery(repo);run_id=body.get('run_id') or (recovery or {}).get('run_id')
                run=_run(repo,run_id)
                if not run.get('applied_revision') or run.get('rollback_revision'):raise SceneError('此修改没有可恢复的原版本')
                original=repo.read(run['base_revision'])
                run['pending_rollback']={'revision':current['revision']+1,'scene_digest':_scene_digest(original)}
                _atomic_json(_run_path(repo,run['id']),run)
                result=repo.commit(original,current['revision']);_publish(app,job,result)
                run.pop('pending_rollback',None);run.update(rollback_revision=result['revision'],rollback_at=time.time());_atomic_json(_run_path(repo,run['id']),run)
                handler._json(200,{'ok':True,**result,'recovery':_recovery(repo)})
            return True
        handler._json(405,{'ok':False,'error':'不支持的操作'})
    except RevisionConflict as exc:handler._json(409,{'ok':False,'conflict':True,'error':str(exc)})
    except FileNotFoundError:handler._json(404,{'ok':False,'error':'批注任务或场景版本不存在'})
    except (SceneError,ValueError,TypeError,KeyError,IndexError) as exc:handler._json(400,{'ok':False,'error':str(exc)[:500]})
    except Exception as exc:handler._json(500,{'ok':False,'error':app._friendly_error(exc)})
    return True
