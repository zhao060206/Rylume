"""Scoped multi-note editing with independent verification. Never writes HEAD."""
from __future__ import annotations
import base64,copy,json,math,re
import fitz
import pipeline
import scene_planner
from scene_document import SceneError,normalize_scene,apply_operations,audit_scene
from scene_render import render_scene,connection_geometry

VISUAL={'x','y','w','h','rotation','font_size_pt','label_dx','label_dy','fill','stroke','stroke_pt'}
EDGE= {'label','type','control','source_port','target_port','stroke','stroke_pt','indirect','uncertain'}

def _text(value):
    if not isinstance(value,str):raise SceneError('批注文字格式无效')
    value=''.join(c for c in value if c>=' ' or c in '\n\t').strip()
    if len(value)>2000:raise SceneError('每条批注最多 2000 字')
    return value

def _num(value):
    if isinstance(value,bool):raise SceneError('批注坐标无效')
    try:value=float(value)
    except (ValueError,TypeError):raise SceneError('批注坐标无效') from None
    if not math.isfinite(value):raise SceneError('批注坐标必须是有限数值')
    return value

def normalize_notes(scene,notes,draft=False):
    scene=normalize_scene(scene)
    if not isinstance(notes,list) or len(notes)>30:raise SceneError('请提供至多 30 条批注')
    result=[];seen=set();cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    for raw in notes:
        if not isinstance(raw,dict):raise SceneError('批注格式无效')
        nid=raw.get('id');shape=raw.get('shape')
        if not isinstance(nid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',nid) or nid in seen:raise SceneError('批注编号重复或无效')
        seen.add(nid)
        if shape=='circle':shape='ellipse'
        if shape not in ('rect','ellipse','whole'):raise SceneError('请选择方框、圆框或整图批注')
        if shape=='whole':x,y,w,h=0.,0.,cw,ch
        else:
            x,y,w,h=(_num(raw.get(k)) for k in ('x','y','w','h'))
            if w<=0 or h<=0 or x<0 or y<0 or x+w>cw+.01 or y+h>ch+.01:raise SceneError('批注区域应位于图纸内')
            w=min(w,cw-x);h=min(h,ch-y)
        instruction=_text(raw.get('instruction',''))
        note=dict(id=nid,shape=shape,x=round(x,5),y=round(y,5),w=round(w,5),h=round(h,5),instruction=instruction,
                  original_instruction=_text(raw.get('original_instruction') or instruction))
        if 'target_ids' in raw:
            ids=raw['target_ids'];known={o['id'] for o in scene['objects']}|{r['id'] for r in scene['relations']}
            if not isinstance(ids,list) or not ids or len(ids)>1000 or any(not isinstance(i,str) or i not in known for i in ids):
                raise SceneError('所选对象已经变化，请重新选择修改范围')
            note['target_ids']=list(dict.fromkeys(ids))
        if not draft:
            if not instruction:raise SceneError('请为每处批注填写修改要求')
            if not resolve_note_targets(scene,note):raise SceneError('批注 '+nid+' 没有涉及可编辑对象或连线，请调整圈框')
        result.append(note)
    return result

def _inside(n,x,y):
    if n['shape']=='whole':return True
    if n['shape']=='rect':return n['x']<=x<=n['x']+n['w'] and n['y']<=y<=n['y']+n['h']
    return ((x-n['x']-n['w']/2)/(n['w']/2))**2+((y-n['y']-n['h']/2)/(n['h']/2))**2<=1

def _segment(n,a,b):
    if _inside(n,*a) or _inside(n,*b):return True
    if n['shape']=='ellipse':
        cx,cy=n['x']+n['w']/2,n['y']+n['h']/2
        ax,ay=(a[0]-cx)/(n['w']/2),(a[1]-cy)/(n['h']/2)
        bx,by=(b[0]-cx)/(n['w']/2),(b[1]-cy)/(n['h']/2)
        dx,dy=bx-ax,by-ay;t=max(0,min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy or 1)))
        return (ax+t*dx)**2+(ay+t*dy)**2<=1
    dx,dy=b[0]-a[0],b[1]-a[1];lo,hi=0.,1.
    for p,q in ((-dx,a[0]-n['x']),(dx,n['x']+n['w']-a[0]),(-dy,a[1]-n['y']),(dy,n['y']+n['h']-a[1])):
        if abs(p)<1e-12:
            if q<0:return False
        elif p<0:lo=max(lo,q/p)
        else:hi=min(hi,q/p)
    return lo<=hi

def _hits(n,o):
    if n['shape']=='whole':return True
    angle=math.radians(o.get('rotation',0));c,s=math.cos(angle),math.sin(angle);cx,cy=o['x']+o['w']/2,o['y']+o['h']/2
    points=[(cx+dx*c-dy*s,cy+dx*s+dy*c) for dx,dy in ((-o['w']/2,-o['h']/2),(o['w']/2,-o['h']/2),(o['w']/2,o['h']/2),(-o['w']/2,o['h']/2))]
    if any(_segment(n,a,b) for a,b in zip(points,points[1:]+points[:1])):return True
    dx,dy=n['x']+n['w']/2-cx,n['y']+n['h']/2-cy
    return abs(c*dx+s*dy)<=o['w']/2 and abs(-s*dx+c*dy)<=o['h']/2

def resolve_note_targets(scene,note):
    objects={o['id']:o for o in scene['objects']}
    targets=[o['id'] for o in scene['objects'] if o['visible'] and not o['locked'] and _hits(note,o)]
    for r in scene['relations']:
        a,b=objects[r['source']],objects[r['target']]
        if not a['visible'] or not b['visible'] or a['locked'] or b['locked']:continue
        if note['shape']=='whole':targets.append(r['id']);continue
        g=connection_geometry(scene,r);points=[]
        for i in range(97):
            t=i/96;u=1-t;points.append((u*u*g['x1']+2*u*t*g['control']['x']+t*t*g['x2'],u*u*g['y1']+2*u*t*g['control']['y']+t*t*g['y2']))
        if any(_segment(note,a,b) for a,b in zip(points,points[1:])):targets.append(r['id'])
    return [i for i in targets if i in note['target_ids']] if note.get('target_ids') else targets

def _explicit(text,field):
    terms={'label':r'文字|标签|名称|改名|命名|label|rename|text','state':r'状态|磷酸化|二聚|修饰|state|phosph|dimer',
        'type':r'类型|图形|形状|素材|受体|激活|抑制|结合|转换|转运|关联|顺序|type|shape|receptor|activat|inhibit|bind|transport|convert',
        'compartment':r'区室|入核|进核|核内|核外|胞外|胞内|compartment|nuclear|cytoplasm',
        'indirect':r'直接|间接|虚线|实线|indirect|direct|dash','uncertain':r'核对|确定|问号|uncertain|verify|confirm'}
    term=terms.get(field,r'(?!)')
    if re.search(r'(?:不(?:要)?(?:改变|改动|修改)|保持).{0,6}(?:'+term+r').{0,3}(?:不变)?',text,re.I):return False
    if re.search(r'(?:'+term+r').{0,4}(?:不变|不改|unchanged)',text,re.I):return False
    return bool(re.search(term,text,re.I))

def validate_candidate_operations(scene,notes,operations):
    scene=normalize_scene(scene);notes=normalize_notes(scene,notes)
    if not isinstance(operations,list) or not operations or len(operations)>1000:raise SceneError('AI 没有提供可应用的修改')
    scopes={n['id']:set(resolve_note_targets(scene,n)) for n in notes};allowed=set().union(*scopes.values())
    objects={o['id']:o for o in scene['objects']};rels={r['id']:r for r in scene['relations']}
    connected={r['id'] for r in rels.values() if r['source'] in allowed or r['target'] in allowed}
    for op in operations:
        if not isinstance(op,dict) or op.get('op') not in ('update','update_relation'):raise SceneError('此候选包含暂不支持的新增或删除操作，请手动调整结构后重新批注')
        oid=op.get('id');changes=op.get('changes')
        if not isinstance(changes,dict) or not changes:raise SceneError('修改属性不能为空')
        if op['op']=='update':
            if oid not in objects or oid not in allowed or objects[oid]['locked']:raise SceneError('AI 修改超出了批注范围或涉及锁定对象')
            permitted=VISUAL|{'label','state','type','compartment'}
        else:
            if oid not in rels or oid not in allowed|connected:raise SceneError('AI 连线修改超出了批注范围')
            r=rels[oid]
            if objects[r['source']]['locked'] or objects[r['target']]['locked']:raise SceneError('不能修改连接到锁定对象的线')
            permitted=EDGE if oid in allowed else {'control','source_port','target_port','stroke','stroke_pt'}
        if changes.keys()-permitted:raise SceneError('候选试图改变稳定身份、关系端点或未授权属性')
        text='\n'.join(n['instruction'] for n in notes if oid in scopes[n['id']])
        for key in changes:
            if key in ('label','state','type','compartment','indirect','uncertain') and not _explicit(text,key):raise SceneError('候选改变了未明确要求的内容：'+key)
    proposed=apply_operations(scene,operations,allowed_ids=allowed|connected)
    before={(f['code'],tuple(f['object_ids'])) for f in audit_scene(scene)['findings']}
    errors=[f for f in audit_scene(proposed)['findings'] if f['severity']=='error' and (f['code'],tuple(f['object_ids'])) not in before]
    if errors:raise SceneError('候选增加了结构错误：'+errors[0]['message'])
    return proposed

def enhance_annotation_instruction(instruction,config):
    original=_text(instruction)
    if not original:raise SceneError('请先填写批注要求')
    try:
        data,_=scene_planner._request(config,[{'role':'system','content':'只澄清表达，禁止新增或删减要求，不补机制、方向、数量、字号、颜色或位置。保留专名、引号内文字、否定及数值。不套用出版规范。返回JSON {enhanced:"..."}。'},{'role':'user','content':original}],max_tokens=1600)
        enhanced=_text(data.get('enhanced',''))
        if not enhanced:raise SceneError('缺少优化文本')
        audit,_=scene_planner._request(config,[{'role':'system','content':'独立核对改写是否完整保留原意。新增具体条件、科学机制、默认规范、删除要求、改变否定均不等价。返回JSON {equivalent:true|false,reason:"逐项依据"}。'},
            {'role':'user','content':json.dumps({'original':original,'enhanced':enhanced},ensure_ascii=False)}],max_tokens=1000)
        anchors=re.findall(r'#[0-9A-Fa-f]{6}|\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9_-]*',original)+re.findall(r'[“"「](.*?)[”"」]',original)
        if audit.get('equivalent') is not True or any(a not in enhanced for a in anchors):raise SceneError('无法确认原意一致')
        return {'original':original,'enhanced':enhanced,'notes':['已做原意对照，请比较后自行采用。']}
    except Exception:return {'original':original,'enhanced':original,'notes':['未得到可确认保持原意的优化建议，原文保持不变。']}

def _changed(before,after):
    old={o['id']:o for o in before['objects']+before['relations']}
    return {o['id'] for o in after['objects']+after['relations'] if o!=old.get(o['id'])}

def _image(scene,notes):
    svg=render_scene(scene);overlay=[]
    for i,n in enumerate(notes,1):
        if n['shape']=='whole':continue
        tag='ellipse' if n['shape']=='ellipse' else 'rect'
        attrs=(f'cx="{n["x"]+n["w"]/2}" cy="{n["y"]+n["h"]/2}" rx="{n["w"]/2}" ry="{n["h"]/2}"' if tag=='ellipse' else f'x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}"')
        overlay.append(f'<{tag} {attrs} fill="none" stroke="#C65D37" stroke-width=".5"/><text x="{n["x"]+1}" y="{n["y"]+3}" font-family="Arial" font-size="3" fill="#A74027">{i}</text>')
    with fitz.open(stream=svg.replace('</svg>',''.join(overlay)+'</svg>').encode(),filetype='svg') as doc:
        with fitz.open('pdf',doc.convert_to_pdf()) as pdf:return base64.b64encode(pdf[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False).tobytes('png')).decode('ascii')

def _review(before,after,notes,operations,config):
    instruction=('你是独立科研图修改核验者。生成器的自报不是证据。逐条对比原始要求、原图、候选与实际属性变化。'
        '仅把有具体证据的完整满足项标verified，部分满足为unfulfilled，不能确认或缺证据为needs_review。不得把“有变化”当作满足要求。'
        '检查未授权科学改写及无关对象变化。返回JSON {checks:[{note_id,status:"verified|needs_review|unfulfilled",message,evidence}],unexpected_changes:false}。')
    context=json.dumps({'notes':notes,'before':before,'after':after,'operations':operations},ensure_ascii=False);vision=config.get('vision') or {}
    if vision.get('base_url') and vision.get('model'):
        content=[{'type':'text','text':instruction+'\n框号对应批注顺序，第一张为原图，第二张为候选。\n'+context},
            {'type':'image_url','image_url':{'url':'data:image/png;base64,'+_image(before,notes)}},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+_image(after,notes)}}]
        req={'model':vision['model'],'temperature':0,'max_tokens':3000,'messages':[{'role':'user','content':content}]}
        if 'deepseek' in vision['model'].lower():req['thinking']={'type':'disabled'}
        response=pipeline._post_json(pipeline._endpoint(vision['base_url'],'/chat/completions'),pipeline._api_key(vision),req,timeout=90)
        data=pipeline._json_object(response['choices'][0]['message']['content']);mode='vision_and_structure'
    else:
        data,_=scene_planner._request(config,[{'role':'system','content':instruction+'没有提供图像，只能核对结构和文字，不得声称视觉已验收。'},{'role':'user','content':context}],max_tokens=3000);mode='structure_and_text'
    if not isinstance(data,dict):raise SceneError('核验没有返回逐项结果')
    checks=[];changed=_changed(before,after)
    for note in notes:
        rows=[c for c in data.get('checks',[]) if isinstance(c,dict) and c.get('note_id')==note['id']];entry=rows[0] if len(rows)==1 else {}
        status=entry.get('status') if entry.get('status') in ('verified','needs_review','unfulfilled') else 'needs_review'
        message=str(entry.get('message') or '核验未完整回答此条要求')[:1200];evidence=str(entry.get('evidence') or '')[:2000]
        if status=='verified' and (not evidence or not changed.intersection(resolve_note_targets(before,note))):status='needs_review';message='缺少可验证变化或依据，不能确认已满足'
        if data.get('unexpected_changes') is not False:status='needs_review';message='未排除额外变化；'+message
        checks.append(dict(note_id=note['id'],status=status,message=message,evidence=evidence))
    return checks,mode

def propose_annotations(scene,notes,config,*,on_progress=None,cancelled=None,max_rounds=3):
    original=normalize_scene(copy.deepcopy(scene));notes=normalize_notes(original,notes)
    if not notes:raise SceneError('请先添加批注')
    max_rounds=max(1,min(3,int(max_rounds)));feedback=[];best=None;attempts=[];scopes={n['id']:resolve_note_targets(original,n) for n in notes}
    def cancel():
        if cancelled and cancelled():raise InterruptedError('已取消，原图保留')
    def progress(stage,message,round):
        cancel()
        if on_progress:on_progress(dict(stage=stage,message=message,round=round,max_rounds=max_rounds))
    for round_no in range(1,max_rounds+1):
        progress('planning',f'第 {round_no}/{max_rounds} 轮：根据 {len(notes)} 处批注修改',round_no)
        system=('只返回科研图修改JSON {operations:[{op:"update|update_relation",id,changes:{...}}],summary:["具体变化"]}。'
            '每轮均基于原图生成完整补丁。只改批注范围，其他对象的位置、样式、身份和科学含义不变。'
            '不得增加/删除对象，不改id、entity_id、source/target、requirements、原始描述和分组。'
            '只在明确要求时改label/state/type/compartment。视觉属性可改x/y/w/h/rotation/font_size_pt/label_dx/label_dy/fill/stroke/stroke_pt；'
            '连线另可改control/source_port/target_port/indirect/uncertain。字号至少7pt。不能执行的要求如实说明，不可用无关的颜色或字号变化充数。')
        try:
            data,_=scene_planner._request(config,[{'role':'system','content':system},{'role':'user','content':json.dumps({'scene':scene_planner.scene_for_model(original),'notes':notes,'scopes':scopes,'previous_feedback':feedback},ensure_ascii=False)}],max_tokens=5500)
            cancel();operations=data.get('operations');proposed=validate_candidate_operations(original,notes,operations)
            if not _changed(original,proposed):raise SceneError('候选没有实际改变图版')
        except InterruptedError:raise
        except Exception as exc:attempts.append(dict(round=round_no,stage='planning',error=str(exc)[:1000]));feedback=[{'error':str(exc)[:1000]}];continue
        progress('verifying',f'第 {round_no}/{max_rounds} 轮：独立核对逐条要求',round_no)
        try:checks,mode=_review(original,proposed,notes,operations,config);cancel()
        except InterruptedError:raise
        except Exception as exc:checks=[dict(note_id=n['id'],status='needs_review',message='独立核验未完成，不能确认已满足',evidence=str(exc)[:500]) for n in notes];mode='unavailable'
        score=sum(c['status']=='verified' for c in checks);summary=data.get('summary') or ['请对比图版与逐条核验结果']
        if isinstance(summary,str):summary=[summary]
        result=dict(base_revision=original['revision'],operations=operations,preview_scene=proposed,preview_svg=render_scene(proposed),summary=[str(v)[:1000] for v in summary[:30]],
            checks=checks,rounds=round_no,can_apply=score==len(notes),verification=dict(mode=mode,all_verified=score==len(notes),verified=score,total=len(notes),scope_checked=True,attempts=copy.deepcopy(attempts)))
        if best is None or score>=best[0]:best=(score,result)
        if score==len(notes):break
        feedback=checks
    cancel()
    if best:
        result=best[1];result['rounds']=round_no;result['verification']['attempts']=attempts;return result
    return dict(base_revision=original['revision'],operations=[],preview_scene=original,preview_svg=render_scene(original),summary=['没有获得可安全应用的候选，原图保留。'],
        checks=[dict(note_id=n['id'],status='unfulfilled',message='未得到符合范围和结构约束的修改',evidence=attempts[-1]['error'] if attempts else '') for n in notes],rounds=round_no,can_apply=False,
        verification=dict(mode='unavailable',all_verified=False,attempts=attempts))
