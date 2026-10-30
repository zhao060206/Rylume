"""Original editable workflow examples; no fabricated experimental results.

The graph is explicit. Reflow changes geometry, never scientific relationships.
"""
from scene_document import empty_scene, normalize_scene

# id, title, category, topology, node descriptions, directed step connections.
# Ordinary workflow arrows denote sequence, not molecular conversion/transport.
FLOW_SPECS = [
 ('sample_route','样本到结果 · 实验路线','实验流程','横向步骤',
  ['Sample|input','Extract|apparatus','Measure|apparatus','Analyse|badge','Report|document'],[(0,1),(1,2),(2,3),(3,4)]),
 ('vertical_protocol','实验方案 · 纵向清单','实验流程','纵向步骤',
  ['Prepare|badge','Treat|badge','Wash|badge','Acquire|apparatus','Interpret|document'],[(0,1),(1,2),(2,3),(3,4)]),
 ('quality_gate','质量门槛 · 通过与重做','分支与筛选','分支决策',
  ['Extract|apparatus','QC passed?|decision','Library prep|badge','Re-extract|apparatus','Sequence|document'],[(0,1),(1,2,'Pass'),(1,3,'Fail'),(3,0,'Repeat'),(2,4)]),
 ('treatment_arms','对照与处理 · 平行实验','实验流程','平行分组',
  ['Matched samples|input','Control|comparison','Treatment|comparison','Readout A|badge','Readout B|badge','Compare|document'],[(0,1),(0,2),(1,3),(2,4),(3,5),(4,5)]),
 ('omics_merge','多组学 · 数据汇合','数据分析','多路汇合',
  ['RNA-seq|database','Proteomics|database','Metabolomics|database','Integration|capsule','Pathways|document'],[(0,3),(1,3),(2,3),(3,4)]),
 ('design_cycle','实验设计 · 迭代闭环','循环与反馈','闭环迭代',
  ['Hypothesis|capsule','Design|badge','Experiment|apparatus','Evaluate|badge'],[(0,1),(1,2),(2,3),(3,0,'Refine')]),
 ('screening','文献筛选 · 纳入与排除','分支与筛选','筛选流程',
  ['Records|database','Screen titles','Full-text review','Included|document','Excluded','Reasons|document'],[(0,1),(1,2),(2,3),(1,4,'Exclude'),(2,5,'Exclude')]),
 ('sample_funnel','样本筛选 · 逐级收敛','分支与筛选','逐级漏斗',
  ['All samples|input','Eligibility','Quality control','Analysis set|document'],[(0,1),(1,2),(2,3)]),
 ('bench_compute','湿实验与分析 · 双泳道','实验流程','双泳道',
  ['Prepare|apparatus','Acquire|apparatus','Validate|badge','Import|database','Process|badge','Interpret|document'],[(0,1),(1,2),(1,3),(3,4),(4,5),(5,2,'Feedback')]),
 ('clinical_timeline','随访安排 · 采样时间轴','实验流程','时间轴',
  ['Baseline|milestone','Intervention|milestone','Follow-up|milestone','Endpoint|document'],[(0,1,'Time 0'),(1,2,'Scheduled'),(2,3,'Final')]),
 ('discovery_validation','发现与验证 · 双阶段','实验流程','分阶段面板',
  ['Cohort A|input','Discover|badge','Candidates|document','Cohort B|input','Validate|badge','Report|document'],[(0,1),(1,2),(2,4),(3,4),(4,5)]),
 ('screen_confirm','初筛与复筛 · 正交确认','分支与筛选','层级筛选',
  ['Library|database','Primary screen','Hits','Orthogonal test','Confirmed|document','Discard'],[(0,1),(1,2),(2,3),(3,4,'Supported'),(3,5,'Not supported')]),
 ('causal_test','阻断与救援 · 实验设计','实验流程','三臂对照',
  ['Model|input','Vehicle','Block','Rescue','Compare|document'],[(0,1),(0,2),(0,3),(1,4),(2,4),(3,4)]),
 ('triangulation','证据整合 · 三路交叉','数据分析','证据三角',
  ['Imaging|document','Molecular|document','Functional|document','Concordance','Interpret|document'],[(0,3),(1,3),(2,3),(3,4)]),
 ('decision_tree','分析选择 · 决策树','分支与筛选','二级决策',
  ['Study aim|input','Paired?|decision','Paired analysis','Independent? |decision','Group analysis','Review design|document'],[(0,1),(1,2,'Yes'),(1,3,'No'),(3,4,'Yes'),(3,5,'Unclear')]),
 ('batch_pipeline','批次处理 · 扇出与归并','数据分析','扇出归并',
  ['Dataset|database','Batch A','Batch B','Batch C','Merge','QC|document'],[(0,1),(0,2),(0,3),(1,4),(2,4),(3,4),(4,5)]),
 ('rna_pipeline','RNA-seq · 分层分析','数据分析','分析管线',
  ['Reads|database','QC / align','Counts|database','Differential','Enrichment|document'],[(0,1),(1,2),(2,3),(3,4)]),
 ('image_pipeline','显微成像 · 采集到定量','数据分析','图像分析',
  ['Specimen|input','Acquire','Segment','Quantify','Validate|document'],[(0,1),(1,2),(2,3),(3,4)]),
 ('handoff_lanes','研究协作 · 三泳道交接','实验流程','三泳道',
  ['Recruit|input','Collect','Prepare','Assay','Analyse','Archive|database'],[(0,1),(1,2),(2,3),(3,4),(4,5)]),
 ('milestone','课题推进 · 里程碑','实验流程','里程碑',
  ['Question|terminal','Pilot|terminal','Main study|terminal','Replication|terminal','Manuscript|document'],[(0,1),(1,2),(2,3),(3,4)]),
 ('feedback_control','质量反馈 · 主线与回路','循环与反馈','外围反馈',
  ['Input|input','Process','Product','QC passed?|decision','Release|document','Adjust'],[(0,1),(1,2),(2,3),(3,4,'Pass'),(3,5,'Fail'),(5,1,'Revise')]),
 ('reversible_states','状态切换 · 可逆过程','循环与反馈','双向切换',
  ['State A','State B','State C'],[(0,1,'Forward'),(1,0,'Reverse'),(1,2,'Forward'),(2,1,'Reverse')]),
 ('paired_readout','机制与表型 · 配对验证','实验流程','上下配对',
  ['Control','Treatment','Molecular A','Molecular B','Phenotype A','Phenotype B'],[(0,2),(1,3),(2,4),(3,5)]),
 ('database_route','数据资源 · 汇入与发布','数据分析','资源管线',
  ['Source A|database','Source B|database','Curate','Version|database','Publish|document'],[(0,2),(1,2),(2,3),(3,4)]),
]
SPEC_BY_ID={row[0]:row for row in FLOW_SPECS}

FLOW_LAYOUTS=[
 ('ranks_lr','按连接分层 · 从左到右','按关系的先后分层，分支保持在同一阅读层。'),
 ('ranks_tb','按连接分层 · 从上到下','从顶部起点向下阅读，适合单栏与分支图。'),
 ('snake','折返路线 · 连续步骤','长步骤折返排列，为每一行留出连线走廊。'),
 ('columns','并排分栏 · 分组阅读','把对象分成两列，适合比较相邻步骤。'),
 ('orbit','环形展开 · 中央留白','沿环形摆放已有对象；保留原有连线，不添加循环。'),
 ('lanes','平行条带 · 多行阅读','按现有分组或顺序分成平行条带，连线保持绑定。'),
]

def flow_layout_catalog():
    return [dict(id='layout_'+sid,title=title,description=description,category='流程排版',family='process',
                 example='workflow',canvas_mm=[180,120],composition=title.split(' · ')[0],template_kind='layout')
            for sid,title,description in FLOW_LAYOUTS]


def place_flow_layout(scene):
    """Only place existing objects; preserve scientific identities and topology."""
    import math
    cw,ch=scene['canvas']['width_mm'],scene['canvas']['height_mm']
    objects=[o for o in scene['objects'] if o.get('role') not in ('context','annotation')]
    n=len(objects)
    if not n:return normalize_scene(scene)
    tid=scene['style']['template'];ids={o['id'] for o in objects};order={o['id']:i for i,o in enumerate(objects)}
    parents={oid:set() for oid in ids};children={oid:set() for oid in ids}
    for r in scene['relations']:
        if r['source'] in ids and r['target'] in ids:
            parents[r['target']].add(r['source']);children[r['source']].add(r['target'])
    ranks={oid:0 for oid in ids};pending={k:set(v) for k,v in parents.items()}
    queue=sorted((oid for oid in ids if not pending[oid]),key=order.get);visited=set()
    while queue:
        oid=queue.pop(0);visited.add(oid)
        for child in sorted(children[oid],key=order.get):
            if child in visited:continue
            ranks[child]=max(ranks[child],ranks[oid]+1);pending[child].discard(oid)
            if not pending[child] and child not in queue:queue.append(child)
    # Cyclic members retain a stable order; layout never adds an edge to close a ring.
    for oid in sorted(ids-visited,key=order.get):ranks[oid]=max(ranks.values())+1
    levels={}
    for o in objects:levels.setdefault(ranks[o['id']],[]).append(o)
    def put(o,x,y,w,h):o.update(x=x-w/2,y=y-h/2,w=w,h=h,label_dx=0,label_dy=0)
    if tid in ('layout_ranks_lr','layout_ranks_tb'):
        vertical=tid.endswith('tb') or cw<110
        count=len(levels)
        for row,rank in enumerate(sorted(levels)):
            items=levels[rank]
            for i,o in enumerate(items):
                if vertical:
                    w=min(30,(cw-16)/len(items)-4);h=min(15,(ch-25)/count-8)
                    x=8+(cw-16)*(i+.5)/len(items);y=12+(ch-30)*(row+.5)/count
                else:
                    w=min(27,(cw-16)/count-5);h=min(17,(ch-30)/len(items)-8)
                    x=8+(cw-16)*(row+.5)/count;y=10+(ch-28)*(i+.5)/len(items)
                put(o,x,y,max(3,w),max(3,h))
    else:
        cols=2 if tid=='layout_columns' else min(3,n);rows=math.ceil(n/cols)
        if tid=='layout_lanes':cols=math.ceil(n/2);rows=2
        for i,o in enumerate(objects):
            row,col=divmod(i,cols)
            if tid=='layout_snake' and row%2:col=cols-1-col
            if tid=='layout_orbit':
                angle=-math.pi/2+2*math.pi*i/n;x=cw/2+(cw/2-23)*math.cos(angle);y=ch/2-3+(ch/2-23)*math.sin(angle)
                w,h=min(25,cw*.24),13
            else:
                w,h=min(28,(cw-16)/cols-5),min(16,(ch-30)/rows-9)
                x=8+(cw-16)*(col+.5)/cols;y=8+(ch-27)*(row+.5)/rows
            put(o,x,y,max(3,w),max(3,h))
    return normalize_scene(scene)


def flow_catalog():
    return [dict(id='flow_'+sid,title=title,category=category,family='process',example='flow_'+sid,
                 description=f'{composition}结构；文字、流程形状和连线均可编辑。示意步骤可替换为自己的方案。',
                 canvas_mm=[180,120],new_scene_only=True,featured=True,composition=composition,
                 template_kind='workflow') for sid,title,category,composition,_,_ in FLOW_SPECS]


FLOW_DETAILS={
 'sample_route':('把样本、检测与分析串成一条实验路线',['样本输入','提取','检测','分析','报告'],'骨架步骤可替换，不包含真实实验条件或测量结果。'),
 'quality_gate':('让通过标准与返工路线清楚分开',['样本提取','QC 决策','Pass / Fail','返工回路','建库与测序'],'请填写具体 QC 阈值；示意流程不提供合格标准。'),
 'treatment_arms':('同尺度呈现对照组与处理组',['共同样本起点','平行对照 / 处理臂','对应读数','共同比较终点'],'示意分组不意味着随机化或已取得差异结果。'),
 'bench_compute':('区分湿实验与计算分析的职责和交接',['Bench / Analysis 泳道','数据采集与导入','处理和解释','分析后返回实验验证'],'步骤与交接可修改，不含具体软件、分析方法或验证结论。'),
 'clinical_timeline':('安排干预前后的采样与随访节点',['连续时间轴','基线','干预','随访','终点评估'],'日期需要填写；间距为示意，不表示真实时间比例或临床方案。'),
 'design_cycle':('表达假设、实验与评价之间的迭代',['假设','设计','实验','评价与修订'],'设计循环不保证研究假设成立；不含实验结果。'),
 'causal_test':('组织阻断与救援的实验分组',['Vehicle','Block','Rescue','共同比较'],'实验设计骨架，不足以独立证明因果；需补充控制条件与可检验的结果。'),
}

_base_flow_catalog=flow_catalog
def flow_catalog():
    result=_base_flow_catalog()
    for t in result:
        sid=t['id'][5:]
        if sid in FLOW_DETAILS:t['usage'],t['includes'],t['limitations']=FLOW_DETAILS[sid]
        if sid=='clinical_timeline':t['canvas_mm']=[180,80]
        if sid=='sample_route':t['canvas_mm']=[180,70]
        if sid=='bench_compute':t['canvas_mm']=[180,100]
    return result


def _refine_flow(scene,sid,width,height):
    """Authored geometry for meaningfully different, editable workflow types."""
    if sid not in ('quality_gate','treatment_arms','bench_compute','clinical_timeline'):return scene
    narrow=width<110;sx=width/180;sy=height/120
    objects={o['id']:o for o in scene['objects']}
    def put(oid,x,y,w=29,h=13):
        o=objects[oid];o.update(x=x*sx-w/2,y=y*sy-h/2,w=w,h=h)
    if sid=='quality_gate':
        coords=[(27,52),(77,52),(125,35),(77,93),(158,35)] if not narrow else [(90,13),(90,42),(137,76),(34,76),(137,105)]
        for i,(x,y) in enumerate(coords):put('step'+str(i),x,y,23 if narrow else 27,18 if i==1 else 12)
        for r in scene['relations']:
            if r['source']=='step3':r.update(source_port='w',target_port='s',control={'x':8*sx,'y':100*sy})
            elif r['target']=='step3':r.update(source_port='s',target_port='n')
    elif sid=='treatment_arms':
        coords=[(90,15),(44,43),(136,43),(44,76),(136,76),(90,104)]
        for i,(x,y) in enumerate(coords):put('step'+str(i),x,y,25 if narrow else 35,12)
        for i in (1,3):objects['step'+str(i)]['fill']='#637D87'
        for i in (2,4):objects['step'+str(i)]['fill']='#AD8062'
    elif sid=='bench_compute':
        coords=[(28,32),(90,32),(152,32),(90,83),(121,83),(152,83)] if not narrow else [(45,24),(45,53),(45,103),(135,53),(135,78),(135,103)]
        for i,(x,y) in enumerate(coords):put('step'+str(i),x,y,(22 if i>=3 else 27) if not narrow else 29,12)
        for i in (0,1,2):objects['step'+str(i)]['fill']='#486B7B'
        for i in (3,4,5):objects['step'+str(i)]['fill']='#8F765F'
        # Data acquisition hands over to analysis; interpretation informs
        # validation. There is no unexplained diagonal shortcut.
        scene['relations']=[dict(id='flowlink'+str(i),source='step'+str(a),target='step'+str(b),type='sequence',label=label,evidence='Illustrative workflow order; no biological effect.')
            for i,(a,b,label) in enumerate([(0,1,''),(1,3,'data'),(3,4,''),(4,5,''),(5,2,'validate')])]
        for i in (0,1):
            lane=objects['lane'+str(i)]
            if narrow:lane.update(x=(3+i*45)*width/90,y=8*sy,w=39*width/90,h=105*sy)
            lane['label']='Bench' if i==0 else 'Analysis'
    else:
        # Timeline is an actual editable axis with visit markers. Placeholder
        # dates are intentionally non-numerical to avoid invented protocols.
        scene['objects']=[o for o in scene['objects'] if not o['id'].startswith('time')]
        scene['source_text']+=' Author must supply actual dates. Axis spacing is schematic.'
        if not narrow:
            for i,x in enumerate((27,69,111,153)):put('step'+str(i),x,36,30,12)
            axis=dict(id='time_axis',type='process',state='timeline_axis',role='context',label='',x=20*sx,y=54*sy,w=140*sx,h=4*sy)
            times=[(x,72) for x in (27,69,111,153)]
        else:
            for i,y in enumerate((22,48,74,100)):put('step'+str(i),58,y,31,12)
            axis=dict(id='time_axis',type='process',state='timeline_vertical',role='context',label='',x=17*width/90,y=17.6667*sy,w=4,h=86.6667*sy)
            times=[(144,y) for y in (22,48,74,100)]
        scene['objects'].insert(0,{**axis,'font_size_pt':8,'fill':'#627787','evidence':scene['source_text']})
        for i,(x,y) in enumerate(times):
            scene['objects'].append(dict(id='time'+str(i),type='text',role='annotation',label='Time 0' if i==0 else 'Set date',x=x*sx-11,y=y*sy,w=22,h=1,font_size_pt=8,evidence='Author must supply actual dates. Axis spacing is schematic.'))
        for r in scene['relations']:r['label']=''
    scene['requirements']={'objects':[o['id'] for o in scene['objects']],'relations':[r['id'] for r in scene['relations']]}
    return scene


def _positions(kind,n,narrow):
    # Authored topologies use at most three columns on the portrait page.
    if kind in ('横向步骤','分析管线','图像分析','资源管线','里程碑'):
        if n==5:return [(28,29),(90,29),(152,29),(152,82),(90,82)] if not narrow else [(40,16),(140,16),(140,55),(40,55),(40,94)]
    if kind=='纵向步骤':return [(90,14+i*21) for i in range(n)]
    if kind=='分支决策':return [(36,22),(90,48),(142,48),(36,82),(142,94)]
    if kind=='平行分组':return [(90,15),(43,44),(137,44),(43,76),(137,76),(90,100)]
    if kind=='多路汇合':return [(30,20),(90,20),(150,20),(90,61),(90,99)]
    if kind=='闭环迭代':return [(52,26),(130,26),(130,84),(52,84)]
    if kind=='筛选流程':return [(60,14),(60,40),(60,67),(60,97),(143,40),(143,73)]
    if kind=='逐级漏斗':return [(90,18+i*25) for i in range(n)]
    if kind=='双泳道':return [(28,33),(90,33),(152,33),(28,83),(90,83),(152,83)]
    if kind=='时间轴':return [(27,42),(69,42),(111,42),(153,42)] if not narrow else [(90,17+i*25) for i in range(n)]
    if kind=='分阶段面板':return [(30,28),(90,28),(150,28),(30,83),(90,83),(150,83)]
    if kind=='层级筛选':return [(45,14),(45,40),(45,67),(112,67),(112,100),(154,39)]
    if kind=='三臂对照':return [(90,18),(30,55),(90,55),(150,55),(90,96)]
    if kind=='证据三角':return [(35,24),(145,24),(35,96),(90,57),(145,96)]
    if kind=='二级决策':return [(30,15),(30,43),(30,90),(115,43),(90,90),(155,90)]
    if kind=='扇出归并':return [(90,13),(30,44),(90,44),(150,44),(90,77),(90,103)]
    if kind=='三泳道':return [(35,25),(132,25),(35,59),(132,59),(35,93),(132,93)]
    if kind=='外围反馈':return [(29,26),(90,26),(151,26),(151,72),(90,99),(29,72)]
    if kind=='双向切换':return [(30,54),(90,54),(150,54)]
    if kind=='上下配对':return [(48,21),(132,21),(48,56),(132,56),(48,93),(132,93)]
    return [(30,22),(145,22),(90,56),(90,79),(90,102)][:n]


def make_flow(example_id,*,width_mm=180,height_mm=120):
    sid=example_id.removeprefix('flow_');_,title,cat,kind,nodes,edges=SPEC_BY_ID[sid]
    scene=empty_scene(title,width_mm=width_mm,height_mm=height_mm);scene['layout']='process'
    scene['style']['template']='flow_'+sid
    scene['provenance']={'method':'original-editable-workflow','example':'flow_'+sid,
        'reference_rights':'Original vector layout. Reference publications are linked, not reproduced.'}
    scene['source_text']='Illustrative workflow: '+title+'. '+kind+'. Steps and branches are design placeholders, not a validated protocol. Ordinary directed links denote workflow sequence only; no molecular activation, conversion or transport is implied. Replace eligibility criteria, timings and analysis methods with the actual study design. No measured data or sample counts are asserted.'
    sx,sy=width_mm/180,height_mm/120;narrow=width_mm<110
    primary,accent=('#36576B','#A16D46') if cat=='实验流程' else ('#536A58','#95714C') if cat=='分支与筛选' else ('#5F567C','#417F83')
    scene['style']['palette'].update(primary=primary,secondary=accent,accent=accent)
    positions=_positions(kind,len(nodes),narrow)
    if sid=='sample_route' and not narrow:positions=[(20+i*35,55) for i in range(5)]
    if sid=='database_route':positions=[(35,23),(35,86),(90,53),(146,53),(146,98)]
    if sid=='rna_pipeline':positions=[(35,20),(35,57),(90,57),(145,57),(145,97)]
    for i,(description,(x,y)) in enumerate(zip(nodes,positions)):
        label,_,shape=description.partition('|');shape=shape or 'card'
        w=28 if sid=='sample_route' and not narrow else 38 if kind in ('纵向步骤','逐级漏斗') else 31 if kind=='时间轴' else 36
        if kind=='逐级漏斗':w=96-i*18
        h=18 if shape=='decision' else 13
        ww=max(21,w*sx) if narrow else w*sx;hh=max(11,h*min(sx,sy)) if narrow else h*sy
        scene['objects'].append(dict(id='step'+str(i),type='process',state='flow_'+shape,label=label.strip(),
            x=x*sx-ww/2,y=y*sy-hh/2,w=ww,h=hh,font_size_pt=8,fill=primary if i%2==0 else accent,
            evidence=scene['source_text']))
    for i,edge in enumerate(edges):
        a,b,*label=edge;r=dict(id='flowlink'+str(i),source='step'+str(a),target='step'+str(b),type='sequence',
            label=label[0] if label else '',evidence='Workflow sequence only, specified by this illustrative design; not a biological effect.')
        if kind=='双向切换':r.update(source_port='s' if a>b else 'n',target_port='s' if a>b else 'n',control={'x':(positions[a][0]+positions[b][0])/2*sx,'y':(83 if a>b else 25)*sy})
        if kind=='闭环迭代':r.update(source_port=('e','s','w','n')[i],target_port=('w','n','e','s')[i])
        if kind=='外围反馈' and a==5:r.update(source_port='n',target_port='w',control={'x':12*sx,'y':15*sy})
        scene['relations'].append(r)
    # Lane backgrounds are editable context objects and cannot invent relationships.
    if kind in ('双泳道','三泳道','分阶段面板'):
        count=3 if kind=='三泳道' else 2
        names=['Clinical','Laboratory','Analysis'] if count==3 else ['Bench','Analysis'] if kind=='双泳道' else ['Discovery','Validation']
        for i in range(count):
            y=(8+i*(104/count))*sy
            scene['objects'].insert(i,dict(id='lane'+str(i),type='process',state='flow_lane',role='context',label=names[i],
                x=5*sx,y=y,w=170*sx,h=(104/count-3)*sy,font_size_pt=8,evidence=scene['source_text']))
    scene['requirements']={'objects':[o['id'] for o in scene['objects']],'relations':[r['id'] for r in scene['relations']]}
    return normalize_scene(_refine_flow(scene,sid,width_mm,height_mm))
