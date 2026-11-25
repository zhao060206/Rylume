"""Relation endpoint symbols (fix plan 2026-11-24, step 3: arrow and line style redesign).

How a relation draws its line ends: arrowheads scale with the line width, tips stop 1 mm short of an
object outline (exactly on an anchor), the line never pokes out of its symbol, dashes are whole at both
ends, binding rings keep clear of both partners, and the live editor draws the very same primitives.
The relation types and their meanings are unchanged; only the drawing is.
"""
import json
import math
import re
import subprocess
from pathlib import Path

import pytest

from relation_visuals import RELATION_DEFINITIONS, relation_parts

ROOT = Path(__file__).resolve().parents[1]
PT_MM = 25.4 / 72
SW = 1.05 * PT_MM                      # default line width in mm
KINDS = [d['id'] for d in RELATION_DEFINITIONS]
NUMBER = r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?'


def _numbers(d):
    return [float(v) for v in re.findall(NUMBER, d)]


def _points(d):
    v = _numbers(d)
    return list(zip(v[0::2], v[1::2]))


def _parts(kind, end=40.0, stroke_pt=1.05, indirect=False, control=None, **anchored):
    """A relation from (0, 0) to (end, 0); both ends are object outlines unless anchored."""
    control = control or (end / 2, 0.0)
    return relation_parts(kind, (0.0, 0.0), (end, 0.0), control, '#333333', stroke_pt, indirect, **anchored)


def _body(parts):
    return [a for _, a in parts if a.get('data-line-body')]


def _symbols(parts):
    return [(t, a) for t, a in parts if a.get('data-endpoint')]


def _chevron(d, width):
    """Open arrowhead 'M arm L vertex L arm': returns (mitred tip, vertex, axis, head length)."""
    (ax, ay), (vx, vy), (bx, by) = _points(d)[:3]
    mx, my = (ax + bx) / 2, (ay + by) / 2
    length = math.hypot(vx - mx, vy - my)
    half = math.hypot(ax - mx, ay - my)
    axis = ((vx - mx) / length, (vy - my) / length)
    reach = width / 2 * math.hypot(length, half) / half     # how far the mitre sticks out past the vertex
    return (vx + axis[0] * reach, vy + axis[1] * reach), (vx, vy), axis, length


def _dashes(body):
    """Visible dashes as (start x, end x); touching pieces count as one dash."""
    runs = []
    for piece in body['d'].split('M')[1:]:
        p = _points(piece)
        if runs and abs(p[0][0] - runs[-1][1]) < 1e-9:
            runs[-1][1] = p[-1][0]
        else:
            runs.append([p[0][0], p[-1][0]])
    return runs


def test_arrowhead_size_follows_the_line_width():
    """A fixed 3 mm head looked clumsy on thin lines; it now scales with the stroke (2.59 mm at 1.05 pt)."""
    lengths = {}
    for stroke_pt in (0.8, 1.05, 1.3):
        (_, head), = _symbols(_parts('activates', stroke_pt=stroke_pt))
        lengths[stroke_pt] = _chevron(head['d'], stroke_pt * PT_MM)[3]
    assert lengths[1.05] == pytest.approx(7 * SW, abs=1e-6)
    assert lengths[1.3] / lengths[0.8] == pytest.approx(1.3 / 0.8, rel=1e-6)


@pytest.mark.parametrize('kind', ['activates', 'transports', 'converts', 'sequence', 'inhibits'])
def test_tip_stops_one_mm_short_of_the_object_and_hides_the_line_end(kind):
    parts = _parts(kind)
    (_, head), = _symbols(parts)
    (body,) = _body(parts)
    line_end = max(x for x, _ in _points(body['d']))
    if kind in ('activates', 'transports'):
        assert head['stroke-linejoin'] == 'miter'
        (tip, _), (vertex, _), _, _ = _chevron(head['d'], SW)
        assert line_end + SW / 2 <= vertex + 1e-9          # the round line cap ends inside the vertex
    elif kind == 'inhibits':
        (bar, _), _ = _points(head['d'])
        tip = bar + float(head['stroke-width']) / 2
        assert head['stroke-linecap'] == 'butt'
        assert line_end + SW / 2 <= tip + 1e-9
    else:
        assert head['stroke'] == 'none'                    # crisp filled head, not rounded by an outline
        xs = [x for x, _ in _points(head['d'])]
        tip = max(xs)
        assert min(xs) < line_end < tip                    # the line ends inside the filled head
    assert tip == pytest.approx(39.0, abs=1e-6)


def test_anchored_ends_put_the_tip_on_the_anchor():
    parts = _parts('activates', anchored_start=True, anchored_end=True)
    (_, head), = _symbols(parts)
    (tip, _), _, _, _ = _chevron(head['d'], SW)
    assert tip == pytest.approx(40.0, abs=1e-6)
    assert _points(_body(parts)[0]['d'])[0] == (0.0, 0.0)


def test_heads_follow_a_curved_line():
    parts = _parts('activates', control=(20.0, -16.0))
    (_, head), = _symbols(parts)
    tip, vertex, axis, _ = _chevron(head['d'], SW)
    assert math.dist(tip, (40.0, 0.0)) == pytest.approx(1.0, abs=.01)
    (ax, ay), _, (bx, by) = _points(head['d'])[:3]
    assert math.dist((ax, ay), vertex) == pytest.approx(math.dist((bx, by), vertex), rel=1e-9)
    end = _points(_body(parts)[0]['d'])[-1]
    behind = (end[0] - vertex[0]) * axis[0] + (end[1] - vertex[1]) * axis[1]
    assert behind + SW / 2 <= .02                          # the line does not poke out of the head


def test_dashes_are_whole_at_both_ends_and_grow_with_the_line():
    thin = _dashes(_body(_parts('activates', indirect=True))[0])
    lengths = [b - a for a, b in thin]
    assert len(thin) >= 5
    assert max(lengths) - min(lengths) < 1e-6             # equal dashes, no stub at either end
    assert thin[0][0] == pytest.approx(1.0, abs=1e-6)
    gaps = lambda runs: [b[0] - a[1] for a, b in zip(runs, runs[1:])]
    thick = _dashes(_body(_parts('activates', stroke_pt=1.6, indirect=True))[0])
    assert min(gaps(thick)) > max(gaps(thin))             # a heavier line gets a longer rhythm


def test_binding_rings_keep_clear_of_both_partners():
    parts = _parts('binds')
    rings = sorted((a for t, a in _symbols(parts) if t == 'circle'), key=lambda a: float(a['cx']))
    assert len(rings) == 2
    first, last = rings
    r = float(first['r'])
    assert float(first['cx']) - r - SW / 2 >= .25          # not drawn over the source outline
    assert float(last['cx']) + r + SW / 2 <= 40 - .25      # nor over the target outline
    xs = [x for x, _ in _points(_body(parts)[0]['d'])]
    assert min(xs) >= float(first['cx']) + r - 1e-9        # the line joins the rings, it does not cross them
    assert max(xs) <= float(last['cx']) - r + 1e-9


def test_close_partners_get_a_single_binding_ring():
    rings = [a for t, a in _symbols(_parts('binds', end=3.5)) if t == 'circle']
    assert len(rings) == 1
    assert float(rings[0]['cx']) == pytest.approx(1.75, abs=1e-6)


def test_conversion_and_next_step_differ_in_shape_not_only_in_size():
    (_, conversion), = _symbols(_parts('converts'))
    (_, step), = _symbols(_parts('sequence'))
    assert len(_points(conversion['d'])) == 3              # flat-backed triangle
    assert len(_points(step['d'])) == 4                    # notched arrow


def test_inhibition_bar_is_in_proportion_to_the_arrowheads():
    (_, bar), = _symbols(_parts('inhibits'))
    (_, arrow), = _symbols(_parts('activates'))
    ys = [y for _, y in _points(bar['d'])]
    assert max(ys) - min(ys) == pytest.approx(1.4 * _chevron(arrow['d'], SW)[3], rel=1e-6)   # 3.6 mm, was 5.6 mm
    assert float(bar['stroke-width']) == pytest.approx(1.6 * SW, rel=1e-6)


def _same_primitives(expected, actual):
    assert len(expected) == len(actual)
    for (tag, attrs), (other, other_attrs) in zip(expected, actual):
        assert tag == other and attrs.keys() == other_attrs.keys()
        for key, value in attrs.items():
            if isinstance(value, (int, float)):
                assert value == pytest.approx(other_attrs[key], rel=1e-9, abs=1e-9)
            elif key == 'd':
                assert re.findall('[MLQZ]', value) == re.findall('[MLQZ]', other_attrs[key])
                assert _numbers(value) == pytest.approx(_numbers(other_attrs[key]), rel=1e-9, abs=1e-9)
            else:
                assert value == other_attrs[key]


def test_live_editor_draws_the_same_primitives_for_every_case(tmp_path):
    shapes = [((1, 2), (31, 25), (14, 3)), ((0, 0), (3.5, 0), (1.75, 0)), ((5, 40), (60, 10), (20, 5)),
              ((10, 10), (10.4, 10.2), (10.2, 10.1)), ((0, 0), (40, 0), (20, -16))]
    cases = [dict(kind=kind, start=s, end=e, control=c, stroke_pt=w, indirect=i, anchored=a)
             for kind in KINDS for w in (0.6, 1.05, 2.0) for i in (False, True)
             for a in ((False, False), (True, True), (True, False)) for s, e, c in shapes]
    source = tmp_path / 'cases.json'
    source.write_text(json.dumps(cases), encoding='utf8')
    js = """const fs=require('fs'),path=require('path'),url=require('url');
    (async()=>{const m=await import(url.pathToFileURL(path.resolve('ui/canvas-editor.js')).href);
    const cases=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
    console.log(JSON.stringify(cases.map(c=>m.relationParts(c.kind,{x:c.start[0],y:c.start[1]},{x:c.end[0],y:c.end[1]},
      {x:c.control[0],y:c.control[1]},'#333333',c.stroke_pt,c.indirect,{start:c.anchored[0],end:c.anchored[1]}))));})();"""
    actual = json.loads(subprocess.check_output(['node', '-e', js, str(source)], cwd=ROOT, text=True, encoding='utf8'))
    assert len(actual) == len(cases)
    for case, live in zip(cases, actual):
        expected = relation_parts(case['kind'], case['start'], case['end'], case['control'], '#333333', case['stroke_pt'],
                                  case['indirect'], anchored_start=case['anchored'][0], anchored_end=case['anchored'][1])
        _same_primitives(json.loads(json.dumps(expected)), live)


@pytest.mark.parametrize('kind', [k for k in KINDS if k != 'binds'])
def test_line_body_always_comes_first(kind):
    """The PowerPoint export takes a relation's first vector as its line, so even a stub must be there."""
    for end in (2.0, 40.0):
        for indirect in (False, True):
            parts = _parts(kind, end=end, indirect=indirect)
            assert parts and parts[0][1].get('data-line-body') == 'true'


def test_powerpoint_line_ends_keep_conversion_and_next_step_apart(tmp_path):
    """Exported connectors use PowerPoint's own line ends: they must match the drawn symbols and the legend."""
    import xml.etree.ElementTree as ET
    import zipfile
    from scene_document import empty_scene, normalize_scene
    from scene_export import export_scene
    scene = empty_scene('Line ends', width_mm=180, height_mm=90)
    for i, kind in enumerate(('activates', 'converts', 'sequence')):
        for key, x in (('a', 20), ('b', 120)):
            scene['objects'].append(dict(id=f'{key}{i}', type='protein', label=f'{key.upper()}{i}', x=x, y=10 + i * 25, w=20, h=9))
        scene['relations'].append(dict(id=f'r{i}', source=f'a{i}', target=f'b{i}', type=kind))
    export_scene(normalize_scene(scene), 'pptx', tmp_path / 'ends.pptx')
    ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
          'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
    with zipfile.ZipFile(tmp_path / 'ends.pptx') as z:
        slide = ET.fromstring(z.read('ppt/slides/slide1.xml'))
    ends = {}
    for connector in slide.iter('{%s}cxnSp' % ns['p']):
        tail = connector.find('.//a:ln/a:tailEnd', ns)
        name = connector.find('p:nvCxnSpPr/p:cNvPr', ns).get('name')
        ends[name] = None if tail is None else (tail.get('type'), tail.get('w'), tail.get('len'))
    # Open arrow, flat triangle, notched arrow. PowerPoint sizes line ends in multiples of the line width
    # (sm 2x, med 3x, lg 5x); "lg" is the closest to the drawn heads (about 7x long, 6x wide).
    assert ends == {'r0': ('arrow', 'lg', 'lg'), 'r1': ('triangle', 'lg', 'lg'), 'r2': ('stealth', 'lg', 'lg')}
