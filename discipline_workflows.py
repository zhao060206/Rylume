"""Distinct editable research workflows; examples, never asserted protocols or results."""
WORKFLOWS=[
 ('reaction_screen','chemistry','反应筛选与复核','平行分组',['底物与条件|input','条件 A','条件 B','产物分析 A','产物分析 B','条件复核|document'],[(0,1),(0,2),(1,3),(2,4),(3,5),(4,5)]),
 ('spectrum_assignment','chemistry','光谱采集与归属','横向步骤',['样品制备|input','光谱采集','背景校正','峰归属','结构核对|document'],[(0,1),(1,2),(2,3),(3,4)]),
 ('sensor_calibration','physics','传感器标定与检验','分支决策',['参考输入|input','采集响应','标定拟合','误差合格？|decision','独立检验|document','调整设置'],[(0,1),(1,2),(2,3),(3,4,'合格'),(3,5,'不合格'),(5,1)]),
 ('optical_measurement','physics','光学测量与拟合','多路汇合',['光源设置','样品准备','探测器校准','测量','模型拟合|document'],[(0,3),(1,3),(2,3),(3,4)]),
 ('materials_cycle','materials','制备—表征—性能迭代','闭环迭代',['设计成分','制备样品','结构表征','性能评价'],[(0,1),(1,2),(2,3),(3,0,'修订设计')]),
 ('materials_compare','materials','材料批次与性能对照','平行分组',['制备条件|input','批次 A','批次 B','结构表征 A','结构表征 B','性能比较|document'],[(0,1),(0,2),(1,3),(2,4),(3,5),(4,5)]),
 ('engineering_verification','engineering','仿真与台架交叉验证','上下配对',['设计参数','试验条件','仿真结果','台架结果','误差分析','设计复核'],[(0,2),(1,3),(2,4),(3,4),(4,5)]),
 ('failure_analysis','engineering','故障定位与复测','分支决策',['异常记录|input','故障假设','隔离试验','定位成功？|decision','修复复测|document','修订假设'],[(0,1),(1,2),(2,3),(3,4,'是'),(3,5,'否'),(5,1)]),
 ('environment_sources','earth-environment','多源环境数据融合','多路汇合',['现场采样','遥感观测','历史记录|database','时空匹配','不确定性评估|document'],[(0,3),(1,3),(2,3),(3,4)]),
 ('water_monitoring','earth-environment','水样采集与质控','分支决策',['采样设计|input','现场采样','样品分析','质控合格？|decision','结果解释|document','复采或复测'],[(0,1),(1,2),(2,3),(3,4,'合格'),(3,5,'不合格'),(5,1)]),
 ('model_evaluation','computing-math','训练、验证与独立测试','横向步骤',['数据划分|database','训练集拟合','验证集调参','冻结模型','独立测试|document'],[(0,1),(1,2),(2,3),(3,4)]),
 ('algorithm_benchmark','computing-math','算法基准与误差归因','平行分组',['统一数据|database','基线算法','候选算法','基线指标','候选指标','误差分析|document'],[(0,1),(0,2),(1,3),(2,4),(3,5),(4,5)]),
 ('cohort_followup','medicine','队列入组与随访','横向步骤',['纳排标准|input','知情同意','基线资料','随访记录','结局分析|document'],[(0,1),(1,2),(2,3),(3,4)]),
 ('diagnostic_validation','medicine','诊断方法与参考标准对照','上下配对',['待评价样本','参考标准','待评价方法','参考结果','方法结果','一致性分析'],[(0,2),(0,1),(1,3),(2,4),(3,5),(4,5)]),
]

def domain_for(sid):
    return next((row[1] for row in WORKFLOWS if row[0]==sid),'')

def counts():
    from collections import Counter
    return dict(Counter(row[1] for row in WORKFLOWS))
