"""The editor canvas (ui/canvas-editor.js edgeGeometry / objectLabelBoxes) must put connector
ends and object label boxes where export and review (scene_render) put them: automatic ports
clear their own labels, binding lines keep 7 mm, and so on.

node has no canvas, so measureMM would fall back to a rough estimate; a stub canvas answers
measureText with the widths scene_render._measure gives, so this compares geometry, not fonts."""
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import scene_render as sr
from relation_visuals import relation_label
from scene_templates import make_template

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ('signal_nucleus', 'signal_relay', 'signal_compact', 'assembly_horizontal', 'sb_antibody_modes',
             'sb_nfkb_release', 'sb_crispr_editing', 'sb_endosome_sorting', 'sb_barrier_transport')
SIZES = ({}, {'width_mm': 90, 'height_mm': 150})

JS = r"""
const path=require('node:path'),{pathToFileURL}=require('node:url');
let buf='';process.stdin.on('data',d=>buf+=d).on('end',async()=>{
 const {widths,scenes}=JSON.parse(buf);let misses=0;
 globalThis.document={createElement:()=>({getContext:()=>({font:'',measureText(t){
  if(Object.hasOwn(widths,t))return {width:widths[t]*1000};
  misses++;return {width:[...t].reduce((s,c)=>s+(c.charCodeAt(0)>255?1:.53),0)*1000};}})})};
 const m=await import(pathToFileURL(path.resolve(process.env.RYLUME_EDITOR_JS||'ui/canvas-editor.js')).href);
 const out=scenes.map(sc=>({boxes:m.objectLabelBoxes(sc).map(b=>[b.id,b.x,b.y,b.w,b.h]),
  ends:sc.relations.map(r=>{const g=m.edgeGeometry(sc,r);return g?[r.id,g.start.x,g.start.y,g.end.x,g.end.y]:[r.id,null];})}));
 console.log(JSON.stringify({misses,out}));
});
"""


def _runs(text):
    out = set()
    for line in str(text).split('\n'):
        parts, sep = (line.split(' '), ' ') if ' ' in line else (list(line), '')
        out.update(sep.join(parts[i:j]) for i in range(len(parts)) for j in range(i + 1, len(parts) + 1))
        out.add(line)
    return {t for t in out if t}


@pytest.mark.skipif(shutil.which('node') is None, reason='node is not installed')
def test_editor_endpoints_and_label_boxes_match_export():
    scenes = [make_template(t, **size) for t in TEMPLATES for size in SIZES]
    strings = set()
    for sc in scenes:
        for o in sc['objects']:
            if o.get('label'):
                strings |= _runs(o['label'])
        for r in sc['relations']:
            if relation_label(sc, r):
                strings |= _runs(relation_label(sc, r))
    widths = {t: sr._measure(t, 1.0) for t in strings}
    raw = subprocess.check_output(['node', '-e', JS], input=json.dumps({'widths': widths, 'scenes': scenes}),
                                  text=True, encoding='utf8', cwd=ROOT, env={**os.environ})
    result = json.loads(raw)
    assert result['misses'] == 0, 'the stub canvas was asked for a width the table does not hold'
    problems = []
    for name, sc, js in zip([f'{t}/{"single" if s else "wide"}' for t in TEMPLATES for s in SIZES], scenes,
                            result['out']):
        py_boxes = {b['id']: b for b in sr._object_label_boxes(sc)}
        for i, x, y, w, h in js['boxes']:
            b = py_boxes[i]
            if max(abs(b['x'] - x), abs(b['y'] - y), abs(b['w'] - w), abs(b['h'] - h)) > .01:
                problems.append(f'{name} label box {i}: py {b} js {(x, y, w, h)}')
        for row in js['ends']:
            r = next(q for q in sc['relations'] if q['id'] == row[0])
            g = sr.connection_geometry(sc, r)
            if row[1] is None:
                problems.append(f'{name} {row[0]}: editor drew no connector')
                continue
            d = max(math.hypot(row[1] - g['x1'], row[2] - g['y1']), math.hypot(row[3] - g['x2'], row[4] - g['y2']))
            if d > .05:
                problems.append(f"{name} {row[0]}: ends differ by {d:.2f} mm, py ({g['x1']:.2f},{g['y1']:.2f})->"
                                f"({g['x2']:.2f},{g['y2']:.2f}) js ({row[1]:.2f},{row[2]:.2f})->({row[3]:.2f},{row[4]:.2f})")
    assert not problems, f'{len(problems)} differences:\n' + '\n'.join(problems[:12])
