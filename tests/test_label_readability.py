"""Object labels stay readable and every detached label has a fix (step 7 of
docs/修复计划-2026-11-24-排版.md).

* Object labels carry a white halo drawn under the glyphs (paint-order:
  stroke) so text on membranes and patterned shapes stays legible. It is the
  same single <text> element, so SVG and PPTX still hold one editable text per
  label line, and label measurement is unchanged.
* label-detached on objects that are neither extracellular ligands nor
  membrane objects (context cells, extracellular processes, organelles) had
  only the default spot as a fix candidate; when that spot hit a neighbour
  the fix gave up. Generic above / left / right / inside-top spots follow.
"""
import copy
import json
import os
import re
from pathlib import Path

import pytest

import scene_render
from scene_document import audit_scene, empty_scene, normalize_scene
from scene_render import label_boxes, preview_finding_fix, render_scene
from scene_storyboards import make_storyboard

ROOT = Path(__file__).resolve().parents[1]


def _codes(scene):
    return {(f['code'], tuple(f['object_ids'])) for f in audit_scene(scene)['findings']}


def _label_texts(svg):
    return re.findall(r'<text\b[^>]*data-label-for="[^"]+"[^>]*>', svg)


# ---------- halo ----------

def test_object_labels_have_halo_and_text_boxes_do_not():
    scene = make_storyboard('mapk_branch', width_mm=180, height_mm=120)
    svg = render_scene(scene)
    kinds = {o['id']: o['type'] for o in scene['objects']}
    tags = _label_texts(svg)
    assert tags
    for tag in tags:
        oid = re.search(r'data-label-for="([^"]+)"', tag).group(1)
        has_halo = 'paint-order="stroke"' in tag and 'stroke="#FFFFFF"' in tag
        assert has_halo == (kinds.get(oid) != 'text'), tag


def test_halo_does_not_change_label_boxes_or_text_count(monkeypatch):
    scene = make_storyboard('mapk_branch', width_mm=180, height_mm=120)
    with_halo = render_scene(copy.deepcopy(scene))
    boxes = label_boxes(copy.deepcopy(scene))
    monkeypatch.setattr(scene_render, 'LABEL_HALO', {})
    without = render_scene(copy.deepcopy(scene))
    assert label_boxes(copy.deepcopy(scene)) == boxes
    assert len(_label_texts(with_halo)) == len(_label_texts(without))
    assert with_halo.count('<text') == without.count('<text')
    assert 'paint-order' not in ''.join(_label_texts(without))


def test_halo_is_painted_under_the_glyphs_in_png_pdf():
    fitz = pytest.importorskip('fitz')
    def dark_pixels(attrs):
        text = scene_render._text(5, 12, 'EGFR', 17, **attrs)
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="16mm" viewBox="0 0 40 16">'
               '<rect x="0" y="6" width="40" height="8" fill="#8899AA"/>' + text + '</svg>').encode()
        doc = fitz.open(stream=svg, filetype='svg')
        pdf = fitz.open(stream=doc.convert_to_pdf(), filetype='pdf')
        pm = pdf[0].get_pixmap(matrix=fitz.Matrix(8, 8), alpha=False)
        s, n = pm.samples, pm.n
        return sum(1 for i in range(0, len(s), n) if s[i] < 80 and s[i+1] < 90 and s[i+2] < 100)
    plain, halo = dark_pixels({}), dark_pixels(scene_render.LABEL_HALO)
    assert plain > 0 and abs(halo - plain) <= .02 * plain


def test_pptx_keeps_one_text_box_per_label_line(tmp_path, monkeypatch):
    pytest.importorskip('svgpathtools')
    from pptx import Presentation
    from scene_export import export_scene
    scene = make_storyboard('mapk_branch', width_mm=180, height_mm=120)
    def texts(shapes):
        for shape in shapes:
            if shape.has_text_frame:
                yield shape.text_frame.text
            if hasattr(shape, 'shapes'):
                yield from texts(shape.shapes)
    def export(name):
        export_scene(copy.deepcopy(scene), 'pptx', tmp_path / name)
        return sorted(texts(Presentation(tmp_path / name).slides[0].shapes))
    with_halo = export('halo.pptx')
    monkeypatch.setattr(scene_render, 'LABEL_HALO', {})
    assert with_halo == export('plain.pptx')
    for o in scene['objects']:
        if o.get('visible', True) and o.get('label') and o['type'] != 'text' and len(scene_render._label_lines(o)[0]) == 1:
            assert o['label'] in with_halo, o['label']


def test_front_end_halo_matches_renderer():
    js = (ROOT / 'ui' / 'canvas-editor.js').read_text(encoding='utf-8')
    m = re.search(r"const LABEL_HALO=\{([^}]*)\}", js)
    assert m, 'canvas-editor.js has no LABEL_HALO'
    body = m.group(1)
    halo = scene_render.LABEL_HALO
    assert "'paint-order':'stroke'" in body
    assert f"'stroke-width':{float(halo['stroke_width'])}" in body
    assert f"stroke:'{halo['stroke']}'" in body
    assert '...(o.type===\'text\'?{}:LABEL_HALO)' in js


# ---------- label-detached fix for generic objects ----------

def _context_cell_scene():
    # Shaped like j_3e782f18f2e0 r1: a large context cell whose label sits
    # 8 mm below its default spot, and a protein right where the default
    # (centred under the cell) would land.
    scene = empty_scene()
    scene['objects'] = [
        {'id': 'recipient', 'type': 'cell', 'role': 'context', 'label': 'Recipient cell',
         'x': 81.5, 'y': 13.5, 'w': 91, 'h': 87, 'label_dx': 0, 'label_dy': 8},
        {'id': 'protein', 'type': 'protein', 'label': '', 'x': 119, 'y': 100.5, 'w': 16, 'h': 4},
    ]
    return normalize_scene(scene)


def _detached(scene, oid):
    return [f for f in audit_scene(scene)['findings'] if f['code'] == 'label-detached' and oid in f['object_ids']]


def test_generic_object_label_detached_is_fixable():
    scene = _context_cell_scene()
    found = _detached(scene, 'recipient')
    assert found
    before = _codes(scene)
    result = preview_finding_fix(scene, found[0])
    assert result['changed']
    after = {(f['code'], tuple(f['object_ids'])) for f in result['audit']['findings']}
    assert not any(c == 'label-detached' for c, _ in after)
    assert after <= before


def test_default_spot_alone_was_not_enough(monkeypatch):
    monkeypatch.setattr(scene_render, '_generic_label_offsets', lambda o: [])
    scene = _context_cell_scene()
    assert not preview_finding_fix(scene, _detached(scene, 'recipient')[0])['changed']


JOBS = [('j_3e782f18f2e0', 1, 'recipient'), ('j_40eba478c92b', 1, 'matrix_synthesis'), ('j_a1458648cd83', 55, 'o_9932863635fa')]


@pytest.mark.parametrize('jid,rev,oid', JOBS)
def test_saved_jobs_label_detached_fix(jid, rev, oid):
    path = Path(os.environ.get('LOCALAPPDATA', '')) / 'CellFigureStudio' / 'studio-jobs' / jid / 'revisions' / str(rev) / 'scene.json'
    if not path.exists():
        pytest.skip('saved job not on this machine')
    scene = normalize_scene(json.loads(path.read_text(encoding='utf-8')))
    found = _detached(scene, oid)
    assert found
    before = _codes(scene)
    result = preview_finding_fix(scene, found[0])
    assert result['changed']
    after = {(f['code'], tuple(f['object_ids'])) for f in result['audit']['findings']}
    assert ('label-detached', (oid,)) not in after and after <= before
