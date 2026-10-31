"""Real HTTP integration for editor revision, repair and export workflows."""
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import app_server


@pytest.fixture
def studio(tmp_path,monkeypatch):
    monkeypatch.setattr(app_server,"JOBS",{})
    monkeypatch.setattr(app_server,"DATA_DIR",tmp_path)
    monkeypatch.setattr(app_server,"JOBS_DIR",tmp_path/"studio-jobs")
    monkeypatch.setattr(app_server,"EXPORT_DIR",tmp_path/"exports")
    monkeypatch.setattr(app_server,"CONFIG_PATH",tmp_path/"config.json")
    app_server.save_config({"mode":"auto","default_illustration_mode":"vector"})
    server = app_server.StudioHTTPServer(("127.0.0.1",0),app_server.Handler)
    worker = threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    root = f"http://127.0.0.1:{server.server_address[1]}"

    def request(path,body=None,method=None,headers=None):
        hdr = {"Content-Type":"application/json",**(headers or {})}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(root+path,data=data,headers=hdr,method=method or ("POST" if body is not None else "GET"))
        try:
            with urllib.request.urlopen(req,timeout=15) as response:
                raw = response.read()
                return response.status,json.loads(raw) if "application/json" in response.headers.get("Content-Type","") else raw
        except urllib.error.HTTPError as exc:
            return exc.code,json.loads(exc.read())
    yield request
    server.shutdown()
    server.server_close()
    worker.join(timeout=3)


def example(studio,name="egfr"):
    status,result = studio("/api/scene/example",{"example":name})
    assert status == 200,result
    job_id = result["job_id"]
    for _ in range(100):
        status,job = studio("/api/jobs/"+job_id)
        if job["status"] in ("completed","failed"):
            break
        time.sleep(0.02)
    assert job["status"]=="completed",job
    return job_id


def test_catalog_disciplines_preserve_all_assets_and_category_provenance(studio):
    status,catalog=studio('/api/scene/catalog')
    assert status==200
    domains={d['id']:d for d in catalog['asset_domains']}
    assert domains['biology']['available']
    assert domains['biology']['count']==sum(a['domain']=='biology' for a in catalog['assets'])>668
    assert sum(d['count'] for d in domains.values())==len(catalog['assets'])
    assert any(a['type']=='cell' and a.get('state')=='plant_interphase' for a in catalog['assets'])
    assert not domains['materials']['available'] and domains['materials']['count']==0
    assert all(domains[k]['available'] and domains[k]['count']>0 for k in ('chemistry','engineering','computing-math'))
    assert all(a['domain'] in domains and a['category_id'] for a in catalog['assets'])
    artwork=[a for a in catalog['assets'] if a.get('asset_id')]
    assert len({a['asset_id'] for a in artwork})==len(artwork)>1500
    equipment=[a for a in artwork if 'pipette' in a['asset_id'] or 'microscope' in a['asset_id']]
    assert equipment and all(a['category']=='实验器材与流程' for a in equipment)


def test_template_preview_is_non_mutating_then_can_be_applied_and_undone(studio):
    job_id=example(studio,'jak_stat');endpoint=f'/api/jobs/{job_id}/scene'
    _,initial=studio(endpoint)
    code,candidate=studio('/api/scene/preview-template',{'job_id':job_id,'base_revision':1,'template':'signal_nucleus'})
    assert code==200,candidate
    assert candidate['scene']['style']['template']=='signal_nucleus'
    _,still=studio(endpoint);assert still['scene']==initial['scene']
    code,applied=studio(endpoint,{'base_revision':1,'operations':[{'op':'replace','scene':candidate['scene']}]},'PATCH')
    assert code==200 and applied['revision']==2
    code,_=studio('/api/scene/preview-template',{'job_id':job_id,'base_revision':1,'template':'signal_relay'})
    assert code==409
    code,undone=studio(endpoint,{'base_revision':2,'operations':[{'op':'replace','scene':initial['scene']}]},'PATCH')
    assert code==200 and undone['scene']['objects']==initial['scene']['objects']


def test_editor_http_save_conflict_reload_and_revision_pinned_export(studio):
    job_id = example(studio)
    endpoint = f"/api/jobs/{job_id}/scene"
    _,initial = studio(endpoint)
    obj = initial["scene"]["objects"][0]
    status,updated = studio(endpoint,{"base_revision":1,"operations":[{
        "op":"update","id":obj["id"],"changes":{"label":"EGF edited","x":obj["x"]+2}}]},"PATCH")
    assert status==200,updated
    assert updated["revision"]==2
    status,conflict = studio(endpoint,{"base_revision":1,"operations":[{"op":"remove","id":obj["id"]}]},"PATCH")
    assert status==409 and conflict["conflict"]
    _,loaded = studio(endpoint)
    assert loaded["scene"]["objects"][0]["label"]=="EGF edited"
    status,saved = studio(f"/api/jobs/{job_id}/save-as",{"format":"svg","revision":1})
    assert status==200,saved
    svg = Path(saved["path"]).read_text(encoding="utf-8")
    assert "EGF edited" not in svg
    assert saved["revision"]==1
    assert "data-object-id" in svg and "<image" not in svg


def test_repeated_submission_returns_existing_job_without_second_model_call(studio,monkeypatch):
    import scene_planner
    from scene_examples import make_example
    calls=[]
    def plan(*args,**kwargs):
        calls.append(1)
        return make_example('egfr'),{}
    monkeypatch.setattr(scene_planner,'plan_scene',plan)
    body={'scene_engine':'v2','text':'EGF activates EGFR','request_id':'submission-test-123'}
    _,first=studio('/api/generate',body)
    _,second=studio('/api/generate',body)
    assert first['job_id']==second['job_id']
    for _ in range(50):
        if calls:break
        time.sleep(.01)
    assert len(calls)==1


def test_legacy_job_is_readable_and_never_overwritten_by_scene_patch(studio):
    folder = app_server.job_paths("j_legacy_test")
    path = folder/"result.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>legacy</text></svg>')
    app_server.JOBS["j_legacy_test"] = {"id":"j_legacy_test","status":"completed","text":"old description","svg_path":str(path)}
    status,result = studio("/api/jobs/j_legacy_test/scene")
    assert status==409 and result["legacy"]
    status,result = studio("/api/jobs/j_legacy_test/scene",{"base_revision":1,"operations":[]},"PATCH")
    assert status==409
    _,svg = studio("/api/jobs/j_legacy_test/svg")
    assert b"legacy" in svg


def test_scene_patch_is_same_origin_and_physical_text_floor_is_enforced(studio):
    job_id = example(studio)
    endpoint = f"/api/jobs/{job_id}/scene"
    _,scene = studio(endpoint)
    op = {"op":"update","id":scene["scene"]["objects"][0]["id"],"changes":{"font_size_pt":4}}
    status,_ = studio(endpoint,{"base_revision":1,"operations":[op]},"PATCH")
    assert status==400
    status,_ = studio(endpoint,{"base_revision":1,"operations":[op]},"PATCH",headers={"Origin":"https://unrelated.invalid"})
    assert status==403
    _,after = studio(endpoint)
    assert after["revision"]==1


def test_ai_candidate_stays_unapplied_and_unselected_objects_are_unchanged(studio,monkeypatch):
    import scene_planner
    job_id = example(studio)
    endpoint = f"/api/jobs/{job_id}/scene"
    _,initial = studio(endpoint)
    selected = initial["scene"]["objects"][0]["id"]
    monkeypatch.setattr(scene_planner,"_request",lambda *a,**k:({
        "operations":[{"op":"update","id":selected,"changes":{"label":"EGF new"}}],"summary":["改名"]},0))
    status,result = studio(f"/api/jobs/{job_id}/revise",{"base_revision":1,"target_ids":[selected],"instruction":"改为 EGF new"})
    assert status==200,result
    _,still = studio(endpoint)
    assert still["revision"]==1
    status,applied = studio(endpoint,{"base_revision":1,"operations":result["candidate"]["operations"]},"PATCH")
    assert status==200
    assert applied["scene"]["objects"][1:]==initial["scene"]["objects"][1:]


def test_ai_failure_preserves_original_scene(studio,monkeypatch):
    import scene_planner
    job_id = example(studio)
    endpoint = f"/api/jobs/{job_id}/scene"
    _,initial = studio(endpoint)
    monkeypatch.setattr(scene_planner,"_request",lambda *a,**k:(_ for _ in ()).throw(RuntimeError("provider unavailable")))
    status,_ = studio(f"/api/jobs/{job_id}/revise",{"base_revision":1,"target_ids":[initial["scene"]["objects"][0]["id"]],"instruction":"change"})
    assert status==500
    _,after = studio(endpoint)
    assert after["scene"]==initial["scene"]


def test_reopen_and_author_confirmation_belong_to_current_revision(studio):
    job_id = example(studio)
    status,_ = studio(f"/api/jobs/{job_id}/confirm",{"revision":1})
    assert status==200
    _,result = studio(f"/api/jobs/{job_id}/scene")
    assert result["audit"]["author_confirmed"]
    obj = result["scene"]["objects"][0]
    studio(f"/api/jobs/{job_id}/scene",{"base_revision":1,"operations":[{"op":"update","id":obj["id"],"changes":{"label":"new"}}]},"PATCH")
    _,result = studio(f"/api/jobs/{job_id}/scene")
    assert not result["audit"]["author_confirmed"]
    app_server.JOBS.clear()
    app_server._load_jobs()
    _,reopened = studio(f"/api/jobs/{job_id}/scene")
    assert reopened["revision"]==2
    assert reopened["scene"]["objects"][0]["label"]=="new"


def test_excluded_visual_advice_keeps_original_evidence_and_revision(studio):
    job_id=example(studio)
    app_server.JOBS[job_id]['scene_vision']={'status':'completed','revision':1,'raw':'original model answer',
        'findings':[{'message':'check this','evidence':'image observation','status':'unverified'}]}
    status,result=studio(f'/api/jobs/{job_id}/review-finding',{'base_revision':1,'index':0,'reason':'checked against source'})
    assert status==200,result
    finding=result['audit']['vision']['findings'][0]
    assert finding['status']=='dismissed' and finding['evidence']=='image observation'
    assert result['audit']['vision']['raw']=='original model answer'
    assert result['revision']==1


def test_history_can_include_all_imported_jobs_beyond_legacy_limit(studio):
    for i in range(65):
        app_server.JOBS[f'j_history_{i}']={'id':f'j_history_{i}','created':i,'title':str(i),'status':'failed'}
    _,default=studio('/api/jobs');_,expanded=studio('/api/jobs?limit=1000')
    assert len(default['jobs'])==50 and len(expanded['jobs'])==65


def test_local_layout_preview_does_not_save_and_preserves_other_objects(studio):
    job=example(studio);endpoint=f'/api/jobs/{job}/scene';_,initial=studio(endpoint)
    chosen=initial['scene']['objects'][0]['id']
    _,edited=studio(endpoint,{'base_revision':1,'operations':[{'op':'update','id':chosen,'changes':{'x':-4}}]},'PATCH')
    finding=next(f for f in edited['audit']['findings'] if f['code']=='outside-canvas')
    status,preview=studio(f'/api/jobs/{job}/preview-fix',{'base_revision':2,'code':finding['code'],'object_ids':finding['object_ids']})
    assert status==200 and preview['changed'],preview
    _,still=studio(endpoint);assert still['revision']==2 and still['scene']==edited['scene']
    assert preview['scene']['relations']==edited['scene']['relations']
    assert all(a==b for a,b in zip(preview['scene']['objects'],edited['scene']['objects']) if a['id']!=chosen)
    _,applied=studio(endpoint,{'base_revision':2,'operations':preview['operations']},'PATCH')
    assert not any(f['code']=='outside-canvas' and chosen in f['object_ids'] for f in applied['audit']['findings'])
    status,_=studio(f'/api/jobs/{job}/preview-fix',{'base_revision':2,'code':finding['code'],'object_ids':finding['object_ids']})
    assert status==409


def test_scientific_advice_is_not_automatically_rewritten(studio):
    job=example(studio);_,initial=studio(f'/api/jobs/{job}/scene')
    relation=initial['scene']['relations'][0]
    studio(f'/api/jobs/{job}/scene',{'base_revision':1,'operations':[{'op':'update_relation','id':relation['id'],'changes':{'uncertain':True}}]},'PATCH')
    status,preview=studio(f'/api/jobs/{job}/preview-fix',{'base_revision':2,'code':'uncertain-relation','object_ids':[relation['id']]})
    assert status==200 and not preview['changed'] and not preview['operations']
    assert next(r for r in preview['scene']['relations'] if r['id']==relation['id'])['uncertain']


def test_intentional_layout_choice_reopens_but_invalidates_on_affected_geometry(studio):
    job=example(studio);endpoint=f'/api/jobs/{job}/scene';_,initial=studio(endpoint)
    a,b=initial['scene']['objects'][:2]
    _,edited=studio(endpoint,{'base_revision':1,'operations':[{'op':'update','id':b['id'],'changes':{'x':a['x'],'y':a['y'],'w':a['w'],'h':a['h']}}]},'PATCH')
    f=next(f for f in edited['audit']['findings'] if f['code']=='overlap' and set(f['object_ids'])=={a['id'],b['id']})
    status,result=studio(f'/api/jobs/{job}/layout-decision',{'base_revision':2,'code':f['code'],'object_ids':f['object_ids']})
    assert status==200 and result['revision']==2
    assert next(x for x in result['audit']['findings'] if x['code']=='overlap' and x['object_ids']==f['object_ids'])['status']=='acknowledged'
    app_server.JOBS.clear();app_server._load_jobs();_,reopened=studio(endpoint)
    assert next(x for x in reopened['audit']['findings'] if x['code']=='overlap' and x['object_ids']==f['object_ids'])['status']=='acknowledged'
    _,unrelated=studio(endpoint,{'base_revision':2,'operations':[{'op':'update','id':initial['scene']['objects'][2]['id'],'changes':{'label':'Unrelated renamed'}}]},'PATCH')
    assert next(x for x in unrelated['audit']['findings'] if x['code']=='overlap' and x['object_ids']==f['object_ids'])['status']=='acknowledged'
    _,moved=studio(endpoint,{'base_revision':3,'operations':[{'op':'update','id':b['id'],'changes':{'x':b['x']+.2}}]},'PATCH')
    assert all(x.get('status')!='acknowledged' for x in moved['audit']['findings'])
    assert studio(f'/api/jobs/{job}/layout-decision',{'base_revision':2,'code':f['code'],'object_ids':f['object_ids']})[0]==409
