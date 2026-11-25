"""Bounded routing for new scenes; explicit author edits are never changed here."""
from __future__ import annotations
import copy
import math


def repair_connection_routes(value, passes=3):
    import numpy as np
    from scene_document import audit_scene, normalize_scene
    from scene_render import connection_geometry, label_boxes, _curve_ratio, line_label_gap, connection_symbol_boxes, _object_label_boxes
    scene=normalize_scene(copy.deepcopy(value));cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    objects={o['id']:o for o in scene['objects']}
    t=np.linspace(.015,.985,100);u=1-t
    for _ in range(passes):
        findings=audit_scene(scene)['findings']
        # A label pushed far from its own line usually sits in a lane too short
        # for it; another route can give it room. The audit never reports
        # detached for a hand-placed label, so author edits stay untouched.
        detached={f['object_ids'][0] for f in findings if f['code']=='line-label-detached'}
        affected={f['object_ids'][0] for f in findings if f['code']=='line-label-overlap'}|detached
        if not affected:break
        changed=False
        for r in scene['relations']:
            if r['id'] not in affected:continue
            labels=[b for b in label_boxes(scene) if b['id']!=r['id']]
            object_labels=_object_label_boxes(scene)
            obstructions=[o for o in scene['objects'] if o.get('visible') and o.get('role')!='context' and o['id'] not in (r['source'],r['target'])]
            boxes=np.array([[b['x']-.3,b['y']-.3,b['x']+b['w']+.3,b['y']+b['h']+.3] for b in labels])
            solids=np.array([[b['x'],b['y'],b['x']+b['w'],b['y']+b['h']] for b in obstructions])
            # The line's own end objects: running through one reads as leaving from the far side.
            def _holds(e,o):return e['x']<=o['x']+o['w']/2<=e['x']+e['w'] and e['y']<=o['y']+o['h']/2<=e['y']+e['h']
            ea,eb=objects[r['source']],objects[r['target']]
            own=np.array([[e['x']+.4,e['y']+.4,e['x']+e['w']-.4,e['y']+e['h']-.4] for e,o in ((ea,eb),(eb,ea))
                          if not r.get('callout') and e.get('depiction')!='anchor' and not e.get('rotation',0)
                          and e.get('type') not in ('text','membrane') and not _holds(e,o)])
            def score(g,rel=None):
                cx,cy=g['control']['x'],g['control']['y']
                x=u*u*g['x1']+2*u*t*cx+t*t*g['x2'];y=u*u*g['y1']+2*u*t*cy+t*t*g['y2']
                label_hits=0;object_hits=0
                if len(boxes):label_hits=int(((x[:,None]>boxes[:,0])&(x[:,None]<boxes[:,2])&(y[:,None]>boxes[:,1])&(y[:,None]<boxes[:,3])).sum())
                if len(solids):object_hits=int(((x[:,None]>solids[:,0])&(x[:,None]<solids[:,2])&(y[:,None]>solids[:,1])&(y[:,None]<solids[:,3])).sum())
                outside=int(((x<.5)|(x>cw-.5)|(y<.5)|(y>ch-.5)).sum())
                # An end symbol over an object label hides the text: weighs like 20 line samples.
                sym_hits=0
                if rel is not None:
                    for sx0,sy0,sx1,sy1 in connection_symbol_boxes(g,rel):
                        sym_hits+=sum(1 for q in object_labels if min(sx1,q['x']+q['w'])-max(sx0,q['x'])>.1 and min(sy1,q['y']+q['h'])-max(sy0,q['y'])>.1)
                own_hits=int(((x[:,None]>own[:,0])&(x[:,None]<own[:,2])&(y[:,None]>own[:,1])&(y[:,None]<own[:,3])).sum()) if len(own) else 0
                length=float(np.hypot(np.diff(x),np.diff(y)).sum())
                detach=0.0
                if rel is not None and rel['id'] in detached:
                    gap=line_label_gap(scene,rel)
                    if round(gap,1)>4:detach=25+5*gap
                return(label_hits+outside*10+own_hits+20*sym_hits,object_hits,detach,length)
            original=connection_geometry(scene,r);best=score(original,r);choice=None
            if best[0]==0 and best[2]==0:continue
            # Ports and control are visual geometry only: relation identity,
            # evidence, type and direction stay unchanged.
            for sp in ('n','e','s','w'):
                for tp in ('n','e','s','w'):
                    probe={**r,'source_port':sp,'target_port':tp,'control':{'x':cw/2,'y':ch/2},'label_position':{'x':0,'y':0}}
                    probe.pop('source_anchor',None);probe.pop('target_anchor',None)
                    g=connection_geometry(scene,probe);mx,my=(g['x1']+g['x2'])/2,(g['y1']+g['y2'])/2
                    for dx,dy in ((0,0),(0,-12),(0,12),(-12,0),(12,0),(-24,0),(24,0),(0,-24),(0,24),(-48,0),(48,0),(0,-48),(0,48),(-24,-24),(24,-24),(-24,24),(24,24),(-72,0),(72,0)):
                        c={'x':mx+dx,'y':my+dy}
                        # Same bend limit as the renderer: dodging a label must not
                        # turn the connector into a hook (audit flags > 1.4).
                        if _curve_ratio(g['x1'],g['y1'],c,g['x2'],g['y2'])>1.3:continue
                        candidate={**g,'control':c};rel={k:v for k,v in r.items() if k not in ('source_anchor','target_anchor')};rel.update(source_port=sp,target_port=tp,control=c);cost=score(candidate,rel)
                        if cost<best:best=cost;choice={'source_port':sp,'target_port':tp,'control':c}
            if choice:
                r.update(choice);r.pop('source_anchor',None);r.pop('target_anchor',None);changed=True
        if not changed:break
    from scene_render import preview_finding_fix
    # A fixed label can block every reasonable lane. Move only that label when
    # the same full audit confirms the correction creates no new problems.
    for _ in range(2):
        improved=False
        for finding in audit_scene(scene)['findings']:
            if finding['code'] not in ('line-label-overlap','label-object-overlap','label-overlap','line-through-object','connector-through-end','connector-outside-canvas','connector-symbol-on-label','connector-overlap'):continue
            result=preview_finding_fix(scene,finding)
            if result['changed']:scene=result['scene'];improved=True
        if not improved:break
    return normalize_scene(scene)
