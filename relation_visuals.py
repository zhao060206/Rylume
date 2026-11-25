"""Explicit studio relation notation, shared by export and live SVG editing.

These are local legend conventions, not a claim of full SBGN compliance.
"""
import math

RELATION_DEFINITIONS = [
    dict(id='activates', title='激活', english='Activation', symbol='open-arrow', description='起点促进终点的活性或作用。', example='激酶 A 促进 B 的活性'),
    dict(id='inhibits', title='抑制', english='Inhibition', symbol='bar', description='横杠所在的一端受到抑制。', example='抑制剂 A 阻断 B'),
    dict(id='binds', title='结合', english='Binding', symbol='paired-circles', description='两端圆点表示结合，不表示作用方向。', example='配体与受体结合'),
    dict(id='converts', title='转换', english='Conversion', symbol='filled-arrow', description='起点转变为终点；实心箭头指向产物。', example='底物 A 转变为产物 B'),
    dict(id='transports', title='转运', english='Transport', symbol='double-chevron', description='双箭头表示对象在位置或区室间移动。', example='蛋白从胞质进入细胞核'),
    dict(id='sequence', title='流程顺序', english='Next step', symbol='step-arrow', description='箭头仅表示步骤的先后，不代表生物学激活。', example='提取样本后进行测量'),
    dict(id='associates', title='普通关联', english='Association', symbol='plain-line', description='无箭头连线，仅表示相关或流程衔接。', example='未明确机制时使用，需核对含义'),
]
BY_ID = {x['id']: x for x in RELATION_DEFINITIONS}


def relation_label(scene, relation):
    return relation.get('label') or (BY_ID[relation['type']]['english'] if scene['style'].get('relation_labels') else '')


# Endpoint geometry, in millimetres. Arrowheads scale with the line (length = width x 7, clamped), tips stop
# TIP_GAP short of an object outline (0 at an anchor), and the line body always ends inside its symbol.
PT_MM = 25.4 / 72
HEAD_PER_WIDTH, HEAD_MIN, HEAD_MAX, HEAD_ASPECT = 7.0, 1.9, 3.4, .44
TIP_GAP, BIND_GAP, BIND_R = 1.0, .5, 1.0
BAR_HALF, BAR_WEIGHT, SEQ_NOTCH = .7, 1.6, .4
# A short connector keeps at least MIN_BODY of visible line: its tip gaps shrink to SHORT_GAP first,
# then its end symbol, never below HEAD_SHORT_MIN.
MIN_BODY, SHORT_GAP, HEAD_SHORT_MIN = 2.0, .5, 1.4
CURVE_SAMPLES = 200


def _curve_point(p0, c, p1, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0],
            u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1])


def relation_parts(kind, start, end, control, color, stroke_pt=1.05, indirect=False, *, anchored_start=False, anchored_end=False):
    """Return SVG primitives. Coordinates and widths use physical millimetres.

    The line is the quadratic curve start-control-end. Symbols are placed by arc length along it and sized
    from the line width. ui/canvas-editor.js relationParts mirrors this function operation for operation
    (tests/test_relation_symbols.py checks they agree), so change both together.
    """
    p0 = (float(start[0]), float(start[1]))
    c = (float(control[0]), float(control[1]))
    p1 = (float(end[0]), float(end[1]))
    points = [_curve_point(p0, c, p1, i / CURVE_SAMPLES) for i in range(CURVE_SAMPLES + 1)]
    acc = [0.0]
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        acc.append(acc[-1] + math.sqrt(dx * dx + dy * dy))
    total = acc[-1]
    if total < 1e-6:
        return []

    def t_at(s):
        s = min(max(s, 0.0), total)
        for i in range(CURVE_SAMPLES):
            if acc[i + 1] >= s:
                seg = acc[i + 1] - acc[i]
                return (i + ((s - acc[i]) / seg if seg > 0 else 0.0)) / CURVE_SAMPLES
        return 1.0

    def at(s):
        return _curve_point(p0, c, p1, t_at(s))

    def fmt(p):
        return f'{p[0]} {p[1]}'

    def pt(T, u, n, back, side=0.0):
        return (T[0] - u[0] * back + n[0] * side, T[1] - u[1] * back + n[1] * side)

    def frame(s_tip, length):
        """Tip point, unit direction (secant over the last `length` of the curve) and its normal."""
        T, B = at(s_tip), at(max(0.0, s_tip - length))
        dx, dy = T[0] - B[0], T[1] - B[1]
        d = math.sqrt(dx * dx + dy * dy)
        if d < 1e-9:
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            d = math.sqrt(dx * dx + dy * dy)
            if d < 1e-9:
                dx, dy, d = 1.0, 0.0, 1.0
        u = (dx / d, dy / d)
        return T, u, (-u[1], u[0])

    def chevron(s_tip, length, half):
        """Open arrowhead whose mitred outer point lands exactly on the tip."""
        off = sw / 2 * math.sqrt(length * length + half * half) / half
        T, u, n = frame(s_tip, length)
        A = pt(T, u, n, off)
        return off, f'M {fmt(pt(A, u, n, length, half))} L {fmt(A)} L {fmt(pt(A, u, n, length, -half))}'

    def sub(ta, tb):
        """The piece of the curve between ta and tb, itself one quadratic (blossom control point)."""
        a, b = _curve_point(p0, c, p1, ta), _curve_point(p0, c, p1, tb)
        k = ((1 - ta) * (1 - tb) * p0[0] + ((1 - ta) * tb + ta * (1 - tb)) * c[0] + ta * tb * p1[0],
             (1 - ta) * (1 - tb) * p0[1] + ((1 - ta) * tb + ta * (1 - tb)) * c[1] + ta * tb * p1[1])
        return f'M {fmt(a)} Q {fmt(k)} {fmt(b)}'

    sw = stroke_pt * PT_MM
    L = min(HEAD_MAX, max(HEAD_MIN, HEAD_PER_WIDTH * sw))
    W = HEAD_ASPECT * L
    g0 = 0.0 if anchored_start else TIP_GAP
    g1 = 0.0 if anchored_end else TIP_GAP
    # How far each end symbol reaches back along the line: a * L + b (b: chevron mitre plus half a stroke).
    mitre_reach = sw / 2 * math.sqrt(1 + HEAD_ASPECT * HEAD_ASPECT) / HEAD_ASPECT + sw / 2
    reach = {'activates': (1.0, mitre_reach), 'transports': (1.4, mitre_reach), 'converts': (1.05, 0.0),
             'sequence': (.95, 0.0), 'inhibits': (0.0, BAR_WEIGHT * sw)}.get(kind)
    if reach and total - g0 - g1 - (reach[0] * L + reach[1]) < MIN_BODY:
        g0, g1 = min(g0, SHORT_GAP), min(g1, SHORT_GAP)
        room = total - g0 - g1 - MIN_BODY - reach[1]
        if reach[0] and room < reach[0] * L:
            L = max(HEAD_SHORT_MIN, room / reach[0])
            W = HEAD_ASPECT * L
    common = {'fill': 'none', 'stroke': color, 'stroke-width': sw, 'stroke-linecap': 'round', 'stroke-linejoin': 'round'}
    mark = dict(common, **{'data-endpoint': BY_ID[kind]['symbol']})
    mitre = {'stroke-linejoin': 'miter', 'stroke-miterlimit': 8}
    heads = []
    tip = total - g1
    s0, s1 = g0, tip
    if kind == 'binds':
        b0 = 0.0 if anchored_start else BIND_GAP
        b1 = 0.0 if anchored_end else BIND_GAP
        ring = dict(mark, fill='#FFFFFF')
        if total < b0 + b1 + 4 * BIND_R + 1.0:
            # No room for two rings and a visible line: one ring between the partners.
            m = at(total / 2)
            return [('circle', dict(ring, cx=m[0], cy=m[1], r=BIND_R))]
        for s in (b0 + BIND_R, total - b1 - BIND_R):
            q = at(s)
            heads.append(('circle', dict(ring, cx=q[0], cy=q[1], r=BIND_R)))
        s0, s1 = b0 + 2 * BIND_R, total - b1 - 2 * BIND_R
    elif kind == 'activates':
        off, d = chevron(tip, L, W)
        heads.append(('path', dict(mark, d=d, **mitre)))
        s1 = tip - off - sw / 2
    elif kind == 'transports':
        off, front = chevron(tip, .8 * L, .8 * W)
        _, back = chevron(tip - .6 * L, .8 * L, .8 * W)
        heads.append(('path', dict(mark, d=front + ' ' + back, **mitre)))
        s1 = tip - off - sw / 2
    elif kind in ('converts', 'sequence'):
        k = 1.05 if kind == 'converts' else .95
        length, half = L * k, W * k
        T, u, n = frame(tip, length)
        if kind == 'sequence':   # notched: tells a workflow step apart from a chemical conversion
            d = (f'M {fmt(T)} L {fmt(pt(T, u, n, length, half))} L {fmt(pt(T, u, n, (1 - SEQ_NOTCH) * length))} '
                 f'L {fmt(pt(T, u, n, length, -half))} Z')
        else:
            d = f'M {fmt(T)} L {fmt(pt(T, u, n, length, half))} L {fmt(pt(T, u, n, length, -half))} Z'
        heads.append(('path', dict(mark, d=d, fill=color, stroke='none')))
        s1 = tip - .6 * length
    elif kind == 'inhibits':
        bw, half = BAR_WEIGHT * sw, BAR_HALF * L
        T, u, n = frame(tip - bw / 2, L)
        heads.append(('path', dict(mark, d=f'M {fmt(pt(T, u, n, 0.0, half))} L {fmt(pt(T, u, n, 0.0, -half))}',
                                   **{'stroke-width': bw, 'stroke-linecap': 'butt'})))
        s1 = tip - bw / 2
    # The line body always comes first, even when it is only a stub inside its symbol: the PowerPoint
    # export (ppt_connections.bind_scene_connections) takes a relation's first vector as its line.
    s1 = max(s1, s0)
    if indirect:
        # Whole dashes at both ends: split the visible length evenly. Explicit pieces (not a
        # dasharray) keep the dashes in native PowerPoint conversion.
        dash, gap = max(1.0, 4.0 * sw), max(.6, 2.6 * sw)
        length = s1 - s0
        count = max(1, math.floor((length + gap) / (dash + gap) + .5))
        if count < 2 and length >= gap + 1.0:
            count = 2
        dash = length if count == 1 else (length - (count - 1) * gap) / count
        pieces = []
        for i in range(count):
            a = s0 + i * (dash + gap)
            pieces.append(sub(t_at(a), t_at(min(s1, a + dash))))
        d = ' '.join(pieces)
    else:
        d = sub(t_at(s0), t_at(s1))
    body = ('path', dict(common, d=d, **{'data-line-body': 'true', 'data-indirect': str(bool(indirect)).lower()}))
    return [body] + heads
