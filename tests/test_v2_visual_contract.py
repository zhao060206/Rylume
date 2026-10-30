"""Final-size, persisted-layout and native-scientific-symbol regressions."""
import xml.etree.ElementTree as ET
import pytest
from scene_document import SceneRepository, audit_scene, apply_operations
from scene_examples import EXAMPLES,make_example
from scene_render import connection_geometry,render_scene


@pytest.mark.parametrize('example',[e['id'] for e in EXAMPLES])
def test_final_sizes_preserve_vector_objects_and_minimum_text(example):
    for width,height in ((180,120),(90,150)):
        scene=make_example(example,width_mm=width,height_mm=height)
        assert not audit_scene(scene)['findings']
        root=ET.fromstring(render_scene(scene))
        assert not list(root.iter('{http://www.w3.org/2000/svg}image'))
        assert all(float(t.attrib['font-size'])>=7*25.4/72-.00001 for t in root.iter('{http://www.w3.org/2000/svg}text'))


def test_repository_persists_geometry_for_model_topologies_with_compartments(tmp_path):
    scene=make_example('jak_stat',layout=False);scene['layout']='network'
    result=SceneRepository(tmp_path).commit(scene)
    assert not result['audit']['errors']
    assert all('x' in o for o in result['scene']['objects']+result['scene']['compartments'])
    assert SceneRepository(tmp_path).read()==result['scene']


def test_routing_does_not_cross_unrelated_molecule_and_follows_move():
    scene=make_example('tgf_smad')
    edge=next(r for r in scene['relations'] if r['source']=='smad23' and r['target']=='smad_complex')
    g=connection_geometry(scene,edge);o=next(o for o in scene['objects'] if o['id']=='smad4')
    for i in range(1,40):
        t=i/40;u=1-t
        x=u*u*g['x1']+2*u*t*g['control']['x']+t*t*g['x2']
        y=u*u*g['y1']+2*u*t*g['control']['y']+t*t*g['y2']
        assert not (o['x']<x<o['x']+o['w'] and o['y']<y<o['y']+o['h'])
    changed=apply_operations(scene,[{'op':'update','id':'smad_complex','changes':{'x':135}}])
    assert connection_geometry(changed,edge)['x2']!=g['x2']


def test_active_does_not_imply_unprovided_phosphorylation():
    root=ET.fromstring(render_scene(make_example('egfr')))
    molecule=next(n for n in root.iter() if n.attrib.get('data-object-id')=='pi3k')
    assert not any(n.text=='P' for n in molecule.iter())
    akt=next(n for n in root.iter() if n.attrib.get('data-object-id')=='akt')
    assert any(n.text=='P' for n in akt.iter())
