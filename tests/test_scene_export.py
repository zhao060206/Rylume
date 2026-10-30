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
