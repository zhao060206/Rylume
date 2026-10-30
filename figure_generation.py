"""One generation contract for text, reference images and editable sketches."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import time
import uuid
from pathlib import Path

from scene_document import SceneError, RevisionConflict, empty_scene, normalize_scene

PREVIEW_ID = re.compile(r'^gp_[a-f0-9]{24}$')


def prepare(app, body):
    if not isinstance(body,dict):
        raise SceneError('生成请求必须是对象')
    config = app.load_config()
    for key in ('text','original_text','generation_brief'):
        if key in body and not isinstance(body[key],str):
            raise SceneError('研究描述必须是文字')
    original = str(body.get('original_text') or body.get('text') or '').strip()
    brief = str(body.get('generation_brief') or body.get('text') or original).strip()
    if len(original) > 8000 or len(brief) > 8000:
        raise SceneError('研究描述请控制在 8000 字以内')
    dimensions = body.get('canvas_mm') or [180,120]
    if not isinstance(dimensions, list) or len(dimensions) != 2:
        raise SceneError('画布尺寸无效')
    checked = normalize_scene(empty_scene(width_mm=dimensions[0], height_mm=dimensions[1]))
    mode=body.get('illustration_mode','vector')
    if mode not in ('image','vector'):
        raise SceneError('请选择矢量绘图或 AI 插画')
    layout_policy = body.get('layout_policy', 'regularize' if body.get('reference_id') else 'preserve')
    if layout_policy not in ('regularize','preserve'):
        raise SceneError('请选择智能整理或严格保留草稿位置')
    supplied_dpi=body.get('dpi',300)
    try:
        dpi=float(supplied_dpi)
        if isinstance(supplied_dpi,bool) or not math.isfinite(dpi) or not dpi.is_integer() or not 72<=dpi<=1200:
            raise ValueError()
    except (ValueError,TypeError,OverflowError):
        raise SceneError('DPI 必须是 72–1200 之间的整数') from None
    config.update(canvas_mm=[checked['canvas']['width_mm'], checked['canvas']['height_mm']],
                  original_text=original, generation_brief=brief, scene_engine='v2',
                  illustration_mode=mode,dpi=int(dpi),layout_policy=layout_policy,style_dna=app.sanitize_style(body.get('style_dna') or {}))
    if body.get('reference_id'):
        import figure_references
        reference = figure_references.read(app.DATA_DIR, body['reference_id'])
        config.update(reference_id=reference['reference_id'], reference_purpose=body.get('reference_purpose') or reference['purpose'],
                      reference_contract=reference['reference_contract'],
                      reference_image_data_url=figure_references.image_data_url(app.DATA_DIR, reference['reference_id']))
        if config['reference_purpose'] not in figure_references.PURPOSES:
            raise SceneError('参考用途无效')
        if config['reference_purpose'] in ('sketch','content') and not reference['reference_contract'].get('objects'):
            raise SceneError('参考草稿尚未识别出对象，无法可靠保留位置与连接。请重新上传清晰草稿，或改用参考画风。')
        config['style_dna'] = app.sanitize_style(reference.get('style_dna') or {})
    if 'draft_scene' in body and not isinstance(body['draft_scene'],dict):
        raise SceneError('画布草稿必须是场景文档')
    if body.get('draft_scene') and isinstance(body['draft_scene'], dict):
        draft_scene = normalize_scene(body['draft_scene'])
        if draft_scene.get('objects'):
            config.update(sketch_scene=draft_scene, draft_source_id='client_draft', draft_source_revision=1)
            config['canvas_mm'] = [draft_scene['canvas']['width_mm'], draft_scene['canvas']['height_mm']]
            if not original:
                original = '按我的画布草稿绘制：' + '；'.join(o.get('label', '') for o in draft_scene['objects'] if o.get('label'))
                config.update(original_text=original, generation_brief=original)
    elif body.get('sketch_job_id'):
        import scene_service
        source = app.JOBS.get(str(body['sketch_job_id']))
        if not source or source.get('scene_engine') != 'v2':
            raise SceneError('请先新建一张可编辑草稿')
        sketch = scene_service.repository(app, source['id']).read()
        if scene_service._revision(body) != sketch['revision']:
            raise RevisionConflict('草稿已变化，请保存后重新生成')
        if not sketch['objects']:
            raise SceneError('请先在草稿中添加对象和标签')
        config.update(sketch_scene=sketch, draft_source_id=source['id'], draft_source_revision=sketch['revision'])
        config['canvas_mm'] = [sketch['canvas']['width_mm'],sketch['canvas']['height_mm']]
        if not original:
            original = '按我的画布草稿绘制：' + '；'.join(o['label'] for o in sketch['objects'] if o['label'])
            config.update(original_text=original, generation_brief=original)
    if not original:
        reference = config.get('reference_contract') or {}
        if config.get('reference_purpose') in ('sketch', 'content') and any(o['label'] for o in reference.get('objects', [])):
            original = '按上传草稿中可见的对象与连接绘制：' + '；'.join(o['label'] for o in reference['objects'] if o['label'])
            config.update(original_text=original, generation_brief=original)
        else:
            raise SceneError('请描述要表达的内容，或为草稿中的对象添加文字')
    # Client-supplied scene JSON is never a trusted preview or source revision.
    if body.get('preview_id'):
        config['prepared_scene'] = load_preview(app.DATA_DIR, body['preview_id'], config)
    return original, config


def fingerprint(config):
    values = {k: config.get(k) for k in ('original_text','generation_brief','canvas_mm','illustration_mode',
                                       'reference_id','reference_purpose','draft_source_id','draft_source_revision','style_dna',
                                       'redraw_ids','redraw_instruction','dpi','layout_policy')}
    for key in ('sketch_scene','prepared_scene'):
        if config.get(key):
            encoded=json.dumps(normalize_scene(config[key]),ensure_ascii=False,sort_keys=True,separators=(',',':'))
            values[key+'_sha256']=hashlib.sha256(encoded.encode()).hexdigest()
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _label(value):
    return re.sub(r'[\W_]+','',str(value).lower())

def apply_constraints(scene, config):
    """Keep authored topology; exact geometry is an explicit, independent policy."""
    scene = copy.deepcopy(scene)
    sketch = config.get('sketch_scene')
    reference = config.get('reference_contract') or {}
    if sketch:
        from scientific_intent import intent_contract, labeled_cell_phase,classical_mitosis_compatible
        biological_context=intent_contract(config['original_text'])['domain']=='biology'
        by_id = {o['id']:o for o in scene['objects']}
        unused = set(by_id)
        kept = []
        # Reserve stable IDs first, so a label match cannot consume another
        # author's object. A list position is never scientific identity.
        matched={o['id']:by_id[o['id']] for o in sketch['objects'] if o['id'] in by_id}
        unused.difference_update(matched)
        for idx, original in enumerate(sketch['objects']):
            if original.get('locked') or original['type']=='text' or original.get('role')=='context':
                kept.append(copy.deepcopy(original))
                continue
            candidate = matched.get(original['id'])
            if candidate is None:
                candidates=[o for o in scene['objects'] if o['id'] in unused and _label(o['label']) and _label(o['label']) == _label(original['label'])]
                candidate=candidates[0] if len(candidates)==1 else None
            if candidate is None:
                phase = labeled_cell_phase(original.get('label',''),biological_context=biological_context or original.get('type') in ('cell','stem_cell'))
                if phase:
                    candidates=[o for o in scene['objects'] if o['id'] in unused and
                        (phase == labeled_cell_phase(o.get('label',''),biological_context=True) or phase == o.get('state'))]
                    candidate=candidates[0] if len(candidates)==1 else None
            if candidate is None:
                kept.append(copy.deepcopy(original))
                scene['unresolved'].append('未能确认草稿对象「'+original['label']+'」的对应关系，已保留作者对象，请核对后单独细化。')
                continue
            else:
                candidate = copy.deepcopy(candidate)
                unused.discard(candidate['id'])
            candidate['id'] = original['id']
            candidate['entity_id'] = original.get('entity_id', original['id'])
            for key in ('x','y','w','h','rotation','label_dx','label_dy','group_id','locked','visible','fill','stroke','stroke_pt','font_size_pt'):
                if key in original:
                    candidate[key] = original[key]
            # Infer biological state from label if missing or generic
            if candidate.get('type') in ('cell', 'stem_cell', 'process') and classical_mitosis_compatible(config['original_text']):
                phase = labeled_cell_phase(original.get('label',''),biological_context=biological_context or candidate.get('type') in ('cell','stem_cell'))
                if phase:
                    candidate['type'] = 'cell'
                    candidate['state'] = phase
            candidate['compartment'] = original.get('compartment','')
            kept.append(candidate)
        # Do not insert unrequested nodes or new causal edges into a user's sketch.
        scene['objects'] = kept
        scene['relations'] = copy.deepcopy(sketch['relations'])
        scene['compartments'] = copy.deepcopy(sketch['compartments'])
        scene['canvas'] = copy.deepcopy(sketch['canvas'])
        scene['requirements'] = {'objects':[o['id'] for o in kept if o.get('visible',True)], 'relations':[r['id'] for r in scene['relations']]}
    elif config.get('reference_purpose') != 'style' and reference.get('objects'):
        source = reference['objects']
        objects = [o for o in scene['objects'] if o.get('role','entity') == 'entity']
        strict=config.get('reference_purpose') in ('sketch','content')
        reference_ids={}
        width,height = config['canvas_mm']
        free=list(objects);matched={}
        from scientific_intent import labeled_cell_phase
        for ref in source:
            candidates=[o for o in free if _label(ref['label']) and _label(ref['label'])==_label(o['label'])]
            if len(candidates)!=1:
                phase=labeled_cell_phase(ref['label'],biological_context=True)
                candidates=[o for o in free if phase and phase==labeled_cell_phase(o['label'],biological_context=True)]
            if len(candidates)!=1:
                candidates=[o for o in free if o['id']==ref['id'] and
                            (not strict or not ref['label'] or not o['label'] or _label(ref['label'])==_label(o['label']))]
            if len(candidates)==1:
                matched[ref['id']]=candidates[0];free.remove(candidates[0])
        if not strict and len(objects)==len(source):
            for ref in source:
                if ref['id'] not in matched and free:matched[ref['id']]=free.pop(0)
        placed=[];used_ids={o['id'] for o in scene['objects']}
        for ref in source:
            obj=matched.get(ref['id'])
            if obj is None:
                if not strict:continue
                ident=ref['id'];suffix=2
                while ident in used_ids:ident=ref['id']+'_'+str(suffix);suffix+=1
                used_ids.add(ident)
                obj={'id':ident,'type':ref.get('type','process'),'label':ref['label'],'state':ref.get('state',''),
                     'evidence':ref['label'],'evidence_source':'reference_image','evidence_ref':config.get('reference_id','')}
                scene['unresolved'].append('参考对象「'+ref['label']+'」未被规划器可靠匹配，已按观察保留，请核对形态。')
            obj.update(reference_object_id=ref['id'],x=round(ref['x']*width,4),y=round(ref['y']*height,4),
                       w=round(ref['w']*width,4),h=round(ref['h']*height,4),compartment='')
            if obj['y']+obj['h']>height-7:obj['label_dy']=-obj['h']-2
            reference_ids[ref['id']]=obj['id'];placed.append(obj)
        if strict:
            kept_ids={o['id'] for o in placed}
            if config.get('reference_purpose')=='content':
                for obj in scene['objects']:
                    evidence=obj.get('evidence','')
                    if obj['id'] not in kept_ids and obj.get('evidence_source','user_text')=='user_text' and evidence and evidence in config['original_text']:
                        placed.append(obj);kept_ids.add(obj['id'])
            scene['objects']=placed
            retained=[]
            for i,relation in enumerate(reference.get('relations') or []):
                a,b=reference_ids.get(relation['source']),reference_ids.get(relation['target'])
                if a and b:retained.append({'id':f'sketch_r{i+1}','source':a,'target':b,'type':relation['type'],
                    'label':relation.get('label',''),'uncertain':relation['type']=='associates',
                    'evidence':'用户上传草稿中可见的连接','evidence_source':'reference_image','evidence_ref':config.get('reference_id','')})
            if config.get('reference_purpose')=='content':
                existing={(r['source'],r['target'],r['type']) for r in retained}
                for relation in scene['relations']:
                    evidence=relation.get('evidence','');key=(relation['source'],relation['target'],relation['type'])
                    if relation['source'] in kept_ids and relation['target'] in kept_ids and key not in existing and relation.get('evidence_source','user_text')=='user_text' and evidence and evidence in config['original_text']:
                        relation=copy.deepcopy(relation);relation['id']='authored_'+relation['id'];retained.append(relation);existing.add(key)
            scene['relations']=retained
            scene['requirements']={'objects':[o['id'] for o in placed if o.get('visible',True)],'relations':[r['id'] for r in retained]}
        if placed:
            scene['compartments']=[]
            for obj in scene['objects']:obj['compartment']=''
        if len(matched)!=len(source):scene['unresolved'].append('参考图的部分对象对应关系待核对；未按列表顺序猜测科学身份。')
        for uncertainty in reference.get('uncertainties') or []:
            scene['unresolved'].append('参考图待核对：' + uncertainty)
    scene['source_text'] = config['original_text']
    from scientific_intent import apply_division_context
    apply_division_context(scene,config['original_text'])
    layout_policy=config.get('layout_policy','preserve')
    layout_summary='严格保留位置、尺寸与作者连接。'
    if layout_policy=='regularize' and (sketch or (reference.get('objects') and config.get('reference_purpose')!='style')):
        from sketch_layout import regularize_sketch
        composition=reference.get('composition','auto') if not sketch else 'auto'
        scene,report=regularize_sketch(scene,composition)
        layout_summary=('已按大致构图整理 '+str(report['adjusted'])+' 个对象：同类尺寸、对齐与间距统一，文字和箭头独立。'
                        +(' 部分位置需要核对，请查看预览提示。' if not report['fits'] else ''))
    contract = {'original_text':config['original_text'], 'generation_brief':config['generation_brief'],
                'source_kind':'canvas-sketch' if sketch else 'reference' if config.get('reference_id') else 'description',
                'reference_id':config.get('reference_id',''), 'reference_summary':reference.get('summary',''),
                'reference_purpose':config.get('reference_purpose',''), 'draft_source_id':config.get('draft_source_id',''),
                'draft_source_revision':str(config.get('draft_source_revision') or ''),
                'layout_policy':layout_policy, 'layout_summary':layout_summary,
                'editable_layers':'主体图形或图片、对象文字、关系箭头与箭头文字分别保留',
                'verification':'核对原始描述、草稿布局与科学状态；机器检查不替代作者科学确认'}
    scene['generation_contract'] = contract
    scene['provenance'].update({k:v for k,v in contract.items() if k not in ('source_kind','verification')})
    scene['provenance']['generation_mode'] = config.get('illustration_mode','vector')
    if not sketch and scene.get('layout')=='process':
        _route_stage_turns(scene)
    contract['expected_objects'] = json.dumps(
        [{'id':o['id'],'label':o['label'],'state':o.get('state',''),
          **({k:o[k] for k in ('x','y','w','h') if k in o} if sketch or config.get('reference_purpose') in ('layout','sketch','content') else {})}
         for o in (sketch['objects'] if sketch and layout_policy=='preserve' else scene['objects'])],ensure_ascii=False)
    contract['expected_relations'] = json.dumps([{k:r.get(k,'') for k in ('source','target','type')} for r in scene['relations']],ensure_ascii=False)
    return normalize_scene(scene)


def _route_stage_turns(scene):
    """A row turn goes around the cell instead of through its caption."""
    objects={o['id']:o for o in scene['objects']}
    width=scene['canvas']['width_mm']
    for r in scene['relations']:
        a,b=objects[r['source']],objects[r['target']]
        if not all(k in x for x in (a,b) for k in ('x','y','w','h')):
            continue
        dx=(b['x']+b['w']/2)-(a['x']+a['w']/2)
        dy=(b['y']+b['h']/2)-(a['y']+a['h']/2)
        if (abs(dy)>max(12,abs(dx)*2) and a['type']=='cell' and b['type']=='cell'
                and not any(r.get(k) for k in ('source_anchor','target_anchor','control'))
                and r.get('source_port','auto')=='auto' and r.get('target_port','auto')=='auto'):
            side='w' if (a['x']+b['x']+a['w']/2+b['w']/2)/2<width/2 else 'e'
            edge=min(a['x'],b['x']) if side=='w' else max(a['x']+a['w'],b['x']+b['w'])
            outside=max(2,edge-14) if side=='w' else min(width-2,edge+14)
            r.update(source_port=side,target_port=side,control={'x':outside,'y':(a['y']+a['h']/2+b['y']+b['h']/2)/2})


def plan(text, config, *, on_stage=None, cancelled=None):
    if config.get('prepared_scene'):
        return copy.deepcopy(config['prepared_scene']), {'method':'accepted-structure-preview'}
    from scene_planner import plan_scene
    scene, meta = plan_scene(text, config, on_stage=on_stage, cancelled=cancelled)
    return apply_constraints(scene, config), meta


def enforce_content_audit(scene):
    """Never label a known contradiction as a successfully generated draft."""
    from scene_document import audit_scene
    codes={'excluded-object','contradicted-relation','excluded-scientific-state','unsupported-mechanism','missing-scientific-state','phase-morphology'}
    blockers=[f for f in audit_scene(scene)['findings'] if f['severity']=='error' and f['code'] in codes]
    if blockers:
        raise SceneError('内容核验未通过，已保留可编辑草稿：'+'；'.join(f['message'] for f in blockers[:5]))


def preview(app, text, config):
    from scene_render import render_scene
    scene, meta = plan(text, config)
    from scene_document import audit_scene
    audit=audit_scene(scene)
    ident = 'gp_' + uuid.uuid4().hex[:24]
    folder = Path(app.DATA_DIR)/'generation-previews'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/(ident+'.json')).write_text(json.dumps({'created':time.time(), 'fingerprint':fingerprint(config),
                                                 'scene':scene, 'planner':meta},ensure_ascii=False),encoding='utf-8')
    return {'ok':True,'preview_id':ident,'scene':scene,'svg':render_scene(scene),
            'contract':scene['generation_contract'],'unresolved':scene['unresolved'],'audit':audit}


def load_preview(data_dir, ident, config):
    if not isinstance(ident,str) or not PREVIEW_ID.fullmatch(ident):
        raise SceneError('结构预览标识无效')
    try:
        stored = json.loads((Path(data_dir)/'generation-previews'/(ident+'.json')).read_text(encoding='utf-8'))
    except (OSError,ValueError):
        raise SceneError('结构预览不存在或已损坏，请重新预览') from None
    if stored['fingerprint'] != fingerprint(config):
        raise RevisionConflict('描述、参考图或草稿已变化，请重新查看结构预览')
    if time.time()-stored['created'] > 86400:
        raise SceneError('结构预览已过期，请重新生成预览')
    return normalize_scene(stored['scene'])


# Only document inputs are persisted. Service addresses, model settings and
# credentials are deliberately absent; retries use the current local settings.
INPUT_KEYS=('original_text','generation_brief','canvas_mm','illustration_mode','dpi','style_dna',
            'reference_id','reference_purpose','layout_policy','sketch_scene','draft_source_id','draft_source_revision',
            'prepared_scene','redraw_ids','redraw_instruction')


def persist_inputs(app,job_id,config):
    values={key:copy.deepcopy(config[key]) for key in INPUT_KEYS if key in config}
    for key in ('sketch_scene','prepared_scene'):
        if values.get(key):values[key]=normalize_scene(values[key])
    folder=Path(app.JOBS_DIR)/job_id
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/'generation-input.json'
    temporary=folder/('generation-input.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(values,ensure_ascii=False),encoding='utf8')
    os.replace(temporary,path)


def retry_inputs(app,job):
    path=Path(app.JOBS_DIR)/job['id']/'generation-input.json'
    if path.exists():
        try:
            saved=json.loads(path.read_text(encoding='utf8'))
            if not isinstance(saved,dict):raise ValueError()
        except (OSError,ValueError):
            raise SceneError('原始生成输入已损坏；当前图版保留，请从画布创建新版本') from None
        body={key:saved[key] for key in ('original_text','generation_brief','canvas_mm','illustration_mode','dpi','style_dna','reference_id','reference_purpose','layout_policy') if key in saved}
        body.setdefault('layout_policy','preserve')
        if saved.get('redraw_ids'):
            body.pop('reference_id',None);body.pop('reference_purpose',None)
        body['text']=saved.get('original_text') or job.get('original_text') or job.get('text') or ''
        text,config=prepare(app,body)
        for key in ('sketch_scene','prepared_scene','draft_source_id','draft_source_revision','redraw_ids','redraw_instruction'):
            if key in saved:
                config[key]=normalize_scene(saved[key]) if key.endswith('_scene') else copy.deepcopy(saved[key])
        return text,config
    # Older jobs have no input snapshot. Reuse their saved object scene rather
    # than guessing the original reference layout or changing render modes.
    import scene_service
    scene=scene_service.repository(app,job['id']).read() if job.get('scene_revision') else None
    contract=(scene or {}).get('generation_contract') or {}
    body={'text':job.get('original_text') or job.get('text') or '',
          'generation_brief':contract.get('generation_brief') or job.get('generation_brief') or job.get('text') or '',
          'canvas_mm':job.get('canvas_mm') or [180,120],
          'illustration_mode':job.get('illustration_mode') or 'vector','dpi':job.get('dpi') or 300,
          'layout_policy':contract.get('layout_policy') or 'preserve'}
    if contract.get('reference_id'):
        body.update(reference_id=contract['reference_id'],reference_purpose=contract.get('reference_purpose') or 'layout')
    text,config=prepare(app,body)
    if scene:config['prepared_scene']=scene
    return text,config
