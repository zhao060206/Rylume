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
    scene=normalize_scene(scene)
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    if not force and all(all(k in o for k in ('x','y','w','h')) for o in scene['objects']) and all(all(k in c for k in ('x','y','w','h')) for c in scene['compartments']):return scene
    if scene['style'].get('template'):
        from scene_templates import place_template
        return place_template(scene)
    pad=7 if cw<110 else 8
    objects=[o for o in scene['objects'] if not o.get('parent_id')]
    mode=scene.get('layout','pathway')
    from scene_topology import rank_layout
    ranked=not scene['compartments'] and mode in ('process','pathway') and rank_layout(scene,objects,force,_put,DEFAULT_DIMS)
    if ranked:pass
    elif scene['compartments']:
        narrow=cw<110
        nuclear=any(c['kind']=='nucleus' or c['id']=='nucleus' for c in scene['compartments'])
        membrane_y=30 if narrow else 31
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
                    y=11 if not narrow else 9
                    if membrane_objects:
                        # Leave 7 mm between the ligand and the receptor it binds, so the
                        # binding symbol (two 2 mm discs) keeps a visible stretch of line.
                        m=membrane_objects[0]
                        mh=m['h'] if not force and 'h' in m else DEFAULT_DIMS[m['type']][1]
                        mt=m['y'] if not force and 'y' in m else membrane_y+(membrane_h-mh)/2
                        y=max(6,min(y,mt-7-h))
                    _put(o,cx-w/2,y,w,h,force)
            elif kind in ('membrane','plasma_membrane'):
                for i,o in enumerate(items):
                    w,h=DEFAULT_DIMS[o['type']];cx=pad+(cw-2*pad)*(i+1)/(len(items)+1)
                    _put(o,cx-w/2,membrane_y+(membrane_h-h)/2,w,h,force)
            elif kind=='nucleus':
                plan=[]
                for i,o in enumerate(items):
                    w,h=DEFAULT_DIMS[o['type']];w=min(w,(cw-2*pad)/(len(items)+.5)-3)
                    cx=pad+15+(cw-2*pad-18)*(i+.5)/len(items)
                    plan.append([o,cx,w,h])
                _widen_label_gaps(scene,plan,pad+1,cw-pad-1)
                for o,cx,w,h in plan:_put(o,cx-w/2,nucleus_y+8,w,min(h,11),force)
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
            # Outer neighbours on about the same row (a mirrored pair at the bottom of a narrow
            # page) keep 9 mm between them: widen the ring up to the page margin if needed.
            k=max(1,len(outer));ang=[2*math.pi*i/k-math.pi/2 for i in range(k)]
            dims=[DEFAULT_DIMS[o['type']] for o in outer];rx=min(cw/2-d[0]/2-pad-5 for d in dims) if dims else 0
            ry=min(ch/2-d[1]/2-pad-7 for d in dims) if dims else 0
            for i in range(k):
                j=(i+1)%k
                if j==i or abs(ry*(math.sin(ang[i])-math.sin(ang[j])))>=(dims[i][1]+dims[j][1])/2:continue
                spread=abs(math.cos(ang[i])-math.cos(ang[j]))
                if spread>1e-6:rx=max(rx,((dims[i][0]+dims[j][0])/2+9)/spread)
            rx_cap=min(cw/2-d[0]/2-pad for d in dims) if dims else 0
            for i,o in enumerate(outer):
                w,h=DEFAULT_DIMS[o['type']];a=2*math.pi*i/max(1,len(outer))-math.pi/2
                cx=cw/2+min(max(0,cw/2-w/2-pad),max(max(0,cw/2-w/2-pad-5),min(rx,rx_cap)))*math.cos(a)
                cy=ch/2+max(0,ch/2-h/2-pad-7)*math.sin(a)
                _put(o,cx-w/2,cy-h/2,w,h,force)
                if cw<110 and centre and o['x']+o['w']/2>cw/2+4:o['label_dx']=8
                elif cw<110 and centre and o['x']+o['w']/2<cw/2-4:o['label_dx']=-8
    # Contained objects participate in their parent's layout, not in a second
    # unrelated grid. Explicitly placed user objects remain where put.
    by_id={o['id']:o for o in scene['objects']}
    def place_children(parent):
        children=[o for o in scene['objects'] if o.get('parent_id')==parent['id']]
        for index,o in enumerate(children):
            w,h=DEFAULT_DIMS[o['type']];w=min(w,parent['w']*.65);h=min(h,parent['h']*.4)
            note=ranked and any(r.get('callout') and r['source']==o['id'] and r['target']==parent['id'] for r in scene['relations'])
            if note:
                w=min(cw-8,max(parent['w'],_measure(o['label'],o.get('font_size_pt',8)*PT_MM)+2));h=3
                x=max(4,min(cw-w-4,parent['x']+parent['w']/2-w/2));y=parent['y']+parent['h']+7+index*7
                o['label_dy']=-2
            elif o.get('placement')=='outside':
                x=parent['x']+(parent['w']-w)/2;y=parent['y']-h-5
            elif o.get('placement')=='boundary':
                x=parent['x']+parent['w']*(index+1)/(len(children)+1)-w/2;y=parent['y']-h/2
            else:
                x=parent['x']+(parent['w']-w)/2;y=parent['y']+(parent['h']-h)*(index+1)/(len(children)+1)
            _put(o,x,y,w,h,force if note else force and not (ranked and o.get('placement')=='outside'));place_children(o)
    for o in objects:place_children(o)
    if scene['compartments'] and not ranked:_auto_object_labels(scene,force)
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


LABEL_GAP_MM=1.5
# White halo under object labels so they stay readable on membranes and
# patterned shapes. paint-order keeps it one text element (still one
# editable text in SVG/PPTX); the stroke does not change measured width.
LABEL_HALO={'stroke':'#FFFFFF','stroke_width':'0.6','stroke_linejoin':'round','stroke_opacity':'0.85','paint_order':'stroke'}
# MuPDF's SVG->PDF writer puts adjacent text runs that start at the same
# origin into one BT/ET block without repeating Tm, so a label drawn with
# fill and halo stroke in one <text> gets its stroke one word to the right;
# it also ignores paint-order.  Before any MuPDF rasterisation, split each
# halo label into stroke-only text, a no-op path (which ends the text block)
# and fill-only text.  render_scene output itself is left unchanged.
import re as _re
_HALO_TEXT=_re.compile(r'<text\b([^>]*\bpaint-order="stroke"[^>]*)>(.*?)</text>',_re.S)
_STROKE_ATTRS=_re.compile(r'\s(?:stroke(?:-[a-z]+)?|paint-order)="[^"]*"')
_HALO_DROP=_re.compile(r'\s(?:fill|data-label-for|paint-order)="[^"]*"')
def svg_for_mupdf(svg):
    def split(m):
        attrs,inner=m.group(1),m.group(2)
        if ' stroke=' not in attrs:return m.group(0)
        halo=_HALO_DROP.sub('',attrs)+' fill="none"'
        plain=_STROKE_ATTRS.sub('',attrs)
        return f'<text{halo}>{inner}</text><path d="M0 0"/><text{plain}>{inner}</text>'
    return _HALO_TEXT.sub(split,svg)
MEMBRANE_KINDS=('membrane','plasma_membrane')


def _label_extent(o):
    lines,fs=_label_lines(o)
    return max(_measure(t,fs) for t in lines),fs*(1.23*(len(lines)-1)+1),fs


def _label_box_at(o,dx,dy,width,height,fs):
    # Same rectangle _object_label_boxes reports for a plain object label.
    cx=o['x']+o['w']/2+dx;baseline=o['y']+o['h']+fs*1.05+dy
    return {'id':o['id'],'x':cx-width/2,'y':baseline-fs*.8,'w':width,'h':height}


def _boxes_touch(a,b,margin=.3):
    return a['x']<b['x']+b['w']+margin and b['x']<a['x']+a['w']+margin and a['y']<b['y']+b['h']+margin and b['y']<a['y']+a['h']+margin


def _generic_label_offsets(o):
    # Fallback spots for any object label, used by the review fix when the
    # type-specific choices (ligand / membrane) do not apply: above the
    # shape, left, right (at mid height) and, for large shapes, inside the top edge.
    width,height,fs=_label_extent(o)
    mid=-o['h']/2-.25*fs-height/2
    spots=[(0,-o['h']-LABEL_GAP_MM-.25*fs-height),(-o['w']/2-LABEL_GAP_MM-width/2,mid),(o['w']/2+LABEL_GAP_MM+width/2,mid)]
    if o['h']>=height+2*LABEL_GAP_MM+2 and o['w']>=width+2:spots.append((0,-o['h']+LABEL_GAP_MM+height))
    return spots


def auto_label_offset(scene,o,placed=(),all_options=False):
    # Offsets (dx, dy) that keep a label against its shape and inside its
    # compartment, or None when the default below-object label is right.
    # Extracellular ligands: left of the shape, right if there is no room.
    # Membrane objects: beside the shape at membrane height; above it (the
    # extracellular side) only if both sides are blocked; never below it,
    # which would put the text in the cytoplasm.
    if o['type']=='text' or not o.get('label') or o.get('state')=='import_text' or str(o.get('state','')).startswith(('legend_','flow_')):return None
    if not all(k in o for k in ('x','y','w','h')):return None
    kind={c['id']:c['kind'] for c in scene['compartments']}.get(o.get('compartment'),'')
    if kind=='extracellular' and o['type']=='ligand':order=('left','right')
    elif kind in MEMBRANE_KINDS:order=('left','right','above')
    else:return None
    width,height,fs=_label_extent(o)
    mid=-o['h']/2-.25*fs-height/2
    options={'left':(-o['w']/2-LABEL_GAP_MM-width/2,mid),'right':(o['w']/2+LABEL_GAP_MM+width/2,mid),
             'above':(0,-o['h']-LABEL_GAP_MM-.25*fs-height)}
    if all_options:return [options[s] for s in order]
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    def encloses(x):return x['x']<=o['x'] and x['y']<=o['y'] and x['x']+x['w']>=o['x']+o['w'] and x['y']+x['h']>=o['y']+o['h']
    obstacles=[{k:x[k] for k in ('x','y','w','h')} for x in scene['objects'] if x is not o and x.get('visible',True) and all(k in x for k in ('x','y','w','h')) and not encloses(x)]+list(placed)
    for side in order:
        box=_label_box_at(o,*options[side],width,height,fs)
        if box['x']<1 or box['y']<1 or box['x']+box['w']>cw-1 or box['y']+box['h']>ch-1:continue
        if any(_boxes_touch(box,b) for b in obstacles):continue
        return options[side]
    return options[order[0]]


def _auto_object_labels(scene,force):
    # Hand-placed labels (label_user_set) are never moved.
    placed=[]
    for o in scene['objects']:
        if o.get('label_user_set') or not (force or (not o.get('label_dx') and not o.get('label_dy'))):continue
        offset=auto_label_offset(scene,o,placed)
        if offset is None:continue
        o['label_dx'],o['label_dy']=round(offset[0],4),round(offset[1],4)
        width,height,fs=_label_extent(o)
        placed.append(_label_box_at(o,o['label_dx'],o['label_dy'],width,height,fs))


def _label_lines(o):
    text=o.get('label','');fs=max(7,o.get('font_size_pt',8))*PT_MM
    if o.get('state')=='import_text':return str(text).split('\n'),fs
    limit=max(5,o['w']) if o.get('type')=='text' else max(5,o['w']-(10 if o.get('state')=='flow_decision' else 5)) if o.get('state','').startswith('flow_') else max(24,min(42,o['w']+12))
    lines=[]
    for explicit in str(text).split('\n'):
        start=len(lines)
        current='';words=explicit.split(' ') if ' ' in explicit else list(explicit)
        spacer=' ' if ' ' in explicit else ''
        for word in words:
            candidate=current+spacer+word if current else word
            if current and _measure(candidate,fs)>limit+.001:lines.append(current);current=word
            else:current=candidate
        if current:lines.append(current)
        if len(lines)-start>1 and len(lines[-1])==1 and len(lines[-2])>2 and any('\u4e00'<=c<='\u9fff' for c in explicit) and ' ' not in explicit:
            joined=lines[-2]+lines[-1];cut=(len(joined)+1)//2;lines[-2:]=[joined[:cut],joined[cut:]]
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
        if uses_text_appearance(o):
            boxes.append({k:o[k] for k in ('id','x','y','w','h')});continue
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
        elif code in ('label-detached','label-wrong-compartment'):
            # Preferred side first, then the other sides, then the default.
            auto=auto_label_offset(original,o)
            ordered=([auto] if auto else [])+[p for p in auto_label_offset(original,o,all_options=True) or [] if p!=auto]
            for dx,dy in ordered+[p for p in [(0,0)]+_generic_label_offsets(o) if p not in ordered]:
                candidates.append([{'op':'update','id':o['id'],'changes':{'label_dx':round(dx,4),'label_dy':round(dy,4),'label_user_set':False}}])
        elif code in ('label-overlap','label-object-overlap','label-outside','line-label-overlap'):
            # Only move the affected label, never nearby molecules or arrows.
            for dx,dy in [(0,0)]+[(dx,dy) for radius in (3,6,10,16,24) for dx,dy in ((0,radius),(0,-radius),(radius,0),(-radius,0),(radius,radius),(-radius,-radius))]:
                candidates.append([{'op':'update','id':o['id'],'changes':{'label_dx':o['label_dx']+dx,'label_dy':o['label_dy']+dy,'label_user_set':bool(o.get('label_user_set'))}}])
    if code=='line-label-overlap':
        for r in original['relations']:
            if r['id'] not in ids:continue
            g=connection_geometry(original,r);mx,my=(g['x1']+g['x2'])/2,(g['y1']+g['y2'])/2
            candidates=[[{'op':'update_relation','id':r['id'],'changes':{'control':c}}] for c in _bend_candidates(g['x1'],g['y1'],g['x2'],g['y2'])]+candidates
    if code in ('label-object-overlap','label-overlap','line-label-overlap'):
        for r in original['relations']:
            if r['id'] not in ids or not r.get('label'):continue
            g=connection_geometry(original,r)
            for radius in (3,6,10,16,24):
                for dx,dy in ((0,radius),(0,-radius),(radius,0),(-radius,0),(radius,radius),(-radius,-radius)):
                    candidates.append([{'op':'update_relation','id':r['id'],'changes':{'label_position':{'x':g['label_x']+dx,'y':g['label_y']+dy}}}])
    if code=='line-label-detached':
        # Pin the label beside its own line: the same normal-side spots the
        # automatic placement tries, nearest first.
        for r in original['relations']:
            if r['id'] not in ids or not r.get('label'):continue
            g=connection_geometry(original,r);c=g['control']
            width=_measure(r['label'],7*PT_MM);height=7*PT_MM
            bx=.25*g['x1']+.5*c['x']+.25*g['x2'];by=.25*g['y1']+.5*c['y']+.25*g['y2']-1.7
            for dx,dy in _label_offsets(g['x1'],g['y1'],c,g['x2'],g['y2'],width,height)[:20]:
                pos={'x':round(bx+dx,4),'y':round(by+dy,4)}
                # A pinned label is skipped by the review, so check the gap here.
                if round(line_label_gap(original,{**r,'label_position':pos}),1)>4:continue
                candidates.append([{'op':'update_relation','id':r['id'],'changes':{'label_position':pos}}])
    if code in ('connector-hook','connector-overshoot','line-through-object','connector-through-end','connector-outside-canvas','connector-symbol-on-label'):
        # Re-route only this connector: automatic route, gentle bends, then other sides.
        for r in original['relations']:
            if not ids or r['id']!=ids[0]:continue
            g=connection_geometry(original,r)
            candidates.append([{'op':'update_relation','id':r['id'],'changes':{'control':None,'source_port':'auto','target_port':'auto'}}])
            candidates.append([{'op':'update_relation','id':r['id'],'changes':{'control':None}}])
            for c in _bend_candidates(g['x1'],g['y1'],g['x2'],g['y2']):
                candidates.append([{'op':'update_relation','id':r['id'],'changes':{'control':c}}])
            for sp in ('n','e','s','w'):
                for tp in ('n','e','s','w'):
                    candidates.append([{'op':'update_relation','id':r['id'],'changes':{'control':None,'source_port':sp,'target_port':tp}}])
            # Another side combined with a gentle bend: a plain side may run along another line.
            for sp in ('n','e','s','w'):
                for tp in ('n','e','s','w'):
                    probe={k:v for k,v in r.items() if k not in ('control','source_anchor','target_anchor')};probe.update(source_port=sp,target_port=tp)
                    try:pg=connection_geometry(original,probe)
                    except Exception:continue
                    for c in _bend_candidates(pg['x1'],pg['y1'],pg['x2'],pg['y2']):
                        candidates.append([{'op':'update_relation','id':r['id'],'changes':{'control':c,'source_port':sp,'target_port':tp}}])
    if code in ('binds-short','connector-body-short'):
        # Pull the two partners apart along their line until the bond (or the line body) shows.
        for r in original['relations']:
            if not ids or r['id']!=ids[0]:continue
            g=connection_geometry(original,r);chord=math.hypot(g['x2']-g['x1'],g['y2']-g['y1'])
            ux,uy=((g['x2']-g['x1'])/chord,(g['y2']-g['y1'])/chord) if chord>1e-6 else (0.0,1.0)
            ends=[(o,sign) for oid,sign in ((r['target'],1),(r['source'],-1)) for o in original['objects'] if o['id']==oid and not o['locked']]
            for step in (1,2,3,4,5,6,8):
                for o,sign in ends:
                    candidates.append([{'op':'update','id':o['id'],'changes':{'x':round(o['x']+sign*ux*step,4),'y':round(o['y']+sign*uy*step,4)}}])
    if code=='connector-overlap':
        # Re-route one of the two connectors: every route of either, shortest first.
        options=[]
        for r in original['relations']:
            if r['id'] not in ids:continue
            g=connection_geometry(original,r)
            changes=[{'control':None,'source_port':'auto','target_port':'auto'},{'control':None}]
            changes+=[{'control':c} for c in _bend_candidates(g['x1'],g['y1'],g['x2'],g['y2'])]
            changes+=[{'control':None,'source_port':sp,'target_port':tp} for sp in 'nesw' for tp in 'nesw']
            for ch in changes:
                probe={k:v for k,v in {**r,**ch}.items() if v is not None}
                try:pts=connection_samples(connection_geometry(original,probe))
                except Exception:continue
                options.append((sum(math.hypot(q[0]-p[0],q[1]-p[1]) for p,q in zip(pts,pts[1:])),r['id'],ch))
        for _,rid,ch in sorted(options,key=lambda o:o[0]):
            candidates.append([{'op':'update_relation','id':rid,'changes':ch}])
    if code=='cell-outline-placement':
        # Move only this stage, nearest spot first, until it sits where its stage belongs.
        spots=sorted({(dx,dy) for d in (2,4,6,9,12,16,20,25,30,36,42,50)
                      for dx,dy in ((d,0),(-d,0),(0,d),(0,-d),(d,d),(d,-d),(-d,d),(-d,-d))},key=lambda p:math.hypot(*p))
        for o in editable:
            for dx,dy in spots:
                x,y=o['x']+dx,o['y']+dy
                if x<0 or y<0 or x+o['w']>cw or y+o['h']>ch:continue
                candidates.append([{'op':'update','id':o['id'],'changes':{'x':round(x,4),'y':round(y,4)}}])
    for operations in candidates:
        proposed=apply_operations(original,operations);audit=audit_scene(proposed)
        remaining={key(f) for f in audit['findings']}
        if target not in remaining and not remaining-known:
            return {'operations':operations,'scene':proposed,'audit':audit,'changed':True}
    return {'operations':[],'scene':original,'audit':before,'changed':False,
            'message':'没有找到只调整相关对象就能解决的方案。可以先定位，再手动调整；当前图版没有变化。'}


def _bend_candidates(x1,y1,x2,y2):
    """Control points offset perpendicular to the chord, nearest first.

    The curve bulges by half the offset; it is kept within max(6, 0.6*chord)
    of the endpoints so a detour never runs far past either end."""
    chord=math.hypot(x2-x1,y2-y1)
    if chord<1e-6:return []
    nx,ny=-(y2-y1)/chord,(x2-x1)/chord;mx,my=(x1+x2)/2,(y1+y2)/2
    reach=max(6,.6*chord)
    return [{'x':mx+side*d*nx,'y':my+side*d*ny} for d in (4,8,16,28,44) if d/2<=reach for side in (1,-1)]


def _curve_ratio(x1,y1,c,x2,y2,n=60):
    """Curve length over chord of the quadratic through control c (1.0 = straight).

    Bends above 1.3 are not offered: the offline audit calls > 1.4 a hook."""
    chord=math.hypot(x2-x1,y2-y1)
    if chord<1e-6:return 1.0
    pts=[((1-t)**2*x1+2*(1-t)*t*c['x']+t*t*x2,(1-t)**2*y1+2*(1-t)*t*c['y']+t*t*y2) for t in (i/n for i in range(n+1))]
    return sum(math.hypot(q[0]-p[0],q[1]-p[1]) for p,q in zip(pts,pts[1:]))/chord


def _resolve_ports(a,b,r):
    """The side of each end object a connector uses (n/s/e/w), auto ports resolved."""
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
    return sp,tp


def _spread_anchor(scene,by_id,r,end,o,side):
    """Spread connectors that share one side of one object, so an arrow tip and the
    next arrow's start no longer meet in one point (it read as a two-way arrow).
    Ends are ordered by where the other end sits, so the lines do not cross."""
    if o.get('depiction')=='anchor' or side not in ('n','s','e','w'):return None
    ends=[]
    for q in scene.get('relations',[]):
        s,t=by_id.get(q.get('source')),by_id.get(q.get('target'))
        if s is None or t is None:continue
        qs,qt=_resolve_ports(s,t,q)
        for e,port,anchor,far,own in (('s',qs,q.get('source_anchor'),t,q['source']),('t',qt,q.get('target_anchor'),s,q['target'])):
            if own==o['id'] and port==side and not anchor:
                key=far['x']+far['w']/2 if side in ('n','s') else far['y']+far['h']/2
                ends.append((key,str(q.get('id')),e))
    ends.sort()
    k=len(ends)
    i=next((n for n,(_,rid,e) in enumerate(ends) if rid==str(r.get('id')) and e==end),None)
    length=o['w'] if side in ('n','s') else o['h']
    if k<2 or i is None or not length>0:return None
    gap=min(4,.8*length/(k-1))
    return {'side':side,'t':.5+(i-(k-1)/2)*gap/length}


LINE_LABEL_GAPS=(1.5,2.5,4,6)


def _label_offsets(x1,y1,c,x2,y2,width,height):
    """Candidate shifts for a connector label from its default spot (just above the
    curve midpoint): beside the line along its normal first (1.5-6 mm from the
    line), then slid along it, then the old free search as a last resort.
    Mirrored by labelOffsets in ui/canvas-editor.js."""
    mx,my=.25*x1+.5*c['x']+.25*x2,.25*y1+.5*c['y']+.25*y2
    tx,ty=x2-x1,y2-y1;n=math.hypot(tx,ty)
    tx,ty=(tx/n,ty/n) if n>1e-9 else (1.0,0.0)
    nx,ny=-ty,tx
    # First side: above a line, or right of a vertical one.
    if ny>1e-9 or (abs(ny)<=1e-9 and nx<0):nx,ny=-nx,-ny
    ext=abs(nx)*width/2+abs(ny)*height/2
    def at(side,gap,slide=0):
        cx=mx+side*nx*(gap+ext)+tx*slide;cy=my+side*ny*(gap+ext)+ty*slide
        return (cx-mx,cy+.3*height-(my-1.7))
    out=[at(s,g) for g in LINE_LABEL_GAPS for s in (1,-1)]
    out+=[at(s,LINE_LABEL_GAPS[1],k*d) for d in (4,8,12) for k in (1,-1) for s in (1,-1)]
    out+=[(0,0),(0,-4),(0,4),(0,-8),(0,8),(-8,0),(8,0),(0,-12),(0,12),(-12,0),(12,0),(-18,0),(18,0),(-24,0),(24,0),(-18,4),(18,4)]
    return out


# process_cell draws this cell outline behind its stages (design units of a 180 x 120 mm page, scaled by
# cw/180 and ch/120). The review checks each stage against the same curve (cell-outline-placement).
CELL_OUTLINE=(((10,31),(14,6),(89,6),(115,25)),((115,25),(140,43),(139,62),(130,82)),
              ((130,82),(111,91),(35,93),(13,76)),((13,76),(3,62),(1,44),(10,31)))
CELL_OUTLINE_PATH='M 10 31 '+' '.join('C '+' '.join(f'{x} {y}' for x,y in seg[1:]) for seg in CELL_OUTLINE)+' Z'
CELL_STAGE_PLACE={'biogenesis':'inside','transport':'inside','fusion':'boundary','released':'outside'}


def cell_outline_polygon(cw,ch,n=40):
    sx,sy=cw/180,ch/120;pts=[]
    for p0,p1,p2,p3 in CELL_OUTLINE:
        for i in range(n):
            t=i/n;u=1-t
            pts.append(((u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0])*sx,(u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1])*sy))
    return pts


def cell_inside_fraction(o,poly,k=9):
    """Share of a k x k grid over the object's box that lies inside the outline polygon."""
    def inside(px,py):
        hit=False
        for (x1,y1),(x2,y2) in zip(poly,poly[1:]+poly[:1]):
            if (y1>py)!=(y2>py) and px<x1+(py-y1)*(x2-x1)/(y2-y1):hit=not hit
        return hit
    return sum(inside(o['x']+o['w']*(i+.5)/k,o['y']+o['h']*(j+.5)/k) for i in range(k) for j in range(k))/(k*k)


def connection_samples(g,n=60):
    """Points along the quadratic connector, endpoints included."""
    x1,y1,x2,y2=g['x1'],g['y1'],g['x2'],g['y2'];cx,cy=g['control']['x'],g['control']['y']
    return [((1-t)**2*x1+2*(1-t)*t*cx+t*t*x2,(1-t)**2*y1+2*(1-t)*t*cy+t*t*y2) for t in (i/n for i in range(n+1))]


_SYMBOL_NUM=_re.compile(r'-?\d+(?:\.\d+)?')


def connection_symbol_boxes(g,r):
    """Boxes (x0,y0,x1,y1) of a connector's end symbols, drawn as _relation draws them."""
    from relation_visuals import relation_parts
    out=[]
    for tag,a in relation_parts(r['type'],(g['x1'],g['y1']),(g['x2'],g['y2']),(g['control']['x'],g['control']['y']),
                                '#000',r.get('stroke_pt',1.05),r.get('indirect',False),
                                anchored_start=bool(r.get('source_anchor')),anchored_end=bool(r.get('target_anchor'))):
        if 'data-endpoint' not in a:continue
        if tag=='circle':
            cx,cy,rr=float(a['cx']),float(a['cy']),float(a['r']);out.append((cx-rr,cy-rr,cx+rr,cy+rr));continue
        v=[float(n) for n in _SYMBOL_NUM.findall(a.get('d',''))]
        if len(v)>=2:
            sw=float(a.get('stroke-width',0) or 0)/2
            out.append((min(v[0::2])-sw,min(v[1::2])-sw,max(v[0::2])+sw,max(v[1::2])+sw))
    return out


def connection_visible_body(g,r,samples=60):
    """Visible line body (mm) of a connector: body samples outside the true shapes of its end
    symbols (filled heads, stroked chevrons and bars with half their width, binding rings).
    Used by the review check connector-body-short (tmp/scan_short2.py measures the same way)."""
    import re as _re
    from relation_visuals import relation_parts
    num=_re.compile(r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?')
    parts=relation_parts(r['type'],(g['x1'],g['y1']),(g['x2'],g['y2']),(g['control']['x'],g['control']['y']),
                         '#000',r.get('stroke_pt',1.05),r.get('indirect',False),
                         anchored_start=bool(r.get('source_anchor')),anchored_end=bool(r.get('target_anchor')))
    def seg_dist(p,a,b):
        ax,ay=b[0]-a[0],b[1]-a[1];l2=ax*ax+ay*ay
        t=0.0 if l2<1e-12 else max(0.0,min(1.0,((p[0]-a[0])*ax+(p[1]-a[1])*ay)/l2))
        return math.hypot(p[0]-a[0]-t*ax,p[1]-a[1]-t*ay)
    def in_poly(p,poly):
        inside=False
        for (x1,y1),(x2,y2) in zip(poly,poly[1:]+poly[:1]):
            if (y1>p[1])!=(y2>p[1]) and p[0]<x1+(p[1]-y1)*(x2-x1)/(y2-y1):inside=not inside
        return inside
    checks=[]
    for tag,a in parts:
        if 'data-endpoint' not in a:continue
        if tag=='circle':
            c,rr=(float(a['cx']),float(a['cy'])),float(a['r'])
            checks.append(lambda p,c=c,rr=rr:math.hypot(p[0]-c[0],p[1]-c[1])<=rr+.05);continue
        filled=a.get('fill') not in (None,'none')
        half=float(a.get('stroke-width',0) or 0)/2 if a.get('stroke')!='none' else 0.0
        for chunk in a.get('d','').split('M')[1:]:
            v=[float(n) for n in num.findall(chunk)];pts=list(zip(v[0::2],v[1::2]));closed='Z' in chunk
            if filled and closed and len(pts)>=3:checks.append(lambda p,poly=pts:in_poly(p,poly))
            if half and pts:
                segs=list(zip(pts,pts[1:]+(pts[:1] if closed else [])))
                checks.append(lambda p,segs=segs,h=half:any(seg_dist(p,s,e)<=h for s,e in segs))
    total=0.0
    for tag,a in parts:
        if a.get('data-line-body')!='true':continue
        for chunk in a.get('d','').split('M')[1:]:
            v=[float(n) for n in num.findall(chunk)]
            if 'Q' in chunk and len(v)>=6:
                (x0,y0),(cx,cy),(x1,y1)=(v[0],v[1]),(v[2],v[3]),(v[4],v[5])
                pts=[((1-t)**2*x0+2*(1-t)*t*cx+t*t*x1,(1-t)**2*y0+2*(1-t)*t*cy+t*t*y1) for t in (i/samples for i in range(samples+1))]
            else:pts=list(zip(v[0::2],v[1::2]))
            for p,q in zip(pts,pts[1:]):
                m=((p[0]+q[0])/2,(p[1]+q[1])/2)
                if not any(chk(m) for chk in checks):total+=math.hypot(q[0]-p[0],q[1]-p[1])
    return total


def connection_overshoot(g,pts=None):
    """How far (mm) the curve runs past the box around its two ends, beyond max(6, 0.6*chord)."""
    pts=pts or connection_samples(g)
    chord=math.hypot(g['x2']-g['x1'],g['y2']-g['y1']);slack=max(6.0,.6*chord)
    lo_x,hi_x=min(g['x1'],g['x2'])-slack,max(g['x1'],g['x2'])+slack
    lo_y,hi_y=min(g['y1'],g['y2'])-slack,max(g['y1'],g['y2'])+slack
    return max([0.0]+[max(lo_x-x,x-hi_x,lo_y-y,y-hi_y) for x,y in pts])


def line_label_gap(scene,r):
    """Distance (mm) from a relation's label box to its own curve; 0 without a label."""
    from relation_visuals import relation_label
    label=relation_label(scene,r)
    if not label:return 0.0
    g=connection_geometry(scene,{**r,'label':label});c=g['control']
    w=_measure(label,7*PT_MM);h=7*PT_MM;x=g['label_x']-w/2;y=g['label_y']-h*.8
    best=float('inf')
    for i in range(81):
        t=i/80;u=1-t
        px=u*u*g['x1']+2*u*t*c['x']+t*t*g['x2'];py=u*u*g['y1']+2*u*t*c['y']+t*t*g['y2']
        best=min(best,math.hypot(max(0,x-px,px-x-w),max(0,y-py,py-y-h)))
    return best


def _widen_label_gaps(scene,plan,lo,hi):
    """plan: [[object, centre_x, w, h], ...] left to right in one row. When two
    neighbours are joined by a labelled relation, open the gap between them to
    the label's width plus 1.5 mm a side, so the label can sit right beside its
    short line instead of being pushed off over the objects. The row shifts
    outward within [lo, hi]; whichever side has no room leaves it to the other."""
    for k in range(len(plan)-1):
        a,b=plan[k],plan[k+1]
        ids={a[0]['id'],b[0]['id']}
        label=next((r['label'] for r in scene['relations'] if r.get('label') and {r['source'],r['target']}==ids),'')
        if not label:continue
        gap=(b[1]-b[2]/2)-(a[1]+a[2]/2);need=_measure(label,7*PT_MM)+3
        if gap>=need:continue
        d=need-gap
        room_l=max(0,plan[0][1]-plan[0][2]/2-lo);room_r=max(0,hi-plan[-1][1]-plan[-1][2]/2)
        right=min(d/2,room_r);left=min(d-right,room_l);right=min(d-left,room_r)
        for p in plan[:k+1]:p[1]-=left
        for p in plan[k+1:]:p[1]+=right


def connection_geometry(scene,r):
    from relation_visuals import relation_label
    r={**r,"label":relation_label(scene,r)}
    x1,y1,x2,y2,control=_cached_curve(scene,r)
    cx,cy=control['x'],control['y'];length=math.hypot(x2-cx,y2-cy) or 1
    lx,ly=.25*x1+.5*cx+.25*x2,.25*y1+.5*cy+.25*y2-1.7
    if r.get('label_position'):
        lx,ly=r['label_position']['x'],r['label_position']['y']
    elif r.get('label'):
        width=_measure(r['label'],7*PT_MM);height=7*PT_MM
        # A membrane counts even as context: a label lying on it is hard to read.
        boxes=[(o['x'],o['y'],o['w'],o['h']) for o in scene['objects'] if o['visible'] and (o.get('role') != 'context' or o.get('type')=='membrane')]
        boxes.extend((b['x'],b['y'],b['w'],b['h']) for b in _object_label_boxes(scene))
        # Context outlines (a cell edge): a label wholly inside is fine, one straddling the edge is not.
        edges=[(o['x'],o['y'],o['w'],o['h']) for o in scene['objects'] if o['visible'] and o.get('role')=='context' and o.get('type')!='membrane']
        # Other connectors: a label lying across another line reads as part of it.
        by_id={o['id']:o for o in scene['objects']};others=[]
        for q in scene['relations']:
            qa,qb=by_id.get(q.get('source')),by_id.get(q.get('target'))
            if q.get('id')==r.get('id') or not qa or not qb or not qa.get('visible',True) or not qb.get('visible',True):continue
            if not all(k in o for o in (qa,qb) for k in ('x','y','w','h')):continue
            qx1,qy1,qx2,qy2,qc=_cached_curve(scene,q)
            others.extend(((1-t)**2*qx1+2*(1-t)*t*qc['x']+t*t*qx2,(1-t)**2*qy1+2*(1-t)*t*qc['y']+t*t*qy2) for t in (n/60 for n in range(61)))
        def label_cost(offset):
            x,y=lx+offset[0]-width/2,ly+offset[1]-height*.8
            if x<.5 or y<.5 or x+width>scene['canvas']['width_mm']-.5 or y+height>scene['canvas']['height_mm']-.5:return 10000
            ov=lambda ox,oy,ow,oh:max(0,min(x+width,ox+ow)-max(x,ox))*max(0,min(y+height,oy+oh)-max(y,oy))
            return (sum(ov(*b) for b in boxes)+sum(.3 for b in edges if .05<ov(*b)<width*height*.98)
                    +2*sum(1 for px,py in others if x-.3<px<x+width+.3 and y-.3<py<y+height+.3))
        offsets=_label_offsets(x1,y1,control,x2,y2,width,height)
        dx,dy=min(enumerate(offsets),key=lambda p:(label_cost(p[1]),p[0]))[1]
        lx+=dx;ly+=dy
    return {'x1':x1,'y1':y1,'x2':x2,'y2':y2,'control':control,
            'path':f'M {x1:.4f} {y1:.4f} Q {cx:.4f} {cy:.4f} {x2:.4f} {y2:.4f}',
            'ux':(x2-cx)/length,'uy':(y2-cy)/length,'label_x':lx,'label_y':ly}


# 5 mm of binding discs plus 2 mm of visible line (scene_document binds-short).
BINDS_MIN_ENDS_MM=7.0


def _clear_own_label(o,side,x,y,box,other=None,reach=1.0,side_reach=2.0,pad=.5,gap=1.5,taken=None):
    """Keep a port point out of its object's own label. Mirrored by clearOwnLabel
    in ui/canvas-editor.js.
    North/south: a label covering the port (within `reach` mm, across the way the
    line leaves) moves the point past the label's outer edge.
    East/west: a label beside the port (within `side_reach` mm, covering its
    height) slides the point along the edge to `gap` mm past the label's top or
    bottom, at least 0.8 mm from the corners, towards the other end of the line.
    No room on the edge: the point is kept."""
    if not box or o.get('depiction')=='anchor' or o.get('rotation',0):return x,y
    x0,y0,x1,y1=box['x'],box['y'],box['x']+box['w'],box['y']+box['h']
    if side=='s' and x0-.2<=x<=x1+.2 and y0-reach<=y<y1:return x,y1+pad
    if side=='n' and x0-.2<=x<=x1+.2 and y0<y<=y1+reach:return x,y0-pad
    if side in ('e','w') and y0-.2<=y<=y1+.2:
        beside=(x0<x+.2 and x1>=x-side_reach) if side=='w' else (x1>x-.2 and x0<=x+side_reach)
        if beside:
            lo,hi=o['y']+.8,o['y']+o['h']-.8
            options=[v for v in (y0-gap,y1+gap) if lo<=v<=hi]
            if options:
                ref=other[1] if other else y
                # Other connectors' ends on this side (y values, or a callable giving
                # them): keep 1.5 mm from each, stepping towards the label (not closer
                # than `pad`) when the usual spot is taken; no room: the point is kept.
                ys=list((taken() if callable(taken) else taken) or ())
                if ys:
                    options=[]
                    for edge,sign in ((y0,-1),(y1,1)):
                        k=gap
                        while k>=pad-1e-9:
                            v=edge+sign*k
                            if lo<=v<=hi and all(abs(v-q)>=1.5 for q in ys):options.append(v);break
                            k-=.25
                    if not options:return x,y
                return x,min(options,key=lambda v:(abs(v-ref),abs(v-y)))
    return x,y


def _freeze(v):
    if isinstance(v,str):return ('#',len(v),hash(v)) if len(v)>200 else v
    if isinstance(v,dict):return tuple(sorted((k,_freeze(x)) for k,x in v.items()))
    if isinstance(v,(list,tuple)):return tuple(_freeze(x) for x in v)
    return v


_CURVES={}


def _cached_curve(scene,r):
    """_connection_curve, memoised on the scene's geometry: every connector label
    checks all the other curves, and the review asks for each geometry many times."""
    c=scene.get('canvas',{})
    key=(c.get('width_mm'),c.get('height_mm'),_freeze(scene['objects']),
         _freeze([{k:v for k,v in q.items() if k!='label'} for q in scene['relations']]),
         _freeze({k:v for k,v in r.items() if k!='label'}),
         id(_bend_candidates),id(_curve_ratio),id(_spread_anchor),id(_resolve_ports),id(_object_label_boxes),id(_clear_own_label))
    hit=_CURVES.get(key)
    if hit is None:
        if len(_CURVES)>4096:_CURVES.clear()
        hit=_CURVES[key]=_connection_curve(scene,r)
    x1,y1,x2,y2,control=hit
    return x1,y1,x2,y2,dict(control)


def _connection_curve(scene,r):
    """Ends and control point of a connector, without its label. Connector labels
    avoid these curves, so nothing here may depend on a connector label."""
    by_id={o['id']:o for o in scene['objects']};a,b=by_id[r['source']],by_id[r['target']]
    sp,tp=_resolve_ports(a,b,r)
    def point(o,p,anchor=None):
        cx,cy=o['x']+o['w']/2,o['y']+o['h']/2
        if o.get('depiction')=='anchor':return cx,cy
        if anchor:p=anchor['side']
        x,y={'e':(o['x']+o['w'],cy),'w':(o['x'],cy),'n':(cx,o['y']),'s':(cx,o['y']+o['h'])}.get(p,(cx,cy))
        if anchor:
            if p in ('n','s'):x=o['x']+o['w']*anchor['t']
            else:y=o['y']+o['h']*anchor['t']
        angle=math.radians(o.get('rotation',0));return (cx+(x-cx)*math.cos(angle)-(y-cy)*math.sin(angle),cy+(x-cx)*math.sin(angle)+(y-cy)*math.cos(angle))
    sa=r.get('source_anchor') or _spread_anchor(scene,by_id,r,'s',a,sp)
    ta=r.get('target_anchor') or _spread_anchor(scene,by_id,r,'t',b,tp)
    x1,y1=point(a,sp,sa);x2,y2=point(b,tp,ta)
    # A label sits right under its box, where a south port is: an automatic port
    # its own label covers moves past the label's outer edge, so the line does not
    # start inside the text. Ports the user set are kept.
    own_boxes={q['id']:q for q in _object_label_boxes(scene)}
    p1,p2=(x1,y1),(x2,y2)
    def taken(o,side):
        # Where the other connectors on this side of o end (before any label slide).
        ys=[]
        for q in scene.get('relations',[]):
            if q.get('id')==r.get('id'):continue
            qa,qb=by_id.get(q.get('source')),by_id.get(q.get('target'))
            if qa is None or qb is None:continue
            qs,qt=_resolve_ports(qa,qb,q)
            for end,port,anchor,own in (('s',qs,q.get('source_anchor'),qa),('t',qt,q.get('target_anchor'),qb)):
                if own['id']!=o['id']:continue
                an=anchor or _spread_anchor(scene,by_id,q,end,own,port)
                if (an['side'] if an else port)==side:ys.append(point(own,port,an)[1])
        return ys
    ss,ts=(sa['side'] if sa else sp),(ta['side'] if ta else tp)
    if not r.get('source_anchor'):x1,y1=_clear_own_label(a,ss,*p1,own_boxes.get(a['id']),p2,taken=lambda:taken(a,ss))
    if not r.get('target_anchor'):x2,y2=_clear_own_label(b,ts,*p2,own_boxes.get(b['id']),p1,taken=lambda:taken(b,ts))
    # Binding discs need room: moving the ends past their labels must not leave
    # a binding line shorter than the review's binds-short limit.
    if r.get('type')=='binds' and (x1,y1,x2,y2)!=(*p1,*p2) and math.hypot(x2-x1,y2-y1)<BINDS_MIN_ENDS_MM:
        (x1,y1),(x2,y2)=p1,p2
    control=r.get('control') or {'x':(x1+x2)/2,'y':(y1+y2)/2}
    if not r.get('control') and not (r.get('source_anchor') or r.get('target_anchor')) and sp==tp:control={'x':max(x1,x2)+12,'y':(y1+y2)/2}
    if not r.get('control') and not r.get('callout'):
        # The line has to leave its own ends' ports, so their labels, the containers
        # around them and the membrane they sit in are not in its way.
        def _touches(o):
            return any(max(o['x'],e['x'])<min(o['x']+o['w'],e['x']+e['w']) and max(o['y'],e['y'])<min(o['y']+o['h'],e['y']+e['h']) for e in (a,b))
        obstacles=[(o['x']-1,o['y']-1,o['w']+2,o['h']+2) for o in scene['objects']
                   if o.get('visible', True) and o.get('role') != 'context' and o['id'] not in (a['id'],b['id']) and not _touches(o)]
        labels=[(q['x']-.5,q['y']-.5,q['w']+1,q['h']+1) for q in _object_label_boxes(scene) if q.get('id') not in (a['id'],b['id'])]
        # The ends' own labels still count, but only bends short enough not to
        # read as a hook may avoid them (see the ratio cap on the candidates).
        own=[(q['x']-.5,q['y']-.5,q['w']+1,q['h']+1) for q in _object_label_boxes(scene) if q.get('id') in (a['id'],b['id'])]
        def cost(c):
            hit=0
            for i in range(1,80):
                t=i/80;u=1-t
                x=u*u*x1+2*u*t*c['x']+t*t*x2;y=u*u*y1+2*u*t*c['y']+t*t*y2
                hit+=8*sum(1 for ox,oy,ow,oh in obstacles if ox<x<ox+ow and oy<y<oy+oh)
                hit+=8*sum(1 for ox,oy,ow,oh in labels if ox<x<ox+ow and oy<y<oy+oh)
                hit+=8*sum(1 for ox,oy,ow,oh in own if ox<x<ox+ow and oy<y<oy+oh)
                if x<1 or y<1 or x>scene['canvas']['width_mm']-1 or y>scene['canvas']['height_mm']-1:hit+=4
                # Past the canvas edge is worse than crossing an object: the curve is cut off.
                if x<0 or y<0 or x>scene['canvas']['width_mm'] or y>scene['canvas']['height_mm']:hit+=40
            return hit
        base=cost(control)
        if base:
            # Bend only perpendicular to the chord. A quadratic's bulge is half
            # its control offset, so cap the offset to keep the curve near its
            # own endpoints; offsets along the chord made it overshoot and fold
            # back (an arrow that seemed to start on the membrane).
            candidates=[c for c in _bend_candidates(x1,y1,x2,y2) if _curve_ratio(x1,y1,c,x2,y2)<=1.3]
            if candidates:
                best=min(candidates,key=lambda c:(cost(c),math.hypot(c['x']-(x1+x2)/2,c['y']-(y1+y2)/2)))
                if cost(best)<base:control=best
    return x1,y1,x2,y2,control


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


def uses_text_appearance(o):
    a=o.get('text_appearance')
    return bool(a and o.get('asset_snapshot') and all(o.get(k)==a[k] for k in ('label','font_size_pt','fill')))


def _object(o,palette,stroke_pt=.8,glyph_tint=.8):
    oid=o['id'];kind=o['type'];x,y,w,h=(o[k] for k in ('x','y','w','h'))
    family=palette['accent'] if kind=='ligand' else palette['secondary'] if kind in ('tf','dna','mrna','complex','domain','fibroblast','collagen','tissue') else palette['primary']
    color=o.get('fill') or family;line=o.get('stroke') or family
    angle=o.get('rotation',0)
    if o.get('depiction')=='anchor':
        artwork=''
    elif o.get('illustration'):
        import base64,io
        from PIL import Image
        with Image.open(io.BytesIO(base64.b64decode(o['illustration']['data'].split(',')[1]))) as image:iw,ih=image.size
        scale=min(w/iw,h/ih);fw,fh=iw*scale,ih*scale
        # Meet inside the physical frame BEFORE the outer non-uniform transform.
        # Fitting into a 100x100 square first distorts illustrations and causes
        # callout anchors to land outside the actual rendered structure.
        artwork = ('<image href="' + _escape(o['illustration']['data'])
                   + f'" x="{(w-fw)/w*50}" y="{(h-fh)/h*50}" width="{fw/w*100}" height="{fh/h*100}" preserveAspectRatio="none"/>')
    elif o.get('text_appearance') and not uses_text_appearance(o):
        artwork=''
    elif o.get('asset_id'):
        from scientific_library import glyph
        if o.get('asset_snapshot'):
            from scientific_library import portable_glyph
            artwork=portable_glyph(o['asset_snapshot']['svg'],None if uses_text_appearance(o) else o.get('fill'),o.get('stroke'))
        else:artwork=glyph(o['asset_id'],o.get('fill'),o.get('stroke'))
    else:artwork=symbol(kind,color,o.get('state') or (o.get('label','') if kind in ('cell','stem_cell') else ''),line,o.get('stroke_pt',stroke_pt)/.8,glyph_tint)
    aria=f' aria-label="{_escape(o.get("label", ""))}"' if uses_text_appearance(o) else ''
    p=[f'<g data-object-id="{oid}" data-type="{kind}"{aria} id="obj-{oid}">',f'<g data-glyph="{oid}" transform="rotate({angle} {x+w/2} {y+h/2})"><g transform="translate({x} {y}) scale({w/100} {h/100})">',artwork,'</g>']
    if o.get('state') == 'phosphorylated' and kind in ('kinase','protein','receptor','receptor_dimer'):
        bx,by=x+w-1,y+1
        p.append(f'<circle cx="{bx}" cy="{by}" r="1.65" fill="{tint(palette["accent"],.4)}" stroke="#FFFFFF" stroke-width=".3"/>')
        p.append(_text(bx,by+.86,'P',7,anchor='middle',fill='#7D5B26'))
    p.append('</g>')
    if uses_text_appearance(o):
        p.append('</g>');return ''.join(p)
    lines,fs=_label_lines(o)
    for i,text in enumerate(lines):p.append(_text(x+w/2+(5 if o.get('state','').startswith('legend_') else 0)+o.get('label_dx',0),label_baseline(o,lines,fs)+i*fs*1.23,text,o.get('font_size_pt',8),fill=o.get('fill','#2F4552') if kind=='text' else '#2F4552',anchor='middle',bold=o.get('font_weight',400)>=600,data_label_for=oid,**(LABEL_HALO if kind!='text' else {})))
    p.append('</g>');return ''.join(p)


def _relation(scene,r,palette):
    from relation_visuals import relation_parts, relation_label
    g=connection_geometry(scene,r);color=r.get('stroke') or ('#AD6460' if r['type']=='inhibits' else palette['primary'])
    p=[f'<g data-relation-id="{r["id"]}" data-relation-type="{r["type"]}" id="rel-{r["id"]}">']
    if r.get('callout') and next(o for o in scene['objects'] if o['id']==r['target']).get('depiction')=='anchor':
        p.append(f'<circle cx="{g["x2"]:.4f}" cy="{g["y2"]:.4f}" r=".7" fill="{color}" stroke="white" stroke-width=".25"/>')
    for tag,attrs in relation_parts(r['type'],(g['x1'],g['y1']),(g['x2'],g['y2']),
                                    (g['control']['x'],g['control']['y']),color,r.get('stroke_pt',1.05),r.get('indirect',False),
                                    anchored_start=bool(r.get('source_anchor')),anchored_end=bool(r.get('target_anchor'))):
        p.append('<'+tag+' '+' '.join(f'{key}="{_escape(value)}"' for key,value in attrs.items())+'/>')
    label=relation_label(scene,r)
    if label:
        width=_measure(label,7*PT_MM)
        p.append(f'<rect x="{g["label_x"]-width/2-.6:.4f}" y="{g["label_y"]-2:.4f}" width="{width+1.2:.4f}" height="2.7" rx=".3" fill="#FFFFFF"/>')
        p.append(_text(g['label_x'],g['label_y'],label,7,anchor='middle',fill=color))
    return ''.join(p)+'</g>'


def render_scene(scene, *, _laid_out=False, embed_scene=False):
    if not _laid_out:
        scene=layout_scene(scene)
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm'];palette=scene['style']['palette']
    from structure_render import composite_layer
    def draw_object(o):return _object(o,palette,scene['style']['stroke_pt'],scene['style']['glyph_tint'])
    p=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw}mm" height="{ch}mm" viewBox="0 0 {cw} {ch}" data-version="{scene["schema_version"]}" data-revision="{scene["revision"]}">',f'<title>{_escape(scene["title"])}</title>',f'<rect width="{cw}" height="{ch}" fill="#FFFFFF"/>','<g id="layer-compartments">']
    from scientific_library import credits
    import json
    p.insert(2,'<metadata>'+_escape(json.dumps({'artwork_credits':credits(scene)},ensure_ascii=False))+'</metadata>')
    if embed_scene:
        from scene_document import normalize_scene
        payload={'format':'rylume-scene','scene':normalize_scene(scene)}
        data=json.dumps(payload['scene'],ensure_ascii=False,separators=(',',':')).encode('utf8')
        if len(data)>512*1024:
            import zlib,base64
            payload={'format':'rylume-scene','scene_zlib':base64.b64encode(zlib.compress(data)).decode('ascii')}
        p.insert(2,'<metadata id="rylume-scene">'+_escape(json.dumps(payload,ensure_ascii=False,separators=(',',':')))+'</metadata>')
    tid=scene['style'].get('template','')
    if tid=='process_cell':
        p.append(f'<g transform="scale({cw/180} {ch/120})"><path d="{CELL_OUTLINE_PATH}" fill="{tint(palette["primary"],.92)}" stroke="{tint(palette["primary"],.3)}" stroke-width=".45"/><path d="M 13 33 C 19 10 87 11 112 28" fill="none" stroke="{tint(palette["primary"],.55)}" stroke-width=".3"/></g>')
        p.append(_text(16*cw/180,25*ch/120,'Cell interior',8,fill='#5D7683'))
        p.append(_text(155*cw/180,116*ch/120,'Extracellular',7,anchor='middle',fill='#5D7683'))
    elif tid=='network_tissue':
        p.append(f'<path d="M 5 {ch*.82} Q {cw*.25} {ch*.77} {cw*.5} {ch*.82} T {cw-5} {ch*.82} L {cw-5} {ch-6} H 5 Z" fill="{tint(palette["secondary"],.93)}"/>')
        for i in range(7):p.append(f'<path d="M {cw*(.06+i*.13)} {ch*.87} q 7 -2 15 0" fill="none" stroke="{tint(palette["secondary"],.55)}" stroke-width=".3"/>')
    p.extend(_compartment(c,palette['primary'],tid=='signal_cell') for c in scene['compartments']);p.append('</g><g id="layer-context">')
    p.append(composite_layer([o for o in scene['objects'] if o['visible'] and o.get('role')=='context'],scene.get('structures',[]),draw_object))
    p.append('</g><g id="layer-relations">')
    objects={o['id']:o for o in scene['objects']}
    p.extend(_relation(scene,r,palette) for r in scene['relations'] if not r.get('callout') and objects[r['source']]['visible'] and objects[r['target']]['visible'])
    p.append('</g><g id="layer-objects">');p.append(composite_layer([o for o in scene['objects'] if o['visible'] and o.get('role')!='context'],scene.get('structures',[]),draw_object));p.append('</g>')
    p.append('<g id="layer-callouts">'+''.join(_relation(scene,r,palette) for r in scene['relations'] if r.get('callout') and objects[r['source']]['visible'] and objects[r['target']]['visible'])+'</g>')
    if scene['style'].get('show_title'):p.append(_text(cw/2,4,scene['title'],10,anchor='middle',bold=True))
    if any(r.get('indirect') for r in scene['relations']):p.append(_text(cw-8,ch-2.5,'Dashed: indirect effect',7,anchor='end',fill='#82919A'))
    p.append('</svg>');return ''.join(p)
