"""Purpose-first catalogue; compatible IDs are not counts of distinct designs."""
RECOMMENDED = (
 'sb_mapk_branch','sb_sting_traffic','sb_nfkb_release','sb_antigen_synapse',
 'sb_autophagy_flux','sb_endosome_sorting','sb_lnp_delivery','sb_socs_feedback',
 'flow_sample_route','flow_quality_gate','flow_treatment_arms','flow_bench_compute',
 'flow_clinical_timeline','flow_design_cycle',
)
VARIANTS = {
 'flow_vertical_protocol':'flow_sample_route','flow_rna_pipeline':'flow_sample_route',
 'flow_image_pipeline':'flow_sample_route','flow_milestone':'flow_sample_route',
 'flow_triangulation':'flow_omics_merge','flow_causal_test':'flow_treatment_arms',
 'flow_paired_readout':'flow_treatment_arms','flow_handoff_lanes':'flow_bench_compute',
}
DETAILS = {
 'sb_mapk_branch':('比较同一受体下游的两条分支',['EGF / EGFR','RAS–RAF–MEK–ERK','PIP2 → PIP3 与 PI3K','AKT 招募'],'省略衔接蛋白、PDK1 与 mTORC2；AKT 招募不等于完全激活。'),
 'sb_sting_traffic':('强调细胞器位置与分子转运',['胞质 DNA 与 cGAS','ATP + GTP → cGAMP','ER → Golgi 的 STING','TBK1 / IRF3'],'简化信号过程；IRF3 入核与各磷酸化中间态未逐一绘制。'),
 'sb_nfkb_release':('解释抑制解除与核转运',['IKK','IκB 降解','胞质 / 核内 NF-κB','靶基因'],'省略上游受体、泛素化及蛋白酶体细节；降解步骤不表示转运。'),
 'sb_antigen_synapse':('同时展示抗原识别与共刺激',['T 细胞与 APC','TCR–pMHC','CD28–B7','双信号激活'],'初始 T 细胞的简化双信号模型；不含细胞因子及抑制性受体。'),
 'sb_autophagy_flux':('展示膜结构随过程发生的变化',['开放隔离膜','双膜自噬体','溶酶体融合','自噬溶酶体'],'形态过程示意，不含实验测量；不能据此判断自噬通量增减。'),
 'sb_endosome_sorting':('同时表达回收与降解的去向',['表面受体','早期内体','回收内体','晚期内体 / 溶酶体'],'概念分选路线；具体受体的分选决定与调控需由作者补充。'),
 'sb_lnp_delivery':('说明载体递送与胞质表达',['LNP 与 mRNA','内吞','内体逃逸','胞质翻译'],'逃逸与功能递送并非必然；不含效率、粒径或核内递送结论。'),
 'sb_socs_feedback':('让负反馈有明确的抑制终点',['细胞因子受体','JAK / STAT','SOCS 表达','SOCS 抑制 JAK'],'省略 STAT 二聚化与入核；SOCS 家族的具体机制需要核对。'),
 'flow_sample_route':('把样本获取、实验测量与分析结果串成一条可追溯路线',['样本输入','提取与测量','分析','结果报告'],'五步路线骨架；需填写样本类型、方法、质控标准与结果载体，不表示完整实验方案。'),
 'flow_quality_gate':('突出质控通过、失败与返工的分流',['提取','质控判断','通过后建库与测序','失败后重新提取'],'通过与失败分支仅作设计示意；质控阈值、重复次数和终止条件需按实际实验填写。'),
 'flow_treatment_arms':('并排比较对照与处理，保留各组到读出的对应关系',['匹配样本','对照组 / 处理组','两组对应读出','汇合比较'],'不预设随机化、盲法、样本量或统计显著性；阻断与救援变体也不能自动证明因果。'),
 'flow_bench_compute':('分别组织湿实验与计算分析，并明确数据交接和返回验证',['实验准备与数据采集','分析导入、处理与解释','数据交接连线','解释结果返回实验验证'],'泳道区分工作类型，不表示严格的人员分工；需填写数据格式、处理方法和验证标准。'),
 'flow_clinical_timeline':('沿可编辑轴线安排干预、随访与终点采样',['基线','干预','随访','终点','时间轴与待填写日期'],'时间间距为示意；日期与时间单位必须由作者填写，不构成临床试验方案或疗效结论。'),
 'flow_design_cycle':('呈现实验假设、设计、执行、评估与修订的迭代闭环',['研究假设','实验设计','实验执行','结果评估','返回假设的修订线'],'闭环表示研究工作如何迭代，不是分子反馈机制；需说明每轮评估依据和停止条件。'),
}

def curate_catalog(items):
 for t in items:
  kind=t.get('template_kind')
  if kind=='workflow':
   t['library_group']='workflow'
   t.setdefault('usage','组织自己的研究步骤、分支或实验分组')
   t.setdefault('includes',[t['composition'],'可替换的步骤与连接'])
   t.setdefault('limitations','流程骨架，不是经过验证的实验方案；需填写真实方法、条件和时间。')
  elif t.get('new_scene_only'):
   t['library_group']='science';t['template_kind']='science'
   t.setdefault('usage',t['description']);t.setdefault('includes',[t['title'].split(' · ')[0]])
   t.setdefault('limitations','教学示意，未覆盖完整机制；使用前需按自己的研究内容核对。')
  else:
   t['library_group']='layout';t['template_kind']='layout'
   t['usage']='仅重新安排当前图中的对象'
   t['includes']=['保留对象身份','保留原有关系','改变位置']
   t['limitations']='排版预设不增加新的通路、分支或反馈。预览中的分子只是示例。'
   t['compatibility_only']=not t['id'].startswith('layout_')
  if t['id'] in DETAILS:t['usage'],t['includes'],t['limitations']=DETAILS[t['id']]
  t['recommended']=t['id'] in RECOMMENDED;t['featured']=t['recommended']
  t['draft']=t['library_group']=='science' and not t['recommended']
  t['variant_of']=VARIANTS.get(t['id'],'');t['search_terms']=' '.join(t.get('includes',[]))
 for t in items:t['variants']=[x['id'] for x in items if x.get('variant_of')==t['id']]
 return items
