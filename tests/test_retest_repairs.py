import copy
import zipfile
import xml.etree.ElementTree as ET

import pytest

from scene_document import empty_scene,normalize_scene,apply_operations
from scene_render import layout_scene,render_scene
from scene_presentation import apply_presentation


def workflow():
    scene=empty_scene();scene['layout']='process'
    scene['objects']=[dict(id='n'+str(i),type='process',label=label) for i,label in enumerate(('样本采集','数据分析','结果验证'),1)]
    scene['relations']=[dict(id='r'+str(i),source='n'+str(i),target='n'+str(i+1),type='sequence') for i in (1,2)]
    return layout_scene(scene)


def test_exact_sketch_request_has_outside_numbers_editable_title_and_requirements():
    scene=workflow()
    config={'generation_brief':'三个等大小方框，标题为“研究流程”，框上方分别用独立数字 1、2、3 标注。所有文字、方框和箭头均可分别编辑。'}
    scene=normalize_scene(apply_presentation(scene,config))
    labels={o['label']:o for o in scene['objects']}
    assert not scene['style']['show_title'] and labels['研究流程']['type']=='text'
    for index in (1,2,3):
        number=labels[str(index)];stage=next(o for o in scene['objects'] if o['id']==number['parent_id'])
        assert number['y']+number['h']<stage['y']
        assert number['id'] in scene['requirements']['objects']
    repeated=normalize_scene(apply_presentation(copy.deepcopy(scene),config))
    assert len(repeated['objects'])==len(scene['objects'])
    from scene_document import audit_scene
    assert not any(f['code']=='containment' for f in audit_scene(scene)['findings'])
    moved=apply_operations(scene,[dict(op='update',id='n1',changes={'x':40})])
    assert next(o for o in moved['objects'] if o['label']=='1')['x']!=labels['1']['x']


def test_no_numbers_when_explicitly_excluded():
    result=apply_presentation(workflow(),{'generation_brief':'不要阶段编号，步骤 1–3 只是原文说明'})
    assert len(result['objects'])==3


def test_preserved_sketch_contract_includes_new_presentation_objects():
    import json
    from figure_generation import apply_constraints
    scene=workflow();text='标题为“研究流程”，框上方用独立数字 1、2、3 标注'
    result=apply_constraints(scene,dict(sketch_scene=scene,original_text=text,generation_brief=text,layout_policy='preserve'))
    expected=json.loads(result['generation_contract']['expected_objects'])
    assert {o['id'] for o in expected}=={o['id'] for o in result['objects']}


def test_branch_rank_layout_is_parallel_and_converges_without_snake():
    scene=empty_scene();scene['layout']='process'
    ids=['seed','random','control','salt','culture','leaves','weight','compare']
    scene['objects']=[dict(id=i,type='process',label=i) for i in ids]
    edges=[('seed','random'),('random','control'),('random','salt'),('control','culture'),('salt','culture'),('culture','leaves'),('culture','weight'),('leaves','compare'),('weight','compare')]
    scene['relations']=[dict(id='r'+str(i),source=a,target=b,type='sequence') for i,(a,b) in enumerate(edges)]
    result=layout_scene(scene);nodes={o['id']:o for o in result['objects']}
    assert nodes['control']['x']==nodes['salt']['x'] and nodes['control']['y']<nodes['salt']['y']
    assert nodes['leaves']['x']==nodes['weight']['x']
    assert nodes['control']['fill']!=nodes['salt']['fill']
    assert all(nodes[a]['x']<nodes[b]['x'] for a,b in edges)
    assert all(8<=o['y'] and o['y']+o['h']<=112 for o in nodes.values())
    assert layout_scene(result)==result, 'Reopening must not rearrange a saved document'


def test_binding_product_is_connected_without_inventing_intermediates():
    from scene_topology import reconcile_binding_products
    scene=empty_scene(source_text='EGF 与 EGFR 结合后激活 PI3K。未提供的中间环节请标记为待确认。')
    scene['objects']=[dict(id=i,type=t,label=label) for i,t,label in [('a','ligand','EGF'),('b','receptor','EGFR'),('ab','complex','EGF–EGFR'),('p','kinase','PI3K')]]
    scene['relations']=[dict(id='binding',source='a',target='b',type='binds',evidence='EGF 与 EGFR 结合'),dict(id='activation',source='ab',target='p',type='activates',evidence='激活 PI3K')]
    scene=reconcile_binding_products(normalize_scene(scene))
    assert {r['source'] for r in scene['relations'] if r['target']=='ab'}=={'a','b'}
    assert len(scene['objects'])==4
    activation=next(r for r in scene['relations'] if r['id']=='activation')
    assert activation['uncertain'] and activation['indirect'] and '待确认' in activation['label']
    assert len(reconcile_binding_products(copy.deepcopy(scene))['relations'])==4


def test_pptx_connections_attach_to_frames_that_move_with_the_object(tmp_path):
    from scene_export import export_scene
    scene=workflow();scene['relations'][0]['source_anchor']={'side':'e','t':.25}
    result=export_scene(scene,'pptx',tmp_path/'workflow.pptx')
    assert result['bound_connections']==2
    ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    with zipfile.ZipFile(tmp_path/'workflow.pptx') as archive:root=ET.fromstring(archive.read('ppt/slides/slide1.xml'))
    for connector in root.findall('.//p:cxnSp',ns):
        for end in ('stCxn','endCxn'):
            bound=connector.find('.//a:'+end,ns);assert bound is not None
            target=next(s for s in root.findall('.//p:sp',ns) if s.find('p:nvSpPr/p:cNvPr',ns).get('id')==bound.get('id'))
            assert target.find('p:nvSpPr/p:cNvPr',ns).get('name').startswith('connection-frame-')
    assert root.findall('.//p:cxnSp/p:spPr/a:prstGeom',ns)
    assert not root.findall('.//p:cxnSp/p:spPr/a:custGeom',ns), 'Office cannot open custom connector geometry'


def test_optimizer_reports_equivalence_reason_without_replacing_original(monkeypatch):
    import pipeline
    monkeypatch.setattr(pipeline,'_chat',lambda *a,**k:'EGF activates AKT.')
    monkeypatch.setattr(pipeline,'chat_json',lambda *a,**k:dict(equivalent=False,reason='将原文 PI3K 替换为 AKT'))
    with pytest.raises(RuntimeError,match='PI3K.*AKT'):
        pipeline.optimize_brief('EGF activates PI3K.',{'text':dict(base_url='test',model='configured')})
