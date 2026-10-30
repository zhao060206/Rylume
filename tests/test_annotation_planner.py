import copy,json,math
import pytest
import annotation_planner as p
from scene_document import empty_scene,normalize_scene,SceneError

def scene():
    s=empty_scene();s['objects']=[dict(id='a',type='protein',label='A',x=10,y=10,w=20,h=12),dict(id='b',type='protein',label='B',x=70,y=10,w=20,h=12),dict(id='c',type='protein',label='C',x=130,y=70,w=20,h=12)];s['relations']=[dict(id='r',source='a',target='b',type='activates')];return normalize_scene(s)
def notes():return [dict(id='n1',shape='rect',x=8,y=8,w=24,h=18,instruction='将标签改为 A1'),dict(id='n2',shape='ellipse',x=128,y=68,w=25,h=18,instruction='字号改为 10 pt')]
def ops():return [dict(op='update',id='a',changes={'label':'A1'}),dict(op='update',id='c',changes={'font_size_pt':10})]
def review(status='verified'):return {'checks':[dict(note_id=n['id'],status=status,message='已对照',evidence='标签 A → A1；字号 8 → 10') for n in notes()],'unexpected_changes':False}

def test_notes_validate_whole_drafts_numbers_and_immutable_input():
    s=scene();before=copy.deepcopy(s);n=notes();assert len(p.normalize_notes(s,n))==2;assert s==before
    assert p.normalize_notes(s,[dict(id='whole',shape='whole',instruction='放大字号')])[0]['w']==180
    assert p.normalize_notes(s,[{**n[0],'instruction':''}],draft=True)
    with pytest.raises(SceneError):p.normalize_notes(s,[{**n[0],'instruction':''}])
    with pytest.raises(SceneError):p.normalize_notes(s,[{**n[0],'x':math.nan}])
    with pytest.raises(SceneError):p.normalize_notes(s,[{**n[0],'w':500}])
    with pytest.raises(SceneError):p.normalize_notes(s,n*20)
    with pytest.raises(SceneError):p.normalize_notes(s,[{**n[0],'x':110,'y':20,'w':5,'h':5}])

def test_targets_include_crossing_line_without_requiring_its_endpoints():
    s=scene();n=dict(id='x',shape='rect',x=45,y=13,w=5,h=6,instruction='改为抑制线')
    assert p.resolve_note_targets(s,n)==['r']
    s['objects'][0]['locked']=True;assert 'r' not in p.resolve_note_targets(s,n)
    partial=dict(id='x',shape='ellipse',x=27,y=12,w=5,h=5,instruction='颜色')
    s=scene();assert 'a' in p.resolve_note_targets(s,partial)

@pytest.mark.parametrize('operation',[
    dict(op='update',id='b',changes={'fill':'#334455'}),dict(op='remove',id='a'),
    dict(op='update',id='a',changes={'entity_id':'new'}),dict(op='update_relation',id='r',changes={'source':'c'}),
    dict(op='update',id='a',changes={'state':'phosphorylated'}),dict(op='update',id='a',changes={'font_size_pt':4})])
def test_scope_stable_identity_science_and_font_guards(operation):
    with pytest.raises(SceneError):p.validate_candidate_operations(scene(),notes(),[operation])

def test_only_connected_geometry_is_allowed_outside_frame():
    n=notes()[:1];s=scene()
    assert p.validate_candidate_operations(s,n,[dict(op='update_relation',id='r',changes={'control':{'x':50,'y':20}})])
    with pytest.raises(SceneError):p.validate_candidate_operations(s,n,[dict(op='update_relation',id='r',changes={'type':'inhibits'})])

def test_independent_review_multi_note_revision_and_retry(monkeypatch):
    s=scene();original=copy.deepcopy(s);calls=[]
    def request(config,messages,**kw):
        calls.append(json.loads(messages[-1]['content']))
        if len(calls)%2:return {'operations':ops(),'summary':['改字与字号']},0
        return review('unfulfilled' if len(calls)==2 else 'verified'),0
    monkeypatch.setattr(p.scene_planner,'_request',request)
    result=p.propose_annotations(s,notes(),{})
    assert result['can_apply'] and result['rounds']==2 and result['preview_scene']['objects'][0]['label']=='A1'
    assert calls[2]['previous_feedback'] and calls[2]['scene']==original and s==original
    assert result['verification']['mode']=='structure_and_text'

def test_reviewer_missing_evidence_and_no_change_cannot_pass(monkeypatch):
    count=0
    def request(*a,**kw):
        nonlocal count;count+=1
        if count%2:return {'operations':ops()[:1],'summary':['所有完成']},0
        return review(),0
    monkeypatch.setattr(p.scene_planner,'_request',request)
    result=p.propose_annotations(scene(),notes(),{})
    assert not result['can_apply'] and result['rounds']==3
    assert result['checks'][1]['status']=='needs_review'

def test_provider_failure_and_cancellation_keep_original(monkeypatch):
    s=scene();monkeypatch.setattr(p.scene_planner,'_request',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('offline')))
    result=p.propose_annotations(s,notes(),{});assert not result['operations'] and not result['can_apply'] and result['preview_scene']==s
    with pytest.raises(InterruptedError):p.propose_annotations(s,notes(),{},cancelled=lambda:True)

def test_enhancement_requires_equivalence_and_literal_preservation(monkeypatch):
    answers=iter([({'enhanced':'请将标签改为 STAT3，字号保持 8 pt'},0),({'equivalent':True},0)])
    monkeypatch.setattr(p.scene_planner,'_request',lambda *a,**kw:next(answers))
    assert p.enhance_annotation_instruction('标签改为 STAT3，字号 8 pt',{})['enhanced'].startswith('请')
    answers=iter([({'enhanced':'将标签改为 STAT6，字号 10 pt'},0),({'equivalent':True},0)])
    original='标签改为 STAT3，字号 8 pt';assert p.enhance_annotation_instruction(original,{})['enhanced']==original
