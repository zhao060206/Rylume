import copy,json,threading,time
import pytest
from test_scene_api import studio,example
import annotation_planner,annotation_service,app_server
from scene_document import apply_operations
from scene_render import render_scene

def note(s):
    o=s['objects'][0];return dict(id='n1',shape='rect',x=max(0,o['x']-1),y=max(0,o['y']-1),w=o['w']+2,h=o['h']+2,instruction='将标签改为 Edited')
def prepare(studio):
    job=example(studio);base=f'/api/jobs/{job}';_,data=studio(base+'/scene');n=note(data['scene']);code,doc=studio(base+'/annotations',{'base_annotation_revision':0,'notes':[n]},'PUT');assert code==200,doc;return job,base,data,n
def fake_plan(scene,notes,config,**kw):
    operations=[dict(op='update',id=scene['objects'][0]['id'],changes={'label':'Edited'})];draft=apply_operations(scene,operations)
    return dict(base_revision=scene['revision'],operations=operations,preview_scene=draft,preview_svg=render_scene(draft),summary=['Edited'],checks=[dict(note_id='n1',status='verified',message='label updated',evidence='label differs')],rounds=1,can_apply=True,verification={'mode':'structure_and_text'})
def start(studio,base):
    code,res=studio(base+'/annotation-runs',dict(base_revision=1,annotation_revision=1,request_id='request_12345678'));assert code==200,res;return res['run']['id']
def wait(studio,base,rid):
    for _ in range(200):
        _,res=studio(base+'/annotation-runs?run_id='+rid)
        if res['run']['status'] not in ('queued','running'):return res['run']
        time.sleep(.01)
    raise AssertionError('run did not finish')

def test_notes_save_conflict_restart_and_origin(studio):
    job,base,data,n=prepare(studio);_,loaded=studio(base+'/annotations');assert loaded['notes'][0]['instruction']==n['instruction']
    code,_=studio(base+'/annotations',dict(base_annotation_revision=0,notes=[]),'PUT');assert code==409
    code,_=studio(base+'/annotations',dict(base_annotation_revision=1,notes=[]),'PUT',headers={'Origin':'https://evil.invalid'});assert code==403
    code,_=studio(base+'/annotations',dict(base_annotation_revision=1,notes=[]),'PUT',headers={'Content-Type':'text/plain'});assert code==415
    app_server.JOBS.clear();app_server._load_jobs();_,loaded=studio(base+'/annotations');assert loaded['annotation_revision']==1
    code,res=studio(base+'/annotations',dict(base_annotation_revision=1,notes=[{**n,'instruction':''}]),'PUT');assert code==200 and res['annotation_revision']==2

def test_candidate_apply_reopen_persistent_rollback_and_idempotency(studio,monkeypatch):
    calls=[]
    def plan(*a,**kw):calls.append(1);return fake_plan(*a,**kw)
    monkeypatch.setattr(annotation_planner,'propose_annotations',plan)
    job,base,data,n=prepare(studio);rid=start(studio,base);run=wait(studio,base,rid)
    assert run['status']=='completed';_,unchanged=studio(base+'/scene');assert unchanged['scene']==data['scene']
    assert start(studio,base)==rid and len(calls)==1
    code,applied=studio(base+'/annotation-apply',dict(run_id=rid,base_revision=1));assert code==200,applied;assert applied['revision']==2
    app_server.JOBS.clear();app_server._load_jobs();_,doc=studio(base+'/annotations');assert doc['recovery']['before_revision']==1
    code,restored=studio(base+'/annotation-rollback',dict(run_id=rid,base_revision=2));assert code==200,restored
    assert restored['revision']==3 and restored['scene']['objects']==data['scene']['objects']
    _,doc=studio(base+'/annotations');assert doc['recovery'] is None
    code,_=studio(base+'/annotation-rollback',dict(run_id=rid,base_revision=3));assert code==400

def test_stale_graph_and_changed_notes_reject_candidate(studio,monkeypatch):
    monkeypatch.setattr(annotation_planner,'propose_annotations',fake_plan)
    _,base,data,n=prepare(studio);rid=start(studio,base);wait(studio,base,rid)
    studio(base+'/annotations',dict(base_annotation_revision=1,notes=[{**n,'instruction':'标签改为 Other'}]),'PUT')
    code,_=studio(base+'/annotation-apply',dict(run_id=rid,base_revision=1));assert code==409
    _,current=studio(base+'/scene');assert current['revision']==1

def test_cancel_running_never_publishes_late_candidate(studio,monkeypatch):
    entered=threading.Event();release=threading.Event()
    def slow(*a,**kw):entered.set();release.wait(3);return fake_plan(*a,**kw)
    monkeypatch.setattr(annotation_planner,'propose_annotations',slow)
    _,base,data,n=prepare(studio);rid=start(studio,base);assert entered.wait(2)
    code,res=studio(base+'/annotation-cancel',{'run_id':rid});assert code==200 and res['run']['status']=='cancelled';release.set();time.sleep(.08)
    _,current=studio(base+'/scene');assert current['revision']==1
    code,_=studio(base+'/annotation-apply',dict(run_id=rid,base_revision=1));assert code==400

def test_failed_model_and_interrupted_run_keep_notes_and_original(studio,monkeypatch):
    monkeypatch.setattr(annotation_planner,'propose_annotations',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('offline')))
    job,base,data,n=prepare(studio);rid=start(studio,base);assert wait(studio,base,rid)['status']=='failed'
    _,current=studio(base+'/scene');assert current['scene']==data['scene'];_,doc=studio(base+'/annotations');assert doc['notes']
    from scene_service import repository
    repo=repository(app_server,job);path=annotation_service._run_path(repo,rid);run=json.loads(path.read_text(encoding="utf8"));run.update(status='running',session='old-session');path.write_text(json.dumps(run))
    _,res=studio(base+'/annotation-runs?run_id='+rid);assert res['run']['status']=='interrupted'


def test_recheck_existing_candidate_uses_no_planning_or_new_images_and_rejects_stale(studio,monkeypatch):
    calls=[]
    def plan(*a,**kw):
        calls.append('planning');result=fake_plan(*a,**kw)
        result.update(can_apply=False,checks=[dict(note_id='n1',status='needs_review',message='模型上下文超限')]);return result
    monkeypatch.setattr(annotation_planner,'propose_annotations',plan)
    monkeypatch.setattr(annotation_planner,'_review',lambda *a,**kw:([dict(note_id='n1',status='verified',message='核对通过',evidence='已比较修改前后文字')],'structure_and_text'))
    _,base,original,n=prepare(studio);rid=start(studio,base);first=wait(studio,base,rid)
    assert not first['candidate']['can_apply']
    code,value=studio(base+'/annotation-runs',dict(base_revision=1,annotation_revision=1,request_id='recheck_12345678',retry_run_id=rid))
    assert code==200,value
    rerun=wait(studio,base,value['run']['id']);assert rerun['candidate']['can_apply'] and calls==['planning']
    _,unchanged=studio(base+'/scene');assert unchanged['scene']==original['scene']
    code,applied=studio(base+'/annotation-apply',dict(run_id=rerun['id'],base_revision=1));assert code==200 and applied['revision']==2
    code,_=studio(base+'/annotation-runs',dict(base_revision=2,annotation_revision=1,request_id='recheck_stale_123',retry_run_id=rid));assert code==409

def test_pending_apply_metadata_recovers_after_commit(studio,monkeypatch):
    monkeypatch.setattr(annotation_planner,'propose_annotations',fake_plan)
    job,base,data,n=prepare(studio);rid=start(studio,base);run=wait(studio,base,rid)
    from scene_service import repository
    repo=repository(app_server,job);draft=apply_operations(data['scene'],run['candidate']['operations']);repo.commit(draft,1)
    path=annotation_service._run_path(repo,rid);stored=json.loads(path.read_text(encoding="utf8"));stored['pending_apply']={'revision':2,'scene_digest':annotation_service._scene_digest(draft)};path.write_text(json.dumps(stored))
    _,doc=studio(base+'/annotations');assert doc['recovery']['applied_revision']==2
