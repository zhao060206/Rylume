"""One generation contract for text, reference images and editable sketches."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import uuid
from pathlib import Path

from scene_document import SceneError, RevisionConflict, empty_scene, normalize_scene

PREVIEW_ID = re.compile(r'^gp_[a-f0-9]{24}$')


def prepare(app, body):
    config = app.load_config()
    original = str(body.get('original_text') or body.get('text') or '').strip()
    brief = str(body.get('generation_brief') or body.get('text') or original).strip()
    if len(original) > 8000 or len(brief) > 8000:
        raise SceneError('研究描述请控制在 8000 字以内')
    dimensions = body.get('canvas_mm') or [180,120]
    if not isinstance(dimensions, list) or len(dimensions) != 2:
        raise SceneError('画布尺寸无效')
    checked = normalize_scene(empty_scene(width_mm=dimensions[0], height_mm=dimensions[1]))
    config.update(canvas_mm=[checked['canvas']['width_mm'], checked['canvas']['height_mm']],
                  original_text=original, generation_brief=brief, scene_engine='v2',
                  illustration_mode='image' if body.get('illustration_mode') == 'image' else 'vector',
                  dpi=int(body.get('dpi') or 300), style_dna=app.sanitize_style(body.get('style_dna') or {}))
    if not 72 <= config['dpi'] <= 1200:
        raise SceneError('DPI 必须在 72–1200 之间')
    if body.get('reference_id'):
        import figure_references
        reference = figure_references.read(app.DATA_DIR, body['reference_id'])
        config.update(reference_id=reference['reference_id'], reference_purpose=body.get('reference_purpose') or reference['purpose'],
                      reference_contract=reference['reference_contract'],
                      reference_image_data_url=figure_references.image_data_url(app.DATA_DIR, reference['reference_id']))
        if config['reference_purpose'] not in figure_references.PURPOSES:
            raise SceneError('参考用途无效')
        config['style_dna'] = app.sanitize_style(reference.get('style_dna') or {})
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
        if body.get('base_revision') != sketch['revision']:
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
                                       'redraw_ids','redraw_instruction')}
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _label(value):
    return re.sub(r'[\W_]+','',str(value).lower())

STAGE_SYNONYMS = {
    'interphase': ('interphase', '间期', 'g1', 's', 'g2'),
    'prophase': ('prophase', '前期'),
    'prometaphase': ('prometaphase', '前中期'),
    'metaphase': ('metaphase', '中期'),
    'anaphase': ('anaphase', '后期'),
    'telophase': ('telophase', '末期'),
    'cytokinesis': ('cytokinesis', '胞质分裂', '分裂期', 'daughter'),
    'apoptotic': ('apoptotic', 'apoptosis', '凋亡'),
}

def apply_constraints(scene, config):
    """Keep user geometry/topology independently of a model's preferred layout."""
    scene = copy.deepcopy(scene)
    sketch = config.get('sketch_scene')
    reference = config.get('reference_contract') or {}
    if sketch:
        by_id = {o['id']:o for o in scene['objects']}
        unused = set(by_id)
        remap = {}
        kept = []
        for idx, original in enumerate(sketch['objects']):
            candidate = by_id.get(original['id'])
            if candidate is None:
                candidate = next((o for o in scene['objects'] if o['id'] in unused and _label(o['label']) == _label(original['label'])), None)
            if candidate is None:
                orig_lbl = _label(original.get('label', ''))
                for std_stage, syns in STAGE_SYNONYMS.items():
                    if any(s in orig_lbl for s in syns):
                        candidate = next((o for o in scene['objects'] if o['id'] in unused and (std_stage in _label(o.get('label', '')) or std_stage == o.get('state'))), None)
                        if candidate:
                            break
            if candidate is None and len(sketch['objects']) == len(scene['objects']) and idx < len(scene['objects']):
                candidate_by_idx = scene['objects'][idx]
                if candidate_by_idx['id'] in unused:
                    candidate = candidate_by_idx
            if candidate is None:
                candidate = copy.deepcopy(original)
            else:
                candidate = copy.deepcopy(candidate)
                unused.discard(candidate['id'])
            remap[candidate['id']] = original['id']
            candidate['id'] = original['id']
            candidate['entity_id'] = original.get('entity_id', original['id'])
            for key in ('x','y','w','h','rotation','label_dx','label_dy','group_id','locked','visible'):
                if key in original:
                    candidate[key] = original[key]
            # Infer biological state from label if missing or generic
            orig_text = (str(original.get('label', '')) + ' ' + str(candidate.get('label', ''))).lower()
            if candidate.get('type') in ('cell', 'stem_cell', 'process') or not candidate.get('state'):
                for std_stage, syns in STAGE_SYNONYMS.items():
                    if any(s in orig_text for s in syns):
                        candidate['type'] = 'cell'
                        candidate['state'] = std_stage
                        break
            candidate['compartment'] = original.get('compartment','')
            kept.append(candidate)
        # Do not insert unrequested nodes or new causal edges into a user's sketch.
        scene['objects'] = kept
        scene['relations'] = copy.deepcopy(sketch['relations'])
        scene['compartments'] = copy.deepcopy(sketch['compartments'])
        scene['canvas'] = copy.deepcopy(sketch['canvas'])
        scene['requirements'] = {'objects':[o['id'] for o in kept], 'relations':[r['id'] for r in scene['relations']]}
    elif config.get('reference_purpose') != 'style' and reference.get('objects'):
        source = reference['objects']
        objects = [o for o in scene['objects'] if o.get('role','entity') == 'entity']
        free = list(source)
        placed = []
        reference_ids = {}
        width,height = config['canvas_mm']
        for obj in objects:
            match = next((x for x in free if x['id'] == obj['id'] or (_label(x['label']) and _label(x['label']) == _label(obj['label']))), None)
            if match is None and len(objects) == len(source) and free:
                match = free[0]
            if match is None:
                continue
            free.remove(match)
            reference_ids[match['id']] = obj['id']
            obj.update(x=round(match['x']*width,4), y=round(match['y']*height,4),
                       w=round(match['w']*width,4), h=round(match['h']*height,4))
            # Reserve label space without changing the object's supplied location.
            if obj['y']+obj['h'] > height-7:
                obj['label_dy'] = -obj['h']-2
            placed.append(obj['id'])
        if len(placed) != len(objects):
            scene['unresolved'].append('参考图与本图对象数量或名称不同，未匹配对象保留自动布局；请在画布核对')
        if config.get('reference_purpose')=='sketch' and len(placed)==len(source):
            # A request to improve a sketch does not authorize extra external nodes.
            scene['objects']=[o for o in scene['objects'] if o['id'] in placed]
            scene['relations']=[r for r in scene['relations'] if r['source'] in placed and r['target'] in placed]
            scene['requirements']={'objects':placed,'relations':[r['id'] for r in scene['relations']]}
        if placed:
            # Leave free reference positions free instead of inventing cell compartments.
            scene['compartments'] = []
            for obj in scene['objects']:
                obj['compartment'] = ''
        if config.get('reference_purpose') in ('sketch','content') and reference.get('relations'):
            retained = []
            for i, relation in enumerate(reference['relations']):
                a,b=reference_ids.get(relation['source']),reference_ids.get(relation['target'])
                if a and b:
                    retained.append({'id':f'sketch_r{i+1}','source':a,'target':b,'type':relation['type'],
                                     'label':relation.get('label',''),'uncertain':relation['type']=='associates',
                                     'evidence':'用户上传草稿中可见的连接', 'evidence_source':'reference_image',
                                     'evidence_ref':config.get('reference_id','')})
            if len(retained)==len(reference['relations']):
                scene['relations']=retained
                scene['requirements']['relations']=[r['id'] for r in retained]
        for uncertainty in reference.get('uncertainties') or []:
            scene['unresolved'].append('参考图待核对：' + uncertainty)
    scene['source_text'] = config['original_text']
    contract = {'original_text':config['original_text'], 'generation_brief':config['generation_brief'],
                'source_kind':'canvas-sketch' if sketch else 'reference' if config.get('reference_id') else 'description',
                'reference_id':config.get('reference_id',''), 'reference_summary':reference.get('summary',''),
                'reference_purpose':config.get('reference_purpose',''), 'draft_source_id':config.get('draft_source_id',''),
                'draft_source_revision':str(config.get('draft_source_revision') or ''),
                'verification':'核对原始描述、草稿布局与科学状态；机器检查不替代作者科学确认'}
    scene['generation_contract'] = contract
    scene['provenance'].update({k:v for k,v in contract.items() if k not in ('source_kind','verification')})
    scene['provenance']['generation_mode'] = config.get('illustration_mode','vector')
    if not sketch and scene.get('layout')=='process':
        _route_stage_turns(scene)
    contract['expected_objects'] = json.dumps(
        [{'id':o['id'],'label':o['label'],'state':o.get('state',''),
          **({k:o[k] for k in ('x','y','w','h') if k in o} if sketch or config.get('reference_purpose') in ('layout','sketch','content') else {})}
         for o in (sketch['objects'] if sketch else scene['objects'])],ensure_ascii=False)
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


def preview(app, text, config):
    from scene_render import render_scene
    scene, meta = plan(text, config)
    ident = 'gp_' + uuid.uuid4().hex[:24]
    folder = Path(app.DATA_DIR)/'generation-previews'
    folder.mkdir(parents=True,exist_ok=True)
    (folder/(ident+'.json')).write_text(json.dumps({'created':time.time(), 'fingerprint':fingerprint(config),
                                                 'scene':scene, 'planner':meta},ensure_ascii=False),encoding='utf-8')
    return {'ok':True,'preview_id':ident,'scene':scene,'svg':render_scene(scene),
            'contract':scene['generation_contract'],'unresolved':scene['unresolved']}


def load_preview(data_dir, ident, config):
    if not isinstance(ident,str) or not PREVIEW_ID.fullmatch(ident):
        raise SceneError('结构预览标识无效')
    stored = json.loads((Path(data_dir)/'generation-previews'/(ident+'.json')).read_text(encoding='utf-8'))
    if stored['fingerprint'] != fingerprint(config):
        raise RevisionConflict('描述、参考图或草稿已变化，请重新查看结构预览')
    if time.time()-stored['created'] > 86400:
        raise SceneError('结构预览已过期，请重新生成预览')
    return normalize_scene(stored['scene'])
