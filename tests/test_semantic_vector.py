import copy
import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from scene_document import SceneError, apply_operations, empty_scene, normalize_scene
from scene_render import render_scene
from figure_imports import native_svg
from semantic_vector import partition, reconstruct
from figure_vectorize import fidelity_report


def sample():
    image=Image.new('RGB',(320,180),'white');d=ImageDraw.Draw(image)
    d.ellipse((20,30,110,125),fill='#89b7cd',outline='#253844',width=2)
    d.rectangle((118,45,180,110),fill='#94b5a6')
    d.line((190,80,280,80),fill='#253844',width=4)
    d.polygon(((280,80),(269,72),(269,88)),fill='#253844')
    out=io.BytesIO();image.save(out,'PNG')
    return image,out.getvalue()


def regions():
    return [dict(id='cell',kind='structure',label='Cell',x=.04,y=.12,w=.32,h=.63,polygon=[[.04,.12],[.36,.12],[.36,.75],[.04,.75]]),
            dict(id='golgi',kind='structure',label='Golgi',x=.36,y=.24,w=.21,h=.39,polygon=[[.36,.24],[.57,.24],[.57,.63],[.36,.63]]),
            dict(id='arrow',kind='arrow',label='Arrow',x=.59,y=.38,w=.3,h=.13,polygon=[[.59,.38],[.89,.38],[.89,.51],[.59,.51]])]


def test_neighbour_ownership_and_transparent_move_not_rectangle_patch():
    image,png=sample();items,owner=partition(np.asarray(image),regions())
    assert not np.any(items[0]['mask']&items[1]['mask'])
    assert owner[70,130]==1 and owner[70,70]==0
    scene,report=reconstruct(png,'real-structures.png',{},regions=regions())
    assert not scene['structures'] and report['structures']==3
    assert not any(o.get('illustration') for o in scene['objects'])
    assert fidelity_report(png,render_scene(scene))['foreground_similarity']>=99
    old=copy.deepcopy(scene)
    after=apply_operations(scene,[{'op':'update','id':'cell','changes':{'x':80}}])
    assert next(o for o in after['objects'] if o['id']=='golgi')==next(o for o in old['objects'] if o['id']=='golgi')
    assert not after['structures']
    # The selected cell no longer exists at its original centre; neighbour kept.
    from vector_fidelity import render_pixels
    pixels=render_pixels(render_scene(after),image.size)
    assert pixels[70,70].min()>250 and pixels[70,130].min()<200


def test_v2_upgrade_and_svg_engineering_roundtrip(tmp_path):
    scene=empty_scene();scene['schema_version']=2
    scene['objects']=[dict(id='outer',type='nucleus',label='Nucleus',x=20,y=20,w=70,h=60),
                      dict(id='inner',type='dna',label='DNA',parent_id='outer',x=40,y=40,w=20,h=10)]
    scene=normalize_scene(scene);assert scene['schema_version']==3
    from scene_export import export_scene
    target=tmp_path/'project.svg';export_scene(scene,'svg',target)
    assert native_svg(target.read_bytes(),'project.svg')==scene
    broken=copy.deepcopy(scene);broken['objects'][0]['parent_id']='inner'
    with pytest.raises(SceneError,match='循环'):normalize_scene(broken)


def test_invalid_structure_never_silently_becomes_bounding_rectangle():
    _,png=sample();invalid=regions();del invalid[0]['polygon']
    with pytest.raises(SceneError,match='轮廓'):reconstruct(png,'test.png',{},regions=invalid)


def test_text_move_leaves_local_background_without_a_white_rectangle():
    from PIL import ImageFont
    from vector_fidelity import render_pixels
    image=Image.new('RGB',(300,160),'#DDEEEE');draw=ImageDraw.Draw(image)
    draw.text((60,55),'STAT',font=ImageFont.truetype('arial.ttf',22),fill='#223344')
    out=io.BytesIO();image.save(out,'PNG')
    regions=[dict(id='container',kind='structure',label='Cell',x=0,y=0,w=1,h=1,polygon=[[0,0],[1,0],[1,1],[0,1]]),
             dict(id='text',kind='text',label='STAT',x=.18,y=.33,w=.25,h=.2)]
    scene,report=reconstruct(out.getvalue(),'text.png',{},regions=regions)
    text=next(o for o in scene['objects'] if o['id']=='text')
    moved=apply_operations(scene,[dict(op='update',id='text',changes={'y':text['y']+25})])
    pixels=render_pixels(render_scene(moved),image.size)
    crop=pixels[55:80,60:120]
    assert crop.min()>170, 'Moving original ink must not leave dark text or white cutout letters'
    assert np.abs(crop.astype(float)-[221,238,238]).mean()<12


def test_polygon_geometry_is_authoritative_over_a_redundant_bad_width():
    image,png=sample();items=regions();items[0]['w']=.99
    scene,report=reconstruct(png,'coordinates.png',{},regions=items)
    assert next(o for o in scene['objects'] if o['id']=='cell')['w']<65


def test_ai_reader_failure_is_not_silently_a_local_conversion():
    from semantic_vector import observations
    with pytest.raises(SceneError,match='配置'):observations(sample()[1],{})


def test_palette_bounds_colour_error_and_retains_exact_flat_fills():
    from semantic_vector import colour_palette
    image=np.asarray(sample()[0]);pixels,palette,report=colour_palette(image)
    assert report['applied'] and report['mean_rgb_error']==0
    assert np.array_equal(pixels,image) and len(palette.getcolors())<=256
    noisy=np.random.default_rng(4).integers(0,256,(150,150,3),dtype=np.uint8)
    pixels,palette,report=colour_palette(noisy)
    assert not report['applied'] and palette is None and np.array_equal(pixels,noisy)


def test_callout_panel_contains_its_text_without_treating_an_ellipse_as_a_panel():
    from semantic_vector import panel_regions
    image=Image.new('RGB',(300,180),'white');d=ImageDraw.Draw(image)
    d.rectangle((10,10,160,80),fill='#d1d7e0');d.ellipse((190,20,280,100),fill='#d1d7e0')
    objects=[dict(id='heading',kind='text',label='Results',x=.1,y=.1,w=.25,h=.12),dict(id='oval',kind='text',label='HSP',x=.7,y=.25,w=.12,h=.1)]
    panels=panel_regions(np.asarray(image),objects)
    assert len(panels)==1 and panels[0]['label']=='Results'
    assert objects[0]['parent_id']==panels[0]['id'] and 'parent_id' not in objects[1]


def test_closeups_do_not_split_a_complete_organelle_or_duplicate_overlap(monkeypatch):
    from semantic_vector import detail_regions
    import figure_imports
    image=Image.new('RGB',(1000,1000),'white');stream=io.BytesIO();image.save(stream,'PNG')
    existing=[dict(id='cell',kind='structure',polygon=[[.05,.05],[.9,.05],[.9,.9],[.05,.9]]),
              dict(id='mvb',kind='structure',polygon=[[.1,.1],[.3,.1],[.3,.3],[.1,.3]]),
              dict(id='other',kind='structure',polygon=[[.7,.7],[.85,.7],[.85,.85],[.7,.85]])]
    calls=[]
    def reader(*args,**kwargs):
        calls.append(1)
        return {'objects':[dict(kind='structure',label='inner vesicle',polygon=[[.2,.2],[.3,.2],[.3,.3],[.2,.3]])]} if len(calls)==1 else {'objects':[]}
    monkeypatch.setattr(figure_imports,'observe',reader)
    assert detail_regions(stream.getvalue(),{},existing)==[] and len(calls)==4


def test_large_model_container_follows_the_observed_boundary():
    from semantic_vector import refine_containers
    image=Image.new('RGB',(600,400),'white');d=ImageDraw.Draw(image);d.ellipse((70,40,470,360),fill='#cce6ee',outline='#48a4b8',width=3);d.rectangle((510,100,580,200),fill='#d1d7e0')
    # A diagonal notch is a model boundary error, not an actual gap in the cell.
    objects=[dict(id='cell',kind='structure',polygon=[[.1,.08],[.8,.08],[.8,.92],[.1,.92],[.55,.5],[.1,.4]])]
    assert refine_containers(np.asarray(image),objects)==['cell']
    import cv2
    mask=np.zeros((400,600),np.uint8)
    cv2.fillPoly(mask,[np.round(np.array(objects[0]['polygon'])*[600,400]).astype(np.int32)],1)
    assert mask[200,190] and not mask[150,540]


def test_new_panel_cannot_cover_earlier_text_and_moves_with_confirmed_child():
    from PIL import ImageFont
    image=Image.new('RGB',(240,130),'white');draw=ImageDraw.Draw(image)
    draw.rectangle((20,20,210,110),fill='#d1d7e0');draw.text((40,40),'STAT',font=ImageFont.truetype('arial.ttf',24),fill='#223344')
    stream=io.BytesIO();image.save(stream,'PNG')
    regions=[dict(id='word',kind='text',label='STAT',parent_id='panel',x=.15,y=.28,w=.4,h=.28),dict(id='panel',kind='structure',label='Panel',polygon=[[.08,.15],[.9,.15],[.9,.86],[.08,.86]])]
    scene,report=reconstruct(stream.getvalue(),'panel.png',{},regions=regions)
    assert [o['id'] for o in scene['objects']].index('panel')<[o['id'] for o in scene['objects']].index('word')
    assert fidelity_report(stream.getvalue(),render_scene(scene))['foreground_similarity']>=99
    panel=next(o for o in scene['objects'] if o['id']=='panel');word=next(o for o in scene['objects'] if o['id']=='word')
    moved=apply_operations(scene,[dict(op='update',id='panel',changes={'x':panel['x']+10})])
    assert next(o for o in moved['objects'] if o['id']=='word')['x']==word['x']+10


def test_region_growth_never_reclaims_an_author_exclusion():
    image,_=sample();items=regions();items[1]['exclusions']=[[[.5,.25],[.565,.25],[.565,.61],[.5,.61]]]
    objects,owner=partition(np.asarray(image),items)
    assert owner[60,165]==-1 and not objects[1]['mask'][60,165]
