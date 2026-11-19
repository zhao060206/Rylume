"""Regressions for the observed 4.12.3 user workflows, not mocked renderer output."""
import copy

from scene_document import empty_scene,normalize_scene,audit_scene,apply_operations
from scene_render import layout_scene,connection_geometry,_label_lines
from scene_service import _visual_audit


def parallel_workflow():
    scene=empty_scene();scene['layout']='process'
    # Deliberately interleave notes and reverse the second branch's node order.
    labels={'seed':'同龄幼苗','note_n':'样本量与重复次数待确认','ctrl':'对照组','salt':'盐处理组',
            'salt_culture':'盐处理组培养','ctrl_culture':'对照组培养','note_salt':'盐浓度待确认',
            'measure':'测量株高与叶片数','note_time':'测量时间待确认','summary':'汇总比较'}
    scene['objects']=[dict(id=i,type='text' if i.startswith('note') else 'process',state='' if i.startswith('note') else 'flow_step',label=label) for i,label in labels.items()]
    main=[('seed','ctrl'),('seed','salt'),('ctrl','ctrl_culture'),('salt','salt_culture'),('ctrl_culture','measure'),('salt_culture','measure'),('measure','summary')]
    notes=[('note_n','seed'),('note_salt','salt_culture'),('note_time','measure')]
    scene['relations']=[dict(id='r'+str(i),source=a,target=b,type='sequence' if (a,b) in main else 'associates',uncertain=(a,b) in notes) for i,(a,b) in enumerate(main+notes)]
    return scene


def test_parallel_workflow_keeps_lanes_with_notes_and_join():
    scene=layout_scene(parallel_workflow());objects={o['id']:o for o in scene['objects']}
    assert scene['provenance']['layout_method']=='topology-with-notes'
    assert objects['ctrl']['y']==objects['ctrl_culture']['y']<objects['salt']['y']==objects['salt_culture']['y']
    for r in scene['relations'][:7]:assert objects[r['source']]['x']<objects[r['target']]['x']
    for r in scene['relations'][7:]:
        assert r['callout'] and not r['uncertain']
        assert objects[r['source']]['parent_id']==r['target']
    assert not {f['code'] for f in audit_scene(scene)['findings']}&{'overlap','line-label-overlap','uncertain-relation','label-outside'}
    assert layout_scene(scene)==scene,'Reopening an authored layout does not rearrange it'
    reflow=layout_scene(scene,force=True);reflow_objects={o['id']:o for o in reflow['objects']}
    assert reflow_objects['note_n']['y']>reflow_objects['seed']['y']+reflow_objects['seed']['h']
    moved=apply_operations(scene,[dict(op='update',id='seed',changes={'x':objects['seed']['x']+4})])
    assert next(o for o in moved['objects'] if o['id']=='note_n')['x']==objects['note_n']['x']+4


def imported_pair():
    scene=empty_scene();scene['provenance']['method']='import-semantic-vector'
    scene['objects']=[dict(id='a',type='process',label='',display_name='Membrane',x=20,y=20,w=40,h=30),dict(id='b',type='process',label='',display_name='Protein',x=25,y=25,w=10,h=10)]
    for o in scene['objects']:o['source_region']={k:o[k]/scene['canvas']['width_mm' if k in ('x','w') else 'height_mm'] for k in ('x','y','w','h')}
    return normalize_scene(scene)


def test_source_transparent_bounds_are_separate_but_new_overlap_is_checked():
    scene=imported_pair();audit=audit_scene(scene)
    assert not audit['findings'] and len(audit['source_overlaps'])==1
    moved=apply_operations(scene,[dict(op='update',id='b',changes={'x':28})])
    assert any(f['code']=='overlap' for f in audit_scene(moved)['findings'])
    scene['objects'][0]['x']+=5;scene['objects'][1]['x']+=5
    assert not audit_scene(scene)['findings'],'Moving the pair together preserves its original overlap'


def test_longer_label_grows_once_but_explicit_width_and_newlines_survive():
    scene=empty_scene();scene['objects']=[dict(id='label',type='text',label='外膜',x=20,y=20,w=8,h=3)]
    scene=normalize_scene(scene)
    grown=apply_operations(scene,[dict(op='update',id='label',changes={'label':'线粒体外膜'})])
    assert len(_label_lines(grown['objects'][0])[0])==1
    assert grown['objects'][0]['w']>scene['objects'][0]['w']
    narrow=apply_operations(grown,[dict(op='update',id='label',changes={'w':6})])
    assert any(f['code']=='text-wrap' for f in audit_scene(narrow)['findings'])
    explicit=apply_operations(scene,[dict(op='update',id='label',changes={'label':'外膜\n内膜','w':12})])
    assert explicit['objects'][0]['w']==12 and _label_lines(explicit['objects'][0])[0]==['外膜','内膜']
    scene['objects'].append(dict(id='target',type='protein',label='P',x=45,y=20,w=12,h=10))
    scene['relations']=[dict(id='line',source='label',target='target',type='associates',callout=True,source_port='e')]
    scene=normalize_scene(scene)
    grown=apply_operations(scene,[dict(op='update',id='label',changes={'label':'线粒体外膜'})])
    label=grown['objects'][0]
    assert label['x']+label['w']==28,'Left callout grows away from its target, preserving the connected edge'


def test_visual_history_is_preserved_without_claiming_current_verification():
    old={'status':'completed','revision':1,'findings':[{'message':'核对复合物'}],'raw':'original opinion'}
    job={'scene_vision':old}
    current,history=_visual_audit(job,2)
    assert current['status']=='not_requested' and current['findings']==[]
    assert history==[old] and job['scene_vision']==old
    job.update(scene_vision={'status':'running','revision':2,'findings':[]},scene_vision_history=[old])
    current,history=_visual_audit(job,2)
    assert current['status']=='running' and history==[old]


def test_callout_ends_at_exact_anchor_center_and_dot_is_exported():
    from scene_render import render_scene
    scene=empty_scene();scene['objects']=[dict(id='label',type='text',label='基质',x=100,y=40,w=15,h=3),dict(id='point',type='protein',label='',display_name='基质',depiction='anchor',x=60,y=40,w=.5,h=.5)]
    scene['relations']=[dict(id='leader',type='associates',callout=True,source='label',target='point')]
    scene=normalize_scene(scene);g=connection_geometry(scene,scene['relations'][0])
    assert (g['x2'],g['y2'])==(60.25,40.25)
    assert 'cx="60.2500" cy="40.2500" r=".7"' in render_scene(scene)


def test_verification_can_correct_initial_callout_coordinates(monkeypatch):
    import pipeline,io
    from PIL import Image
    from figure_assets import image_asset
    from scene_presentation import apply_presentation,locate_callouts
    scene=empty_scene();scene['objects']=[dict(id='body',type='mitochondrion',label='线粒体'),dict(id='part',type='membrane',label='内膜',parent_id='body'),dict(id='label',type='text',label='内膜')]
    scene['relations']=[dict(id='line',source='label',target='part',type='associates')]
    scene=normalize_scene(apply_presentation(layout_scene(scene),{'illustration_mode':'image'}))
    stream=io.BytesIO();Image.new('RGB',(200,100),'#88aa99').save(stream,'PNG');scene['objects'][0]['illustration']=image_asset(stream.getvalue())
    calls=[]
    def respond(*args,**kwargs):
        calls.append(args)
        return {'parts':[dict(id='part',x=.2 if len(calls)==1 else .75,y=.4,visible=True,evidence='膜的可见双层边缘')]}
    monkeypatch.setattr(pipeline,'chat_json',respond)
    result=normalize_scene(locate_callouts(scene,{}));part=result['objects'][1]
    assert len(calls)==2 and part['localization']['x']==.75 and part['localization']['evidence']=='膜的可见双层边缘'
    assert part['edit_status']=='needs_review','Model checks never impersonate author confirmation'


def test_callout_snaps_only_tiny_whitespace_errors_to_visible_pixels():
    from PIL import Image,ImageDraw
    from scene_presentation import visible_pixel_point
    im=Image.new('RGBA',(200,100),(255,255,255,0));ImageDraw.Draw(im).rectangle((40,30,160,70),fill='#224488')
    assert visible_pixel_point(im,.5,.29)[1]>=.30
    assert visible_pixel_point(im,.5,.05) is None
