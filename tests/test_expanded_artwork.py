"""The distributed collection must be usable, attributed and truly vector."""
from pathlib import Path
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from resource_packs import safe_svg

ROOT=Path(__file__).resolve().parents[1]

def test_expansion_is_real_safe_attributed_and_not_relabelled_duplicates():
    items=json.loads((ROOT/'assets/bioicons/manifest.json').read_text(encoding='utf8'))
    new=[a for a in items if a['asset_id'].startswith('biox_')]
    assert len(new)>=900
    assert len({a['asset_id'] for a in items})==len(items)
    geometries=set()
    for a in new:
        original=ROOT/'assets/bioicons'/(a['asset_id']+'.original.svg')
        assert hashlib.sha256(original.read_bytes()).hexdigest()==a['sha256']
        assert a['author'] and a['license'] in ('CC BY 3.0','CC BY 4.0','CC0 1.0')
        assert a['source_url'].startswith('https://github.com/duerrsimon/bioicons/blob/d29e766ea7580b8063c4f47b29e872db40a4d979/')
        svg=(ROOT/'ui/library'/(a['asset_id']+'.svg')).read_text(encoding='utf8')
        safe_svg(svg)
        nodes=list(ET.fromstring(svg).iter())
        assert all(n.tag.split('}')[-1] in ('svg','path') for n in nodes)
        identity=''.join(n.get('d','') for n in nodes)
        assert identity not in geometries;geometries.add(identity)

def test_new_disciplines_survive_snapshots_and_four_native_exports(tmp_path):
    from scene_document import empty_scene,normalize_scene
    from scientific_library import library
    from scene_export import export_scene
    chosen={}
    for a in library().values():
        if a['asset_id'].startswith('biox_'):chosen.setdefault(a.get('domain','biology'),a)
    assert {'biology','chemistry','computing-math'}<=set(chosen)
    scene=empty_scene();scene['objects']=[]
    for i,a in enumerate(chosen.values()):
        scene['objects'].append(dict(id='new_'+str(i),type=a['type'],label=a['label'],asset_id=a['asset_id'],x=10+i*26,y=20,w=22,h=22))
    scene=normalize_scene(scene)
    for fmt in ('svg','pdf','png','pptx'):
        result=export_scene(scene,fmt,tmp_path/('expanded.'+fmt))
        assert not result['raster_objects']
        assert len(result['artwork_credits'])==len(chosen)
        assert Path(result['path']).stat().st_size>100
    with zipfile.ZipFile(tmp_path/'expanded.pptx') as archive:
        assert not any(n.startswith('ppt/media/') for n in archive.namelist())
        slide=archive.read('ppt/slides/slide1.xml').decode()
        assert 'custGeom' in slide and 'new_0' in slide
