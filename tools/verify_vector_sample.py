"""Export a real imported scene through HTTP and audit editable output.

Run against an isolated local server; no model credentials are read.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8910')
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reuse',action='store_true',help='Audit previously exported files against their archived scene and revision')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def api(path, body=None):
        raw = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(args.url+path, data=raw, headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response)

    document = api('/api/jobs/'+args.job+'/scene') if not args.reuse else None
    scene = document['scene'] if document else json.loads((args.output/'scene.json').read_text(encoding='utf8'))
    revision=scene['revision']
    (args.output/'scene.json').write_text(json.dumps(scene, ensure_ascii=False), encoding='utf8')
    results = {'revision': revision, 'job': args.job, 'objects': len(scene['objects']), 'exports': {}}
    for fmt in ('svg','png','pdf','pptx'):
        started = time.monotonic()
        destination = args.output/('figure.'+fmt)
        result = json.loads(destination.with_suffix(destination.suffix+'.json').read_text(encoding='utf8')) if args.reuse else api('/api/jobs/'+args.job+'/save-as', {'format':fmt,'revision':revision,'path':str(destination.resolve()),'dpi':300})
        assert result['revision'] == revision and not result['raster_objects'], result
        results['exports'][fmt] = {'seconds': round(time.monotonic()-started,2),'bytes':destination.stat().st_size,
            'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
        print(fmt, results['exports'][fmt], flush=True)
    svg = ET.parse(args.output/'figure.svg').getroot()
    assert not any(e.tag.rsplit('}',1)[-1]=='image' for e in svg.iter())
    results['svg_paths'] = sum(e.tag.rsplit('}',1)[-1]=='path' for e in svg.iter())
    import fitz
    with fitz.open(args.output/'figure.pdf') as pdf:
        assert sum(len(page.get_images()) for page in pdf)==0
        results['pdf_vector_drawings'] = sum(len(page.get_drawings()) for page in pdf)
    ns = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    with zipfile.ZipFile(args.output/'figure.pptx') as archive:
        assert not any(n.startswith('ppt/media/') for n in archive.namelist())
        slide = ET.fromstring(archive.read('ppt/slides/slide1.xml'))
        assert not slide.findall('.//p:pic',ns)
        results['pptx_freeforms'] = len(slide.findall('.//a:custGeom',ns))
        texts = [e.text or '' for e in slide.findall('.//a:t',ns)]
        results['pptx_texts'] = len(texts)
        from scene_render import uses_text_appearance
        expected = [o['label'] for o in scene['objects'] if o['type']=='text' and o['visible'] and o['label'] and not uses_text_appearance(o)]
        results['preserved_outline_labels']=sum(uses_text_appearance(o) for o in scene['objects'])
        assert all(text in texts for text in expected), (expected,texts)
        assert results['pptx_freeforms'] >= results['svg_paths']
        ids=[e.get('id') for e in slide.findall('.//p:cNvPr',ns)]
        assert len(ids)==len(set(ids)), 'PowerPoint shape IDs must be unique'
    results['passed'] = True
    (args.output/'verification.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(results, ensure_ascii=False, indent=2), flush=True)


if __name__=='__main__':
    main()
