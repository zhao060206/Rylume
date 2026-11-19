"""Authored presentation constraints and image-part callouts, without new mechanisms."""
import json
import math
import re


def callout_groups(scene):
    objects={o['id']:o for o in scene['objects']}
    groups={}
    for relation in scene['relations']:
        a,b=objects[relation['source']],objects[relation['target']]
        if a['type']!='text' and b['type']=='text':a,b=b,a
        if a['type']!='text' or not b.get('parent_id') or relation['type']!='associates':continue
        parent=objects[b['parent_id']]
        if parent['type']=='text':continue
        groups.setdefault(parent['id'],[]).append((a,b,relation))
    return groups


def apply_presentation(scene, config):
    brief=str(config.get('generation_brief') or scene['source_text'])
    title_term=r'(?:图题|图?标题|figure title)'
    if re.search(title_term,brief,re.I) and not re.search(r'(?:无|不(?:要|需|显示|添加)?).{0,3}'+title_term,brief,re.I):
        scene['style']['show_title']=True
        requested=re.search(title_term+r'\s*(?:为|是|[:：])?\s*[“「"]([^”」"\n]{1,120})[”」"]',brief,re.I)
        if requested:scene['title']=requested[1]
        titles=[o for o in scene['objects'] if o['type']=='text' and o['label']==scene['title']
                and not any(r['source']==o['id'] or r['target']==o['id'] for r in scene['relations'])]
        if requested and not titles:
            ident='figure_title'
            ids={o['id'] for o in scene['objects']}
            while ident in ids:ident+='_title'
            title=dict(id=ident,type='text',role='annotation',label=scene['title'],evidence='')
            scene['objects'].append(title);titles=[title]
            scene['requirements']['objects'].append(ident)
        if titles:
            # Keep the model's editable title rather than drawing it twice.
            scene['style']['show_title']=False
            for o in titles:o.update(x=8,y=2,w=scene['canvas']['width_mm']-16,h=4,label_dy=-1,font_size_pt=10)
    if scene['layout']=='process':
        steps=[o for o in scene['objects'] if o['type']=='process' and not o.get('parent_id')]
        for o in steps:
            if not o.get('asset_id') and not o.get('state'):o['state']='flow_step'
        numbering=re.search(r'阶段编号|步骤编号|步骤\s*1\s*[–—-]\s*\d+|numbered steps|(?:独立)?数字\s*1\s*[、,，]\s*2\s*[、,，]\s*3',brief,re.I)
        denied=re.search(r'(?:不要|不需(?:要)?|无需|不添加|不显示)\s*(?:阶段|步骤|独立数字)?编号|(?:不要|无需)\s*(?:独立)?数字',brief)
        if numbering and not denied:
            above=bool(re.search(r'(?:框|阶段|步骤|方框)(?:的)?(?:上方|顶部)|above',brief,re.I))
            ids={o['id'] for o in scene['objects']}
            for i,o in enumerate(steps,1):
                ident='step_number_'+o['id'][:76]
                if ident not in ids:
                    # The text is a separately selectable child, so it follows
                    # its stage on move without losing independent editing.
                    scene['objects'].append(dict(id=ident,type='text',role='annotation',label=str(i),
                        parent_id=o['id'],placement='outside' if above else 'inside',x=o['x']+o['w']/2-2.5 if above else o['x']+1,
                        y=o['y']-7 if above else o['y']+.5,w=5,h=2,
                        font_size_pt=8,label_dy=-2,evidence=''))
                    scene['requirements']['objects'].append(ident)
                    ids.add(ident)
    if config.get('illustration_mode')!='image':return scene
    by_id={o['id']:o for o in scene['objects']};groups=callout_groups(scene)
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    for row,(parent_id,items) in enumerate(groups.items()):
        parent=by_id[parent_id];slot=(ch-24)/len(groups)
        parent['display_name']=parent.get('display_name') or parent['label']
        parent['label']=''
        ph=min(slot-10,cw*.40)
        parent.update(x=cw*.18,y=12+row*slot+(slot-ph)/2,w=cw*.56,h=ph)
        names=[]
        for i,(label,part,relation) in enumerate(items):
            name=part.get('display_name') or part['label'];names.append(name)
            part.update(display_name=name,depiction='anchor',role='annotation',placement='inside',label='',w=.5,h=.5,
                        x=parent['x']+parent['w']/2,y=parent['y']+parent['h']/2)
            size=max(8,label.get('font_size_pt',8))
            text_width=sum(1 if ord(c)>127 else .55 for c in label['label'])*size*25.4/72
            label.update(x=cw*.80,y=parent['y']+parent['h']*(i+1)/(len(items)+1)-2,w=min(cw*.18,max(8,text_width+2)),h=3,
                         font_size_pt=max(8,label.get('font_size_pt',8)),role='annotation',label_dy=-3)
            relation.update(source=label['id'],target=part['id'],callout=True,source_port='w',target_port='e',stroke_pt=.7)
            if relation.get('label','').strip().lower() in ('指示线','引线','标注','关联','callout','pointer','leader line'):relation['label']=''
            for key in ('control','source_anchor','target_anchor'):relation.pop(key,None)
        parent['visual_description']=(parent.get('visual_description','')+'。主体必须清楚呈现这些原文指定部位：'+'、'.join(names))[:1000]
    return scene


def locate_callouts(scene, config):
    """Locate named parts in the actual generated pixels; never guess a feature."""
    import pipeline
    from scene_document import SceneError
    objects={o['id']:o for o in scene['objects']}
    source=config.get('vision') or {}
    if not source.get('base_url') or not source.get('model'):source=config.get('text') or {}
    for parent_id,items in callout_groups(scene).items():
        if config.get('redraw_ids') and parent_id not in config['redraw_ids']:continue
        parent=objects[parent_id]
        if not parent.get('illustration'):continue
        names=[{'id':part['id'],'name':part.get('display_name','')} for _,part,_ in items]
        result=pipeline.chat_json({**config,'text':source},[{'role':'user','content':[
            {'type':'text','text':'Locate these explicitly requested scientific parts in this generated illustration. Return JSON {parts:[{id,x,y,visible:true}]} with x,y normalized 0..1 in the attached image. Choose a point ON the named visible feature, not a label or empty background. If a feature is absent or ambiguous set visible=false, do not guess. Names: '+json.dumps(names,ensure_ascii=False)},
            {'type':'image_url','image_url':{'url':parent['illustration']['data']}}]}],temperature=0,max_tokens=1600,timeout=90,allow_fallback=False)
        candidates={p.get('id'):p for p in result.get('parts',[]) if isinstance(p,dict)}
        # A second pass sees numbered markers on the actual pixels rather
        # than accepting the first coordinates as scientific evidence.
        import base64,io
        from PIL import Image,ImageDraw
        with Image.open(io.BytesIO(base64.b64decode(parent['illustration']['data'].split(',')[1]))) as original:
            pixels=original.convert('RGBA');marked=original.convert('RGB');iw,ih=marked.size
        draw=ImageDraw.Draw(marked)
        for index,item in enumerate(names,1):
            p=candidates.get(item['id'],{});x,y=p.get('x'),p.get('y')
            if type(x) in (float,int) and type(y) in (float,int) and all(math.isfinite(v) and 0<=v<=1 for v in (x,y)):
                px,py=x*iw,y*ih;r=max(3,min(iw,ih)/160)
                draw.ellipse((px-r,py-r,px+r,py+r),outline='red',width=2);draw.text((px+r+2,py),str(index),fill='red')
        stream=io.BytesIO();marked.save(stream,'PNG')
        verification=pipeline.chat_json({**config,'text':source},[{'role':'user','content':[
            {'type':'text','text':'Verify every proposed marker against the named scientific feature in these pixels. Numbered red circles are candidates, not ground truth. Return JSON {parts:[{id,x,y,visible:true,evidence:"visible feature and why this point matches"}]}. Correct wrong coordinates (normalized 0..1). If absent or ambiguous set visible=false. Do not infer unseen anatomy. Candidates: '+json.dumps([dict(item,index=i+1,candidate=candidates.get(item['id'])) for i,item in enumerate(names)],ensure_ascii=False)},
            {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()}}]}],temperature=0,max_tokens=2200,timeout=90,allow_fallback=False)
        found={p.get('id'):p for p in verification.get('parts',[]) if isinstance(p,dict)}
        missing=[]
        for _,part,_ in items:
            point=found.get(part['id'],{});x,y=point.get('x'),point.get('y')
            if point.get('visible') is not True or type(x) not in (float,int) or type(y) not in (float,int) or not all(math.isfinite(v) and 0<=v<=1 for v in (x,y)):
                missing.append(part.get('display_name') or part['id']);continue
            snapped=visible_pixel_point(pixels,x,y)
            if snapped is None:
                missing.append(part.get('display_name') or part['id']);continue
            x,y=snapped
            # The cropped image is fitted inside the parent's frame (SVG meet).
            scale=min(parent['w']/iw,parent['h']/ih);w,h=iw*scale,ih*scale
            part.update(x=max(parent['x'],min(parent['x']+parent['w']-.5,parent['x']+(parent['w']-w)/2+x*w-.25)),y=max(parent['y'],min(parent['y']+parent['h']-.5,parent['y']+(parent['h']-h)/2+y*h-.25)),edit_status='needs_review')
            part['localization']={'status':'model_checked','evidence':str(point.get('evidence') or '模型已二次对照像素；仍需作者核对')[:1000],'x':x,'y':y}
        arrange_callout_labels(scene,parent,items)
        if missing:raise SceneError('插画中未能可靠定位：'+'、'.join(missing)+'。已保留草稿，请核对或重绘主体。')
    return scene


def visible_pixel_point(image,x,y):
    """Correct only sub-feature whitespace error; never bridge a missing part."""
    import numpy as np
    px=min(image.width-1,max(0,round(x*(image.width-1))));py=min(image.height-1,max(0,round(y*(image.height-1))))
    rgb=np.asarray(image);ink=(rgb[:,:,3]>128)&(rgb[:,:,:3].min(axis=2)<245)
    if ink[py,px]:return x,y
    radius=max(2,round(min(image.size)*.03));left=max(0,px-radius);top=max(0,py-radius)
    ys,xs=np.nonzero(ink[top:min(image.height,py+radius+1),left:min(image.width,px+radius+1)])
    if not len(xs):return None
    distances=(xs+left-px)**2+(ys+top-py)**2;index=distances.argmin()
    if distances[index]>radius**2:return None
    return ((xs[index]+left)/(image.width-1),(ys[index]+top)/(image.height-1))


def arrange_callout_labels(scene,parent,items):
    """Place leaders on the nearest side in anchor order, keeping them distinct."""
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    for side in ('left','right'):
        group=[item for item in items if ('left' if item[1]['x']+item[1]['w']/2<parent['x']+parent['w']/2 else 'right')==side]
        group.sort(key=lambda item:item[1]['y'])
        if not group:continue
        gap=max(6,min(10,(ch-16)/max(1,len(group))))
        desired=[max(8,min(ch-8-gap*(len(group)-1-i),part['y'])) for i,(_,part,_) in enumerate(group)]
        for i in range(1,len(desired)):desired[i]=max(desired[i],desired[i-1]+gap)
        for y,(label,part,relation) in zip(desired,group):
            label['y']=y;label['x']=max(2,parent['x']-label['w']-5) if side=='left' else min(cw-label['w']-2,parent['x']+parent['w']+5)
            relation.update(source_port='e' if side=='left' else 'w',target_port='auto')
            relation.pop('control',None)
