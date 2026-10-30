"""User-level contracts: readable notation, workflow semantics, editable export."""
import json,re,subprocess,zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest
from relation_visuals import RELATION_DEFINITIONS,relation_parts
from scene_document import empty_scene,normalize_scene,apply_operations,audit_scene,SceneRepository
from scene_render import render_scene,connection_geometry
from scene_flows import FLOW_SPECS,make_flow
from scene_export import export_scene

ROOT=Path(__file__).resolve().parents[1]
def notation_scene():
    scene=empty_scene('Relation notation',width_mm=180,height_mm=160)
    for i,definition in enumerate(RELATION_DEFINITIONS):
        for key,x in [('a',20),('b',130)]:scene['objects'].append(dict(id=key+str(i),type='protein',label=key.upper(),x=x,y=8+i*20,w=20,h=9))
        scene['relations'].append(dict(id='r'+str(i),source='a'+str(i),target='b'+str(i),type=definition['id']))
    return normalize_scene(scene)

def test_endpoint_shapes_distinguish_all_biological_meanings_in_monochrome():
    scene=notation_scene();root=ET.fromstring(render_scene(scene));ns={'s':'http://www.w3.org/2000/svg'}
    signatures=[]
    for i,t in enumerate(RELATION_DEFINITIONS):
        g=root.find(f".//s:g[@data-relation-id='r{i}']",ns)
        symbols=[n for n in g if n.get('data-endpoint')]
        if t['id']=='associates':assert not symbols
        elif t['id']=='binds':assert len(symbols)==2 and all(n.tag.endswith('circle') for n in symbols)
        else:assert symbols and symbols[0].get('data-endpoint')==t['symbol']
        signatures.append(tuple((n.tag,n.get('data-endpoint')) for n in symbols))
    assert len(set(signatures))==len(RELATION_DEFINITIONS)

def test_indirectness_uncertainty_and_custom_text_remain_independent():
    scene=notation_scene();scene['style']['relation_labels']=True
    r=scene['relations'][0];r.update(label='Author label',indirect=True,uncertain=True)
    root=ET.fromstring(render_scene(scene));ns={'s':'http://www.w3.org/2000/svg'}
    g=root.find(".//s:g[@data-relation-id='r0']",ns)
    assert g.find("s:path[@data-indirect='true']",ns) is not None
    assert g.find("s:path[@data-endpoint='open-arrow']",ns) is not None
    assert [t.text for t in g.findall('s:text',ns)]==['Author label','?']
    assert 'Inhibition' in render_scene(scene)
    assert scene['relations'][0]['label']=='Author label'

def test_live_and_export_renderers_share_the_same_physical_symbols():
    # Compare actual primitives from both runtimes, including curved/dashed paths.
    js="""const fs=require('fs');const s=fs.readFileSync('ui/canvas-editor.js','utf8');
    (async()=>{const m=await import('data:text/javascript;base64,'+Buffer.from(s).toString('base64'));
    console.log(JSON.stringify({definitions:m.RELATION_DEFINITIONS,parts:m.RELATION_DEFINITIONS.map(t=>m.relationParts(t.id,{x:1,y:2},{x:31,y:25},{x:14,y:3},'#333333',1.2,true))}));})();"""
    data=json.loads(subprocess.check_output(['node','-e',js],cwd=ROOT,text=True,encoding='utf8'))
    assert data['definitions']==RELATION_DEFINITIONS
    for t,actual in zip(RELATION_DEFINITIONS,data['parts']):
        expected=relation_parts(t['id'],(1,2),(31,25),(14,3),'#333333',1.2,True)
        assert len(expected)==len(actual)
        for (tag,attrs),(other,otherattrs) in zip(expected,actual):
            assert tag==other and attrs.keys()==otherattrs.keys()
            for key,value in attrs.items():
                if isinstance(value,(float,int)):assert value==pytest.approx(otherattrs[key])
                elif key=='d':
                    assert re.findall('[MLQZ]',value)==re.findall('[MLQZ]',otherattrs[key])
                    nums=lambda s:[float(v) for v in re.findall(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?',s)]
                    assert nums(value)==pytest.approx(nums(otherattrs[key]))
                else:assert value==otherattrs[key]

@pytest.mark.parametrize('spec',FLOW_SPECS,ids=lambda x:x[0])
def test_workflows_are_editable_graphs_at_both_paper_sizes(spec):
    for w,h in ((180,120),(90,150)):
        scene=make_flow('flow_'+spec[0],width_mm=w,height_mm=h)
        assert not audit_scene(scene)['findings']
        assert all(r['type']=='sequence' and not r['uncertain'] for r in scene['relations'])
        assert all(o['font_size_pt']>=7 for o in scene['objects'])
        r=scene['relations'][0];before=connection_geometry(scene,r)
        source=next(o for o in scene['objects'] if o['id']==r['source'])
        updated=apply_operations(scene,[dict(op='update',id=source['id'],changes=dict(x=source['x']+2,label='Edited'))])
        assert connection_geometry(updated,r)!=before
        assert updated['relations']==scene['relations']

@pytest.mark.parametrize('tid',['quality_gate','bench_compute','screening','reversible_states'])
def test_workflow_and_its_author_edits_survive_reopen_and_four_exports(tmp_path,tid):
    scene=make_flow('flow_'+tid);repo=SceneRepository(tmp_path/tid);result=repo.commit(scene)
    changes=[dict(op='update',id='step0',changes=dict(label='Author edit',fill='#635876'))]
    saved=repo.patch(1,changes);scene=repo.read();assert scene==saved['scene']
    for fmt in ('svg','pdf','png','pptx'):
        result=export_scene(scene,fmt,tmp_path/(tid+'.'+fmt));assert result['revision']==2 and not result['raster_objects']
    with zipfile.ZipFile(tmp_path/(tid+'.pptx')) as z:
        assert not any(p.startswith('ppt/media/') for p in z.namelist())
        assert b'Author edit' in z.read('ppt/slides/slide1.xml')

def test_all_relation_symbols_export_as_editable_pptx_and_readable_text(tmp_path):
    scene=notation_scene();scene['style']['relation_labels']=True
    svg=render_scene(scene);(tmp_path/'notation.svg').write_text(svg,encoding='utf8')
    for fmt in ('svg','pdf','png','pptx'):export_scene(scene,fmt,tmp_path/('notation.'+fmt))
    with zipfile.ZipFile(tmp_path/'notation.pptx') as z:
        assert not any(p.startswith('ppt/media/') for p in z.namelist())
        text=z.read('ppt/slides/slide1.xml').decode()
        assert all(d['english'] in text for d in RELATION_DEFINITIONS)


def test_current_graph_can_be_rearranged_without_replacing_its_content():
    from scene_templates import apply_template
    scene=make_flow('flow_treatment_arms')
    scene['objects'].reverse()  # rank follows the graph, never input-list order
    original=json.loads(json.dumps(scene))
    for tid in ('layout_ranks_lr','layout_ranks_tb','layout_snake','layout_columns','layout_orbit','layout_lanes'):
        arranged=apply_template(scene,tid)
        assert [(o['id'],o['label'],o['state']) for o in arranged['objects']]==[(o['id'],o['label'],o['state']) for o in original['objects']]
        assert arranged['relations']==original['relations']
        assert arranged['requirements']==original['requirements']
        assert not audit_scene(arranged)['errors']
    arranged=apply_template(scene,'layout_ranks_lr');obj={o['id']:o for o in arranged['objects']}
    assert obj['step0']['x']<obj['step1']['x']<obj['step3']['x']<obj['step5']['x']


def test_freeform_state_cannot_invoke_an_unknown_legend_symbol():
    from biology_glyphs import symbol
    assert symbol('process','#334455','legend_author_state')
