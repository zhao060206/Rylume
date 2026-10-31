"""Annotation image calls are author-scoped and candidates never mutate HEAD."""
import base64,copy,io,json,threading
import pytest
from PIL import Image,ImageDraw
import annotation_redraw as redraw
import annotation_planner as planner
import figure_assets
from scene_document import SceneError
from test_annotation_planner import scene

CONFIG={'text':{'base_url':'http://127.0.0.1:1/v1','model':'text-test'},'image':{'base_url':'http://127.0.0.1:1/v1','model':'image-test'}}

def test_popup_consent_only_authorizes_the_named_objects():
    s=scene();n={'id':'n1','shape':'whole','instruction':'让这张图的插画更高级','image_generation':'allow','image_target_ids':['a']}
    n=planner.normalize_notes(s,[n])[0];scopes={'n1':planner.resolve_note_targets(s,n)}
    allowed,pending=redraw.resolve_requests(s,[n],scopes,[{'object_id':'a','note_ids':['n1'],'instruction':'细化 A'}])
    assert len(allowed)==1 and not pending
    other=next(o['id'] for o in s['objects'] if o['id']!='a' and redraw.eligible(o))
    allowed,pending=redraw.resolve_requests(s,[n],scopes,[{'object_id':other,'note_ids':['n1'],'instruction':'细化其他主体'}])
    assert not allowed and len(pending)==1,'A new planner round cannot expand a one-object popup approval'

def note(text='重绘 A 的插画，增加清晰的内部纹理，文字和箭头不改',**kw):
    return {'id':'n1','shape':'rect','x':9,'y':9,'w':22,'h':14,'instruction':text,**kw}
def request(instruction='细化单个 A 蛋白的内部纹理，保留原身份与状态'):
    return {'object_id':'a','note_ids':['n1'],'instruction':instruction}
def png():
    out=io.BytesIO();image=Image.new('RGB',(96,64),'white');ImageDraw.Draw(image).ellipse((15,12,80,50),fill='#6d889e');image.save(out,format='PNG');return out.getvalue()
def mock_planner(monkeypatch, *, proposal=None, vision=False):
    proposal=proposal or {'operations':[],'redraw_requests':[request()],'summary':['细化 A 插画']}
    messages=[]
    def model(config,turns,**kw):
        body=json.loads(turns[-1]['content']);messages.append(body)
        if 'before' in body:
            return {'checks':[{'note_id':'n1','status':'verified','message':'对照已完成','evidence':'该对象插画哈希已变化，文字及其他对象未变化'}],'unexpected_changes':False},0
        return copy.deepcopy(proposal),0
    monkeypatch.setattr(planner.scene_planner,'_request',model)
    if vision:
        result={'checks':[{'note_id':'n1','status':'verified','message':'图像细节符合要求','evidence':'已对照原对象、候选及批注，纹理更清晰，其余文字与连线相同'}],'unexpected_changes':False}
        monkeypatch.setattr(planner.pipeline,'_post_json',lambda *a,**k:{'choices':[{'message':{'content':json.dumps(result)}}]})
    return messages


@pytest.mark.parametrize('text',[
    '不要调用生图模型，只改文字', '不需要重绘，调整字号', 'do not redraw the image',
    '只改标签 A 为 A1', '图片不动，只调整连线', 'no need to redraw anything'])
def test_explicit_prohibition_wins_even_with_allow_control(text):
    assert redraw.intent(note(text,image_generation='allow'),scene()['objects'])=='deny'


@pytest.mark.parametrize('text',['重绘这个蛋白的插画','调用生图模型重新画 A','让这个蛋白具有更逼真的内部纹理'])
def test_explicit_or_strong_visual_intent_can_allow(text):
    assert redraw.intent(note(text),scene()['objects'])=='allow'


def test_generic_polish_and_model_enhancement_cannot_authorize_image():
    assert redraw.intent(note('把这一处优化得更漂亮'),scene()['objects'])=='ask'
    assert redraw.intent(note('请调用生图模型重绘A',original_instruction='让A更漂亮'),scene()['objects'])=='ask'
    assert redraw.intent(note('重绘箭头和方框'),scene()['objects'])=='ask'


def test_scope_locked_repeated_ids_and_denial_reject_before_image_call():
    s=scene();n=planner.normalize_notes(s,[note()]);scopes={'n1':['a']}
    with pytest.raises(SceneError):redraw.resolve_requests(s,n,scopes,[{**request(),'object_id':'b'}])
    with pytest.raises(SceneError):redraw.resolve_requests(s,n,scopes,[request(),request()])
    s['objects'][0]['locked']=True
    with pytest.raises(SceneError):redraw.resolve_requests(s,n,scopes,[request()])
    s=scene();n=planner.normalize_notes(s,[note(image_generation='deny')])
    with pytest.raises(SceneError):redraw.resolve_requests(s,n,scopes,[request()])


def test_ambiguous_request_returns_permission_candidate_without_image_calls(monkeypatch):
    mock_planner(monkeypatch)
    calls=[];monkeypatch.setattr(figure_assets,'referenced_image',lambda *a,**k:calls.append(1))
    original=scene();result=planner.propose_annotations(original,[note('这一处更高级一点')],CONFIG)
    assert result['pending_image_requests'][0]['object_id']=='a'
    assert not result['can_apply'] and not calls
    assert result['preview_scene']==original


def test_explicit_redraw_uses_current_object_pixels_and_preserves_editable_layers(monkeypatch):
    messages=mock_planner(monkeypatch);calls=[]
    def image(prompt,config,reference):
        calls.append((prompt,reference));return png()
    monkeypatch.setattr(figure_assets,'referenced_image',image)
    original=scene();snapshot=copy.deepcopy(original)
    result=planner.propose_annotations(original,[note()],CONFIG)
    assert len(calls)==1 and calls[0][1].startswith('data:image/png;base64,')
    assert 'ONE isolated' in calls[0][0] and 'Author request' in calls[0][0]
    assert result['manual_visual_review_allowed'] and not result['can_apply']
    assert result['checks'][0]['reason_code']=='image_requires_visual_review'
    after=result['preview_scene'];assert after['relations']==original['relations']
    for a,b in zip(after['objects'],original['objects']):
        a=copy.deepcopy(a);a.pop('illustration',None);assert a==b
    assert after['objects'][0]['illustration'] and original==snapshot
    assert 'base64,' not in json.dumps(messages)
    assert result['image_results'][0]['sha256']==after['objects'][0]['illustration']['sha256']


def test_vision_review_can_verify_the_redraw(monkeypatch):
    mock_planner(monkeypatch,vision=True);monkeypatch.setattr(figure_assets,'referenced_image',lambda *a,**k:png())
    config=copy.deepcopy(CONFIG);config['vision']={'base_url':'http://127.0.0.1:1/v1','model':'vision-test'}
    result=planner.propose_annotations(scene(),[note()],config)
    assert result['can_apply'] and result['verification']['mode']=='vision_and_structure'


def test_model_image_patch_is_rejected_and_service_failure_keeps_original(monkeypatch):
    asset=figure_assets.image_asset(png());bad={'operations':[{'op':'update','id':'a','changes':{'illustration':asset}}]}
    mock_planner(monkeypatch,proposal=bad);calls=[];monkeypatch.setattr(figure_assets,'referenced_image',lambda *a,**k:calls.append(1))
    s=scene();result=planner.propose_annotations(s,[note()],CONFIG)
    assert not result['can_apply'] and result['preview_scene']==s and not calls
    mock_planner(monkeypatch)
    def offline(*a,**k):calls.append(1);raise RuntimeError('local image service offline')
    monkeypatch.setattr(figure_assets,'referenced_image',offline)
    result=planner.propose_annotations(s,[note()],CONFIG)
    assert len(calls)==1 and not result['can_apply'] and result['preview_scene']==s
    assert 'offline' in result['image_error']


def test_cancel_discards_a_late_image(monkeypatch):
    mock_planner(monkeypatch);event=threading.Event()
    def late(*a,**k):event.set();return png()
    monkeypatch.setattr(figure_assets,'referenced_image',late)
    original=scene();snapshot=copy.deepcopy(original)
    with pytest.raises(InterruptedError):planner.propose_annotations(original,[note()],CONFIG,cancelled=event.is_set)
    assert original==snapshot


def test_illustration_patch_requires_exact_server_provenance():
    s=scene();n=planner.normalize_notes(s,[note()]);asset=figure_assets.image_asset(png())
    operations=[{'op':'update','id':'a','changes':{'illustration':asset}}]
    with pytest.raises(SceneError):planner.validate_candidate_operations(s,n,operations)
    with pytest.raises(SceneError):planner.validate_candidate_operations(s,n,operations,image_authorizations={'a':'wrong'})
    assert planner.validate_candidate_operations(s,n,operations,image_authorizations={'a':asset['sha256']})['objects'][0]['illustration']
