"""Original scientific storyboards, built from editable objects, not paper images.

Each storyboard describes a particular mechanism or experimental sequence. The
illustrations are teaching schematics, never representations of measured data.
"""
from __future__ import annotations
from scene_document import empty_scene, normalize_scene

# Distinct subjects AND reading structures. These are not palette variants.
STORYBOARDS = [
 ('mapk_branch','EGFR 双分支 · MAPK / AKT','信号与反馈','pathway','branch'),
 ('sting_traffic','cGAS–STING · 细胞器转运','信号与反馈','pathway','organelle'),
 ('nfkb_release','NF-κB · 抑制解除与入核','信号与反馈','pathway','release'),
 ('notch_contact','Notch · 邻接细胞界面','细胞接触','network','contact'),
 ('wnt_switch','Wnt · 开关状态对照','状态对照','pathway','comparison'),
 ('socs_feedback','JAK–STAT · SOCS 负反馈','信号与反馈','pathway','feedback'),
 ('checkpoint_contact','PD-1 / PD-L1 · 免疫接触面','细胞接触','network','contact'),
 ('car_t_contact','CAR-T · 靶向识别与杀伤','细胞接触','network','contact'),
 ('antigen_synapse','抗原呈递 · 双信号突触','细胞接触','network','contact'),
 ('autophagy_flux','自噬通量 · 包裹到降解','运输与递送','process','stages'),
 ('mitophagy','线粒体自噬 · 选择性清除','运输与递送','process','organelle'),
 ('secretory_route','分泌通路 · ER–Golgi–胞外','运输与递送','process','organelle'),
 ('endosome_sorting','内吞分选 · 回收与降解','运输与递送','process','branch'),
 ('exosome_transfer','胞外囊泡 · 供体到受体','运输与递送','process','zoom'),
 ('lnp_delivery','LNP–mRNA · 内吞与逃逸','运输与递送','process','cutaway'),
 ('particle_assembly','纳米递送体 · 组分装配','结构与组装','assembly','assembly'),
 ('barrier_transport','血管屏障 · 跨层递送','组织与空间','process','section'),
 ('apoptosis_routes','细胞凋亡 · 两路汇聚','信号与反馈','pathway','convergence'),
 ('inflamed_barrier','血管内皮 · 稳态 / 炎症','状态对照','network','comparison'),
 ('wound_landscape','伤口修复 · 组织时空变化','组织与空间','process','stages'),
 ('tumor_ecology','肿瘤生态 · 血管与免疫区','组织与空间','network','landscape'),
 ('stem_fates','干细胞命运 · 分化树','组织与空间','network','tree'),
 ('organoid_culture','类器官培养 · 实验路线','实验与工具','process','workflow'),
 ('crispr_editing','CRISPR–Cas9 · 靶向与修复','实验与工具','process','branch'),
 ('single_cell','单细胞测序 · 样本到图谱','实验与工具','process','workflow'),
 ('infection_response','细菌感染 · 吞噬与呈递','细胞接触','network','zoom'),
 ('antibody_modes','抗体功能 · 中和与调理','状态对照','network','comparison'),
 ('translation_route','基因表达 · 从核到胞质','结构与组装','process','cutaway'),
]

def storyboard_catalog():
    return [dict(id='sb_'+sid,title=title,category=cat,family=family,example=sid,
                 description=DESCRIPTIONS[sid],canvas_mm=[180,120],new_scene_only=True,
                 featured=True,composition=composition) for sid,title,cat,family,composition in STORYBOARDS]

DESCRIPTIONS = {
 'mapk_branch':'同一受体分出 RAS–ERK 与 PI3K–AKT 两条路线，终点分区。',
 'sting_traffic':'ER 与 Golgi 作为空间锚点，突出 STING 转运和核内响应。',
 'nfkb_release':'把 IκB 降解和 NF-κB 核转运画成两个相邻事件。',
 'notch_contact':'发送细胞与接收细胞之间展示配体、受体与胞内片段。',
 'wnt_switch':'并列比较 Wnt 缺失和存在时 β-catenin 的不同去向。',
 'socs_feedback':'主轴与外围抑制回路分离，SOCS 反馈有明确终点。',
 'checkpoint_contact':'两侧细胞与中间膜受体形成放大的免疫检查点界面。',
 'car_t_contact':'从 CAR 识别到效应颗粒和靶细胞凋亡的跨细胞叙事。',
 'antigen_synapse':'TCR–pMHC 和 CD28–B7 两组接触清晰对应。',
 'autophagy_flux':'隔离膜、封闭自噬体、融合与降解显示真实状态变化。',
 'mitophagy':'受损线粒体、泛素标记、包裹与溶酶体阶段。',
 'secretory_route':'细胞器大图与运输囊泡串联，不用相同流程框代替形态。',
 'endosome_sorting':'中心早期内体分出质膜回收和溶酶体降解路线。',
 'exosome_transfer':'供体与受体全景，下方放大囊泡内容物与递送。',
 'lnp_delivery':'载体与细胞剖面并置，展示内体逃逸后的胞质翻译。',
 'particle_assembly':'脂质、RNA 和颗粒分层组装，组分逐一可编辑。',
 'barrier_transport':'血管腔、内皮屏障和组织层次的纵向剖面。',
 'apoptosis_routes':'外源性与线粒体路线汇聚于执行者 caspase。',
 'inflamed_barrier':'同尺度比较连续连接与炎症条件下的通透性变化。',
 'wound_landscape':'炎症、增殖、重塑三段组织情境和对应细胞。',
 'tumor_ecology':'肿瘤核心、血管和基质位置分明，连接免疫与供给。',
 'stem_fates':'共同起点分出三个示意谱系，不含虚构定量结果。',
 'organoid_culture':'取材、分离、基质包埋、培养与表型检查。',
 'crispr_editing':'递送与靶向后分出 NHEJ / 模板依赖修复。',
 'single_cell':'解离、单细胞捕获、建库测序和细胞注释。',
 'infection_response':'吞噬细胞与病原体全景，局部展示吞噬溶酶体。',
 'antibody_modes':'两个功能面板对比阻断结合与 Fc 介导吞噬。',
 'translation_route':'核内 DNA 与转录、核输出、胞质翻译的空间分工。',
}

class Board:
    def __init__(self,sid,width,height):
        meta=next(x for x in STORYBOARDS if x[0]==sid)
        self.scene=empty_scene(meta[1],width_mm=width,height_mm=height)
        self.scene['layout']=meta[3];self.sid=sid;self.narrow=width<110
        themes={
          '信号与反馈':('marine','#395A75','#459B99','#DC8A5A'),
          '细胞接触':('rose','#9A6172','#548A8F','#C39959'),
          '状态对照':('violet','#74629E','#539995','#CE9654'),
          '运输与递送':('cobalt','#3D6EAC','#71999E','#C18A39'),
          '结构与组装':('berry','#8A557F','#8B8EAC','#BE9D58'),
          '组织与空间':('forest','#376B59','#8C9D78','#B7664C'),
          '实验与工具':('earth','#91684C','#7A8D64','#AB6474')}
        theme,p,s,a=themes[meta[2]]
        self.scene['style'].update(colorway=theme,palette=dict(primary=p,secondary=s,accent=a))
        self.sx=width/180;self.sy=height/120
        self.scene['provenance']={'method':'original-scientific-storyboard','example':sid,
          'reference_rights':'Original composition; artwork credits accompany exports. No publication figure is embedded.'}
        self.brief=[]
    def node(self,oid,typ,label,x,y,w=20,h=15,art=None,role='entity',**kw):
        # Preserve artwork aspect ratio, also on a single-column page.
        scale=min(self.sx,self.sy)
        ww,hh=w*scale,h*scale
        if typ=='text':ww=max(ww,24 if role=='annotation' else 12);hh=1
        o=dict(id=oid,type=typ,label=label,x=x*self.sx-ww/2,y=y*self.sy-hh/2,
               w=ww,h=hh,role=role,font_size_pt=8,**kw)
        if art:
            from scientific_library import library
            if art not in library():raise ValueError('Missing art '+art)
            o['asset_id']=art
        self.scene['objects'].append(o);return o
    def edge(self,a,b,typ='sequence',label='',**kw):
        self.scene['relations'].append(dict(id='r'+str(len(self.scene['relations'])+1),source=a,target=b,type=typ,label=label,**kw))
    def heading(self,oid,label,x,y):self.node(oid,'text',label,x,y,55,1,role='annotation')
    def cell(self,oid,label,x,y,w=58,h=60,art=None):
        if art in ('bio_emptycell_oval','bio_emptycell_half_1'):art=None
        return self.node(oid,'cell',label,x,y,w,h,art=art,role='context',state='cell_context')
    def finish(self,brief):
        # Explicit morphology: a phagosome is not a spiked virus, a lysosome is
        # not an exocytic omega pore, and an LNP has no exosome tetraspanins.
        for o in self.scene['objects']:
            label=o['label'].lower()
            if 'autophagosome' in label or 'mitophagosome' in label:o['state']='autophagosome'
            elif o['type']=='pathogen' and ('bacter' in label or self.sid=='antibody_modes' and o['id']=='target'):
                o['state']='bacterium'
            elif 'autolysosome' in label:o['state']='autolysosome'
            elif 'phagolysosome' in label:o['state']='phagolysosome'
            elif 'phagosome' in label:o['state']='phagosome'
            elif 'lysosom' in label:o['state']='lysosome'
            elif 'endosom' in label:o['state']='endosome'
            elif 'organoid culture' in label:o['state']='organoid'
            elif 'lipid nanoparticle' in label or 'lnp' in label or 'rna–lipid' in label:o['state']='lnp'
        self.scene['source_text']=brief+' Simplified teaching schematic; omitted intermediates are not implied to be direct interactions. No experimental data are shown.'
        self.scene['requirements']={'objects':[o['id'] for o in self.scene['objects']],
                                    'relations':[r['id'] for r in self.scene['relations']]}
        for o in self.scene['objects']+self.scene['relations']:o['evidence']=brief[:1000]
        scene=normalize_scene(self.scene)
        # Labels are measured at their final physical 8pt size, never shrunk.
        from scene_render import repair_geometry
        return repair_geometry(scene,passes=2)

def _steps(b,items,links=True):
    """A large artwork row with a second narrative row, or a portrait column."""
    n=len(items)
    for i,item in enumerate(items):
        oid,typ,label,art=item
        if b.narrow:x,y=90,16+(88*i/max(1,n-1));w,h=42,28
        else:
            x=22+136*i/max(1,n-1);y=53 if i%2==0 else 72;w,h=29,28
        b.node(oid,typ,label,x,y,w,h,art=art)
        if not b.narrow:b.heading('step'+str(i),f'{i+1:02d}',x,25)
        if links and i:b.edge(items[i-1][0],oid)

def make_storyboard(sid,*,width_mm=180,height_mm=120):
    b=Board(sid,width_mm,height_mm);N=b.node;E=b.edge;H=b.heading
    if sid=='mapk_branch':
        # Explicit substrate/product: PI3K is a catalyst, not the substrate.
        H('extracellular','Extracellular',29,8)
        N('mem','membrane','',90,27,166,5,role='context',fill='#9AAAB4')
        N('egf','ligand','EGF',88,10,12,7,label_dx=-11,label_dy=-4);N('egfr','receptor_dimer','EGFR',88,27,16,19)
        H('arm_mapk','a   RAS–MAPK',35,43);H('arm_akt','b   PI3K–AKT',136,43)
        for oid,typ,label,x,y in [('ras','protein','RAS–GTP',32,58),('raf','kinase','RAF',32,80),('mek','kinase','MEK',67,80),('erk','kinase','ERK',67,102),('pi3k','kinase','PI3K',114,62)]:N(oid,typ,label,x,y,17,10)
        N('pip2','lipid','PIP2',126,32,10,9,state='bisphosphate',fill='#AD885D')
        N('pip3','lipid','PIP3',158,32,10,9,state='trisphosphate',fill='#B16B51')
        N('akt','kinase','AKT',154,83,18,11,fill='#B16B51')
        E('egf','egfr','binds');E('egfr','ras','activates',indirect=True,control={'x':32*b.sx,'y':30*b.sy})
        E('ras','raf','activates');E('raf','mek','activates');E('mek','erk','activates')
        E('egfr','pi3k','activates',indirect=True);E('pip2','pip3','converts','PI3K')
        E('pi3k','pip2','associates',source_port='n',target_port='s')
        E('pip3','akt','binds','recruitment',source_port='e',target_port='e',control={'x':175*b.sx,'y':62*b.sy})
        if b.narrow:
            # Authored single-column arrangement: keep physical text size and
            # move the branches, rather than stretching a wide composition.
            positions={'mem':(45,31,82,4),'egf':(43,12,10,7),'egfr':(43,31,13,19),
                'ras':(19,75,14,10),'raf':(19,100,14,10),'mek':(19,126,14,10),'erk':(48,126,14,10),
                'pi3k':(59,77,14,10),'pip2':(61,37,8,10),'pip3':(79,37,8,10),'akt':(76,109,14,10),
                'extracellular':(20,7,28,1),'arm_mapk':(20,54,28,1),'arm_akt':(75,55,22,1)}
            for o in b.scene['objects']:
                x,y,w,h=positions[o['id']];o.update(x=x-w/2,y=y-h/2,w=w,h=h)
                if o['id']=='arm_mapk':o['label']='a   MAPK'
                if o['id']=='arm_akt':o['label']='b   AKT'
            for r in b.scene['relations']:
                if r['target']=='ras':r['control']={'x':16,'y':42}
                if r['source']=='pip3':r['control']={'x':88,'y':80}
        brief='EGF binds and activates EGFR. Through omitted adaptors EGFR activates RAS and PI3K. RAS activates RAF, RAF activates MEK, and MEK activates ERK. PI3K catalyses conversion of the explicit substrate PIP2 into PIP3. PIP3 recruits AKT; recruitment does not imply full AKT activation. PDK1, mTORC2 and downstream effectors are omitted.'
    elif sid=='sting_traffic':
        N('er','er','ER',30,56,43,33,art='bio_endoplasmatic_reticulum_rough',role='context');N('golgi','golgi','Golgi',107,50,40,32,art='bio_golgi_2d_1',role='context')
        N('dna','dna','Cytosolic DNA',25,18,28,9);N('cgas','protein','cGAS',67,18,18,11);N('cgamp','ligand','cGAMP',67,49,14,9);N('sting','protein','STING · ER',35,55,19,11);N('gsting','protein','STING · Golgi',107,50,22,11,entity_id='sting');N('tbk','kinase','TBK1',147,52,18,11);N('irf','tf','IRF3',146,85,18,12);N('genes','dna','IFN genes',89,98,30,9)
        N('substrates','ligand','ATP + GTP',107,15,19,9)
        E('dna','cgas','binds');E('substrates','cgamp','converts','cGAS');E('cgas','cgamp','associates','catalysis');E('cgamp','sting','binds');E('sting','gsting','transports');E('gsting','tbk','activates');E('tbk','irf','activates');E('irf','genes','activates',indirect=True)
        brief='Cytosolic DNA activates cGAS to synthesize cGAMP. cGAMP binds STING. Activated STING traffics from ER to Golgi and recruits TBK1. TBK1 phosphorylates IRF3, which drives interferon gene expression after nuclear import (not detailed).'
    elif sid=='nfkb_release':
        b.cell('cell','Cytoplasm',66,62,111,81);N('nuc','nucleus','Nucleus',145,75,52,57,role='context')
        N('stim','ligand','Inflammatory signal',29,15,15,9);N('ikk','kinase','IKK',38,46,21,13);N('ikb','protein','IκB',75,42,18,11);N('nfkb','tf','NF-κB',74,72,21,14);N('deg','process','IκB degradation',104,23,30,12);N('nfn','tf','Nuclear NF-κB',144,65,22,14,entity_id='nfkb');N('genes','dna','Target genes',144,91,27,9)
        E('stim','ikk','activates',indirect=True);E('ikk','ikb','activates','phosphorylation');E('ikb','deg','sequence','proteolysis');E('ikb','nfkb','inhibits');E('nfkb','nfn','transports');E('nfn','genes','activates')
        brief='Inflammatory signalling activates IKK through omitted upstream components. IKK-dependent IκB phosphorylation promotes IκB degradation. Removal of inhibitory IκB permits NF-κB nuclear entry and target-gene transcription.'
    elif sid in ('notch_contact','checkpoint_contact','car_t_contact','antigen_synapse'):
        b.cell('left_cell','Sender' if sid=='notch_contact' else 'T cell',31,54,57,67,art='bio_t_lymphocyte' if sid!='notch_contact' else 'bio_emptycell_oval')
        b.cell('right_cell','Receiver' if sid=='notch_contact' else 'APC' if sid=='antigen_synapse' else 'Target cell',150,54,57,67)
        H('interface','Cell contact interface',90,12)
        if sid=='notch_contact':
            N('dll','ligand','DLL / JAG',66,41,16,13);N('notch','receptor','Notch',108,41,14,23);N('nicd','protein','NICD',131,76,18,11);N('genes','dna','RBPJ targets',155,98,29,9)
            E('dll','notch','binds');E('notch','nicd','converts','cleavage');E('nicd','genes','activates',indirect=True)
            brief='Membrane-bound DLL/JAG on a sending cell binds Notch on a neighbouring cell. Proteolytic cleavage releases NICD; nuclear NICD associates with RBPJ to regulate transcription. Cleavage enzymes and nuclear import are omitted.'
        elif sid=='checkpoint_contact':
            N('pd1','receptor','PD-1',68,43,13,23);N('pdl1','ligand','PD-L1',109,43,14,18);N('shp','protein','SHP2',49,83,18,11);N('tcr','complex','TCR signalling',88,99,25,13);N('block','antibody','Blocking antibody',113,18,16,17,art='bio_antibody')
            E('pdl1','pd1','binds');E('pd1','shp','associates');E('shp','tcr','inhibits');E('block','pdl1','inhibits')
            brief='Tumour/APC PD-L1 engages T-cell PD-1. PD-1 recruits phosphatases including SHP2 that attenuate TCR/CD28 signalling. A PD-L1-blocking antibody is shown as a therapeutic intervention, not as an endogenous component.'
        elif sid=='car_t_contact':
            N('car','receptor','CAR',68,42,14,24);N('antigen','ligand','Target antigen',111,42,16,12);N('gran','vesicle','Cytotoxic granules',62,84,23,22);N('death','process','Target apoptosis',137,93,28,16)
            E('antigen','car','binds');E('car','gran','activates',indirect=True);E('gran','death','activates','perforin / granzymes',indirect=True)
            brief='A CAR recognises its target antigen on another cell. CAR signalling promotes cytotoxic granule release. Perforin/granzyme-mediated processes can induce target-cell apoptosis; intermediate steps are omitted.'
        else:
            N('tcr','receptor','TCR',66,35,13,20);N('pmhc','complex','Peptide–MHC',110,35,23,14);N('cd28','receptor','CD28',66,76,13,20);N('b7','ligand','B7',110,76,14,11);N('activation','process','T-cell activation',29,100,27,13)
            E('pmhc','tcr','binds');E('b7','cd28','binds');E('tcr','activation','activates',indirect=True);E('cd28','activation','activates','costimulation',indirect=True)
            # Matched cutaways put both receptor pairs at cell boundaries.
            # A complete, detailed T cell next to an empty APC was visually
            # unbalanced and left all membrane proteins floating in the gap.
            for o in b.scene['objects']:
                if o['id'] in ('left_cell','right_cell'):
                    left=o['id']=='left_cell';o.pop('asset_id',None)
                    o.update(state='contact_left' if left else 'contact_right',
                        x=(5 if left else 113)*b.sx,y=22*b.sy,w=62*b.sx,h=84*b.sy,
                        label_dx=0,label_dy=-82*b.sy,fill='#5C8299' if left else '#7F9584')
                if o['id'] in ('tcr','cd28'):o['rotation']=90
                if o['id']=='activation':o.update(x=15*b.sx,y=83*b.sy,w=27*min(b.sx,b.sy),h=12*min(b.sx,b.sy))
            for r in b.scene['relations']:
                if r['source']=='tcr':r['control']={'x':28*b.sx,'y':50*b.sy}
                if r['source']=='cd28':r['control']={'x':48*b.sx,'y':94*b.sy}
            brief='An antigen-presenting cell displays peptide–MHC to a cognate TCR. B7 on the APC engages CD28 on the T cell. Together antigen recognition and costimulation support naive T-cell activation; this is a simplified two-signal model.'
    elif sid in ('autophagy_flux','mitophagy','secretory_route','organoid_culture','single_cell'):
        specs={
          'autophagy_flux': [('cargo','complex','Cytoplasmic cargo',None),('phago','vesicle','Phagophore',None),('auto','mvb','Autophagosome',None),('lyso','vesicle_fusion','Autolysosome',None)],
          'mitophagy':[('mito','mitochondrion','Damaged mitochondrion','bio_mitochondrium_1'),('tag','protein','Ubiquitin-tagged cargo',None),('auto','mvb','Mitophagosome',None),('lyso','vesicle_fusion','Lysosomal clearance',None)],
          'secretory_route':[('er','er','Endoplasmic reticulum','bio_endoplasmatic_reticulum_rough'),('golgi','golgi','Golgi','bio_golgi_2d_1'),('ves','vesicle','Secretory vesicle',None),('fusion','vesicle_fusion','Secretion',None)],
          'organoid_culture':[('sample','tissue','Tissue isolation',None),('cells','cell','Cell preparation','bio_cell_complete'),('matrix','vesicle','Matrix embedding',None),('culture','complex','Organoid culture',None),('assay','process','Phenotype assays',None)],
          'single_cell':[('tissue','tissue','Tissue dissociation',None),('cell','cell','Single-cell capture','bio_cell_complete'),('rna','mrna','Barcoded cDNA',None),('seq','process','Library / sequencing',None),('map','process','Cell annotation',None)]}
        _steps(b,specs[sid])
        if sid=='autophagy_flux':
            # State-specific native glyphs: open membrane, closed double membrane, fused lysosome.
            next(o for o in b.scene['objects'] if o['id']=='phago')['state']='phagophore'
            next(o for o in b.scene['objects'] if o['id']=='auto')['state']='autophagosome'
            # Fusion has two visible inputs, rather than silently turning an
            # autophagosome into a lysosome. Stage labels describe the event.
            N('lysosome','vesicle','Lysosome',142,40 if not b.narrow else 82,21,21,state='lysosome',fill='#AE7C67')
            E('lysosome','lyso','sequence','fusion')
            for r in b.scene['relations']:
                if r['target']=='lyso':r['label']='fusion' if r['source']=='auto' else r['label']
            if not b.narrow:
                for oid,x,y in [('cargo',22,58),('phago',65,58),('auto',108,58),('lyso',154,75)]:
                    o=next(o for o in b.scene['objects'] if o['id']==oid);o.update(x=x*b.sx-o['w']/2,y=y*b.sy-o['h']/2)
                for o in b.scene['objects']:
                    if o['id'].startswith('step'):o['label']=['Cargo','Sequestration','Closure','Degradation'][int(o['id'][4:])]
            brief='Autophagy sequesters cytoplasmic cargo in an open phagophore, which closes into a double-membrane autophagosome. Fusion with lysosomes creates an autolysosome for degradation. Arrows denote stages, not direct molecular activation.'
        elif sid=='mitophagy':brief='Damaged mitochondria may be selectively marked for autophagic clearance. The illustrated ubiquitin-dependent route packages marked cargo in a mitophagosome followed by lysosomal degradation. Ubiquitin-independent mitophagy routes are omitted.'
        elif sid=='secretory_route':brief='Conventional secretory cargo passes from ER to Golgi, is sorted into secretory vesicles and released by plasma-membrane fusion. Arrows summarise transport stages; transport machinery is omitted.'
        elif sid=='organoid_culture':brief='Illustrative organoid workflow: isolate tissue, prepare cells or fragments, embed in extracellular matrix, culture under tissue-specific conditions, and assess phenotype. Culture conditions and protocol-specific timing must be supplied by the author.'
        else:brief='Illustrative single-cell RNA sequencing workflow: tissue dissociation, single-cell capture, barcoded cDNA generation, library preparation and sequencing, followed by computational cell annotation. No simulated clustering plot or quantitative result is shown.'
    elif sid=='endosome_sorting':
        b.cell('cell','Endocytic sorting',90,61,157,96)
        N('surface','receptor','Surface receptor',26,28,14,22);N('early','vesicle','Early endosome',83,54,29,28);N('recycle','vesicle','Recycling endosome',141,26,24,23);N('late','mvb','Late endosome',135,86,27,26);N('lyso','vesicle_fusion','Lysosome',57,98,25,22)
        E('surface','early','transports');E('early','recycle','transports');E('recycle','surface','transports',label='recycling',control={'x':90*b.sx,'y':4*b.sy});E('early','late','sequence','maturation');E('late','lyso','transports',label='cargo degradation')
        brief='Endocytosed receptors reach early endosomes. Cargo can return via recycling endosomes to the surface or progress through late endosomes to lysosomes. Individual receptor sorting decisions are context-dependent.'
    elif sid in ('lnp_delivery','exosome_transfer','infection_response'):
        b.cell('recipient','Recipient cell' if sid!='infection_response' else 'Phagocyte',127,57,91,87,art='bio_emptycell_half_1')
        if sid=='lnp_delivery':
            N('lnp','vesicle','Lipid nanoparticle',26,27,32,30);N('rna','mrna','mRNA cargo',26,75,28,9,art='bio_rna');N('endo','vesicle','Endosome',100,33,28,27);N('free','mrna','Cytosolic mRNA',144,64,25,9,art='bio_rna');N('protein','protein','Translated protein',133,96,23,14)
            E('rna','lnp','associates');E('lnp','endo','transports',label='endocytosis');E('endo','free','transports',label='cargo escape');E('free','protein','sequence','translation')
            brief='An LNP carries mRNA into an endosome by endocytosis. A fraction of cargo escapes to the cytosol, where mRNA is translated. The schematic does not imply that all internalised particles escape or reach the nucleus.'
        elif sid=='exosome_transfer':
            b.cell('donor','Donor cell',31,34,45,39,art='bio_cell_complete');N('mvb','mvb','MVB',55,79,27,27);N('ev','vesicle','Extracellular vesicle',93,93,21,21);N('uptake','vesicle','Uptake',132,39,24,24);N('cargo','mrna','Delivered cargo',141,80,25,8,art='bio_rna')
            E('donor','mvb');E('mvb','ev','sequence',label='release');E('ev','uptake','transports');E('uptake','cargo','transports',indirect=True)
            brief='A donor-cell MVB can fuse with the plasma membrane and release intraluminal vesicles as exosomes. Recipient-cell uptake is shown. Functional cytosolic cargo delivery is a possible outcome dependent on context, not a guaranteed property of all extracellular vesicles.'
        else:
            N('bacteria','pathogen','Bacterium',26,27,27,23);N('phago','vesicle','Phagosome',98,31,27,26);N('lyso','vesicle_fusion','Phagolysosome',142,64,28,26);N('antigen','complex','Peptide–MHC II',113,98,27,14)
            E('bacteria','phago',label='engulfment');E('phago','lyso',label='fusion');E('lyso','antigen','sequence','processing',indirect=True)
            brief='A professional phagocyte engulfs bacteria into a phagosome. Phagosome–lysosome fusion supports microbial processing. In antigen-presenting cells, peptides may be loaded on MHC II for display; MHC loading compartments are not detailed.'
    elif sid=='particle_assembly':
        N('lipid','lipid','Ionizable lipid',25,30,16,13);N('helper','lipid','Helper lipids',25,77,18,14);N('rna','mrna','mRNA',76,18,31,10,art='bio_rna');N('core','vesicle','RNA–lipid assembly',83,65,35,34);N('lnp','vesicle','Formulated LNP',145,60,39,38);N('peg','protein','PEG–lipid',145,98,24,12)
        E('lipid','core','associates');E('helper','core','associates');E('rna','core','associates');E('core','lnp','converts','formulation');E('peg','lnp','associates')
        brief='Conceptual LNP formulation: ionizable lipid, helper lipids, mRNA and PEG–lipid contribute to a formulated particle. Geometry is schematic, not an atomic structure, stoichiometric model or universal core–shell architecture.'
    elif sid in ('wnt_switch','inflamed_barrier','antibody_modes'):
        H('condition_a','a   '+('Wnt absent' if sid=='wnt_switch' else 'Homeostasis' if sid=='inflamed_barrier' else 'Neutralisation'),43,10)
        H('condition_b','b   '+('Wnt present' if sid=='wnt_switch' else 'Inflammation' if sid=='inflamed_barrier' else 'Opsonisation'),135,10)
        if sid=='wnt_switch':
            for p,x in [('a',43),('b',135)]:
                N(p+'mem','membrane','',x,30,72,6,role='context');N(p+'beta','protein','β-catenin',x,57,25,14);N(p+'effect','process','Degradation' if p=='a' else 'TCF / LEF transcription',x,96,32,17)
                E(p+'beta',p+'effect','transports' if p=='a' else 'activates',indirect=p=='b')
            N('wnt','ligand','Wnt',135,20,13,9);N('fzd','receptor','FZD / LRP',135,32,16,18);E('wnt','fzd','binds');E('fzd','bbeta','activates','stabilisation',indirect=True)
            brief='Without Wnt, the destruction complex promotes β-catenin degradation. Wnt binding to Frizzled/LRP inhibits destruction-complex activity, allowing β-catenin accumulation and nuclear TCF/LEF-dependent transcription. The destruction complex and nuclear import are omitted.'
        elif sid=='inflamed_barrier':
            for p,x in [('a',43),('b',135)]:
                N(p+'tissue','tissue','Tissue',x,90,65,26,role='context');N(p+'endo','endothelial','Continuous junctions' if p=='a' else 'Altered junctions',x,45,60,16,state='intact' if p=='a' else 'disrupted');N(p+'cargo','ligand','Circulating solute',x,22,13,9)
            N('leak','ligand','Increased permeability',135,78,13,9);E('bcargo','leak',label='context-dependent')
            brief='Conceptual endothelial barrier comparison: a continuous junctional barrier at homeostasis versus altered junctions and increased permeability under some inflammatory conditions. These are illustrative states, not quantitative measurements or a claim that every inflammatory setting has the same phenotype.'
        else:
            N('virus','pathogen','Virus',43,35,27,25);N('ab','antibody','Neutralising antibody',43,72,23,25,art='bio_antibody');N('entry','receptor','Cell entry',43,101,15,17);E('ab','virus','binds');E('ab','entry','inhibits')
            N('target','pathogen','Antibody-coated target',135,33,25,23);N('fc','antibody','Fc recognition',135,68,23,25,art='bio_antibody');N('phag','immune_cell','Phagocyte',135,99,24,23,art='bio_macrophage');E('fc','target','binds');E('target','phag',label='Fc receptor-mediated',indirect=True)
            brief='Neutralising antibodies can block viral attachment or entry. Opsonising antibodies coat targets and support Fc-receptor-mediated uptake by phagocytes. These are different antibody functions; actual activity depends on epitope, isotype and cellular context.'
    elif sid in ('socs_feedback','apoptosis_routes','crispr_editing','stem_fates'):
        if sid=='socs_feedback':
            N('cytokine','ligand','Cytokine',25,20,15,10);N('receptor','receptor_dimer','Cytokine receptor',25,53,17,23);N('jak','kinase','JAK',66,54,19,13);N('stat','tf','STAT',108,54,20,14);N('dna','dna','SOCS transcription',146,83,30,9);N('socs','protein','SOCS',81,99,22,13)
            E('cytokine','receptor','binds');E('receptor','jak','activates');E('jak','stat','activates');E('stat','dna','activates',indirect=True);E('dna','socs','sequence','expression');E('socs','jak','inhibits')
            brief='Cytokine receptor signalling activates JAK and STAT. Activated STAT drives SOCS gene expression after dimerisation and nuclear import (omitted). SOCS proteins provide negative feedback on receptor-associated JAK signalling; SOCS-family mechanisms vary.'
        elif sid=='apoptosis_routes':
            N('death','receptor','Death receptor',33,24,17,22);N('mito','mitochondrion','Mitochondrial route',144,25,33,23,art='bio_mitochondrium_1');N('c8','protein','Caspase-8',35,65,24,13);N('c9','protein','Caspase-9',143,65,24,13);N('c3','protein','Caspase-3 / 7',90,87,27,13);N('apo','process','Apoptotic execution',90,106,32,10)
            E('death','c8','activates',indirect=True);E('mito','c9','activates',indirect=True);E('c8','c3','activates');E('c9','c3','activates');E('c3','apo','activates')
            brief='Extrinsic death-receptor signalling can activate caspase-8 through a death-inducing complex. Intrinsic mitochondrial cytochrome-c release supports apoptosome-mediated caspase-9 activation. Both routes can activate executioner caspases-3/7. Bid-mediated cross-talk and regulatory proteins are omitted.'
        elif sid=='crispr_editing':
            N('guide','mrna','Guide RNA',28,24,27,9,art='bio_rna');N('cas','protein','Cas9',28,65,24,15);N('rnp','complex','Cas9–gRNA',83,43,28,19);N('target','dna','Target DNA',138,30,32,11);N('cut','dna','Double-strand break',133,67,32,11);N('nhej','process','NHEJ · indels',89,101,29,12);N('hdr','process','Template repair',152,101,30,12)
            E('guide','rnp','binds');E('cas','rnp','binds');E('rnp','target','binds');E('target','cut','converts');E('cut','nhej','converts');E('cut','hdr','converts','donor template')
            brief='Cas9 and a guide RNA form a ribonucleoprotein that recognises a complementary target adjacent to a suitable PAM and introduces a DNA double-strand break. Repair may occur by NHEJ, often producing indels, or template-dependent repair with a donor. Efficiencies and outcomes are not guaranteed.'
        else:
            N('stem','stem_cell','Pluripotent cell',90,22,27,24);N('ecto','cell','Ectoderm',29,65,26,23);N('meso','cell','Mesoderm',90,65,26,23);N('endo','cell','Endoderm',151,65,26,23)
            for oid in ('ecto','meso','endo'):E('stem',oid,'converts')
            H('e1','Neural lineages',29,103);H('e2','Muscle / blood',90,103);H('e3','Gut / liver',151,103)
            brief='Pluripotent cells can differentiate into ectoderm, mesoderm and endoderm under appropriate developmental conditions. Representative derivatives are neural lineages, muscle/blood, and gut/liver. This is a conceptual lineage overview, not a culture recipe or fate-probability measurement.'
    elif sid=='barrier_transport':
        H('lumen','Vascular lumen',34,12);H('interstitial','Interstitial tissue',130,103)
        N('barrier','membrane','Endothelial barrier',90,55,167,9,role='context');N('endo1','endothelial','Endothelium',45,55,48,16,role='context');N('endo2','endothelial','',133,55,48,16,role='context');N('particle','vesicle','Circulating carrier',40,27,23,22);N('uptake','vesicle','Endocytic vesicle',91,55,19,18);N('release','vesicle','Tissue delivery',135,86,23,22)
        E('particle','uptake','transports');E('uptake','release','transports',label='transcytosis',indirect=True)
        brief='Conceptual transcytosis route for a carrier: uptake at the luminal endothelial surface, intracellular vesicular transport and abluminal release. This template does not claim universal barrier crossing or exclude paracellular and other routes.'
    elif sid=='wound_landscape':
        for i,(title,oid,typ,label,art) in enumerate([('Inflammation','immune','immune_cell','Macrophage','bio_macrophage'),('Proliferation','fibro','fibroblast','Fibroblast','bio_fibroblast_4'),('Remodelling','matrix','collagen','Collagen',None)]):
            x=30+i*60;H('h'+str(i),title,x,16);N('t'+str(i),'tissue','',x,81,52,29,role='context');N(oid,typ,label,x,55,31,27,art=art)
        E('immune','fibro',label='phase progression',indirect=True);E('fibro','matrix',label='matrix remodelling',indirect=True)
        brief='Wound repair includes overlapping inflammatory, proliferative and remodelling phases. Macrophages, fibroblasts and extracellular matrix are representative features. Arrows indicate temporal progression, not exclusive one-cell causal transitions. Haemostasis and many other participants are omitted.'
    elif sid=='tumor_ecology':
        N('tissue','tissue','Stroma',90,88,169,47,role='context');N('tumor','tumor_cell','Tumour',88,52,44,41);N('vessel','endothelial','Vascular supply',32,28,43,21);N('macro','immune_cell','Macrophage',37,83,29,28,art='bio_macrophage');N('tcell','immune_cell','CD8 T cell',146,30,27,26,art='bio_t_lymphocyte');N('caf','fibroblast','Fibroblast',143,88,35,23,art='bio_fibroblast_4')
        E('vessel','tumor','associates');E('tcell','tumor','inhibits','cytotoxicity',indirect=True);E('macro','tumor','associates');E('caf','tumor','associates','matrix / signals')
        brief='A spatial tumour microenvironment overview contains tumour cells, vascular endothelium, macrophages, CD8 T cells and fibroblasts. CD8-mediated killing is shown as an inhibitory effect. Macrophage and fibroblast contacts are associations because their functional direction is context-dependent.'
    elif sid=='translation_route':
        N('nucleus','nucleus','Nucleus',49,53,77,76,role='context');N('dna','dna','DNA',40,35,31,11,art='bio_dna_double_stranded_ribbon');N('nascent','mrna','Transcription',51,71,28,9,art='bio_rna');N('pore','nuclear_pore','Nuclear pore',89,64,9,16);N('rna','mrna','Cytoplasmic mRNA',133,44,29,9,art='bio_rna');N('rib','complex','Ribosome',139,80,29,23);N('protein','protein','Polypeptide',96,102,24,13)
        E('dna','nascent','sequence','transcription');E('nascent','pore','transports');E('pore','rna','transports',label='export');E('rna','rib','binds');E('rib','protein','associates','synthesis')
        brief='In a eukaryotic cell, DNA transcription occurs in the nucleus. Processed mRNA is exported through nuclear pores and translated by cytoplasmic ribosomes into polypeptides. RNA processing and protein maturation are omitted.'
    else:raise ValueError('Unknown storyboard '+sid)
    # A generic external RNA ribbon used here resembles double-stranded DNA
    # at these aspect ratios. Use our explicit single-strand native glyph.
    for o in b.scene['objects']:
        if o['type']=='mrna' and o.get('asset_id')=='bio_rna':o.pop('asset_id')
    return b.finish(brief)
