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


def relation_parts(kind, start, end, control, color, stroke_pt=1.05, indirect=False, *, anchored_start=False, anchored_end=False):
    """Return SVG primitives. Coordinates and widths use physical millimetres."""
    x1,y1=start; x2,y2=end; cx,cy=control
    # Keep symbols clear of object outlines, including when rendered below them.
    vx,vy=cx-x1,cy-y1; length=math.hypot(vx,vy) or 1
    gap=0 if anchored_start else 1.2
    x1+=vx/length*gap; y1+=vy/length*gap
    vx,vy=x2-cx,y2-cy; length=math.hypot(vx,vy) or 1
    ux,uy=vx/length,vy/length;gap=0 if anchored_end else 1.2;x2-=ux*gap;y2-=uy*gap
    sw=stroke_pt*25.4/72
    common={'fill':'none','stroke':color,'stroke-width':sw,'stroke-linecap':'round','stroke-linejoin':'round'}
    if indirect:
        # Explicit segments preserve dashes in native PowerPoint conversion.
        points=[((1-i/120)**2*x1+2*(1-i/120)*(i/120)*cx+(i/120)**2*x2,
                 (1-i/120)**2*y1+2*(1-i/120)*(i/120)*cy+(i/120)**2*y2) for i in range(121)]
        segments=[];distance=0
        for a,b in zip(points,points[1:]):
            if distance%2.5<1.5:segments.append(f'M {a[0]} {a[1]} L {b[0]} {b[1]}')
            distance+=math.dist(a,b)
        path=' '.join(segments)
    else:path=f'M {x1} {y1} Q {cx} {cy} {x2} {y2}'
    parts=[('path',dict(common,d=path,**{'data-line-body':'true','data-indirect':str(bool(indirect)).lower()}))]
    def at(back,side=0):return f'{x2-ux*back-uy*side} {y2-uy*back+ux*side}'
    attrs=dict(common,**{'data-endpoint':BY_ID[kind]['symbol']})
    if kind=='inhibits':parts.append(('path',dict(attrs,d=f'M {at(0,2.8)} L {at(0,-2.8)}',**{'stroke-width':max(sw,.58)})))
    elif kind=='activates':parts.append(('path',dict(attrs,d=f'M {at(3.0,1.45)} L {at(0)} L {at(3.0,-1.45)}')))
    elif kind=='sequence':parts.append(('path',dict(attrs,d=f'M {at(2.2,1.1)} L {at(0)} L {at(2.2,-1.1)} Z',fill=color)))
    elif kind=='converts':parts.append(('path',dict(attrs,d=f'M {at(3.2,1.5)} L {at(0)} L {at(3.2,-1.5)} Z',fill=color)))
    elif kind=='transports':
        parts.append(('path',dict(attrs,d=' '.join(f'M {at(b+2.4,1.25)} L {at(b)} L {at(b+2.4,-1.25)}' for b in (0,2.5)))))
    elif kind=='binds':
        for x,y in ((x1,y1),(x2,y2)):parts.append(('circle',dict(attrs,cx=x,cy=y,r=1.15,fill='#FFFFFF')))
    return parts
