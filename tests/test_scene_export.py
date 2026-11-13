import json
import zipfile
import xml.etree.ElementTree as ET

import fitz
from PIL import Image

from scene_examples import make_example
from scene_export import export_scene


def test_svg_pdf_png_and_pptx_share_revision_and_physical_size(tmp_path):
    scene = make_example("jak_stat")
    scene["revision"] = 7
    results = {}
    for fmt in ("svg","pdf","png","pptx"):
        dest = tmp_path/f"figure.{fmt}"
        results[fmt] = export_scene(scene,fmt,dest,dpi=300)
        assert results[fmt]["revision"]==7
        assert dest.is_file() and dest.stat().st_size>100
        assert json.loads(dest.with_suffix(dest.suffix+".json").read_text())["revision"]==7
    with Image.open(tmp_path/"figure.png") as image:
        assert image.size==(2126,1417)
        assert abs(image.info["dpi"][0]-300)<1
    with fitz.open(tmp_path/"figure.pdf") as doc:
        assert abs(doc[0].rect.width-180/25.4*72)<0.1
        assert abs(doc[0].rect.height-120/25.4*72)<0.1
    ns={"p":"http://schemas.openxmlformats.org/presentationml/2006/main","a":"http://schemas.openxmlformats.org/drawingml/2006/main"}
    with zipfile.ZipFile(tmp_path/"figure.pptx") as archive:
        root = ET.fromstring(archive.read("ppt/slides/slide1.xml"))
        assert not root.findall(".//p:pic",ns)
        texts=[n.text for n in root.findall(".//a:t",ns)]
        ids=[n.get('id') for n in root.findall('.//p:cNvPr',ns)]
        assert len(ids)==len(set(ids)), 'Each native shape needs a distinct PowerPoint ID'
        assert root.findall('.//a:cubicBezTo',ns), 'Bezier curves must survive as editable curves'
        assert any("STAT" in t for t in texts)
        sizes=[int(n.get("sz")) for n in root.findall(".//a:rPr",ns) if n.get("sz")]
        assert sizes and min(sizes)>=699
        groupnames={n.get("name") for n in root.findall(".//p:grpSp/p:nvGrpSpPr/p:cNvPr",ns)}
        assert {o["id"] for o in scene["objects"]} <= groupnames
        dna_group=next(g for g in root.findall('.//p:grpSp',ns) if g.find('p:nvGrpSpPr/p:cNvPr',ns).get('name')=='dna')
        assert len(dna_group.findall('p:sp',ns))>=15  # 13 rungs + two helix strands must survive native conversion.
        pres=ET.fromstring(archive.read("ppt/presentation.xml"))
        size=pres.find("p:sldSz",ns)
        assert abs(int(size.get("cx"))-180*36000)<=1
        assert abs(int(size.get("cy"))-120*36000)<=1


def test_600dpi_export_uses_correct_pixel_dimensions(tmp_path):
    scene=make_example("exosome",width_mm=90,height_mm=90)
    export_scene(scene,"png",tmp_path/"figure.png",dpi=600)
    with Image.open(tmp_path/"figure.png") as image:
        assert image.size==(2126,2126)


def test_large_native_export_releases_presentation_graph(tmp_path, monkeypatch):
    import weakref
    import ppt_native
    references=[]
    factory=ppt_native.Presentation
    def tracked_presentation():
        presentation=factory()
        references.append(weakref.ref(presentation))
        return presentation
    monkeypatch.setattr(ppt_native,'Presentation',tracked_presentation)
    source=tmp_path/'many-paths.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">'+
        '<path d="M 10 10 C 12 8 18 8 20 10 L 20 20 Z" fill="#326c82"/>'*5001+'</svg>')
    result=ppt_native.build(source,tmp_path/'native',preview=False)
    assert result['paths']==5001 and result['shapes']==5001
    assert references[0]() is None, 'A finished export must release its cyclic presentation graph'
    with zipfile.ZipFile(result['pptx']) as archive:
        root=ET.fromstring(archive.read('ppt/slides/slide1.xml'))
        ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        assert len(root.findall('.//a:cubicBezTo',ns))==5001


def test_native_curves_keep_geometry_and_paint_without_temporary_freeforms(tmp_path,monkeypatch):
    import ppt_native
    from pptx import Presentation
    from pptx.shapes.freeform import FreeformBuilder
    def no_temporary_rectangle(*a,**k):raise AssertionError('SVG curves must be written directly')
    monkeypatch.setattr(FreeformBuilder,'convert_to_shape',no_temporary_rectangle)
    source=tmp_path/'curves.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="100"><g data-object-id="enzyme" transform="translate(5 7) scale(2)"><path d="M 0 0 C 3 -2 8 1 10 4 Q 12 8 8 10 L 0 0 Z" fill="#326c82" stroke="#123456" stroke-width="1.5" stroke-dasharray="3 2"/></g></svg>')
    result=ppt_native.build(source,tmp_path/'out',preview=False)
    shape=Presentation(result['pptx']).slides[0].shapes[0].shapes[0]
    assert str(shape.fill.fore_color.rgb)=='326C82'
    assert str(shape.line.color.rgb)=='123456'
    assert abs(shape.line.width-3*ppt_native.EMU_PX)<1
    with zipfile.ZipFile(result['pptx']) as archive:
        root=ET.fromstring(archive.read('ppt/slides/slide1.xml'));ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
        assert len(root.findall('.//a:cubicBezTo',ns))==1 and len(root.findall('.//a:quadBezTo',ns))==1
        assert root.find('.//a:prstDash',ns).get('val')=='dash'
        assert not root.findall('.//p:style',ns)
