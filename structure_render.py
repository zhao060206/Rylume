"""Render whole-structure transforms without rewriting the stored source paths."""
from functools import lru_cache
import math
import xml.etree.ElementTree as ET

def _mul(p,q):
    a,b,c,d,e,f=p;A,B,C,D,E,F=q
    return a*A+c*B,b*A+d*B,a*C+c*D,b*C+d*D,a*E+c*F+e,b*E+d*F+f

@lru_cache(maxsize=128)
def offset_svg(svg,width,height,angle,offsets):
    if not offsets:return svg
    from svgelements import Matrix
    root=ET.fromstring(svg);box=list(map(float,root.get('viewBox').split()));r=math.radians(angle)
    world=(math.cos(r)*width/box[2],math.sin(r)*width/box[2],-math.sin(r)*height/box[3],math.cos(r)*height/box[3],0,0)
    changes={index:(dx,dy) for index,dx,dy in offsets};index=0
    def walk(node,parent):
        nonlocal index
        tag=node.tag.split('}')[-1]
        if tag in ('path','rect','circle','ellipse','line','polyline','polygon'):
            if index in changes:
                dx,dy=changes[index];a,b,c,d,_,_=_mul(world,parent);det=a*d-b*c
                if abs(det)<1e-12:raise ValueError('结构变换不可逆')
                tx,ty=(d*dx-c*dy)/det,(-b*dx+a*dy)/det
                node.set('transform',f'translate({tx:.10g} {ty:.10g}) '+node.get('transform',''))
            index+=1
        m=Matrix(node.get('transform',''))
        current=_mul(parent,(m.a,m.b,m.c,m.d,m.e,m.f))
        for child in node:walk(child,current)
    walk(root,(1,0,0,1,0,0));return ET.tostring(root,encoding='unicode')

def rendered_object(obj,structures):
    offsets=[]
    for group in structures:
        dx,dy=group.get('dx',0),group.get('dy',0)
        if not(dx or dy):continue
        for part in group['parts']:
            if part['owner']==obj['id']:offsets.extend((i,dx,dy) for i in part['indices'])
    if not offsets:return obj
    svg=offset_svg(obj['asset_snapshot']['svg'],obj['w'],obj['h'],obj.get('rotation',0),tuple(offsets))
    return {**obj,'asset_snapshot':{**obj['asset_snapshot'],'svg':svg}}


SHAPES={'path','rect','circle','ellipse','line','polyline','polygon'}

@lru_cache(maxsize=256)
def selected_svg(svg,indices,exclude=False):
    """Keep selected paths and their original transforms/styles, without flattening."""
    root=ET.fromstring(svg);wanted=set(indices);index=0
    def walk(parent):
        nonlocal index
        for child in list(parent):
            if child.tag.split('}')[-1] in SHAPES:
                keep=(index not in wanted) if exclude else (index in wanted);index+=1
                if not keep:parent.remove(child)
            else:walk(child)
    walk(root)
    return ET.tostring(root,encoding='unicode')


def patch_rects(background):
    colors=[[int(c[i:i+2],16) for i in (1,3,5)] for c in background['colors']]
    for j in range(8):
        for i in range(8):
            u,v=(i+.5)/8,(j+.5)/8
            # JavaScript Math.round rounds positive half values upward.
            rgb=[math.floor(colors[0][k]*(1-u)*(1-v)+colors[1][k]*u*(1-v)+colors[2][k]*(1-u)*v+colors[3][k]*u*v+.5) for k in range(3)]
            yield {'x':background['x']+i*background['w']/8,'y':background['y']+j*background['h']/8,'w':background['w']/8+.002,'h':background['h']/8+.002,'fill':'#'+''.join(f'{c:02x}' for c in rgb)}


def composite_layer(objects,structures,draw):
    """Vector equivalent of the display compositor; no bitmap enters exports."""
    ids={o['id'] for o in objects}
    active=[g for g in structures if g.get('background') and (g.get('visible') is False or abs(g.get('dx',0))>1e-7 or abs(g.get('dy',0))>1e-7) and all(p['owner'] in ids for p in g['parts'])]
    fallback=[g for g in structures if g not in active]
    removed={}
    for g in active:
        for part in g['parts']:removed.setdefault(part['owner'],set()).update(part['indices'])
    result=[]
    for o in objects:
        base=rendered_object(o,fallback)
        if o['id'] in removed:
            base={**base,'asset_snapshot':{**base['asset_snapshot'],'svg':selected_svg(base['asset_snapshot']['svg'],tuple(sorted(removed[o['id']])),True)}}
        result.append(draw(base))
    if not active:return ''.join(result)
    by_id={o['id']:o for o in objects}
    def members(parts):
        selected={}
        for part in parts:selected.setdefault(part['owner'],set()).update(part['indices'])
        # Iterate in source drawing order, including the original nested transforms.
        for o in objects:
            if o['id'] not in selected:continue
            svg=selected_svg(o['asset_snapshot']['svg'],tuple(sorted(selected[o['id']])))
            art=draw({**o,'label':'','asset_snapshot':{**o['asset_snapshot'],'svg':svg}})
            # The complete structure is the selectable group in PowerPoint.
            # Colour-batch owners are implementation details, not more groups.
            yield art.replace(f'data-object-id="{o["id"]}"',f'data-structure-member="{o["id"]}"',1).replace(f'id="obj-{o["id"]}"','',1)
    for g in active:
        for r in patch_rects(g['background']):result.append(f'<rect x="{r["x"]}" y="{r["y"]}" width="{r["w"]}" height="{r["h"]}" fill="{r["fill"]}"/>')
    for g in active:
        if g.get('visible') is False:continue
        result.append(f'<g data-structure-id="{g["id"]}" transform="translate({g.get("dx",0)} {g.get("dy",0)})">')
        result.extend(members(g['parts']));result.append('</g>')
    result.extend(members([p for g in active for p in g.get('foreground',[]) if p['owner'] in by_id]))
    return ''.join(result)
