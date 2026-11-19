"""Deterministic rank layout for acyclic workflows and small mechanisms."""
import re


def reconcile_binding_products(scene):
    """Connect an explicitly extracted binding product to its two reactants.

    Requires both an evidenced binding edge and an exact compound name. No
    intermediates or textbook pathway knowledge are introduced here.
    """
    objects={o['id']:o for o in scene['objects']}
    def name(value):return re.sub(r'[^a-z0-9\u4e00-\u9fff]','',value.lower())
    for relation in list(scene['relations']):
        if relation['type']!='binds' or not relation.get('evidence'):continue
        a,b=objects[relation['source']],objects[relation['target']]
        names=[name(a['label']),name(b['label'])]
        if not all(names):continue
        for product in objects.values():
            if product['id'] in (a['id'],b['id']) or product['type'] not in ('complex','receptor_dimer'):continue
            label=name(re.sub(r'复合物|复合体|complex', '',product['label'],flags=re.I))
            if label not in (names[0]+names[1],names[1]+names[0]):continue
            # Already connected products and author-drawn scenes need no repair.
            if any(r['target']==product['id'] for r in scene['relations']):continue
            for index,reactant in enumerate((a,b)):
                ident=('formation_'+relation['id'])[:88]+str(index)
                if any(r['id']==ident for r in scene['relations']):continue
                scene['relations'].append(dict(id=ident,source=reactant['id'],target=product['id'],
                    type='converts',label='结合形成' if index==0 else '',evidence=relation['evidence']))
                scene['requirements']['relations'].append(ident)
    text=scene['source_text']
    if re.search(r'(?:未提供|未说明|不明确).{0,12}中间(?:环节|步骤).{0,15}待确认',text):
        for relation in scene['relations']:
            if relation['type'] in ('activates','inhibits','transports'):
                relation.update(indirect=True,uncertain=True)
                if not relation.get('label'):relation['label']='中间环节待确认'
    return scene


def rank_layout(scene,objects,force,put,dims):
    """Return false for cycles/disconnected graphs so existing layouts apply."""
    if len(objects)<2:return False
    ids={o['id'] for o in objects}
    edges={(r['source'],r['target']) for r in scene['relations']
           if r['source'] in ids and r['target'] in ids and r['type'] in ('sequence','activates','converts','transports')}
    notes=[]
    connected={x for edge in edges for x in edge}
    for obj in objects:
        if obj['id'] in connected:continue
        links=[r for r in scene['relations'] if r['type']=='associates' and obj['id'] in (r['source'],r['target'])]
        targets=[r['target'] if r['source']==obj['id'] else r['source'] for r in links]
        if obj['type']=='text' and len(links)==1 and targets[0] in connected:
            notes.append((obj,targets[0],links[0]))
    main_objects=[o for o in objects if o['id'] not in {n[0]['id'] for n in notes}]
    ids={o['id'] for o in main_objects}
    # A binding pair is a joint input, not a temporal step from one partner to
    # the other. Formation edges place both inputs before their product.
    if not edges or {x for edge in edges for x in edge}!=ids:return False
    incoming={i:set() for i in ids};outgoing={i:set() for i in ids}
    for a,b in edges:incoming[b].add(a);outgoing[a].add(b)
    pending={i:len(incoming[i]) for i in ids};queue=[o['id'] for o in main_objects if not pending[o['id']]]
    ranks={i:0 for i in queue};order={o['id']:index for index,o in enumerate(main_objects)}
    visited=[]
    while queue:
        node=queue.pop(0);visited.append(node)
        for target in sorted(outgoing[node],key=order.get):
            ranks[target]=max(ranks.get(target,0),ranks[node]+1)
            pending[target]-=1
            if pending[target]==0:queue.append(target)
    if len(visited)!=len(main_objects):return False
    columns=[[o for o in main_objects if ranks[o['id']]==rank] for rank in range(max(ranks.values())+1)]
    lanes={}
    for items in columns:
        def lane(o):
            parents=incoming[o['id']]
            return sum(lanes[p] for p in parents)/len(parents) if parents else order[o['id']]
        items.sort(key=lambda o:(lane(o),order[o['id']]))
        for row,o in enumerate(items):lanes[o['id']]=row
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    vertical=cw<110 and len(columns)>3
    # Reserve room for a title and outside labels at the final physical size.
    main=(ch-26 if vertical else cw-16)/len(columns)
    cross= cw-16 if vertical else ch-32
    for rank,items in enumerate(columns):
        slot=cross/len(items)
        for row,o in enumerate(items):
            w,h=dims[o['type']]
            if o['type']=='process':w,h=29,16
            if vertical:w,h=min(w,slot-5),min(h,main-9)
            else:w,h=min(w,main-6),min(h,slot-12)
            if w<10 or h<5:return False
    # No mutation until we know every rank fits.
    for rank,items in enumerate(columns):
        slot=cross/len(items)
        for row,o in enumerate(items):
            w,h=dims[o['type']]
            if o['type']=='process':w,h=29,16
            if vertical:
                w,h=min(w,slot-5),min(h,main-9);x=8+slot*(row+.5)-w/2;y=12+main*(rank+.5)-h/2
            else:
                w,h=min(w,main-6),min(h,slot-12);x=8+main*(rank+.5)-w/2;y=12+slot*(row+.5)-h/2
            put(o,x,y,w,h,force)
    if scene['layout']=='process':
        colors=(scene['style']['palette']['primary'],scene['style']['palette']['accent'],scene['style']['palette']['secondary'])
        branches={}
        for node in visited:
            parents=incoming[node]
            inherited={branches[p] for p in parents if p in branches}
            if len(parents)==1 and len(outgoing[next(iter(parents))])>1:
                siblings=sorted(outgoing[next(iter(parents))],key=order.get);branches[node]=siblings.index(node)%len(colors)
            elif len(inherited)==1 and len(parents)==1:branches[node]=next(iter(inherited))
        for o in main_objects:
            if o['id'] in branches:o.setdefault('fill',colors[branches[o['id']]])
    by_id={o['id']:o for o in main_objects}
    counts={}
    from scene_render import _measure
    from scene_document import PT_MM
    for note,target,relation in notes:
        parent=by_id[target];index=counts.get(target,0);counts[target]=index+1
        w=min(cw-8,max(parent['w'],_measure(note['label'],note.get('font_size_pt',8)*PT_MM)+2))
        put(note,max(4,min(cw-w-4,parent['x']+parent['w']/2-w/2)),parent['y']+parent['h']+7+index*7,w,3,force)
        note.update(role='annotation',parent_id=target,placement='outside',label_dy=-2)
        relation.update(callout=True,uncertain=False,source=note['id'],target=target,source_port='n',target_port='s')
    scene['provenance']['layout_method']='topology-with-notes' if notes else 'topology'
    for r in scene['relations']:
        if (r['source'],r['target']) not in edges:continue
        if force or not r.get('control'):
            r.pop('control',None)
            r.update(source_port='s' if vertical else 'e',target_port='n' if vertical else 'w')
    return True
