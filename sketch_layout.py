"""Turn approximate sketch positions into measured layout, without changing science.

The model identifies objects and topology. This module removes hand-drawing
jitter and sizes glyphs deterministically; the source pixels remain untouched.
"""
from __future__ import annotations

import copy
import math
from statistics import median

from scene_document import normalize_scene, PT_MM
from scene_render import DEFAULT_DIMS, _label_lines, _measure, layout_scene, repair_geometry


def _clusters(items, axis, tolerance):
    groups = []
    for obj in sorted(items, key=lambda o: (o[axis] + o['w' if axis == 'x' else 'h']/2, o['id'])):
        center = obj[axis] + obj['w' if axis == 'x' else 'h']/2
        if not groups or center - median(p[0] for p in groups[-1]) > tolerance:
            groups.append([])
        groups[-1].append((center, obj))
    return [[p[1] for p in group] for group in groups]


def _bounds(items):
    x = min(o['x'] for o in items); y = min(o['y'] for o in items)
    return x, y, max(o['x']+o['w'] for o in items)-x, max(o['y']+o['h'] for o in items)-y


def _overlap(a, b, padding=0):
    return (max(0, min(a['x']+a['w']+padding, b['x']+b['w'])-max(a['x']-padding, b['x'])) *
            max(0, min(a['y']+a['h']+padding, b['y']+b['h'])-max(a['y']-padding, b['y'])))


def _arrangement(items, composition):
    cx = [o['x']+o['w']/2 for o in items]; cy = [o['y']+o['h']/2 for o in items]
    dx, dy = max(cx)-min(cx), max(cy)-min(cy)
    if composition not in ('row', 'column', 'cycle', 'serpentine'):
        radial=[]
        if len(items)>=5 and dx>30 and dy>30 and len(_clusters(items,'y',10))>=3 and len(_clusters(items,'x',10))>=3:
            midx=(max(cx)+min(cx))/2; midy=(max(cy)+min(cy))/2
            radial=[math.hypot((x-midx)/(dx/2),(y-midy)/(dy/2)) for x,y in zip(cx,cy)]
        if radial and min(radial)>.6 and max(radial)-min(radial)<.35:
            composition='cycle'
        elif dy < max(8, median(o['h'] for o in items)*.6) or (dx > 2*dy and dy < 25):
            composition = 'row'
        elif dx < max(8, median(o['w'] for o in items)*.6) or (dy > 2*dx and dx < 25):
            composition = 'column'
        else:
            composition = 'grid'
    return composition


def _region(items, canvas, compartment):
    if compartment:
        return compartment['x']+3, compartment['y']+3, max(1, compartment['w']-6), max(1, compartment['h']-6)
    return 7, 7, canvas['width_mm']-14, canvas['height_mm']-14


def _frame(original, needed_w, needed_h, region):
    rx, ry, rw, rh = region
    x, y, w, h = original
    width = min(rw, max(needed_w, w)); height = min(rh, max(needed_h, h))
    return (min(max(rx, x+w/2-width/2), rx+rw-width),
            min(max(ry, y+h/2-height/2), ry+rh-height), width, height)


def _grid_positions(items, composition, cell_w, cell_h, region, original):
    if composition == 'row':
        rows = [sorted(items, key=lambda o: (o['x']+o['w']/2, o['id']))]
    elif composition == 'column':
        rows = [[o] for o in sorted(items, key=lambda o: (o['y']+o['h']/2, o['id']))]
    else:
        rows = _clusters(items, 'y', max(6, min(13, median(o['h'] for o in items)*.65)))
        for row in rows:
            row.sort(key=lambda o: (o['x']+o['w']/2, o['id']))
    cols = max(map(len, rows))
    # Keep shared columns for branches, rather than centering each row independently.
    x_groups = _clusters(items, 'x', max(6, min(14, median(o['w'] for o in items)*.55)))
    shared = composition not in ('row', 'column') and len(x_groups) <= cols+1
    x_slot = {o['id']:i for i, group in enumerate(x_groups) for o in group}
    if shared:
        cols = len(x_groups)
        shared = all(len({x_slot[o['id']] for o in row}) == len(row) for row in rows)
    if not shared:
        cols = max(map(len, rows))
    wrapped = cols*cell_w > region[2] or len(rows)*cell_h > region[3]
    if wrapped:
        # Read row by row, retaining a serpentine direction where requested.
        ordered = [o for i,row in enumerate(rows) for o in (list(reversed(row)) if composition == 'serpentine' and i%2 else row)]
        cols = max(1, min(len(items), int(region[2]//cell_w)))
        rows = [ordered[i:i+cols] for i in range(0, len(ordered), cols)]
        shared = False
    frame = _frame(original, cols*cell_w, len(rows)*cell_h, region)
    x, y, width, height = frame
    positions = {}
    for row_index, row in enumerate(rows):
        for column, obj in enumerate(row):
            column = x_slot[obj['id']] if shared else cols-1-column if wrapped and composition == 'serpentine' and row_index%2 else column
            positions[obj['id']] = (x+width*(column+.5)/cols, y+height*(row_index+.5)/len(rows))
    return positions, wrapped, cols*cell_w <= region[2] and len(rows)*cell_h <= region[3]


def _cycle_positions(items, cell_w, cell_h, region, original):
    x, y, width, height = _frame(original, cell_w*3, cell_h*3, region)
    center = x+width/2, y+height/2
    ordered = sorted(items, key=lambda o: math.atan2(o['y']+o['h']/2-center[1], o['x']+o['w']/2-center[0]))
    first = ordered[0]
    start = math.atan2(first['y']+first['h']/2-center[1], first['x']+first['w']/2-center[0])
    # Quantize the ring's orientation, while preserving circular order and direction.
    start = round(start/(math.pi/4))*(math.pi/4)
    rx, ry = max(0, (width-cell_w)/2), max(0, (height-cell_h)/2)
    positions = {o['id']:(center[0]+rx*math.cos(start+i*math.tau/len(items)),
                         center[1]+ry*math.sin(start+i*math.tau/len(items))) for i,o in enumerate(ordered)}
    return positions, False, rx > 0 and ry > 0


def regularize_sketch(scene, composition='auto'):
    original = layout_scene(scene)
    result = copy.deepcopy(original)
    protected = {o['id'] for o in result['objects'] if o['locked'] or not o['visible'] or
                 o['type'] in ('text', 'membrane', 'nuclear_pore') or o['role'] == 'context' or
                 (result['layout'] == 'assembly' and o.get('group_id'))}
    groups = {}
    for obj in result['objects']:
        if obj['id'] not in protected:
            groups.setdefault((obj.get('compartment', ''), obj.get('group_id', '')), []).append(obj)
    compmap = {c['id']:c for c in result['compartments']}
    moved, methods, fits, notes = set(), [], True, []
    for (cid, _), items in groups.items():
        old_box = _bounds(items)
        method = _arrangement(items, composition)
        sizes = {}
        for obj in items:
            w, h = DEFAULT_DIMS.get(obj['type'], (26, 22))
            if obj['type'] in ('cell', 'stem_cell'):
                w, h = 26, 26
            elif obj['type'] == 'process':
                w, h = (26, 22) if obj.get('state') == 'flow_decision' else (28, 18)
            sizes[obj['id']] = (w, h)
        cell_w = max(w for w,h in sizes.values())+10
        cell_h = max(h for w,h in sizes.values())+14
        for obj in items:
            measure_obj = {**obj, 'w':sizes[obj['id']][0], 'h':sizes[obj['id']][1]}
            lines, fs = _label_lines(measure_obj)
            cell_w = max(cell_w, max(_measure(line, fs) for line in lines)+7)
            cell_h = max(cell_h, sizes[obj['id']][1]+fs*(1.23*len(lines)+1)+7)
        region = _region(items, result['canvas'], compmap.get(cid))
        if method == 'cycle' and len(items) >= 3:
            positions, wrapped, fit = _cycle_positions(items, cell_w, cell_h, region, old_box)
        else:
            positions, wrapped, fit = _grid_positions(items, method, cell_w, cell_h, region, old_box)
        if not fit:
            fits = False
            notes.append('当前画布空间不足以规整排放全部对象，请增大纸张或拆分图版；未缩小字号或改变科学关系。')
            continue
        if wrapped:
            notes.append('对象较多，已按原阅读顺序换行排列，请在结构预览中核对。')
        for obj in items:
            cx, cy = positions[obj['id']]; w, h = sizes[obj['id']]
            obj.update(x=round(cx-w/2, 4), y=round(cy-cell_h/2+4, 4), w=w, h=h,
                       rotation=0, label_dx=0, label_dy=0)
            moved.add(obj['id'])
        methods.append(method)
    # Endpoints stay bound to the same IDs. Hand-drawn bends and caption offsets
    # are geometry, so recompute them instead of retaining old absolute points.
    for relation in result['relations']:
        if relation['source'] in moved and relation['target'] in moved:
            for key in ('control', 'label_position', 'source_anchor', 'target_anchor'):
                relation.pop(key, None)
            relation.update(source_port='auto', target_port='auto')
    # Keep explicitly locked geometry and text byte-for-byte, even during repair.
    fixed = {o['id']:copy.deepcopy(o) for o in result['objects'] if o['id'] in protected}
    result = repair_geometry(result, passes=2)
    for i,obj in enumerate(result['objects']):
        if obj['id'] in fixed:
            result['objects'][i] = fixed[obj['id']]
    visible = [o for o in result['objects'] if o['visible'] and o['role']=='entity' and o['type'] not in ('membrane','nuclear_pore','text')]
    collisions = [(a['id'],b['id']) for i,a in enumerate(visible) for b in visible[i+1:]
                  if (a['id'] in moved or b['id'] in moved) and _overlap(a,b) > .5]
    if collisions:
        fits = False
        notes.append('部分对象受锁定、分组或画布空间限制仍有重叠，请核对结构预览后调整。')
    result['unresolved'].extend(note for note in dict.fromkeys(notes) if note not in result['unresolved'])
    report = {'methods':list(dict.fromkeys(methods)), 'adjusted':len(moved), 'protected':len(protected),
              'fits':fits, 'overlaps':len(collisions)}
    return normalize_scene(result), report
