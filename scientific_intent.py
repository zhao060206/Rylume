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
PLANT_CONTEXT=re.compile(r'植物|洋葱|拟南芥|水稻|玉米|烟草|\b(?:plant|onion|arabidopsis|rice|maize|tobacco)\b',re.I)
SPECIAL_DIVISION=re.compile(r'非经典|异常|无丝|突变|非对称|酵母|真菌|闭合.{0,8}分裂|核膜.{0,6}(?:不破|始终|一直)|无中心体|无星射线|non.?canonical|mutant|abnormal|asymmetric|yeast|fungal|closed mitosis|(?:no|without) (?:centrosomes|asters)',re.I)
EXPERIMENT_OR_MECHANISM=re.compile(r'实验(?:流程|方案|步骤)|免疫染色|调控|机制|检查点|纺锤体组装|\b(?:protocol|assay|experimental|mechanism|regulator|checkpoint|kinase)\b|spindle assembly',re.I)
_NEGATIVE_PHASE=re.compile(r'不要(?:画|显示|包含|包括|绘制)?|不(?:画|显示|含|包含|包括|绘制)|排除|省略|略去|去掉|\b(?:exclude|omit|without|except)\b|\b(?:do not|never)\s+(?:show|draw|include|depict)\b',re.I)


def classical_mitosis_compatible(text):
    text=str(text or '')
    return not (MEIOSIS.search(text) or PLANT_CONTEXT.search(text) or SPECIAL_DIVISION.search(text)
                or ENGINEERING.search(text) or EXPERIMENT_OR_MECHANISM.search(text))


def apply_division_context(scene,text):
    """Keep the same authored phase while selecting an appropriate glyph family."""
    plant=bool(PLANT_CONTEXT.search(str(text))) and not bool(MEIOSIS.search(str(text))) and not bool(re.search(r'非经典|异常|突变|非对称|闭合|封闭|non.?canonical|mutant|abnormal|asymmetric|closed',str(text),re.I))
    special=bool(MEIOSIS.search(str(text)) or SPECIAL_DIVISION.search(str(text)))
    if not plant and not special:return scene
    warned=False
    for obj in scene.get('objects',[]):
        if obj.get('locked') or obj.get('illustration'):continue
        if plant and obj.get('type')=='process' and labeled_cell_phase(obj.get('label',''),biological_context=True):obj['type']='cell'
        if obj.get('type') not in ('cell','stem_cell'):continue
        phase=canonical_phase(obj.get('state','')) or labeled_cell_phase(obj.get('label',''),biological_context=True)
        if not phase:continue
        if plant:
            obj['state']='plant_'+phase
            obj.pop('asset_id',None);obj.pop('asset_snapshot',None)
        elif obj.get('asset_id'):
            continue
        elif obj.get('state','') in ('',phase):
            obj['state']='special_'+phase
            warned=True
    if warned:
        message='该物种或分裂方式不能使用通用动物细胞分期图元；当前保留通用细胞草稿，请使用相符素材或 AI 插画细化特异结构。'
        if message not in scene['unresolved']:scene['unresolved'].append(message)
    return scene


def requested_phase_tokens(text):
    """Track explicit exclusion lists independently of ordinary phase mentions."""
    text=str(text);states={}
    for match in _PHASE_RE.finditer(text):
        prefix=re.split(r'[。；;\n.!?！？]',text[:match.start()])[-1]
        negatives=list(_NEGATIVE_PHASE.finditer(prefix));excluded=False
        if negatives:
            tail=_PHASE_RE.sub('',prefix[negatives[-1].end():])
            tail=re.sub(r'\b(?:and|or|the|stage|stages|phase|phases)\b|阶段|细胞|和|及|与|或|的','',tail,flags=re.I)
            excluded=not bool(re.search(r'[A-Za-z\u3400-\u9fff]',tail))
        if re.match(r'\s*(?:阶段)?\s*(?:不画|不显示|不包含|省略)',text[match.end():]):excluded=True
        states[match.lastgroup]=excluded
    return [k for k,v in states.items() if not v],[k for k,v in states.items() if v]


def excluded_object_evidence(text,label):
    """Only explicit global 'do not add X' constraints; no guessing conditional absence."""
    if not label:return ''
    name=re.escape(label)
    if re.search(r'[A-Za-z0-9]',label):name=r'(?<![A-Za-z0-9_])'+name+r'(?![A-Za-z0-9_])'
    match=re.search(r'(?:不要添加|不要加入|不添加|不加入|\b(?:do not|never)\s+add\s+(?:the\s+)?)\s*'+name,str(text),re.I)
    return match.group(0) if match else ''


def contradicted_relation_evidence(text,source,target,kind):
    if kind not in ('activates','inhibits') or not source or not target:return ''
    def name(value):return r'(?<![A-Za-z0-9_])'+re.escape(value)+r'(?![A-Za-z0-9_])'
    negative=r'\s*(?:(?:does|do|did|can|will)\s+not|cannot|never|不(?:会|能|直接)?|未(?:能|直接)?|没有)\s*(?:directly\s+)?'
    verb=r'(?:activat(?:e|es|ed)|激活|促进)' if kind=='activates' else r'(?:inhibit(?:s|ed)?|抑制)'
    gap=r'\s*(?:the\s+)?'
    pattern=name(source)+negative+verb+gap+name(target)
    match=re.search(pattern,str(text),re.I)
    if not match and kind=='activates':
        match=re.search(name(target)+r'\s+(?:is|was)\s+not\s+(?:directly\s+)?activated\s+by\s+'+name(source),str(text),re.I)
    return match.group(0) if match else ''
PHASE_FEATURES = {
    'interphase':'Exactly one cell with a continuous intact nuclear envelope, visible nucleolus and diffuse chromatin; no condensed X-shaped chromosomes or bipolar spindle.',
    'prophase':'Exactly one cell with chromosomes condensing INSIDE a continuous intact nuclear envelope. The nuclear envelope must be a complete unbroken boundary, NOT dashed, fragmented, dissolved or absent. Centrosomes separate outside the nucleus and form asters; spindle fibres must not cross the intact nuclear envelope.',
    'prometaphase':'Exactly one cell with a disassembled nuclear envelope; fragments may remain. Condensed chromosomes are not yet aligned. Bipolar spindle microtubules attach to kinetochores.',
    'metaphase':'Exactly one cell with no nuclear envelope. Paired sister chromatids align on the equatorial metaphase plate with centrosomes at opposite poles and a bipolar spindle.',
    'anaphase':'Exactly one cell. Sister chromatids have separated and move centromere-first to opposite poles; two groups of V-shaped daughter chromosomes, no nuclear envelopes.',
    'telophase':'Exactly one elongated cell with two re-forming nuclear envelopes around separate chromosome groups; chromatin decondenses and the cleavage furrow begins.',
    'cytokinesis':'A dividing cell with a deep cleavage furrow producing two daughter cells, each with its own intact nucleus. This is one cytokinesis event, not a montage of different phases.',
}


def phase_tokens(text):
    result=[]
    for match in _PHASE_RE.finditer(str(text)):
        if match.lastgroup not in result:
            result.append(match.lastgroup)
    return result


def canonical_phase(value):
    tokens=phase_tokens(str(value).replace('_',' '))
    return tokens[-1] if tokens else ''


def labeled_cell_phase(value, *, biological_context=False):
    """Recognize a named cell phase, never a substring in a protein or project step."""
    text=str(value).replace('_',' ')
    tokens=phase_tokens(text)
    if len(tokens)!=1:
        return ''
    remainder=_PHASE_RE.sub('',text)
    remainder=re.sub(r'\b(?:animal|mitotic|cell|cells|stage|phase)\b|动物|有丝分裂|细胞|阶段', '', remainder, flags=re.I)
    if re.search(r'[A-Za-z\u3400-\u9fff]',remainder):
        return ''
    # Chinese 前期/中期/后期 are also ordinary project phases.
    if not biological_context and not re.search(r'细胞|\b(?:interphase|prophase|prometaphase|metaphase|anaphase|telophase|cytokinesis)\b',text,re.I):
        return ''
    return tokens[0]


def intent_contract(original_text):
    text=str(original_text or '')
    mitosis=bool(MITOSIS.search(text)) and not bool(MEIOSIS.search(text))
    engineering=bool(ENGINEERING.search(text))
    concrete_biology=bool(re.search(r'细胞|蛋白|受体|染色体|\b(?:protein|receptor|chromosome|animal cell|plant cell|human cell)\b',text,re.I))
    biology=bool(BIOLOGY.search(text)) and (not engineering or concrete_biology)
    phases,excluded=requested_phase_tokens(text)
    temporal=mitosis or bool(re.search(r'细胞周期|\bcell cycle\b|\bcell division\b',text,re.I))
    return {'domain':'biology' if biology else 'engineering' if engineering else 'general',
            'layout_kind':'process' if temporal else 'network' if re.search(r'互作|网络|反馈|network|feedback',text,re.I) else 'auto',
            'explicit_phases':phases,'excluded_phases':excluded,'requires_mitosis':mitosis,
            'depicts_phases':bool(re.search(r'分期|全周期|全过程|有丝分裂.{0,8}(?:流程|过程|周期|[:：])|\b(?:mitosis|mitotic)\s+(?:stages|phases|cycle|process)\b|\b(?:draw|show|depict)\b.{0,35}\b(?:cells|phases|stages)\b',text,re.I)),
            'expects_cycle':temporal and bool(re.search(r'全周期|闭环|循环|cycle|cyclic|回环',text,re.I))}


def mitosis_candidate(original_text,width_mm=180,height_mm=120):
    contract=intent_contract(original_text)
    if not contract['requires_mitosis'] or contract['explicit_phases'] or contract['excluded_phases'] or not classical_mitosis_compatible(original_text) or re.search(r'(?:不要|不含|不画).{0,12}有丝分裂|(?:do not|without|exclude).{0,18}mitosis',original_text,re.I):
        return None
    # This shortcut is only for a plain request for the general stages.
    # Mentioning mitosis in a specific interaction is not authorization to
    # replace that study with a textbook cycle.
    remainder=re.sub(r'\b(?:please|draw|show|create|generate|make|a|an|the|of|for|eukaryotic|animal|human|cell|cells|mitosis|mitotic|full|complete|cycle|stages|phases|process|diagram|figure|flowchart|schematic)\b','',original_text,flags=re.I)
    remainder=re.sub(r'有丝分裂|真核|哺乳动物|动物|人类|细胞|全周期|全过程|生命周期|周期|分期|流程图|流线图|流程|过程|闭环|循环|示意图|绘制|生成|制作|帮我|请|画|一张|一个|的|图','',remainder)
    if re.search(r'[A-Za-z\u3400-\u9fff]',remainder):return None
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
    if not classical_mitosis_compatible(original_text):return None
    source=config.get('sketch_scene')
    reference=config.get('reference_contract') or {}
    if source:
        items=source['objects']; relations=source['relations']; evidence_source='canvas_sketch'
    elif config.get('reference_purpose') in ('sketch','content'):
        items=reference.get('objects') or [];relations=reference.get('relations') or [];evidence_source='reference_image'
    else:return None
    biological_context=intent_contract(original_text)['domain']=='biology'
    if not items or not all(labeled_cell_phase(o.get('label',''),biological_context=biological_context or o.get('type') in ('cell','stem_cell')) for o in items):
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
