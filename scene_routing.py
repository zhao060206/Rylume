"""Bounded routing for new scenes; explicit author edits are never changed here."""
from __future__ import annotations
import copy
import math


def repair_connection_routes(value, passes=3):
    import numpy as np
    from scene_document import audit_scene, normalize_scene
    from scene_render import connection_geometry, label_boxes
    scene=normalize_scene(copy.deepcopy(value));cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    objects={o['id']:o for o in scene['objects']}
    t=np.linspace(.015,.985,100);u=1-t
    for _ in range(passes):
        findings=audit_scene(scene)['findings']
        affected={f['object_ids'][0] for f in findings if f['code']=='line-label-overlap'}
        if not affected:break
        changed=False
        for r in scene['relations']:
            if r['id'] not in affected:continue
            labels=[b for b in label_boxes(scene) if b['id']!=r['id']]
            obstructions=[o for o in scene['objects'] if o.get('visible') and o.get('role')!='context' and o['id'] not in (r['source'],r['target'])]
            boxes=np.array([[b['x']-.3,b['y']-.3,b['x']+b['w']+.3,b['y']+b['h']+.3] for b in labels])
            solids=np.array([[b['x'],b['y'],b['x']+b['w'],b['y']+b['h']] for b in obstructions])
            def score(g):
                cx,cy=g['control']['x'],g['control']['y']
                x=u*u*g['x1']+2*u*t*cx+t*t*g['x2'];y=u*u*g['y1']+2*u*t*cy+t*t*g['y2']
                label_hits=0;object_hits=0
                if len(boxes):label_hits=int(((x[:,None]>boxes[:,0])&(x[:,None]<boxes[:,2])&(y[:,None]>boxes[:,1])&(y[:,None]<boxes[:,3])).sum())
                if len(solids):object_hits=int(((x[:,None]>solids[:,0])&(x[:,None]<solids[:,2])&(y[:,None]>solids[:,1])&(y[:,None]<solids[:,3])).sum())
                outside=int(((x<.5)|(x>cw-.5)|(y<.5)|(y>ch-.5)).sum())
                length=float(np.hypot(np.diff(x),np.diff(y)).sum())
                return(label_hits+outside*10,object_hits,length)
            original=connection_geometry(scene,r);best=score(original);choice=None
            if best[0]==0:continue
            # Ports and control are visual geometry only: relation identity,
            # evidence, type and direction stay unchanged.
            for sp in ('n','e','s','w'):
                for tp in ('n','e','s','w'):
                    probe={**r,'source_port':sp,'target_port':tp,'control':{'x':cw/2,'y':ch/2},'label_position':{'x':0,'y':0}}
                    probe.pop('source_anchor',None);probe.pop('target_anchor',None)
                    g=connection_geometry(scene,probe);mx,my=(g['x1']+g['x2'])/2,(g['y1']+g['y2'])/2
                    for dx,dy in ((0,0),(0,-12),(0,12),(-12,0),(12,0),(-24,0),(24,0),(0,-24),(0,24),(-48,0),(48,0),(0,-48),(0,48),(-24,-24),(24,-24),(-24,24),(24,24),(-72,0),(72,0)):
                        c={'x':mx+dx,'y':my+dy};candidate={**g,'control':c};cost=score(candidate)
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
            if finding['code'] not in ('line-label-overlap','label-object-overlap','label-overlap'):continue
            result=preview_finding_fix(scene,finding)
            if result['changed']:scene=result['scene'];improved=True
        if not improved:break
    return normalize_scene(scene)
