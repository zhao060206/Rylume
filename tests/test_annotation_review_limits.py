import base64,copy,io,json,random
from PIL import Image
import annotation_planner as planner
import figure_assets
from scene_document import apply_operations
from test_annotation_planner import scene,notes,ops,review


def test_detailed_raster_preview_has_bounded_pixels_and_bytes():
    rng=random.Random(871)
    img=Image.frombytes('RGB',(1400,900),rng.randbytes(1400*900*3))
    buf=io.BytesIO();img.save(buf,format='PNG')
    s=scene();s['objects'][0]['illustration']=figure_assets.image_asset(buf.getvalue())
    for limit in (100_000,35_000):
        url=planner._image(s,planner.normalize_notes(s,notes()),limit)
        assert url.startswith('data:image/jpeg;base64,')
        raw=base64.b64decode(url.split(',',1)[1]);assert len(raw)<=limit
        preview=Image.open(io.BytesIO(raw));assert max(preview.size)<=1400
    assert s['objects'][0]['illustration']['data'].startswith('data:image/png;base64,')


def test_context_overflow_retries_smaller_then_falls_back_to_honest_text_review(monkeypatch):
    s=scene();after=apply_operations(s,ops());requests=[];text_requests=[]
    def vision(url,key,body,**kw):
        requests.append(body)
        raise RuntimeError('HTTP 400: The input token count exceeds the maximum number of tokens allowed 1048576')
    def text(config,messages,**kw):
        text_requests.append(messages);return review(),0
    monkeypatch.setattr(planner.pipeline,'_post_json',vision)
    monkeypatch.setattr(planner.scene_planner,'_request',text)
    checks,mode=planner._review(s,after,planner.normalize_notes(s,notes()),ops(),{'vision':{'base_url':'http://127.0.0.1','model':'fake'},'text':{'model':'fake'}})
    assert mode=='structure_and_text' and all(c['status']=='verified' for c in checks)
    assert len(requests)==2 and len(text_requests)==1
    for req,limit in zip(requests,(100_000,35_000)):
        parts=req['messages'][0]['content'];assert 'base64,' not in parts[0]['text']
        assert all(len(base64.b64decode(p['image_url']['url'].split(',',1)[1]))<=limit for p in parts[1:])
    assert '没有提供图像' in text_requests[0][0]['content']


def test_recheck_preserves_failed_scientific_findings_and_does_not_redraw(monkeypatch):
    s=scene();n=planner.normalize_notes(s,notes());operations=ops();after=apply_operations(s,operations)
    candidate={'base_revision':s['revision'],'operations':operations,'preview_scene':after,'preview_svg':'',
               'checks':[{'note_id':'n1','status':'unfulfilled','message':'缺少要求','evidence':'标签错误'},
                         {'note_id':'n2','status':'needs_review','message':'核验失败'}],
               'can_apply':False,'image_results':[]}
    monkeypatch.setattr(planner,'_review',lambda *a,**k:([dict(note_id=x['id'],status='verified',message='ok',evidence='checked') for x in n],'structure_and_text'))
    monkeypatch.setattr(figure_assets,'referenced_image',lambda *a,**k:(_ for _ in ()).throw(AssertionError('must not redraw')))
    previous=copy.deepcopy(candidate);result=planner.recheck_annotations(s,n,candidate,{})
    assert not result['can_apply'] and result['checks'][0]['status']=='unfulfilled'
    assert result['preview_scene']==after and candidate==previous


def test_model_capacity_error_is_explained_without_raw_provider_response():
    message=planner._review_error(RuntimeError('HTTP 400: The input token count exceeds the maximum number of tokens allowed 1048576'))
    assert '超过模型容量' in message and '重新核验' in message and 'HTTP 400' not in message


def test_visual_result_that_admits_it_cannot_see_pixels_needs_author_confirmation():
    check={'status':'verified','message':'结构已经核对','evidence':'仅对比了结构，无法判断图像纹理'}
    assert planner._requires_image_review(check,'vision_and_structure')
    assert planner._requires_image_review(check,'structure_and_text')
    assert not planner._requires_image_review({'status':'verified','evidence':'已看到纹理变清晰'},'vision_and_structure')


def test_large_context_preserves_scoped_evidence_and_marks_background_summary():
    s=scene()
    for i in range(80):
        o=copy.deepcopy(s['objects'][1]);o.update(id='bg'+str(i),entity_id='bg'+str(i),x=40+i,y=40,evidence='背景证据'*200)
        s['objects'].append(o)
    s['objects'][0]['evidence']='目标的原始证据'
    before=copy.deepcopy(s);n=planner.normalize_notes(s,notes()[:1])
    context=json.loads(planner._review_context(s,s,n,[]))
    assert context['context_note'] and len(json.dumps(context,ensure_ascii=False).encode())<220_000
    assert context['before']['objects'][0]['evidence']=='目标的原始证据'
    assert 'evidence' not in next(o for o in context['before']['objects'] if o['id']=='bg0')
    assert len(context['before']['objects'])==len(s['objects']) and s==before
