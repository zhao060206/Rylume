"""Observed structures own disjoint vector regions; moving one never erases neighbours.

The model only identifies regions. Original pixels supply every visible colour.
No generative repair, inferred scientific contents, or bounding-box background patch.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from scene_document import SceneError, empty_scene, normalize_scene

INSTRUCTION = '''Identify independently movable structures in this scientific figure.
Return JSON only: {"objects":[{"id":"cell1","kind":"structure|arrow|text",
"label":"visible name or brief observed structure name", "x":0.1,"y":0.1,"w":0.2,"h":0.2,
"polygon":[[0.1,0.1],[0.3,0.1],[0.3,0.3],[0.1,0.3]],"confidence":0.9,
"parent_id":"optional enclosing structure ID"}],"warnings":["specific uncertainty"]}.
Coordinates normalized 0..1. Tightly trace the visible outer boundary with 8-40 vertices,
including all parts belonging to ONE structure (e.g. one Golgi stack, NOT each cisterna).
Separate every arrow, label, cell, organelle, instrument. Do NOT include neighbouring
structures, labels or arrows in a structure polygon. Text may use its bounding rectangle.
Nested structures may overlap: smaller regions own their pixels. Parent means containment,
not temporal sequence. Do not describe a whole panel as one structure if its contents can
be distinguished. Keep text exactly as printed, including case, Greek letters and numbers.
No invented data, reconstruction, hidden shapes, SVG or pixel arrays. Up to 180 objects.
Uncertain boundaries, occlusion or unreadable text must appear in warnings.'''


def observe(png, config):
    from figure_imports import observe as read
    return read(png, config, instruction=INSTRUCTION)


def detail_regions(png, config, existing, checkpoint=None):
    """Read overlapping close-ups; merge only fully visible, distinct objects."""
    from figure_imports import observe as read
    image=Image.open(io.BytesIO(png)).convert('RGB');width,height=image.size
    if width*height<400_000 or sum(o.get('kind')=='structure' for o in existing)<3:return []
    tick=checkpoint or (lambda message:None);added=[]
    def box(o):
        points=o.get('polygon') or []
        if not points:return None
        xs,ys=zip(*points);return min(xs),min(ys),max(xs),max(ys)
    def duplicate(candidate):
        a=box(candidate)
        if a is None:return True
        area=(a[2]-a[0])*(a[3]-a[1])
        for other in [*existing,*added]:
            if other.get('kind')!='structure':continue
            b=box(other)
            if b is None:continue
            other_area=(b[2]-b[0])*(b[3]-b[1])
            intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
            if min(area,other_area)>0 and intersection/min(area,other_area)>.7:
                if min(area,other_area)/max(area,other_area)>.45:return True
                # Small details inside an already complete organelle stay in
                # that organelle, rather than turning one MVB into many pieces.
                if other_area<.12 and area<other_area*.45 and intersection/area>.85:return True
        return False
    for index,(x0,y0,x1,y1) in enumerate(((0,0,.58,.58),(.42,0,1,.58),(0,.42,.58,1),(.42,.42,1,1))):
        tick(f'正在放大核对第 {index+1}/4 个区域，补齐小图标与说明框')
        left,top,right,bottom=round(x0*width),round(y0*height),round(x1*width),round(y1*height)
        stream=io.BytesIO();image.crop((left,top,right,bottom)).save(stream,'PNG')
        result=read(stream.getvalue(),config,instruction=INSTRUCTION+'\nCLOSE-UP INVENTORY: Return ONLY complete visible structures/icons and filled annotation panels. Include each small vesicle, receptor icon, ligand, and callout panel as one structure. For a text panel, trace the coloured panel background and set its label to a short heading actually printed in it. Do not return individual text lines or arrows. Do not split an organelle into paths. Exclude shapes cut by the crop boundary. Do not infer invisible parts. Coordinates are relative to THIS cropped image. Up to 40 objects.')
        if not isinstance(result,dict) or not isinstance(result.get('objects'),list):raise SceneError('局部结构清点返回格式有误，原图保留，请重新转换。')
        for n,raw in enumerate(result['objects'][:40]):
            if raw.get('kind')!='structure':continue
            points=raw.get('polygon')
            if not isinstance(points,list) or not 3<=len(points)<=100:continue
            try:
                points=[[float(x),float(y)] for x,y in points]
            except (TypeError,ValueError):continue
            if any(not 0<=v<=1 for p in points for v in p):continue
            # An icon touching a crop edge has no observed complete outline.
            if any((x<.003 and left>0) or (x>.997 and right<width) or (y<.003 and top>0) or (y>.997 and bottom<height) for x,y in points):continue
            obj={'id':f'detail_{index}_{n}','kind':'structure','label':str(raw.get('label') or '局部结构')[:240],
                 'polygon':[[(left+x*(right-left))/width,(top+y*(bottom-top))/height] for x,y in points],
                 'confidence':raw.get('confidence',0)}
            if not duplicate(obj):added.append(obj)
    return added


def refine_containers(rgb, objects):
    """Fit a large model outline to observed colour boundaries, before ownership."""
    height,width=rgb.shape[:2];refined=[]
    for obj in objects:
        points=obj.get('polygon')
        if obj.get('kind')!='structure' or not isinstance(points,list):continue
        coords=np.array(points,dtype=np.float32)*[width,height]
        if abs(cv2.contourArea(coords.astype(np.int32)))<width*height*.12:continue
        original=np.zeros((height,width),np.uint8);cv2.fillPoly(original,[coords.astype(np.int32)],1)
        pad=round(min(width,height)*.055);left=max(0,int(coords[:,0].min())-pad);right=min(width,int(coords[:,0].max())+pad)
        top=max(0,int(coords[:,1].min())-pad);bottom=min(height,int(coords[:,1].max())+pad)
        crop=rgb[top:bottom,left:right];seed=original[top:bottom,left:right]
        factor=min(1,800/max(crop.shape[:2]));size=(max(1,round(crop.shape[1]*factor)),max(1,round(crop.shape[0]*factor)))
        work=cv2.resize(crop,size);prior=cv2.resize(seed,size,interpolation=cv2.INTER_NEAREST)
        samples=work[(prior>0)&np.any(work<235,axis=2)&(work.mean(axis=2)>130)]
        if len(samples)<50:continue
        colours,counts=np.unique(samples//16,axis=0,return_counts=True);dominant=np.median(samples[np.all(samples//16==colours[counts.argmax()],axis=1)],axis=0)
        labels=np.full(work.shape[:2],cv2.GC_PR_BGD,np.uint8);labels[prior>0]=cv2.GC_PR_FGD
        labels[np.all(work>248,axis=2)]=cv2.GC_BGD
        core=(np.linalg.norm(work.astype(np.float32)-dominant,axis=2)<14)&(prior>0)
        core=cv2.erode(core.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
        if not core.any() or not np.any(labels==cv2.GC_BGD):continue
        labels[core]=cv2.GC_FGD
        cv2.grabCut(work,labels,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),3,cv2.GC_INIT_WITH_MASK)
        mask=((labels==cv2.GC_FGD)|(labels==cv2.GC_PR_FGD)).astype(np.uint8)
        contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        if not contours:continue
        contour=max(contours,key=cv2.contourArea);candidate=np.zeros_like(prior);cv2.drawContours(candidate,[contour],-1,1,cv2.FILLED)
        observed=prior.astype(bool)&np.any(work<245,axis=2)
        if np.sum(candidate.astype(bool)&observed)<np.sum(observed)*.9 or candidate.sum()>prior.sum()*2.5:continue
        # Include the observed outer stroke, not just the pale interior found
        # by GrabCut. Other labelled objects still win exclusive ownership.
        candidate=cv2.dilate(candidate,np.ones((3,3),np.uint8))
        contour=max(cv2.findContours(candidate,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0],key=cv2.contourArea)
        epsilon=.8
        outline=cv2.approxPolyDP(contour,epsilon,True)
        while len(outline)>100:
            epsilon*=1.3;outline=cv2.approxPolyDP(contour,epsilon,True)
        if len(outline)<3:continue
        obj['polygon']=[[(left+x/factor)/width,(top+y/factor)/height] for [[x,y]] in outline.tolist()]
        refined.append(obj['id'])
    return refined


def panel_regions(rgb, objects):
    """Recover filled rectangular callouts from colour and observed OCR lines."""
    height,width=rgb.shape[:2];text=[o for o in objects if o.get('kind')=='text'];panels=[];seen=[]
    for word in text:
        x,y,w,h=[float(word.get(k,0)) for k in ('x','y','w','h')]
        left=max(0,round(x*width)-3);right=min(width,round((x+w)*width)+3)
        top=max(0,round(y*height)-3);bottom=min(height,round((y+h)*height)+3)
        crop=rgb[top:bottom,left:right]
        if crop.size==0:continue
        colour=np.median(crop.reshape(-1,3),axis=0)
        if not 150<colour.mean()<240 or colour.max()-colour.min()>26:continue
        if any(np.linalg.norm(colour-other)<4 for other in seen):continue
        seen.append(colour)
        mask=(np.max(np.abs(rgb.astype(np.int16)-colour),axis=2)<5).astype(np.uint8)
        count,labels,stats,_=cv2.connectedComponentsWithStats(mask,connectivity=8)
        for n in range(1,count):
            px,py,pw,ph,area=map(int,stats[n])
            if area<500 or area>width*height*.35 or min(pw,ph)<10 or area/(pw*ph)<.65:continue
            # An ellipse, pale cell fill or gradient is not a rectangular panel.
            corners=[mask[cy:cy+3,cx:cx+3].mean() for cx,cy in ((px,py),(px+pw-3,py),(px,py+ph-3),(px+pw-3,py+ph-3))]
            if min(corners)<.6:continue
            lines=[o for o in text if px<=(o['x']+o['w']/2)*width<=px+pw and py<=(o['y']+o['h']/2)*height<=py+ph]
            if not lines:continue
            a=(px/width,py/height,(px+pw)/width,(py+ph)/height);overlap=False
            for other in [*objects,*panels]:
                if other.get('kind')!='structure' or not other.get('polygon'):continue
                xs,ys=zip(*other['polygon']);b=(min(xs),min(ys),max(xs),max(ys))
                intersect=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                aa=(a[2]-a[0])*(a[3]-a[1]);bb=(b[2]-b[0])*(b[3]-b[1])
                if min(aa,bb)>0 and intersect/min(aa,bb)>.8 and min(aa,bb)/max(aa,bb)>.5:overlap=True;break
            if overlap:continue
            lines.sort(key=lambda o:(o['y'],o['x']))
            ident='panel_'+str(len(panels))
            while any(o['id']==ident for o in [*objects,*panels]):ident+='a'
            panels.append({'id':ident,'kind':'structure','label':' '.join(o['label'] for o in lines)[:180],
                'polygon':[[a[0],a[1]],[a[2],a[1]],[a[2],a[3]],[a[0],a[3]]],'confidence':1})
            for line in lines:line['parent_id']=ident
    return panels


def remaining_regions(png, config, objects, checkpoint=None):
    """A measured, single follow-up pass for genuinely unassigned contents."""
    from figure_imports import observe as read
    rgb=np.asarray(Image.open(io.BytesIO(png)).convert('RGB'));_,owner=partition(rgb,objects)
    foreground=np.any(rgb<245,axis=2);missing=(owner<0)&foreground
    if not foreground.any() or missing.sum()/foreground.sum()<.02:return []
    if checkpoint:checkpoint('正在对照尚未分配的部分，补齐遗漏的图标、说明框和连线')
    overlay=np.where((owner>=0)[:,:,None],(rgb.astype(np.float32)*.15+255*.85).astype(np.uint8),rgb)
    stream=io.BytesIO();Image.fromarray(overlay).save(stream,'PNG')
    result=read(png,config,detail_png=stream.getvalue(),instruction=INSTRUCTION+'\nREMAINING-REGION CHECK: The second image fades assigned pixels. Return ONLY whole structures/icons, coloured text panels, arrow lines or legend groups that own a substantial still-coloured region. Use ORIGINAL coordinates and original labels. Include a complete outer boundary even when some text/parts are already assigned. Never split a known organelle into small internal details. Do not identify thin tracing-edge slivers as new objects. Do not return a whole cell or whole figure. Up to 30 objects.')
    if not isinstance(result,dict) or not isinstance(result.get('objects'),list):raise SceneError('遗漏清点返回格式有误，请重试；原图保留。')
    added=[];height,width=owner.shape
    for n,raw in enumerate(result['objects'][:30]):
        if raw.get('kind') not in ('structure','arrow') or not isinstance(raw.get('polygon'),list):continue
        try:points=np.array(raw['polygon'],dtype=float)
        except (TypeError,ValueError):continue
        if points.ndim!=2 or points.shape[1]!=2 or not 3<=len(points)<=100 or not np.isfinite(points).all() or np.any((points<0)|(points>1)):continue
        mask=np.zeros(owner.shape,np.uint8);cv2.fillPoly(mask,[np.round(points*[width,height]).astype(np.int32)],1)
        ink=mask.astype(bool)&foreground;unassigned=ink&missing
        if unassigned.sum()<100 or unassigned.sum()/max(1,ink.sum())<.2:continue
        if ink.sum()>foreground.sum()*.18:continue
        obj={'id':f'completion_{n}','kind':raw['kind'],'label':str(raw.get('label') or '补全结构')[:240],
             'polygon':points.tolist(),'confidence':raw.get('confidence',0)}
        added.append(obj);missing[mask>0]=False
    return added


def observations(png, config, checkpoint=None):
    """A requested AI conversion must fail visibly when the reader is unavailable."""
    value=observe(png, config)
    if not isinstance(value,dict) or not isinstance(value.get('objects'),list) or not 1<=len(value['objects'])<=180:
        raise SceneError('模型没有返回有效结构区域；原图已保留，请重试或选择本机路径模式。')
    if sum(o.get('kind')=='arrow' for o in value['objects'])<sum(o.get('kind')=='structure' for o in value['objects']) and sum(o.get('kind')=='structure' for o in value['objects'])>2:
        from figure_imports import observe as read
        arrows=read(png,config,instruction=INSTRUCTION+'\nSECOND PASS: Return ONLY the visible arrows and connector lines. Do not return text or biological structures. Include curved arrows. Trace each line and its arrowhead tightly; do not enclose the whitespace between distant structures. If there are no arrows, return objects:[] and explain in warnings.')
        if not isinstance(arrows,dict) or not isinstance(arrows.get('objects'),list):raise SceneError('连线轮廓识别未完成，请重试；原图保留。')
        if any(o.get('kind')=='arrow' for o in arrows['objects']):value['objects']=[o for o in value['objects'] if o.get('kind')!='arrow']
        for i,arrow in enumerate(arrows['objects'][:80]):
            if arrow.get('kind')!='arrow':continue
            value['objects'].append({**arrow,'id':f'arrow_pass_{i}'})
        if not any(o.get('kind')=='arrow' for o in value['objects']):
            value.setdefault('warnings',[]).append('AI 未识别到独立连线；请在原图中补选箭头边界。')
    value['objects'].extend(detail_regions(png,config,value['objects'],checkpoint))
    refine_containers(np.asarray(Image.open(io.BytesIO(png)).convert('RGB')),value['objects'])
    from figure_vectorize import local_text_observation
    local,warnings=local_text_observation(png)
    # Pixel-aligned OCR owns text geometry. A model may confuse width with the
    # right coordinate; such a box must never swallow unrelated labels.
    model_text=[o for o in value['objects'] if o.get('kind')=='text']
    if local.get('objects'):
        from difflib import SequenceMatcher
        value['objects']=[o for o in value['objects'] if o.get('kind')!='text']
        for item in local['objects']:
            label=item['label'];nearby=[]
            for other in model_text:
                proposed=str(other.get('label','')).strip()
                if not proposed or '\n' in proposed:continue
                try:
                    cx=float(other['x'])+float(other['w'])/2;cy=float(other['y'])+float(other['h'])/2
                    distance=((item['x']+item['w']/2-cx)**2+(item['y']+item['h']/2-cy)**2)**.5
                except (KeyError,ValueError,TypeError):continue
                similarity=SequenceMatcher(None,label.casefold(),proposed.casefold()).ratio()
                if distance<.08 and similarity>.65:nearby.append((similarity-distance,proposed))
            candidate=max(nearby)[1] if nearby else ''
            item={**item,'id':'local_'+item['id']}
            if candidate and candidate!=label:
                item['model_suggestion']=candidate
                warnings.append(f'文字识别不一致：OCR {label} / 模型 {candidate}，请对照原图后采用。')
            value['objects'].append(item)
    else:
        warnings.append('本机 OCR 未给出可用字框，采用模型文字区域；请重点核对范围和拼写。')
    value['objects'].extend(panel_regions(np.asarray(Image.open(io.BytesIO(png)).convert('RGB')),value['objects']))
    value['objects'].extend(remaining_regions(png,config,value['objects'],checkpoint))
    return value, warnings[:30]


def partition(rgb, objects):
    """Exclusive ownership, smallest explicit region first; no neighbour capture."""
    height,width=rgb.shape[:2];seen=set();items=[]
    from figure_imports import _number
    for index, raw in enumerate(objects):
        if not isinstance(raw,dict) or raw.get('kind') not in ('structure','arrow','text'):
            raise SceneError('结构区域类型无效，请重新识别')
        ident=raw.get('id')
        if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,70}',ident) or ident in seen:
            raise SceneError('结构区域 ID 无效或重复')
        seen.add(ident)
        item={**raw}
        if raw['kind']=='text':
            x,y,w,h=[_number(raw.get(k),0,1) for k in ('x','y','w','h')]
            if min(w,h)<=0 or x+w>1.001 or y+h>1.001:raise SceneError('文字区域超出原图')
            polygon=[[x,y],[x+w,y],[x+w,y+h],[x,y+h]]
        else:
            polygon=raw.get('polygon')
            if not isinstance(polygon,list) or not 3<=len(polygon)<=100:raise SceneError('结构缺少可用的轮廓；请重新识别或补选边界')
        pts=[]
        for point in polygon:
            if not isinstance(point,list) or len(point)!=2:raise SceneError('结构轮廓坐标无效')
            pts.append([round(_number(point[0],0,1)*width),round(_number(point[1],0,1)*height)])
        if raw['kind']!='text':
            px,py=zip(*pts);x=min(px)/width;y=min(py)/height;w=(max(px)-min(px))/width;h=(max(py)-min(py))/height
            if min(w,h)<=0:raise SceneError('结构轮廓面积无效')
        mask=np.zeros((height,width),np.uint8);cv2.fillPoly(mask,[np.array(pts,np.int32)],1)
        if raw['kind']=='text':
            # OCR boxes are not opaque text panels. Assign ink only so moving
            # a word never carries the cytoplasm or another icon with it.
            left=max(0,int(x*width));top=max(0,int(y*height));right=min(width,int((x+w)*width)+1);bottom=min(height,int((y+h)*height)+1)
            crop=rgb[top:bottom,left:right].astype(np.float32)
            if crop.size:
                light=crop.mean(axis=2);background=float(np.percentile(light,75));chroma=crop.max(axis=2)-crop.min(axis=2)
                ink=(light<background-28)&(chroma<85) if background>128 else (light>background+30)&(chroma<85)
                dilated=cv2.dilate(ink.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
                delta=np.abs(light-background)>5
                mask[:]=0;mask[top:bottom,left:right]=(dilated&delta).astype(np.uint8)
        exclusions=raw.get('exclusions',[])
        if not isinstance(exclusions,list) or len(exclusions)>30:raise SceneError('排除区域数量无效')
        excluded_mask=np.zeros((height,width),np.uint8) if exclusions else None
        for region in exclusions:
            if not isinstance(region,list) or not 3<=len(region)<=100:raise SceneError('排除轮廓无效')
            excluded=[]
            for p in region:
                if not isinstance(p,list) or len(p)!=2:raise SceneError('排除轮廓坐标无效')
                excluded.append([round(_number(p[0],0,1)*width),round(_number(p[1],0,1)*height)])
            cv2.fillPoly(mask,[np.array(excluded,np.int32)],0)
            cv2.fillPoly(excluded_mask,[np.array(excluded,np.int32)],1)
        item['polygon']=[[px/width,py/height] for px,py in pts]
        item.update(x=x,y=y,w=w,h=h,mask=mask.astype(bool),index=index)
        if excluded_mask is not None:item['excluded_mask']=excluded_mask.astype(bool)
        if item['kind']=='structure':item['coverage_mask']=item['mask'].copy()
        items.append(item)
    # An approximate polygon often contains the parent's pale fill around an
    # organelle. Remove only background connected to the polygon boundary.
    # Every excluded pixel remains owned by its parent or the residual layer.
    for item in items:
        mask=item['mask'];area=int(mask.sum())
        if item['kind']=='text' or area>height*width*.12 or area<16:continue
        ring=cv2.dilate(mask.astype(np.uint8),np.ones((7,7),np.uint8)).astype(bool)&~mask
        samples=rgb[ring]
        if len(samples)<30:continue
        quantized=samples//12
        colours,counts=np.unique(quantized,axis=0,return_counts=True);winning=int(counts.argmax())
        if counts[winning]<len(samples)*.25:continue
        chosen=np.all(quantized==colours[winning],axis=1)
        background=np.median(samples[chosen],axis=0)
        similar=(np.linalg.norm(rgb.astype(np.float32)-background,axis=2)<18)&mask
        count,components=cv2.connectedComponents(similar.astype(np.uint8),connectivity=8)
        border=mask&~cv2.erode(mask.astype(np.uint8),np.ones((3,3),np.uint8)).astype(bool)
        reachable=np.unique(components[border&similar]);reachable=reachable[reachable!=0]
        remove=np.isin(components,reachable) if len(reachable) else np.zeros(mask.shape,bool)
        if remove.sum()<area*.9:
            item['mask']=mask&~remove;item['boundary_refined']=bool(remove.any())
            if item['kind']=='structure':
                # Recover the rest of a cisterna/outline when the model's
                # polygon cuts across it. Only connected foreground seeded by
                # this region can grow; a nearby separate icon cannot join it.
                ys,xs=np.where(mask);pad=min(18,max(4,round(max(xs.max()-xs.min(),ys.max()-ys.min())*.12)))
                left=max(0,int(xs.min())-pad);right=min(width,int(xs.max())+pad+1);top=max(0,int(ys.min())-pad);bottom=min(height,int(ys.max())+pad+1)
                foreground=np.linalg.norm(rgb[top:bottom,left:right].astype(np.float32)-background,axis=2)>=18
                _,parts=cv2.connectedComponents(foreground.astype(np.uint8),connectivity=8)
                seeds=item['mask'][top:bottom,left:right]&foreground;labels=np.unique(parts[seeds]);labels=labels[labels!=0]
                grown=np.isin(parts,labels) if len(labels) else np.zeros(parts.shape,bool)
                item['mask'][top:bottom,left:right]|=grown
    ownership=np.full((height,width),-1,np.int16)
    # Exact white is the known page background. Other colours always survive,
    # including coloured panels and uncertain/unassigned boundary pixels.
    foreground=np.any(rgb<255,axis=2)
    for item in sorted(items,key=lambda i:(0 if i['kind']=='text' else 1 if i['kind']=='arrow' else 2,int(i['mask'].sum()))):
        if 'excluded_mask' in item:item['mask']&=~item['excluded_mask']
        mask=item['mask'] & foreground & (ownership<0)
        ownership[mask]=item['index'];item['mask']=mask
    return items,ownership


def colour_palette(rgb, *, error_budget=1.25):
    """Bound colour error while avoiding thousands of almost equal fills."""
    image=Image.fromarray(rgb);foreground=np.any(rgb<245,axis=2)
    # Antialiasing creates hundreds of nearly identical colours in each label.
    # Select the smallest palette that satisfies the SAME measured error bound,
    # rather than exporting a native PowerPoint shape for every shade.
    for colours in (16,32,64,128,256):
        palette=image.quantize(colors=colours,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
        pixels=np.asarray(palette.convert('RGB'))
        error=float(np.abs(rgb.astype(np.float32)-pixels).mean(axis=2)[foreground].mean()) if foreground.any() else 0.0
        if error<=error_budget:return pixels,palette,{'applied':True,'colours':len(palette.getcolors()),'mean_rgb_error':round(error,4)}
    return rgb,None,{'applied':False,'mean_rgb_error':round(error,4)}


def estimate_container_background(rgb, holes, container):
    """Estimate a smooth colour plane; never extend nearby organelle edges.

    Large-hole Telea inpainting creates radial streaks. This local estimate
    preserves background shading, not scientifically meaningful hidden detail.
    """
    import cv2
    result=rgb.copy()
    count,components=cv2.connectedComponents(holes.astype(np.uint8))
    for ident in range(1,count):
        hole=components==ident
        ys,xs=np.where(hole)
        radius=max(5,min(30,round(min(xs.max()-xs.min()+1,ys.max()-ys.min()+1)*.15)))
        ring=cv2.dilate(hole.astype(np.uint8),np.ones((radius*2+1,radius*2+1),np.uint8)).astype(bool)&container&~holes
        ry,rx=np.where(ring)
        if not len(rx):continue
        colour=rgb[ry,rx].astype(float);median=np.median(colour,axis=0)
        distance=np.linalg.norm(colour-median,axis=1)
        good=distance<=max(8,float(np.percentile(distance,65)))
        rx,ry,colour=rx[good],ry[good],colour[good]
        cx,cy=xs.mean(),ys.mean();span=max(1,xs.max()-xs.min(),ys.max()-ys.min())
        basis=np.column_stack([np.ones(len(rx)),(rx-cx)/span,(ry-cy)/span])
        fit=np.linalg.lstsq(basis,colour,rcond=None)[0]
        predicted=np.column_stack([np.ones(len(xs)),(xs-cx)/span,(ys-cy)/span])@fit
        low,high=np.percentile(colour,[5,95],axis=0)
        result[ys,xs]=np.clip(predicted,low,high).round().astype(np.uint8)
    return result


def reconstruct(png, name, config, *, checkpoint=None, regions=None):
    from figure_imports import _dimensions, _snapshot
    from figure_vectorize import _text_color, _font_weight
    from vector_fidelity import region_paths
    tick=checkpoint or (lambda message:None)
    tick('正在识别每个结构、文字和箭头的边界')
    if regions is None:value,warnings=observations(png,config,tick)
    else:value,warnings={'objects':regions,'warnings':[]},[]
    if not isinstance(value.get('objects'),list) or not 1<=len(value['objects'])<=240:raise SceneError('每张图版需包含 1–240 个独立区域，请分图转换')
    image=Image.open(io.BytesIO(png)).convert('RGB');rgb=np.asarray(image)
    items,owner=partition(rgb,value['objects'])
    # Physical containment is observable independently of molecular semantics.
    # Recover the surface under a movable inset instead of baking a white hole
    # into the containing cell. Estimates never replace the preserved source.
    structures=[o for o in items if o['kind']=='structure']
    for child in structures:
        if child.get('parent_id'):continue
        area=int(child['coverage_mask'].sum())
        parents=[p for p in structures if p is not child and p['coverage_mask'].sum()>area*1.6
                 and (child['coverage_mask']&p['coverage_mask']).sum()/max(1,area)>.97]
        if parents:child['parent_id']=min(parents,key=lambda p:p['coverage_mask'].sum())['id']
    # Text wholly inside a structure follows it while remaining independently
    # selectable. External captions are deliberately not associated by proximity.
    for caption in (o for o in items if o['kind']=='text' and not o.get('parent_id')):
        area=int(caption['mask'].sum())
        parents=[p for p in structures if area and (caption['mask']&p['coverage_mask']).sum()/area>.97]
        if parents:caption['parent_id']=min(parents,key=lambda p:p['coverage_mask'].sum())['id']
    estimated_backgrounds=0
    text_mask=np.isin(owner,[o['index'] for o in items if o['kind']=='text'])
    # Repair the exact glyph silhouette below text. Using an OCR rectangle here
    # would erase adjacent icons; leaving a transparent glyph would leave white
    # cutout letters behind when the author moves or rewrites the label.
    underlay=cv2.inpaint(rgb,text_mask.astype(np.uint8)*255,3,cv2.INPAINT_TELEA) if text_mask.any() else rgb
    remaining=text_mask.copy()
    for item in sorted((o for o in items if o['kind']=='structure'),key=lambda o:int(o['coverage_mask'].sum())):
        fill=remaining&item['coverage_mask'];item['render_mask']=item['mask']|fill;remaining[fill]=False
    width,height=_dimensions(*image.size);scale=width/image.width
    scene=empty_scene(Path(name).stem,width_mm=width,height_mm=height);scene['layout']='network'
    scene['style']['show_title']=False
    total_paths=0;total_bytes=0;regions_report=[];palette_reports=[]
    def add(mask,ident,role,label,kind,item=None,pixels=None):
        nonlocal total_paths,total_bytes
        ys,xs=np.where(mask)
        if not len(xs):return
        x,y,right,bottom=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
        pixels=rgb if pixels is None else pixels
        crop=pixels[y:bottom,x:right];local=mask[y:bottom,x:right]
        # An organelle needs its own measured palette: a figure-wide palette
        # wastes colours on unrelated panels and loses subtle local gradients.
        crop,palette,palette_report=colour_palette(crop,error_budget=1.25)
        palette_reports.append(palette_report)
        # Smooth original curves first; retain only measured colour residuals.
        # Alpha, not an opaque crop rectangle, defines a structure's ownership.
        from vectorizer import vectorize_vtracer
        from vector_fidelity import render_pixels
        rgba=np.dstack((crop,local.astype(np.uint8)*255));stream=io.BytesIO();Image.fromarray(rgba).save(stream,'PNG')
        traced,_=vectorize_vtracer(stream.getvalue(),quality='high',overrides={'hierarchical':'cutout','filter_speckle':0,'color_precision':6,'layer_difference':8,'path_precision':3})
        import xml.etree.ElementTree as ET
        root=ET.fromstring(traced);root.attrib.pop('version',None);root.set('viewBox',f'0 0 {right-x} {bottom-y}')
        target=np.where(local[:,:,None],crop,255)
        actual=render_pixels(ET.tostring(root),(right-x,bottom-y))
        errors=(np.abs(target.astype(float)-actual).max(axis=2)>6)&local
        paths=region_paths(crop,errors,precision=1 if palette is not None else 4,batch=2000)
        # Cutout contours of the same colour do not overlap; merge them without
        # changing painter semantics. Keep a structure as one edit object.
        from svgelements import SVG, Shape, Path as SvgPath
        import html
        colours={}
        for element in SVG.parse(io.BytesIO(traced)).elements():
            if not isinstance(element,Shape):continue
            data=re.sub(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?',lambda m:format(float(m[0]),'.3f').rstrip('0').rstrip('.'),SvgPath(element).d())
            colours.setdefault(str(element.fill),[]).append(data)
        markup=f'<svg viewBox="0 0 {right-x} {bottom-y}">'+''.join(f'<path fill="{colour}" stroke="none" d="{html.escape(" ".join(parts),quote=True)}"/>' for colour,parts in colours.items())+''.join(paths)+'</svg>'
        if kind in ('text','arrow'):
            # Thin lettering and arrowheads are most sensitive to spline
            # overshoot. Preserve their exact owned regions instead.
            markup=f'<svg viewBox="0 0 {right-x} {bottom-y}">'+''.join(region_paths(crop,local,precision=1 if palette is not None else 2,batch=2000))+'</svg>'
        total_bytes+=len(markup.encode())
        if total_bytes>24*1024*1024:raise SceneError('图像细节超出可流畅编辑容量，请裁切为单张图版。原图已保留。')
        try:snapshot=_snapshot('import_'+ident,markup)
        except ValueError as exc:raise SceneError('结构轮廓过于复杂，请裁切图版或提高原图清晰度后重试：'+str(exc)) from None
        obj={'id':ident,'type':'text' if kind=='text' else 'process','role':role,'label':label if kind=='text' else '',
             'display_name':label or ('未分配细节' if role=='context' else ident), 'source_role':kind,
             'x':x*scale,'y':y*scale,'w':max(.1,(right-x)*scale),'h':max(.1,(bottom-y)*scale),
             'source_region':{'x':x/image.width,'y':y/image.height,'w':(right-x)/image.width,'h':(bottom-y)/image.height},
             'evidence_source':'reference_image','edit_status':'needs_review',**snapshot}
        if item and item.get('parent_id'):obj['parent_id']=item['parent_id']
        if kind=='text':
            size=max(7,min(48,(bottom-y)*scale*72/25.4*.8/max(1,len(label.splitlines()))));fill=_text_color(image,(x,y,right,bottom))
            obj.update(state='import_text',font_size_pt=size,fill=fill,font_weight=_font_weight(image,(x,y,right,bottom),size),
                       label_dy=-(bottom-y)*scale/2-size*25.4/72*.75,
                       text_appearance={'label':label,'font_size_pt':size,'fill':fill},
                       ocr={'original':label,'confidence':min(1,max(0,float(item.get('confidence',0)))),'confirmed':False,**({'suggested':item['model_suggestion']} if item.get('model_suggestion') else {})})
        scene['objects'].append(obj);total_paths+=len(list(ET.fromstring(markup).iter()))-1
        if item:regions_report.append({k:item[k] for k in ('id','kind','x','y','w','h','polygon','parent_id','exclusions','confidence','boundary_refined','model_suggestion') if k in item}|{'label':label,'pixels':int(mask.sum()),'region':obj['source_region']})
    tick('正在按独立边界建立透明矢量结构')
    residual=((owner<0)&np.any(rgb<255,axis=2))|remaining
    # Small ordered tiles keep complex unassigned artwork within snapshot limits.
    for top in range(0,image.height,160):
        for left in range(0,image.width,160):
            mask=np.zeros(owner.shape,bool);mask[top:top+160,left:left+160]=residual[top:top+160,left:left+160]
            add(mask,f'residual_{top}_{left}','context','未分配细节','residual',pixels=underlay)
    # Text underlays belong below ink, including panels discovered after OCR.
    # Model response order must never let a newly found panel cover its labels.
    for item in sorted(items,key=lambda o:({'structure':0,'arrow':1,'text':2}[o['kind']],-int(o['mask'].sum()))):
        tick('正在建立独立对象：'+str(item.get('label') or item['id'])[:70])
        mask=item.get('render_mask',item['mask']);pixels=underlay if item['kind']=='structure' else rgb
        if item['kind']=='structure':
            children=[o for o in structures if o.get('parent_id')==item['id']]
            if children:
                holes=np.logical_or.reduce([o['coverage_mask'] for o in children])&item['coverage_mask']
                pixels=estimate_container_background(underlay,holes,item['coverage_mask'])
                mask=mask|holes;estimated_backgrounds+=1
        add(mask,item['id'],'entity',str(item.get('label') or '')[:240],item['kind'],item,pixels=pixels)
    present={o['id'] for o in scene['objects']}
    for obj in scene['objects']:
        if obj.get('parent_id') not in present:obj.pop('parent_id',None)
    all_foreground=int(np.any(rgb<245,axis=2).sum())
    assigned=int(((owner>=0)&np.any(rgb<245,axis=2)).sum())
    coverage=round(100*assigned/max(1,all_foreground),2)
    scene['provenance'].update(method='import-semantic-vector',segmentation_method='exclusive-observed-regions',raster_embedded=False,ocr_source='vision+local-ocr')
    scene['unresolved']=[str(w)[:500] for w in (value.get('warnings') or [])[:20]]+warnings+[
        '结构、箭头和标签按原图独立保存，尚需对照核对边界与文字；像素接近度不代表语义核验。',
        '包含结构的背景已按周围颜色估计补底；被遮挡的真实细节仍无法从原图恢复，请移动后核对，必要时明确要求 AI 重绘。',
        '原图箭头保留为独立矢量轮廓，可移动、旋转、缩放；尚未绑定科研对象端口。']
    if text_mask.any():scene['unresolved'].append('文字原位按字形轮廓在本机局部补底，背景为周围像素估计；请核对彩色背景与交叉线。')
    if coverage<98:scene['unresolved'].append(f'已分配 {coverage}% 的前景像素；剩余细节保留在背景层。请补选边界后重新转换。')
    report={'vector_paths':total_paths,'vector_groups':len(scene['objects']),'structures':len(regions_report),'estimated_backgrounds':estimated_backgrounds,
            'regions':regions_report,'regions_confirmed':False,'assigned_foreground_percent':coverage,
            'outline_labels':sum(o['type']=='text' for o in scene['objects']),'raster_embedded':False,
            'segmentation_method':'exclusive-observed-regions','unassigned_pixels':int(residual.sum()),
            'colour_palette':{'method':'per-object-measured','objects_optimised':sum(p['applied'] for p in palette_reports),'objects':len(palette_reports),'max_mean_rgb_error':max((p['mean_rgb_error'] for p in palette_reports if p['applied']),default=0)}}
    return normalize_scene(scene),report
