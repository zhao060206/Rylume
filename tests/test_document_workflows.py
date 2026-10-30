import copy
import pytest
from test_scene_api import studio, example
from scene_document import empty_scene, normalize_scene, SceneError
from annotation_planner import normalize_notes, resolve_note_targets, validate_candidate_operations

def test_import_is_independent_and_invalid_import_is_non_mutating(studio):
    job=example(studio,'jak_stat');_,source=studio('/api/jobs/'+job+'/scene')
    code,result=studio('/api/scene/import',{'scene':source['scene']});assert code==200,result
    assert result['job_id']!=job
    _,clone=studio('/api/jobs/'+result['job_id']+'/scene');assert clone['revision']==1 and clone['scene']['objects']==source['scene']['objects']
    _,original=studio('/api/jobs/'+job+'/scene');assert original['scene']==source['scene']
    _,before=studio('/api/jobs');code,_=studio('/api/scene/import',{'scene':{'schema_version':999}});assert code==400
    _,after=studio('/api/jobs');assert after['jobs']==before['jobs']

def test_rename_archive_collection_and_stale_edit(studio):
    job=example(studio);_,source=studio('/api/jobs/'+job+'/scene')
    code,result=studio('/api/jobs/'+job+'/document-info',{'base_revision':1,'title':'我的 EGFR 图版','collection':'论文一','archived':True});assert code==200,result
    _,meta=studio('/api/jobs/'+job);assert meta['title']=='我的 EGFR 图版' and meta['collection']=='论文一' and meta['archived']
    _,current=studio('/api/jobs/'+job+'/scene');assert current['revision']==2 and current['scene']['objects']==source['scene']['objects']
    code,_=studio('/api/jobs/'+job+'/document-info',{'base_revision':1,'title':'过期改名'});assert code==409
    code,_=studio('/api/jobs/'+job+'/document-info',{'base_revision':2,'archived':False});assert code==200

def test_restore_retains_immutable_history_and_checks_base_revision(studio):
    job=example(studio);endpoint='/api/jobs/'+job
    _,source=studio(endpoint+'/scene');oid=source['scene']['objects'][0]['id']
    _,changed=studio(endpoint+'/scene',{'base_revision':1,'operations':[{'op':'update','id':oid,'changes':{'label':'编辑后的名称'}}]},'PATCH')
    code,restored=studio(endpoint+'/restore-revision',{'base_revision':2,'revision':1});assert code==200 and restored['revision']==3
    assert restored['scene']['objects']==source['scene']['objects']
    _,historical=studio(endpoint+'/revisions?revision=2');assert historical['scene']==changed['scene']
    _,listing=studio(endpoint+'/revisions');assert [r['revision'] for r in listing['revisions']]==[3,2,1]
    assert listing['revisions'][0]['label']=='恢复自 r1'
    code,_=studio(endpoint+'/restore-revision',{'base_revision':2,'revision':1});assert code==409

def test_export_preflight_and_preview_do_not_change_head(studio):
    job=example(studio);endpoint='/api/jobs/'+job;_,source=studio(endpoint+'/scene')
    code,info=studio(endpoint+'/export-info');assert code==200 and info['width_mm']==180 and info['width_px']==2126
    assert info['vector'] and info['revision']==1 and info['min_font_pt']>=7
    candidate=copy.deepcopy(source['scene']);candidate['canvas']['height_mm']=135
    code,result=studio('/api/scene/preview',{'scene':candidate});assert code==200 and '<svg' in result['svg']
    _,current=studio(endpoint+'/scene');assert current['scene']==source['scene']

def test_selected_scope_protects_overlapping_unselected_object():
    scene=empty_scene();scene['objects']=[dict(id='a',type='protein',label='A',x=10,y=10,w=20,h=12),dict(id='b',type='protein',label='B',x=15,y=10,w=20,h=12)];scene=normalize_scene(scene)
    notes=[dict(id='selection',shape='whole',instruction='字号改为 10 pt',target_ids=['a'])]
    normalized=normalize_notes(scene,notes);assert resolve_note_targets(scene,normalized[0])==['a']
    with pytest.raises(SceneError,match='范围'):validate_candidate_operations(scene,notes,[dict(op='update',id='b',changes={'font_size_pt':10})])
    result=validate_candidate_operations(scene,notes,[dict(op='update',id='a',changes={'font_size_pt':10})]);assert result['objects'][1]==scene['objects'][1]
    with pytest.raises(SceneError):normalize_notes(scene,[{**notes[0],'target_ids':['missing']}])
