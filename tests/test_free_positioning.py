import copy,json,math,subprocess,xml.etree.ElementTree as ET,zipfile
from pathlib import Path
import pytest
from scene_document import empty_scene,normalize_scene,apply_operations,SceneError,SceneRepository
from scene_render import connection_geometry,render_scene
from scene_export import export_scene

def scene():
    s=empty_scene();s['objects']=[dict(id='a',type='protein',label='A',x=10,y=20,w=20,h=12,label_dx=-7.4,label_dy=8.2),dict(id='b',type='protein',label='B',x=100,y=30,w=20,h=12)]
    s['relations']=[dict(id='r',source='a',target='b',type='activates',label='Activation',source_anchor=dict(side='e',t=.17),target_anchor=dict(side='w',t=.23),label_position=dict(x=72,y=80))]
    return normalize_scene(s)

def test_custom_positions_roundtrip_revisions_and_keep_binding(tmp_path):
    repo=SceneRepository(tmp_path);initial=repo.commit(scene());loaded=repo.read()
    assert loaded['relations'][0]['target_anchor']=={'side':'w','t':.23}
    updated=repo.patch(initial['revision'],[dict(op='update',id='b',changes=dict(x=112,y=34,w=40,h=24,rotation=90))])['scene']
    g=connection_geometry(updated,updated['relations'][0]);assert (g['x2'],g['y2'])==pytest.approx((138.48,26))
    assert (g['label_x'],g['label_y'])==(72,80)
    assert updated['objects'][0]['label_dx']==-7.4

@pytest.mark.parametrize('field,value',[('source_anchor',dict(side='auto',t=.3)),('target_anchor',dict(side='e',t=1.01)),('target_anchor',dict(side='n',t=float('nan'))),('target_anchor',dict(side='n',t=True)),('label_position',dict(x=float('inf'),y=2)),('source_anchor',[])])
def test_reject_invalid_custom_positions(field,value):
    s=scene();s['relations'][0][field]=value
    with pytest.raises(SceneError):normalize_scene(s)

def test_frontend_and_export_geometry_match_for_all_rotated_edges():
    samples=[]
    for angle in (0,35,90,180,287):
        for side in ('n','e','s','w'):
            s=scene();s['objects'][0]['rotation']=angle;s['objects'][1]['rotation']=-angle
            s['relations'][0].update(source_anchor=dict(side=side,t=.131),target_anchor=dict(side=side,t=.827));samples.append(s)
    js="""const fs=require('fs');(async()=>{const m=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('ui/canvas-editor.js','utf8')).toString('base64'));let input=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(input.map(s=>m.edgeGeometry(s,s.relations[0]))));})();"""
    actual=json.loads(subprocess.check_output(['node','-e',js],input=json.dumps(samples),text=True,encoding='utf8',cwd=Path(__file__).resolve().parents[1]))
    for s,a in zip(samples,actual):
        b=connection_geometry(s,s['relations'][0]);assert (b['x1'],b['y1'],b['x2'],b['y2'],b['label_x'],b['label_y'])==pytest.approx((a['start']['x'],a['start']['y'],a['end']['x'],a['end']['y'],a['label']['x'],a['label']['y']))

def test_manual_label_and_touching_arrow_tip_survive_all_exports(tmp_path):
    s=scene();ns={'s':'http://www.w3.org/2000/svg'};root=ET.fromstring(render_scene(s))
    text=root.find('.//s:g[@data-relation-id="r"]/s:text',ns);assert (float(text.get('x')),float(text.get('y')))==(72,80)
    path=root.find('.//s:g[@data-relation-id="r"]/s:path[@data-line-body]',ns)
    numbers=[float(n) for n in path.get('d').split() if n not in ('M','Q')];assert numbers[:2]==pytest.approx([30,22.04]);assert numbers[-2:]==pytest.approx([100,32.76])
    for fmt in ('svg','png','pdf','pptx'):assert export_scene(s,fmt,tmp_path/f'custom.{fmt}')['revision']==s['revision']
    with zipfile.ZipFile(tmp_path/'custom.pptx') as z:
        slide=ET.fromstring(z.read('ppt/slides/slide1.xml'));n={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
        shape=next(sp for sp in slide.findall('.//p:sp',n) if sp.find('.//a:t',n) is not None and sp.find('.//a:t',n).text=='Activation')
        offset=shape.find('.//a:xfrm/a:off',n);assert abs(int(offset.get('x'))/36000-72)<15 and abs(int(offset.get('y'))/36000-80)<5
