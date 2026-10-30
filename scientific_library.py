"""Trusted, vendored scientific art. Documents refer to IDs, never arbitrary SVG."""
import json
from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent

@lru_cache(maxsize=1)
def library():
    path = ROOT/'assets/bioicons/manifest.json'
    return {item['asset_id']: item for item in json.loads(path.read_text(encoding='utf8'))} if path.exists() else {}

@lru_cache(maxsize=256)
def glyph(asset_id,fill=None,stroke=None):
    item = library()[asset_id]
    root = ET.fromstring((ROOT/'ui/library'/f'{asset_id}.svg').read_text(encoding='utf8'))
    x,y,w,h = map(float,root.get('viewBox').split())
    if fill or stroke:
        from biology_glyphs import tint
        for node in root.iter():
            original=node.get('fill','none')
            if fill and original.startswith('#') and original.lower() not in ('#ffffff','#fff'):
                original=original.lstrip('#')
                if len(original)==6:
                    luminance=sum(int(original[i:i+2],16)*v for i,v in ((0,.2126),(2,.7152),(4,.0722)))/255
                    node.set('fill',tint(fill,.15+luminance*.65))
            if stroke and node.get('stroke','none')!='none':node.set('stroke',stroke)
    # Match the 100 x 100 coordinate system of the native scientific glyphs.
    inner = ''.join(ET.tostring(c,encoding='unicode').replace('ns0:','').replace(':ns0','') for c in root)
    return f'<g transform="scale({100/w} {100/h}) translate({-x} {-y})">{inner}</g>'

def credits(scene):
    ids = sorted({o.get('asset_id') for o in scene['objects'] if o.get('asset_id')})
    result=[{k: library()[aid][k] for k in ('asset_id','label','author','author_url','license','license_url','source_url','modifications')} for aid in ids]
    for item in result:
        if any(o.get('asset_id')==item['asset_id'] and (o.get('fill') or o.get('stroke')) for o in scene['objects']):item['modifications']+=' Recoloured by the figure author.'
    return result
