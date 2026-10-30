"""User-facing library contracts: trusted art, attribution and native export."""
import copy
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest

from scene_document import normalize_scene, empty_scene, SceneError, audit_scene
from scene_export import export_scene
from scene_templates import TEMPLATES, make_template, apply_template
from scientific_library import library, glyph


def test_every_vendored_asset_is_offline_flat_vector_and_has_provenance():
    assert len(library()) >= 60
    for aid,asset in library().items():
        assert asset['author'] and asset['license_url'] and asset['source_url'] and asset['sha256']
        root=ET.fromstring('<svg>'+glyph(aid)+'</svg>')
        assert all(n.tag.split('}')[-1] in ('svg','g','path') for n in root.iter())
        assert not any('url(' in v or 'javascript:' in v for n in root.iter() for v in n.attrib.values())


@pytest.mark.parametrize('template',TEMPLATES,ids=lambda t:t['id'])
def test_templates_preserve_science_and_fit_both_physical_sizes(template):
    from scene_examples import make_example
    for width,height in ((180,120),(90,150)):
        source=make_example(template['example'],width_mm=width,height_mm=height)
        scene=apply_template(source,template['id'])
        assert [(o['id'],o['label'],o['entity_id'],o['state']) for o in source['objects']]==[(o['id'],o['label'],o['entity_id'],o['state']) for o in scene['objects']]
        assert source['relations']==scene['relations']
        assert scene['requirements']==source['requirements']
        assert not audit_scene(scene)['errors']
        assert all(o['font_size_pt']>=7 for o in scene['objects'])


def test_unknown_asset_cannot_load_arbitrary_file_or_svg():
    scene=empty_scene();scene['objects']=[dict(id='p',type='protein',label='P',asset_id='../../config.json')]
    with pytest.raises(SceneError,match='未知科研素材'):normalize_scene(scene)


def test_artwork_does_not_replace_mechanistic_glyphs_with_different_entities():
    # A seven-helix GPCR is not an EGFR RTK; an antibody is not a cytokine.
    for template in TEMPLATES:
        scene=make_template(template['id'])
        for o in scene['objects']:
            if o['id'] in ('egfr','cytokine','pip2','pip3','stat_dimer','nuclear_stat','library','analysis'):
                assert not o.get('asset_id'),(template['id'],o['id'])
    old=empty_scene();old['style'].pop('glyph_tint')
    assert normalize_scene(old)['style']['glyph_tint']==.8


def test_art_survives_all_four_exports_with_editable_paths_and_credits(tmp_path):
    scene=empty_scene();asset=library()['bio_macrophage']
    scene['objects']=[dict(id='macrophage',type='immune_cell',label='Macrophage',asset_id=asset['asset_id'],x=20,y=20,w=28,h=25)]
    scene=normalize_scene(scene)
    for fmt in ('svg','pdf','png','pptx'):
        result=export_scene(scene,fmt,tmp_path/('art.'+fmt))
        assert result['raster_objects']==[]
        assert result['artwork_credits'][0]['asset_id']=='bio_macrophage'
        assert 'Servier' in Path(result['credits_path']).read_text(encoding='utf8')
    svg=(tmp_path/'art.svg').read_text(encoding='utf8')
    assert '<image' not in svg and 'Servier' in svg
    with zipfile.ZipFile(tmp_path/'art.pptx') as z:
        assert not any(n.startswith('ppt/media/') for n in z.namelist())
        slide=z.read('ppt/slides/slide1.xml').decode()
        assert 'name="macrophage"' in slide and 'custGeom' in slide and 'Macrophage' in slide
