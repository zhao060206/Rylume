"""Compare complete-structure display layers with vector exports (no models)."""
from pathlib import Path
import argparse,json,sys,xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import fitz
import numpy as np
from PIL import Image
from scene_render import render_scene

def raster(svg,size):
    doc=fitz.open(stream=svg.encode(),filetype='svg')
    pdf=fitz.open(stream=doc.convert_to_pdf(),filetype='pdf')
    pix=pdf[0].get_pixmap(matrix=fitz.Matrix(size[0]/pdf[0].rect.width,size[1]/pdf[0].rect.height),alpha=False)
    im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
    return im.resize(size,Image.Resampling.LANCZOS)

def main():
    p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args();root=a.folder
    scene=json.loads((root/'moved-scene.json').read_text())
    svg=render_scene(scene);tree=ET.fromstring(svg)
    assert not any(n.tag.endswith('image') for n in tree.iter())
    # Display surface contains illustration paths; labels are separate live layers.
    for n in list(tree):
        if n.get('id') in ('layer-objects','layer-relations'):tree.remove(n)
    display=Image.open(root/'moved-display.png').convert('RGB')
    vector=raster(ET.tostring(tree,encoding='unicode'),display.size)
    vector.save(root/'moved-vector-context.png')
    d=np.abs(np.asarray(display,dtype=float)-np.asarray(vector,dtype=float))
    report={'mean_rgb_error':float(d.mean()),'rgb_similarity_percent':float(100*(1-d.mean()/255)),
            'fraction_channels_over_24':float((d>24).mean()),'no_svg_bitmaps':True,
            'complete_structure_count':len(scene['structures'])}
    (root/'display-export-comparison.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    assert report['rgb_similarity_percent']>=99,'Display and vector export diverge'

if __name__=='__main__':main()
