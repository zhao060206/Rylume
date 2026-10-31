"""Image permission, candidate apply and rollback through the actual HTTP API."""
import copy,json,time
import pytest
import app_server,annotation_service,annotation_planner,figure_assets
from test_scene_api import studio,example
from test_annotation_redraw import png


def setup(studio,monkeypatch,text='重绘此处的插画，其他对象和标签不变'):
    job=example(studio);base='/api/jobs/'+job;_,doc=studio(base+'/scene')
    target=next(o for o in doc['scene']['objects'] if o.get('role')=='entity' and o['type'] not in ('text','membrane','nuclear_pore'))
    note={'id':'n1','shape':'rect','x':max(0,target['x']-1),'y':max(0,target['y']-1),'w':target['w']+2,'h':target['h']+2,
          'target_ids':[target['id']],'instruction':text}
    code,value=studio(base+'/annotations',{'base_annotation_revision':0,'notes':[note]},'PUT');assert code==200,value
    app_server.save_config({'text':{'base_url':'http://127.0.0.1:1/v1','model':'text-test'},'image':{'base_url':'http://127.0.0.1:1/v1','model':'image-test'}})
    def model(config,messages,**kw):
        body=json.loads(messages[-1]['content'])
        if 'before' in body:return {'checks':[{'note_id':'n1','status':'verified','message':'可编辑结构符合要求','evidence':'对象身份、标签、位置和连接与原图一致'}],'unexpected_changes':False},0
        return {'operations':[],'redraw_requests':[{'object_id':target['id'],'note_ids':['n1'],'instruction':'细化当前单个主体，保留科学身份与状态'}],'summary':['重绘局部插画']},0
    monkeypatch.setattr(annotation_planner.scene_planner,'_request',model)
    calls=[]
    def image(*a,**k):calls.append(1);return png()
    monkeypatch.setattr(figure_assets,'referenced_image',image)
    return base,doc,target,calls


def start(studio,base,revision=1,request_id='redraw_request_001'):
    code,value=studio(base+'/annotation-runs',{'base_revision':1,'annotation_revision':revision,'request_id':request_id});assert code==200,value
    run=value['run'];identity=run['id']
    for _ in range(200):
        _,value=studio(base+'/annotation-runs?run_id='+identity);run=value['run']
        if run['status'] not in ('queued','running'):return run
        time.sleep(.02)
    raise AssertionError('Redraw timed out')


def test_image_candidate_needs_author_visual_review_and_rollback_keeps_original(studio,monkeypatch):
    base,original,target,calls=setup(studio,monkeypatch);run=start(studio,base)
    assert run['status']=='completed' and len(calls)==1
    candidate=run['candidate'];assert candidate['manual_visual_review_allowed'] and not candidate['can_apply']
    _,unchanged=studio(base+'/scene');assert unchanged['scene']==original['scene']
    code,_=studio(base+'/annotation-apply',{'run_id':run['id'],'base_revision':1});assert code==400
    code,saved=studio(base+'/annotation-apply',{'run_id':run['id'],'base_revision':1,'author_visual_confirmed':True});assert code==200,saved
    before={o['id']:o for o in original['scene']['objects']}
    for obj in saved['scene']['objects']:
        expected=before[obj['id']];actual=copy.deepcopy(obj)
        if obj['id']==target['id']:assert actual.pop('illustration')
        assert actual==expected
    assert saved['scene']['relations']==original['scene']['relations']
    code,restored=studio(base+'/annotation-rollback',{'run_id':run['id'],'base_revision':2})
    assert code==200 and restored['scene']['objects']==original['scene']['objects']


def test_unclear_intent_requires_saved_permission_and_creates_new_candidate(studio,monkeypatch):
    base,original,target,calls=setup(studio,monkeypatch,'这处能否更漂亮一点')
    run=start(studio,base);assert run['candidate']['pending_image_requests'] and not calls
    code,_=studio(base+'/annotation-apply',{'run_id':run['id'],'base_revision':1,'author_visual_confirmed':True});assert code==400
    _,notes=studio(base+'/annotations');note=notes['notes'][0];note['image_generation']='allow'
    code,saved=studio(base+'/annotations',{'base_annotation_revision':1,'notes':[note]},'PUT');assert code==200
    approved=start(studio,base,revision=saved['annotation_revision'],request_id='redraw_request_002')
    assert approved['candidate']['image_results'] and len(calls)==1
    _,current=studio(base+'/scene');assert current['scene']==original['scene']


def test_author_confirmation_cannot_override_an_unfulfilled_check(studio,monkeypatch):
    base,original,target,calls=setup(studio,monkeypatch)
    original_review=annotation_planner._review
    monkeypatch.setattr(annotation_planner,'_review',lambda *a,**k:([{'note_id':'n1','status':'unfulfilled','message':'缺少要求','evidence':'部分需求未完成'}],'structure_and_text'))
    run=start(studio,base);assert not run['candidate']['manual_visual_review_allowed']
    code,_=studio(base+'/annotation-apply',{'run_id':run['id'],'base_revision':1,'author_visual_confirmed':True});assert code==400
    assert len(calls)==1
