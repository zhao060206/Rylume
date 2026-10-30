"""Deterministic biological scene layout and physical-size SVG rendering."""
from __future__ import annotations
import copy
import html
import math
from functools import lru_cache

from biology_glyphs import symbol,tint
from scene_document import PT_MM,normalize_scene

DEFAULT_DIMS={
    'symbol':(22,24),
    'ligand':(13,9),'receptor':(11,20),'receptor_dimer':(17,21),'gpcr':(18,19),
    'kinase':(17,12),'protein':(17,12),'tf':(18,12),'dna':(29,9),'mrna':(24,8),
    'lipid':(9,9),'vesicle':(24,24),'mvb':(29,29),'vesicle_fusion':(29,26),
    'nucleus':(32,28),'mitochondrion':(26,17),'golgi':(23,19),'er':(27,20),
    'cell':(25,23),'tumor_cell':(25,23),'immune_cell':(23,23),'fibroblast':(28,16),
    'endothelial':(28,18),'collagen':(25,26),'tissue':(34,29),'complex':(22,16),
    'domain':(18,10),'process':(27,17),'text':(28,3),
    'pathogen':(18,18),'membrane':(60,7),'nuclear_pore':(7,9),'antibody':(16,18),'junction':(26,16),'channel':(18,19),'stem_cell':(22,22),'organelle':(26,20),
}


def _escape(value):return html.escape(str(value),quote=True)


def _put(obj,x,y,w,h,force):
    for key,value in zip(('x','y','w','h'),(x,y,w,h)):
        if force or key not in obj:obj[key]=round(value,4)


def layout_scene(scene,force=False):
    scene=normalize_scene(copy.deepcopy(scene))
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    if not force and all(all(k in o for k in ('x','y','w','h')) for o in scene['objects']) and all(all(k in c for k in ('x','y','w','h')) for c in scene['compartments']):return scene
    if scene['style'].get('template'):
        from scene_templates import place_template
        return place_template(scene)
    pad=7 if cw<110 else 8
    objects=scene['objects']
    mode=scene.get('layout','pathway')
    if scene['compartments']:
        narrow=cw<110
        nuclear=any(c['kind']=='nucleus' or c['id']=='nucleus' for c in scene['compartments'])
        membrane_y=25 if narrow else 31
        membrane_h=6
        nucleus_y=ch-33 if nuclear else ch-pad
        for c in scene['compartments']:
            kind=c['kind']
            if kind=='extracellular':box=(pad,5,cw-2*pad,membrane_y-5)
            elif kind in ('membrane','plasma_membrane'):box=(pad,membrane_y,cw-2*pad,membrane_h)
            elif kind=='nucleus':box=(pad,nucleus_y,cw-2*pad,ch-nucleus_y-pad)
            else:box=(pad,membrane_y+membrane_h+1,cw-2*pad,max(12,nucleus_y-membrane_y-membrane_h-2))
            for key,value in zip(('x','y','w','h'),box):c[key]=round(value,3)
        compmap={c['id']:c for c in scene['compartments']}
        by_comp={}
        for o in objects:by_comp.setdefault(o.get('compartment') or 'cytoplasm',[]).append(o)
        for cid,items in by_comp.items():
            c=compmap.get(cid)
            kind=c['kind'] if c else 'cytoplasm'
            if kind=='extracellular':
                for i,o in enumerate(items):
                    w,h=DEFAULT_DIMS[o['type']];cx=pad+(cw-2*pad)*(i+1)/(len(items)+1)
                    # Align a ligand to its membrane binding partner rather
                    # than to an unrelated decorative cell centre.
                    targets=[r['target'] for r in scene['relations'] if r['source']==o['id']]
                    membrane_objects=[x for x in objects if x['id'] in targets and compmap.get(x.get('compartment'),{}).get('kind')=='membrane']
                    if membrane_objects:
                        siblings=by_comp.get(membrane_objects[0]['compartment'],[])
                        cx=pad+(cw-2*pad)*(siblings.index(membrane_objects[0])+1)/(len(siblings)+1)
                    _put(o,cx-w/2,11 if not narrow else 9,w,h,force)
                    if force or not o.get('label_dx'):
                        o['label_dx']=-w-5 if not narrow else -w-2
                        o['label_dy']=-h-1
            elif kind in ('membrane','plasma_membrane'):
                for i,o in enumerate(items):
                    w,h=DEFAULT_DIMS[o['type']];cx=pad+(cw-2*pad)*(i+1)/(len(items)+1)
                    _put(o,cx-w/2,membrane_y+(membrane_h-h)/2,w,h,force)
            elif kind=='nucleus':
                for i,o in enumerate(items):
                    w,h=DEFAULT_DIMS[o['type']];w=min(w,(cw-2*pad)/(len(items)+.5)-3)
                    cx=pad+15+(cw-2*pad-18)*(i+.5)/len(items)
                    _put(o,cx-w/2,nucleus_y+8,w,min(h,11),force)
            else:
                top=membrane_y+membrane_h+17
                bottom=(nucleus_y-8) if nuclear else ch-pad-8
                cols=(2 if len(items)>4 else 1) if narrow else min(4 if len(items)>6 else 3,len(items))
                if not nuclear and len(items)==4:cols=2
                rows=math.ceil(len(items)/cols)
                if rows>1:
                    top=membrane_y+membrane_h+12
                    bottom=(nucleus_y-7) if nuclear else ch-pad-8
                slot_w=(cw-2*pad-12)/cols
                for i,o in enumerate(items):
                    w,h=DEFAULT_DIMS[o['type']];w=min(w,slot_w-8)
                    row,col=divmod(i,cols)
                    if row%2:col=cols-1-col
                    cx=pad+6+slot_w*(col+.5)
                    y=top+(bottom-top-h)*(row/(rows-1) if rows>1 else .25)
                    _put(o,cx-w/2,y,w,h,force)
    elif mode=='process':
        count=len(objects)
        cols=min(count,max(1,int((cw-2*pad)/34)))
        rows=math.ceil(count/cols) if count else 0
        if rows>1:cols=math.ceil(count/rows)
        if cols:
            slot=(cw-2*pad)/cols
            height=(ch-2*pad)/rows
            for i,o in enumerate(objects):
                row,col=divmod(i,cols);w,h=DEFAULT_DIMS[o['type']]
                if row%2:col=cols-1-col
                w=min(max(w,25),slot-10);h=min(max(h,25),height-17)
                _put(o,pad+slot*(col+.5)-w/2,pad+height*row+(height-h-8)/2,w,h,force)
    elif mode=='assembly':
        groups={}
        for o in objects:groups.setdefault(o.get('group_id') or o['id'],[]).append(o)
        rows=len(groups)
        for row,items in enumerate(groups.values()):
            total=sum(DEFAULT_DIMS[o['type']][0]+5 for o in items)-5
            x=(cw-total)/2
            y=ch*(row+1)/(rows+1)-5
            for o in items:
                w,h=DEFAULT_DIMS[o['type']];_put(o,x,y,w,h,force);x+=w+5
    else:
        n=len(objects)
        if n:
            centre=objects[0] if any(r['source']==objects[0]['id'] or r['target']==objects[0]['id'] for r in scene['relations']) and n>=5 else None
            outer=[o for o in objects if o is not centre]
            if centre:
                w,h=DEFAULT_DIMS[centre['type']];_put(centre,cw/2-w/2,ch/2-h/2,w,h,force)
            for i,o in enumerate(outer):
                w,h=DEFAULT_DIMS[o['type']];a=2*math.pi*i/max(1,len(outer))-math.pi/2
                cx=cw/2+max(0,cw/2-w/2-pad-5)*math.cos(a)
                cy=ch/2+max(0,ch/2-h/2-pad-7)*math.sin(a)
                _put(o,cx-w/2,cy-h/2,w,h,force)
                if cw<110 and centre and o['x']+o['w']/2>cw/2+4:o['label_dx']=8
                elif cw<110 and centre and o['x']+o['w']/2<cw/2-4:o['label_dx']=-8
    # Explicitly placed user objects remain where the author put them.
    return normalize_scene(scene)


@lru_cache(maxsize=4)
def _font(cjk=False):
    try:
        from PIL import ImageFont
        return ImageFont.truetype('C:/Windows/Fonts/msyh.ttc' if cjk else 'C:/Windows/Fonts/arial.ttf',1000)
    except OSError:return None


def _measure(text,fs):
    font=_font(any(ord(c)>255 for c in text))
    return (font.getlength(text)/1000 if font else sum(1 if ord(c)>255 else .53 for c in text))*fs


def _label_lines(o):
    text=o.get('label','');fs=max(7,o.get('font_size_pt',8))*PT_MM
    limit=max(5,o['w']-(10 if o.get('state')=='flow_decision' else 5)) if o.get('state','').startswith('flow_') else max(24,min(42,o['w']+12))
    lines=[];current=''
    words=text.split(' ') if ' ' in text else list(text)
    spacer=' ' if ' ' in text else ''
    for word in words:
        candidate=current+spacer+word if current else word
        if current and _measure(candidate,fs)>limit:lines.append(current);current=word
        else:current=candidate
    if current:lines.append(current)
    return lines or [''],fs


def label_baseline(o,lines,fs):
    if o.get('state','').startswith('legend_'):return o['y']+o['h']/2+fs*.3+o.get('label_dy',0)
    if o.get('state')=='flow_lane':return o['y']+3.5+o.get('label_dy',0)
    if o.get('state','').startswith('flow_'):
        return o['y']+o['h']/2+fs*.3-(len(lines)-1)*fs*1.23/2+o.get('label_dy',0)
    return o['y']+o['h']+fs*1.05+o.get('label_dy',0)


def _object_label_boxes(scene):
    boxes=[]
    for o in scene['objects']:
        if not o.get('visible',True) or not o.get('label') or not all(k in o for k in ('x','y','w','h')):continue
        lines,fs=_label_lines(o);width=max(_measure(t,fs) for t in lines)
        cx=o['x']+o['w']/2+(5 if o.get('state','').startswith('legend_') else 0)+o.get('label_dx',0)
        baseline=label_baseline(o,lines,fs)
        boxes.append({'id':o['id'],'x':cx-width/2,'y':baseline-fs*.8,'w':width,'h':fs*(1.23*(len(lines)-1)+1)})
    return boxes


def label_boxes(scene):
    boxes=_object_label_boxes(scene)
    from relation_visuals import relation_label
    for original in scene['relations']:
        r={**original,'label':relation_label(scene,original)}
        if not r.get('label') or not all(all(k in o for k in ('x','y','w','h')) for o in scene['objects']):continue
        g=connection_geometry(scene,r);width=_measure(r['label'],7*PT_MM)
        boxes.append({'id':r['id'],'x':g['label_x']-width/2,'y':g['label_y']-7*PT_MM*.8,'w':width,'h':7*PT_MM})
    return boxes


def repair_geometry(scene,passes=2):
    """Bounded geometry-only repair; never changes entities, states or edges."""
    scene=layout_scene(copy.deepcopy(scene));cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    for _ in range(min(2,max(0,passes))):
        changed=False
        for o in scene['objects']:
            if o['locked']:continue
            for axis,size,limit in (('x','w',cw),('y','h',ch)):
                value=min(max(.8,o[axis]),max(.8,limit-o[size]-.8))
                if value!=o[axis]:o[axis]=value;changed=True
        for o in scene['objects']:
            if o['locked'] or not o['visible'] or not o['label']:continue
            boxes=label_boxes(scene);box=next(b for b in boxes if b['id']==o['id'])
            obstacles=[(x['x'],x['y'],x['w'],x['h']) for x in scene['objects'] if x['visible'] and x.get('role') != 'context' and x['id']!=o['id']]
            obstacles.extend((b['x'],b['y'],b['w'],b['h']) for b in boxes if b['id']!=o['id'])
            def cost(dx,dy):
                x,y,w,h=box['x']+dx,box['y']+dy,box['w'],box['h']
                if x<.5 or y<.5 or x+w>cw-.5 or y+h>ch-.5:return 10000
                return sum(max(0,min(x+w,ox+ow)-max(x,ox))*max(0,min(y+h,oy+oh)-max(y,oy)) for ox,oy,ow,oh in obstacles)
            if cost(0,0)>.4:
                offsets=[(0,0)]+[(dx,dy) for dx,dy in ((0,4),(0,-4),(0,8),(0,-8),(-8,0),(8,0),(-12,0),(12,0))]
                dx,dy=min(offsets,key=lambda p:(cost(*p),math.hypot(*p)))
                if dx or dy:o['label_dx']+=dx;o['label_dy']+=dy;changed=True
        if not changed:break
    return normalize_scene(scene)


def preview_finding_fix(scene, finding):
    """Find one local layout improvement without saving or changing science."""
    from scene_document import audit_scene, apply_operations
    original=normalize_scene(copy.deepcopy(scene))
    code=finding['code'];ids=finding.get('object_ids',[])
    editable=[o for o in original['objects'] if o['id'] in ids and not o['locked']]
    before=audit_scene(original)
    key=lambda f:(f['code'],tuple(f['object_ids']))
    target=key(finding);known={key(f) for f in before['findings']}
    candidates=[];cw,ch=original['canvas']['width_mm'],original['canvas']['height_mm']
    for o in editable:
        if code=='outside-canvas' and o['w']<=cw and o['h']<=ch:
            candidates.append([{'op':'update','id':o['id'],'changes':{'x':min(max(0,o['x']),cw-o['w']),'y':min(max(0,o['y']),ch-o['h'])}}])
        elif code in ('label-overlap','label-object-overlap','label-outside'):
            # Only move the affected label, never nearby molecules or arrows.
            for dx,dy in [(0,0)]+[(dx,dy) for radius in (3,6,10,16,24) for dx,dy in ((0,radius),(0,-radius),(radius,0),(-radius,0),(radius,radius),(-radius,-radius))]:
                candidates.append([{'op':'update','id':o['id'],'changes':{'label_dx':o['label_dx']+dx,'label_dy':o['label_dy']+dy}}])
    for operations in candidates:
        proposed=apply_operations(original,operations);audit=audit_scene(proposed)
        remaining={key(f) for f in audit['findings']}
        if target not in remaining and not remaining-known:
            return {'operations':operations,'scene':proposed,'audit':audit,'changed':True}
    return {'operations':[],'scene':original,'audit':before,'changed':False,
            'message':'没有找到只调整相关对象就能解决的方案。可以先定位，再手动调整；当前图版没有变化。'}


def connection_geometry(scene,r):
    from relation_visuals import relation_label
    r={**r,"label":relation_label(scene,r)}
    by_id={o['id']:o for o in scene['objects']};a,b=by_id[r['source']],by_id[r['target']]
    dx=(b['x']+b['w']/2)-(a['x']+a['w']/2)
    dy=(b['y']+b['h']/2)-(a['y']+a['h']/2)
    sp=r.get('source_port','auto');tp=r.get('target_port','auto')
    if a['type']=='ligand' and b['type'] in ('receptor','receptor_dimer','gpcr') and dy>0:
        if sp=='auto':sp='s'
        if tp=='auto':tp='n'
    if sp=='auto' and tp=='auto':
        if abs(dy) > abs(dx) * 1.15:
            sp = 's' if dy > 0 else 'n'
            tp = 'n' if dy > 0 else 's'
        else:
            sp = 'e' if dx >= 0 else 'w'
            tp = 'w' if dx >= 0 else 'e'
    elif sp=='auto':
        sp = ('s' if dy > 0 else 'n') if abs(dy) > abs(dx) * 1.15 else ('e' if dx >= 0 else 'w')
    elif tp=='auto':
        tp = ('n' if dy > 0 else 's') if abs(dy) > abs(dx) * 1.15 else ('w' if dx >= 0 else 'e')
    def point(o,p,anchor=None):
        cx,cy=o['x']+o['w']/2,o['y']+o['h']/2
        if anchor:p=anchor['side']
        x,y={'e':(o['x']+o['w'],cy),'w':(o['x'],cy),'n':(cx,o['y']),'s':(cx,o['y']+o['h'])}.get(p,(cx,cy))
        if anchor:
            if p in ('n','s'):x=o['x']+o['w']*anchor['t']
            else:y=o['y']+o['h']*anchor['t']
        angle=math.radians(o.get('rotation',0));return (cx+(x-cx)*math.cos(angle)-(y-cy)*math.sin(angle),cy+(x-cx)*math.sin(angle)+(y-cy)*math.cos(angle))
    x1,y1=point(a,sp,r.get('source_anchor'));x2,y2=point(b,tp,r.get('target_anchor'))
    control=r.get('control') or {'x':(x1+x2)/2,'y':(y1+y2)/2}
    if not r.get('control') and not (r.get('source_anchor') or r.get('target_anchor')) and sp==tp:control={'x':max(x1,x2)+12,'y':(y1+y2)/2}
    if not r.get('control'):
        obstacles=[(o['x']-1,o['y']-1,o['w']+2,o['h']+2) for o in scene['objects']
                   if o.get('visible', True) and o.get('role') != 'context' and o['id'] not in (a['id'],b['id'])]
        def cost(c):
            hit=0
            for i in range(1,30):
                t=i/30;u=1-t
                x=u*u*x1+2*u*t*c['x']+t*t*x2;y=u*u*y1+2*u*t*c['y']+t*t*y2
                hit+=sum(1 for ox,oy,ow,oh in obstacles if ox<x<ox+ow and oy<y<oy+oh)
                if x<1 or y<1 or x>scene['canvas']['width_mm']-1 or y>scene['canvas']['height_mm']-1:hit+=4
            return hit
        if cost(control):
            midx,midy=(x1+x2)/2,(y1+y2)/2
            candidates=[control]+[{'x':midx+dx,'y':midy+dy} for dx,dy in ((0,-18),(0,18),(0,-36),(0,36),(-24,0),(24,0),(0,-60),(0,60))]
            control=min(candidates,key=lambda c:(cost(c),math.hypot(c['x']-midx,c['y']-midy)))
    cx,cy=control['x'],control['y'];length=math.hypot(x2-cx,y2-cy) or 1
    lx,ly=.25*x1+.5*cx+.25*x2,.25*y1+.5*cy+.25*y2-1.7
    if r.get('label_position'):
        lx,ly=r['label_position']['x'],r['label_position']['y']
    elif r.get('label'):
        width=_measure(r['label'],7*PT_MM);height=7*PT_MM
        boxes=[(o['x'],o['y'],o['w'],o['h']) for o in scene['objects'] if o['visible'] and o.get('role') != 'context']
        boxes.extend((b['x'],b['y'],b['w'],b['h']) for b in _object_label_boxes(scene))
        def label_cost(offset):
            x,y=lx+offset[0]-width/2,ly+offset[1]-height*.8
            if x<.5 or y<.5 or x+width>scene['canvas']['width_mm']-.5 or y+height>scene['canvas']['height_mm']-.5:return 10000
            return sum(max(0,min(x+width,ox+ow)-max(x,ox))*max(0,min(y+height,oy+oh)-max(y,oy)) for ox,oy,ow,oh in boxes)
        offsets=[(0,0),(0,-4),(0,4),(0,-8),(0,8),(-8,0),(8,0),(0,-12),(0,12),(-12,0),(12,0),(-18,0),(18,0),(-24,0),(24,0),(-18,4),(18,4)]
        dx,dy=min(offsets,key=lambda p:(label_cost(p),math.hypot(*p)))
        lx+=dx;ly+=dy
    return {'x1':x1,'y1':y1,'x2':x2,'y2':y2,'control':control,
            'path':f'M {x1:.4f} {y1:.4f} Q {cx:.4f} {cy:.4f} {x2:.4f} {y2:.4f}',
            'ux':(x2-cx)/length,'uy':(y2-cy)/length,'label_x':lx,'label_y':ly}


def _text(x,y,text,size=8,fill='#2F4552',anchor='start',bold=False,**attributes):
    attrs=' '.join(f'{key.replace("_","-")}="{_escape(value)}"' for key,value in attributes.items())
    return f'<text x="{x:.4f}" y="{y:.4f}" font-size="{max(7,size)*PT_MM:.5f}" font-family="Arial,Microsoft YaHei,sans-serif" fill="{fill}" text-anchor="{anchor}" font-weight="{600 if bold else 400}" {attrs}>{_escape(text)}</text>'


def _compartment(c,primary,organic=False):
    x,y,w,h=(c[k] for k in ('x','y','w','h'));kind=c['kind'];p=[]
    if kind in ('membrane','plasma_membrane'):
        p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{tint(primary,.91)}"/>')
        for step in range(int(w/2.3)+1):
            xx=x+step*2.3
            p.append(f'<path d="M {xx-.3} {y+1.3} L {xx-.5} {y+h/2} M {xx+.3} {y+1.3} L {xx+.5} {y+h/2} M {xx-.3} {y+h-1.3} L {xx-.5} {y+h/2} M {xx+.3} {y+h-1.3} L {xx+.5} {y+h/2}" fill="none" stroke="{tint(primary,.45)}" stroke-width=".13"/>')
            for yy in (y+.7,y+h-.7):p.append(f'<circle cx="{xx}" cy="{yy}" r=".55" fill="{tint(primary,.25)}"/>')
    elif kind=='nucleus':
        if organic:
            p.append(f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2}" ry="{h/2}" fill="{tint(primary,.94)}" stroke="{tint(primary,.35)}" stroke-width=".4"/>')
            p.append(f'<ellipse cx="{x+w/2}" cy="{y+h/2}" rx="{w/2-1.3}" ry="{h/2-1.3}" fill="none" stroke="{tint(primary,.5)}" stroke-width=".23"/>')
            p.append(_text(x+w/2,y+6,c['label'],7,anchor='middle',fill='#657D8B'))
            return ''.join(p)
        p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="5" fill="{tint(primary,.96)}" stroke="{tint(primary,.5)}" stroke-width=".3"/>')
        p.append(f'<path d="M {x+3} {y+1.5} L {x+w-3} {y+1.5}" fill="none" stroke="{tint(primary,.6)}" stroke-width=".2"/>')
        for xx in range(round(x+12),round(x+w-5),13):p.append(f'<rect x="{xx}" y="{y-.45}" width="2" height="2.3" rx=".4" fill="#FFFFFF" stroke="{tint(primary,.4)}" stroke-width=".2"/>')
    else:p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{tint(primary,.985) if kind=="extracellular" else "#FFFFFF"}"/>')
    if kind!='membrane':p.append(_text(x+2,y+4,c['label'],7,fill='#81929B'))
    # A membrane is already recognizable; its long label goes in the caption
    # rather than on top of receptor and lipid objects.
    return ''.join(p)


def _object(o,palette,stroke_pt=.8,glyph_tint=.8):
    oid=o['id'];kind=o['type'];x,y,w,h=(o[k] for k in ('x','y','w','h'))
    family=palette['accent'] if kind=='ligand' else palette['secondary'] if kind in ('tf','dna','mrna','complex','domain','fibroblast','collagen','tissue') else palette['primary']
    color=o.get('fill') or family;line=o.get('stroke') or family
    angle=o.get('rotation',0)
    if o.get('illustration'):
        artwork = ('<image href="' + _escape(o['illustration']['data'])
                   + '" x="0" y="0" width="100" height="100" preserveAspectRatio="xMidYMid meet"/>')
    elif o.get('asset_id'):
        from scientific_library import glyph
        if o.get('asset_snapshot'):
            from scientific_library import portable_glyph
            artwork=portable_glyph(o['asset_snapshot']['svg'],o.get('fill'),o.get('stroke'))
        else:artwork=glyph(o['asset_id'],o.get('fill'),o.get('stroke'))
    else:artwork=symbol(kind,color,o.get('state') or (o.get('label','') if kind in ('cell','stem_cell') else ''),line,o.get('stroke_pt',stroke_pt)/.8,glyph_tint)
    p=[f'<g data-object-id="{oid}" data-type="{kind}" id="obj-{oid}">',f'<g data-glyph="{oid}" transform="rotate({angle} {x+w/2} {y+h/2})"><g transform="translate({x} {y}) scale({w/100} {h/100})">',artwork,'</g>']
    if o.get('state') == 'phosphorylated' and kind in ('kinase','protein','receptor','receptor_dimer'):
        bx,by=x+w-1,y+1
        p.append(f'<circle cx="{bx}" cy="{by}" r="1.65" fill="{tint(palette["accent"],.4)}" stroke="#FFFFFF" stroke-width=".3"/>')
        p.append(_text(bx,by+.86,'P',7,anchor='middle',fill='#7D5B26'))
    p.append('</g>')
    lines,fs=_label_lines(o)
    for i,text in enumerate(lines):p.append(_text(x+w/2+(5 if o.get('state','').startswith('legend_') else 0)+o.get('label_dx',0),label_baseline(o,lines,fs)+i*fs*1.23,text,o.get('font_size_pt',8),anchor='middle',data_label_for=oid))
    p.append('</g>');return ''.join(p)


def _relation(scene,r,palette):
    from relation_visuals import relation_parts, relation_label
    g=connection_geometry(scene,r);color=r.get('stroke') or ('#AD6460' if r['type']=='inhibits' else palette['primary'])
    p=[f'<g data-relation-id="{r["id"]}" data-relation-type="{r["type"]}" id="rel-{r["id"]}">']
    for tag,attrs in relation_parts(r['type'],(g['x1'],g['y1']),(g['x2'],g['y2']),
                                    (g['control']['x'],g['control']['y']),color,r.get('stroke_pt',1.05),r.get('indirect',False),
                                    anchored_start=bool(r.get('source_anchor')),anchored_end=bool(r.get('target_anchor'))):
        p.append('<'+tag+' '+' '.join(f'{key}="{_escape(value)}"' for key,value in attrs.items())+'/>')
    label=relation_label(scene,r)
    if label:
        width=_measure(label,7*PT_MM)
        p.append(f'<rect x="{g["label_x"]-width/2-.6:.4f}" y="{g["label_y"]-2:.4f}" width="{width+1.2:.4f}" height="2.7" rx=".3" fill="#FFFFFF"/>')
        p.append(_text(g['label_x'],g['label_y'],label,7,anchor='middle',fill=color))
    if r.get('uncertain'):p.append(_text(g['label_x'],g['label_y']+3,'?',7,anchor='middle',fill='#A3783B'))
    return ''.join(p)+'</g>'


def render_scene(scene):
    scene=layout_scene(scene)
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm'];palette=scene['style']['palette']
    p=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw}mm" height="{ch}mm" viewBox="0 0 {cw} {ch}" data-version="2" data-revision="{scene["revision"]}">',f'<title>{_escape(scene["title"])}</title>',f'<rect width="{cw}" height="{ch}" fill="#FFFFFF"/>','<g id="layer-compartments">']
    from scientific_library import credits
    import json
    p.insert(2,'<metadata>'+_escape(json.dumps({'artwork_credits':credits(scene)},ensure_ascii=False))+'</metadata>')
    tid=scene['style'].get('template','')
    if tid=='process_cell':
        p.append(f'<g transform="scale({cw/180} {ch/120})"><path d="M 10 31 C 14 6 89 6 115 25 C 140 43 139 62 130 82 C 111 91 35 93 13 76 C 3 62 1 44 10 31 Z" fill="{tint(palette["primary"],.92)}" stroke="{tint(palette["primary"],.3)}" stroke-width=".45"/><path d="M 13 33 C 19 10 87 11 112 28" fill="none" stroke="{tint(palette["primary"],.55)}" stroke-width=".3"/></g>')
        p.append(_text(16*cw/180,25*ch/120,'Cell interior',8,fill='#5D7683'))
        p.append(_text(155*cw/180,116*ch/120,'Extracellular',7,anchor='middle',fill='#5D7683'))
    elif tid=='network_tissue':
        p.append(f'<path d="M 5 {ch*.82} Q {cw*.25} {ch*.77} {cw*.5} {ch*.82} T {cw-5} {ch*.82} L {cw-5} {ch-6} H 5 Z" fill="{tint(palette["secondary"],.93)}"/>')
        for i in range(7):p.append(f'<path d="M {cw*(.06+i*.13)} {ch*.87} q 7 -2 15 0" fill="none" stroke="{tint(palette["secondary"],.55)}" stroke-width=".3"/>')
    p.extend(_compartment(c,palette['primary'],tid=='signal_cell') for c in scene['compartments']);p.append('</g><g id="layer-context">')
    p.extend(_object(o,palette,scene['style']['stroke_pt'],scene['style']['glyph_tint']) for o in scene['objects'] if o['visible'] and o.get('role')=='context')
    p.append('</g><g id="layer-relations">')
    objects={o['id']:o for o in scene['objects']}
    p.extend(_relation(scene,r,palette) for r in scene['relations'] if objects[r['source']]['visible'] and objects[r['target']]['visible'])
    p.append('</g><g id="layer-objects">');p.extend(_object(o,palette,scene['style']['stroke_pt'],scene['style']['glyph_tint']) for o in scene['objects'] if o['visible'] and o.get('role')!='context');p.append('</g>')
    if scene['style'].get('show_title'):p.append(_text(cw/2,4,scene['title'],10,anchor='middle',bold=True))
    if any(r.get('indirect') or r.get('uncertain') for r in scene['relations']):p.append(_text(cw-8,ch-2.5,'Dashed: indirect effect; ?: meaning to verify',7,anchor='end',fill='#82919A'))
    p.append('</svg>');return ''.join(p)
