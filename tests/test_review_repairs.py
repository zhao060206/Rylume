import copy
import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from scene_document import empty_scene, normalize_scene, apply_operations, SceneError
from scene_render import layout_scene, render_scene, connection_geometry
from scene_presentation import apply_presentation, locate_callouts


def structural_scene():
    scene=empty_scene();scene['objects']=[dict(id='organelle',type='mitochondrion',label='Organelle'),
        dict(id='part',type='membrane',label='Inner membrane',parent_id='organelle'),
        dict(id='caption',type='text',label='Inner membrane')]
    scene['relations']=[dict(id='pointer',source='caption',target='part',type='associates')]
    return layout_scene(scene)


def test_image_callout_is_an_anchor_not_an_extra_membrane_and_avoids_feedback_route():
    scene=normalize_scene(apply_presentation(structural_scene(),{'illustration_mode':'image'}))
    parent,part,label=scene['objects'];relation=scene['relations'][0]
    assert part['depiction']=='anchor' and not part['label'] and relation['callout']
    assert parent['w']>50 and label['x']>parent['x']+parent['w']
    g=connection_geometry(scene,relation)
    assert g['control']['x']==pytest.approx((g['x1']+g['x2'])/2)
    svg=render_scene(scene);assert svg.index('id="layer-callouts"')>svg.index('id="layer-objects"')


def test_callout_localization_uses_pixels_and_refuses_unseen_parts(monkeypatch):
    import pipeline
    from figure_assets import image_asset
    scene=normalize_scene(apply_presentation(structural_scene(),{'illustration_mode':'image'}))
    im=Image.new('RGB',(200,100),'#88aa99');stream=io.BytesIO();im.save(stream,'PNG')
    scene['objects'][0]['illustration']=image_asset(stream.getvalue())
    def locate(config,messages,**kwargs):
        assert config['text']['model']=='vision-text-fallback'
        assert messages[0]['content'][1]['image_url']['url'].startswith('data:image/png')
        return {'parts':[dict(id='part',x=.7,y=.45,visible=True)]}
    monkeypatch.setattr(pipeline,'chat_json',locate)
    locate_callouts(scene,{'text':{'model':'vision-text-fallback'}})
    assert scene['objects'][1]['x']>scene['objects'][0]['x']+scene['objects'][0]['w']/2
    monkeypatch.setattr(pipeline,'chat_json',lambda *a,**k:{'parts':[dict(id='part',visible=False)]})
    with pytest.raises(SceneError,match='未能可靠定位'):locate_callouts(scene,{})


def test_workflow_preserves_requested_inside_labels_title_and_independent_numbers():
    scene=empty_scene();scene['layout']='process';scene['objects']=[dict(id='step'+str(i),type='process',label=label) for i,label in enumerate(['培养','处理','观察'])]
    scene=layout_scene(scene)
    scene=normalize_scene(apply_presentation(scene,{'generation_brief':'图题、阶段编号（步骤 1–3）和框内名称'}))
    assert scene['style']['show_title'] and all(o['state']=='flow_step' for o in scene['objects'][:3])
    assert [o['label'] for o in scene['objects'][3:]]==['1','2','3']
    moved=apply_operations(scene,[dict(op='update',id='step0',changes={'x':scene['objects'][0]['x']+10})])
    assert moved['objects'][3]['x']==scene['objects'][3]['x']+10


def test_moving_an_imported_inset_reveals_estimated_container_colour_not_white():
    from semantic_vector import reconstruct
    from vector_fidelity import render_pixels
    image=Image.new('RGB',(200,160),'white');d=ImageDraw.Draw(image)
    d.rectangle((10,10,190,150),fill='#bbddee');d.ellipse((55,45,110,100),fill='#557788')
    stream=io.BytesIO();image.save(stream,'PNG')
    regions=[dict(id='cell',kind='structure',label='Cell',polygon=[[.05,.0625],[.95,.0625],[.95,.9375],[.05,.9375]]),
             dict(id='nucleus',kind='structure',label='Nucleus',polygon=[[.275,.28125],[.55,.28125],[.55,.625],[.275,.625]])]
    scene,report=reconstruct(stream.getvalue(),'nested.png',{},regions=regions)
    assert report['estimated_backgrounds']==1
    nucleus=next(o for o in scene['objects'] if o['id']=='nucleus')
    moved=apply_operations(scene,[dict(op='update',id='nucleus',changes={'x':nucleus['x']+60})])
    actual=render_pixels(render_scene(moved),image.size)
    assert np.abs(actual[65,75].astype(float)-[187,221,238]).mean()<15


def test_editable_export_keeps_source_art_and_emits_text_frames(tmp_path):
    import json
    from pptx import Presentation
    from semantic_vector import reconstruct
    from scene_export import export_scene
    image=Image.new('RGB',(160,80),'white');ImageDraw.Draw(image).text((15,25),'Label',fill='black')
    stream=io.BytesIO();image.save(stream,'PNG')
    scene,_=reconstruct(stream.getvalue(),'label.png',{},regions=[dict(id='word',kind='text',label='Label',x=.08,y=.25,w=.37,h=.35)])
    original=copy.deepcopy(scene)
    result=export_scene(scene,'pptx',tmp_path/'editable.pptx',text_mode='editable')
    def texts(shapes):
        for shape in shapes:
            if shape.has_text_frame:yield shape.text
            if hasattr(shape,'shapes'):yield from texts(shape.shapes)
    assert 'Label' in list(texts(Presentation(tmp_path/'editable.pptx').slides[0].shapes))
    assert scene==original and result['text_mode']=='editable' and result['outline_labels']==0


def test_redraw_can_only_relocate_its_own_unlocked_part_anchors():
    from annotation_planner import validate_candidate_operations
    scene=normalize_scene(apply_presentation(structural_scene(),{'illustration_mode':'image'}))
    scene['objects'][0]['x']=10
    note=dict(id='n',shape='whole',instruction='重新绘制主体，保持文字不变',target_ids=['organelle'])
    move=dict(op='update',id='part',changes={'x':40,'y':40})
    with pytest.raises(SceneError,match='超出'):validate_candidate_operations(scene,[note],[move])
    changed=validate_candidate_operations(scene,[note],[move],image_authorizations={'organelle':'server-sha'})
    assert changed['objects'][1]['x']==40
    scene['objects'][1]['locked']=True
    with pytest.raises(SceneError,match='超出'):validate_candidate_operations(scene,[note],[move],image_authorizations={'organelle':'server-sha'})


def test_large_background_hole_has_no_radial_organelle_streaks():
    from semantic_vector import estimate_container_background
    yy,xx=np.mgrid[:120,:160]
    base=np.stack([180+xx*.1,210+xx*.08,230+xx*.05],axis=2).astype(np.uint8)
    hole=(xx-80)**2+(yy-60)**2<26**2
    source=base.copy();source[hole]=[30,70,120]
    source[33:38,65:95]=[30,70,120]
    actual=estimate_container_background(source,hole,np.ones(hole.shape,dtype=bool))
    assert np.abs(actual[hole].astype(float)-base[hole]).mean()<3
    assert np.array_equal(actual[~hole],source[~hole])


def test_model_service_error_does_not_blame_image_service_for_text_failure():
    import app_server,pipeline
    assert '生图' not in app_server._friendly_error(RuntimeError('HTTP 503 Service Unavailable'))
    assert '生图' in app_server._friendly_error(pipeline.ImageServiceError('HTTP 503'))


def test_imported_text_inside_structure_follows_it_without_grouping_external_caption():
    from semantic_vector import reconstruct
    image=Image.new('RGB',(200,160),'white');d=ImageDraw.Draw(image);d.rectangle((10,10,140,130),fill='#bbddee');d.text((40,50),'Inside',fill='black');d.text((150,30),'Out',fill='black')
    stream=io.BytesIO();image.save(stream,'PNG')
    regions=[dict(id='cell',kind='structure',label='Cell',polygon=[[.05,.0625],[.7,.0625],[.7,.8125],[.05,.8125]]),dict(id='caption',kind='text',label='Inside',x=.18,y=.25,w=.3,h=.2),dict(id='outside',kind='text',label='Out',x=.75,y=.1,w=.24,h=.25)]
    scene,_=reconstruct(stream.getvalue(),'captions.png',{},regions=regions)
    caption=next(o for o in scene['objects'] if o['id']=='caption');outside=next(o for o in scene['objects'] if o['id']=='outside')
    assert caption['parent_id']=='cell' and 'parent_id' not in outside
    moved=apply_operations(scene,[dict(op='update',id='cell',changes={'x':20})]);assert next(o for o in moved['objects'] if o['id']=='caption')['x']>caption['x']


def test_connection_test_uses_text_when_visual_model_name_is_empty(monkeypatch):
    import app_server
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def open_request(request,**kwargs):
        import json
        assert json.loads(request.data)['model']=='usable-text'
        return Response()
    monkeypatch.setattr(app_server.urllib.request,'urlopen',open_request)
    result=app_server.test_target({'vision':{'base_url':'http://unused','model':''},'text':{'base_url':'http://test','model':'usable-text'}},'vision')
    assert result['ok'] and result['message']=='复用文本模型，连接正常'


def test_quoted_figure_title_is_exact_and_negative_title_request_is_respected():
    scene=empty_scene();scene['style']['show_title']=False
    actual=apply_presentation(copy.deepcopy(scene),{'generation_brief':'标题为“线粒体结构示意”。不要添加通路。'})
    assert not actual['style']['show_title'] and actual['title']=='线粒体结构示意'
    assert any(o['type']=='text' and o['label']==actual['title'] for o in actual['objects'])
    assert not apply_presentation(scene,{'generation_brief':'不要添加标题'})['style']['show_title']


def test_callout_generic_words_are_not_drawn_and_an_editable_title_is_not_duplicated():
    scene=structural_scene();scene['title']='线粒体结构示意';scene['objects'].append(dict(id='title_text',type='text',label=scene['title']))
    scene['relations'][0]['label']='指示线'
    result=apply_presentation(scene,{'illustration_mode':'image','generation_brief':'标题为“线粒体结构示意”'})
    assert result['relations'][0]['label']==''
    assert result['objects'][2]['w']<40
    assert not result['style']['show_title'] and result['objects'][-1]['y']==2


def test_wide_illustration_keeps_physical_aspect_ratio_for_callout_geometry():
    from figure_assets import image_asset
    from vector_fidelity import render_pixels
    image=Image.new('RGB',(200,100),'#cc2244');buf=io.BytesIO();image.save(buf,'PNG')
    scene=empty_scene(width_mm=100,height_mm=100);scene['style']['show_title']=False
    scene['objects']=[dict(id='wide',type='organelle',label='',display_name='Wide illustration',x=10,y=10,w=80,h=60,illustration=image_asset(buf.getvalue()))]
    pixels=render_pixels(render_scene(scene),(1000,1000));mask=(pixels[:,:,0]>150)&(pixels[:,:,1]<80);ys,xs=np.where(mask)
    assert xs.max()-xs.min()+1==pytest.approx(800,abs=2)
    assert ys.max()-ys.min()+1==pytest.approx(400,abs=2)


def test_discipline_narrow_layouts_use_real_millimetres_and_clear_groups():
    from scene_flows import make_flow
    from scene_document import audit_scene
    scene=make_flow('flow_reaction_screen',width_mm=90,height_mm=150)
    steps={o['id']:o for o in scene['objects']}
    assert steps['step0']['x']+steps['step0']['w']/2==45
    assert steps['step0']['y']+steps['step0']['h']/2==12
    assert steps['step1']['x']+steps['step1']['w']<steps['step2']['x']
    assert audit_scene(scene)['errors']==0
    decision=make_flow('flow_sensor_calibration',width_mm=90,height_mm=150)
    assert decision['relations'][-1]['source_port']=='w'
    assert decision['relations'][-1]['control']['x']<3


def test_reference_analysis_failure_preserves_actionable_reason(monkeypatch,tmp_path):
    import figure_references
    image=Image.new('RGB',(60,60),'white');buf=io.BytesIO();image.save(buf,'PNG')
    monkeypatch.setattr(figure_references,'analyze',lambda *a:(_ for _ in ()).throw(RuntimeError('HTTP 429 busy')))
    result=figure_references.create(tmp_path,'data:image/png;base64,'+__import__('base64').b64encode(buf.getvalue()).decode(),{})
    assert result['analysis_status']=='unavailable'
    assert '原图已保留' in result['analysis_message'] and '429' in result['analysis_message']


def test_annotation_service_failures_are_concise_and_do_not_echo_provider_json(monkeypatch):
    import annotation_planner
    original=empty_scene();original['objects']=[dict(id='obj',type='process',label='A',x=1,y=1,w=10,h=10)]
    notes=[dict(id='n',shape='whole',instruction='将 A 改为 B',target_ids=['obj'])]
    monkeypatch.setattr(annotation_planner.scene_planner,'_request',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('HTTP 429: {"error":"provider detail"}')))
    result=annotation_planner.propose_annotations(original,notes,{},max_rounds=1)
    assert result['can_apply'] is False
    assert 'provider detail' not in result['verification']['attempts'][0]['error']
    assert '429' in result['verification']['attempts'][0]['error']
