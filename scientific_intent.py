"""Independent scientific intent, separate from visual layout and model output."""
from __future__ import annotations
import re

PHASES = (
    ('interphase','Interphase',r'间期|\binterphase\b'),
    ('prophase','Prophase',r'前期|\bprophase\b'),
    ('prometaphase','Prometaphase',r'前中期|\bprometaphase\b'),
    ('metaphase','Metaphase',r'中期|\bmetaphase\b'),
    ('anaphase','Anaphase',r'后期|\banaphase\b'),
    ('telophase','Telophase',r'末期|\btelophase\b'),
    ('cytokinesis','Cytokinesis',r'胞质分裂|\bcytokinesis\b'),
)
_PHASE_RE = re.compile('|'.join(f'(?P<{key}>{pattern})' for key,label,pattern in sorted(PHASES,key=lambda p:len(p[2]),reverse=True)),re.I)
MITOSIS = re.compile(r'有丝分裂|\bmitosis\b|\bmitotic\b',re.I)
MEIOSIS = re.compile(r'减数分裂|\bmeiosis\b|\bmeiotic\b',re.I)
ENGINEERING = re.compile(r'机器人|控制器|传感器|执行器|控制系统|闭环控制|反馈控制|电化学|电池|燃料电池|光伏|太阳能|生命周期评价|robot|controller|actuator|sensor|closed.loop control|fuel cell|solar cell|battery|life.cycle assessment',re.I)
BIOLOGY = re.compile(r'细胞|有丝分裂|减数分裂|蛋白|受体|配体|胞质|染色体|纺锤|核膜|信号通路|囊泡|肿瘤|免疫|\bmitosis\b|\bmitotic\b|\bmeiosis\b|\bprotein\b|\breceptor\b|\bligand\b|\bvesicle\b|\bchromosome\w*\b|\bspindle\b|\bcell(?:ular)?\b',re.I)
SOURCE = 'https://openstax.org/books/biology-2e/pages/10-2-the-cell-cycle'


def phase_tokens(text):
    result=[]
    for match in _PHASE_RE.finditer(str(text)):
        if match.lastgroup not in result:
            result.append(match.lastgroup)
    return result


def canonical_phase(value):
    tokens=phase_tokens(str(value).replace('_',' '))
    return tokens[-1] if tokens else ''


def intent_contract(original_text):
    text=str(original_text or '')
    mitosis=bool(MITOSIS.search(text)) and not bool(MEIOSIS.search(text))
    engineering=bool(ENGINEERING.search(text))
    biology=bool(BIOLOGY.search(text)) and (mitosis or not engineering)
    phases=phase_tokens(text)
    temporal=mitosis or bool(re.search(r'细胞周期|\bcell cycle\b|\bcell division\b',text,re.I))
    return {'domain':'biology' if biology else 'engineering' if engineering else 'general',
            'layout_kind':'process' if temporal else 'network' if re.search(r'互作|网络|反馈|network|feedback',text,re.I) else 'auto',
            'explicit_phases':phases,'requires_mitosis':mitosis,
            'expects_cycle':temporal and bool(re.search(r'全周期|闭环|循环|cycle|cyclic|回环',text,re.I))}


def mitosis_candidate(original_text,width_mm=180,height_mm=120):
    contract=intent_contract(original_text)
    if not contract['requires_mitosis'] or contract['explicit_phases'] or re.search(r'非经典|异常|无丝|突变|非对称|non.?canonical|mutant|abnormal|asymmetric',original_text,re.I):
        return None
    from scene_document import empty_scene,normalize_scene
    scene=empty_scene(title='有丝分裂 · 经典分期候选',source_text=original_text,width_mm=width_mm,height_mm=height_mm)
    scene['layout']='process'
    phases=list(PHASES)
    if not contract['expects_cycle'] and not re.search(r'间期|准备|interphase',original_text,re.I):
        phases=phases[1:]
    columns=(len(phases)+1)//2
    pad=10; top=10; row_height=(height_mm-2*top)/2
    cell_width=(width_mm-2*pad)/columns
    size=min(34,cell_width-10,row_height-13)
    for i,(key,label,pattern) in enumerate(phases):
        row=i//columns; col=i%columns if row==0 else columns-1-i%columns
        if row and len(phases)-columns>1:
            col=(columns-1)*(1-(i-columns)/(len(phases)-columns-1))
        scene['objects'].append({'id':'phase_'+key,'entity_id':'dividing_cell','type':'cell','label':label,'state':key,
            'x':pad+col*cell_width+(cell_width-size)/2,'y':top+row*row_height,'w':size,'h':size,
            'evidence':'经典有丝分裂示意分期；作者尚未确认的教科书补充',
            'evidence_source':'knowledge','evidence_ref':SOURCE})
    for a,b in zip(scene['objects'],scene['objects'][1:]):
        scene['relations'].append({'id':'step_'+str(len(scene['relations'])+1),'source':a['id'],'target':b['id'],
                                   'type':'sequence','evidence':'经典有丝分裂分期顺序','evidence_source':'knowledge','evidence_ref':SOURCE})
    if contract['expects_cycle']:
        scene['relations'].append({'id':'next_cycle','source':scene['objects'][-1]['id'],'target':scene['objects'][0]['id'],
            'type':'sequence','label':'Next cycle','indirect':False,'evidence':'细胞分裂后子代进入下一轮周期',
            'evidence_source':'knowledge','evidence_ref':SOURCE})
    scene['unresolved']=['原描述未列出分期，当前展示经典动物细胞有丝分裂候选；请确认是否采用这些阶段与形态。']
    if contract['expects_cycle']:
        scene['unresolved'].append('回连表示子代进入下一细胞周期，不表示有丝分裂阶段逆转；胞质分裂与末期可在时间上重叠。')
    scene['provenance'].update(method='scientific-knowledge-candidate',knowledge_sources=SOURCE,
        scientific_assumptions='依据公开教科书补充经典动物细胞有丝分裂分期；不是用户原文已明确的机制。')
    scene['requirements']={'objects':[o['id'] for o in scene['objects']],'relations':[r['id'] for r in scene['relations']]}
    return normalize_scene(scene)


def phase_sketch(original_text,config):
    """Known phase labels can be drawn without asking a model to rediscover them."""
    source=config.get('sketch_scene')
    reference=config.get('reference_contract') or {}
    if source:
        items=source['objects']; relations=source['relations']; evidence_source='canvas_sketch'
    elif config.get('reference_purpose') in ('sketch','content'):
        items=reference.get('objects') or [];relations=reference.get('relations') or [];evidence_source='reference_image'
    else:return None
    if not items or not all(canonical_phase(o.get('label','')) for o in items):
        return None
    from scene_document import empty_scene,normalize_scene
    import copy
    width,height=config.get('canvas_mm') or [180,120]
    scene=empty_scene(title='细胞分期 · 按作者草稿',source_text=original_text,width_mm=width,height_mm=height)
    scene['layout']='process'
    if source:scene['compartments']=copy.deepcopy(source['compartments'])
    for item in items:
        obj=copy.deepcopy(item) if source else {'id':item['id'],'label':item['label']}
        obj.update(type='cell',state=canonical_phase(item['label']),entity_id='dividing_cell',
                   evidence=item['label'],evidence_source=evidence_source,
                   evidence_ref=config.get('reference_id') or item['id'])
        obj.pop('asset_id',None);obj.pop('asset_snapshot',None);obj.pop('illustration',None)
        scene['objects'].append(obj)
    for i,r in enumerate(relations):
        scene['relations'].append({**copy.deepcopy(r),'id':r.get('id') or 'draft_r'+str(i+1),
            'evidence':'作者草稿中可见的连接','evidence_source':evidence_source,
            'evidence_ref':config.get('reference_id') or r.get('id','')})
    scene['provenance'].update(method='author-phase-sketch',knowledge_sources=SOURCE,
        scientific_assumptions='按作者标明的分期使用对应的经典细胞形态；具体结构仍需作者核对。')
    scene['unresolved']=['按草稿标签绘制经典动物细胞分期形态，请核对物种及研究中特殊结构。']
    scene['requirements']={'objects':[o['id'] for o in scene['objects']],'relations':[r['id'] for r in scene['relations']]}
    return normalize_scene(scene)
