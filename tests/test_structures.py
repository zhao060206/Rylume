import pytest
from scene_document import empty_scene,normalize_scene,apply_operations,SceneError
from test_scene_api import studio,example

def structured_scene():
    scene=empty_scene()
    scene['objects']=[{'id':'art','type':'process','label':'','x':5,'y':5,'w':20,'h':20,'asset_id':'import_art','asset_snapshot':{'svg':'<svg viewBox="0 0 20 20"><path d="M0 0H20V20H0Z" fill="#abcdef"/><path d="M5 5H15V15H5Z" fill="#123456"/></svg>','meta':{'asset_id':'import_art'}}}]
    scene['structures']=[{'id':'organelle','label':'完整细胞器','parts':[{'owner':'art','indices':[0,1]}]}]
    return normalize_scene(scene)

def test_structure_is_data_only_and_cannot_overlap_or_reference_missing_objects():
    scene=structured_scene();assert scene['structures'][0]['parts'][0]['indices']==[0,1]
    scene['structures'].append({'id':'duplicate','parts':[{'owner':'art','indices':[1]}]})
    with pytest.raises(SceneError,match='重复'):normalize_scene(scene)
    scene['structures']= [{'id':'bad','parts':[{'owner':'missing','indices':[0]}]}]
    with pytest.raises(SceneError,match='不存在'):normalize_scene(scene)

def test_structure_metadata_and_owner_removal_are_undoable_without_changing_art():
    scene=structured_scene();ungrouped=apply_operations(scene,[{'op':'set_structures','structures':[]}])
    assert ungrouped['objects']==scene['objects'] and not ungrouped['structures']
    restored=apply_operations(ungrouped,[{'op':'set_structures','structures':scene['structures']}])
    assert restored==scene
    deleted=apply_operations(scene,[{'op':'remove','id':'art'}]);assert not deleted['structures']

def test_structure_translation_changes_export_but_never_rewrites_source_paths():
    from scene_render import render_scene
    scene=structured_scene();original=render_scene(scene)
    group={**scene['structures'][0],'dx':8,'dy':-3}
    moved=apply_operations(scene,[{'op':'set_structures','structures':[group]}])
    assert moved['objects']==scene['objects']
    assert render_scene(moved)!=original and '<image' not in render_scene(moved)
    restored=apply_operations(moved,[{'op':'set_structures','structures':scene['structures']}])
    assert render_scene(restored)==original

def test_offset_conversion_respects_nested_parent_and_rotated_object():
    import xml.etree.ElementTree as ET
    from structure_render import offset_svg
    svg='<svg viewBox="0 0 20 20"><g transform="scale(2)"><path d="M1 1H2V2H1Z"/></g></svg>'
    result=offset_svg(svg,20,20,90,((0,6,4),))
    path=next(n for n in ET.fromstring(result).iter() if n.tag.endswith('path'))
    assert path.get('transform').startswith('translate(2 -3)')

def test_structure_membership_survives_real_save_and_reopen(studio):
    job=example(studio);path='/api/jobs/'+job+'/scene';before=studio(path)[1]
    # Use a portable two-path artwork so this checks the same public save route.
    art=structured_scene()['objects'][0]
    code,result=studio(path,{'base_revision':before['revision'],'response':'delta','operations':[{'op':'add','object':art},{'op':'set_structures','structures':structured_scene()['structures']}]},'PATCH')
    assert code==200 and result['scene_delta']['fields']['structures'][0]['label']=='完整细胞器'
    reopened=studio(path)[1];assert reopened['scene']['structures']==structured_scene()['structures']
    assert reopened['scene']['objects'][-1]['asset_snapshot']['svg']==art['asset_snapshot']['svg']


def test_background_and_foreground_roundtrip_and_reject_bad_data():
    scene=structured_scene();g=scene['structures'][0]
    g['background']={'x':4,'y':4,'w':22,'h':22,'colors':['#ffffff']*4}
    g['foreground']=[{'owner':'art','indices':[0]}]
    normalized=normalize_scene(scene)
    assert normalized['structures'][0]==g
    for bad in ({'w':0}, {'colors':['#fff']}, {'colors':['url(secret)']*4}):
        g['background']={**normalized['structures'][0]['background'],**bad}
        with pytest.raises(SceneError):normalize_scene(scene)


def test_composited_export_keeps_original_at_rest_and_moves_complete_vector_group():
    from scene_render import render_scene
    scene=structured_scene();original=render_scene(scene)
    scene['structures'][0]['background']={'x':4,'y':4,'w':22,'h':22,'colors':['#ffffff']*4}
    assert render_scene(scene)==original
    scene['structures'][0].update(dx=8,dy=3)
    svg=render_scene(scene)
    import xml.etree.ElementTree as ET
    root=ET.fromstring(svg)
    group=next(n for n in root.iter() if n.get('data-structure-id')=='organelle')
    assert [float(v) for v in group.get('transform')[10:-1].split()]==[8,3]
    assert len([n for n in group.iter() if n.tag.endswith('path')])==2
    assert not any(n.tag.endswith('image') for n in root.iter())
    assert scene['objects']==structured_scene()['objects']


def test_complete_structure_is_a_native_powerpoint_group(tmp_path):
    from scene_export import export_scene
    from pptx import Presentation
    scene=structured_scene();scene['structures'][0].update(dx=8,dy=3,background={'x':4,'y':4,'w':22,'h':22,'colors':['#ffffff']*4})
    file=tmp_path/'structure.pptx';export_scene(scene,'pptx',file)
    slide=Presentation(file).slides[0]
    group=next(shape for shape in slide.shapes if shape.name=='organelle')
    assert len(group.shapes)==2  # Native paths inside one complete structure.
    import zipfile
    with zipfile.ZipFile(file) as archive:assert not any(n.startswith('ppt/media/') for n in archive.namelist())


def test_delete_structure_keeps_reversible_source_and_removes_exported_members():
    from scene_render import render_scene
    import xml.etree.ElementTree as ET
    scene=structured_scene();scene['structures'][0]['background']={'x':4,'y':4,'w':22,'h':22,'colors':['#ffffff']*4}
    original=render_scene(scene)
    deleted=apply_operations(scene,[{'op':'set_structures','structures':[{**scene['structures'][0],'visible':False}]}])
    assert deleted['objects']==scene['objects']
    assert not [n for n in ET.fromstring(render_scene(deleted)).iter() if n.tag.endswith('path')]
    restored=apply_operations(deleted,[{'op':'set_structures','structures':scene['structures']}])
    assert render_scene(restored)==original


def test_experimental_workflow_uses_sequence_not_transport():
    from scene_examples import make_example
    scene=make_example('workflow',layout=False)
    assert scene['relations'] and {r['type'] for r in scene['relations']}=={'sequence'}
