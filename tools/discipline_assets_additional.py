"""Additional first-party vector symbols for the discipline resource packs.

The pack builder keeps geometry in Python so every symbol remains editable SVG,
has no external image dependency, and can be audited together with its label.
These are deliberately small, recognisable scientific glyphs rather than
renamed copies of the starter palette.
"""
from __future__ import annotations

from discipline_assets_extended import (
    INK, BLUE, PALE, TEAL, GOLD, RED, WHITE,
    tag, path, rect, circle, ellipse, line, polygon, text, arrow, dashed,
    chain, curve, dots, cylinder, screen, flame,
)


def axes(curve_body: str, xlab: str = "x", ylab: str = "y") -> str:
    return line(12, 86, 92, 86) + line(12, 86, 12, 10) + curve_body + text(xlab, 88, 97, 8) + text(ylab, 18, 18, 8)


def spectrum(peaks, color=BLUE) -> str:
    body = axes("")
    for x, h, c in peaks:
        body += line(x, 86, x, 86 - h, c, 3)
    return body


def molecule_ring(n=6, center=(50, 50), radius=27, fill=BLUE) -> str:
    cx, cy = center
    pts = [(cx + radius * __import__('math').cos(2 * __import__('math').pi * i / n),
            cy + radius * __import__('math').sin(2 * __import__('math').pi * i / n)) for i in range(n)]
    body = chain(pts + [pts[0]], INK, 2)
    body += ''.join(circle(x, y, 6, fill) for x, y in pts)
    return body


def flow_box(accent=BLUE, inner=TEAL) -> str:
    return rect(10, 17, 80, 68, PALE, 4) + arrow(8, 51, 31, 51, accent, 3, 7) + arrow(69, 51, 93, 51, inner, 3, 7) + path('M31 37 L50 37 L50 65 L69 65', stroke=INK, sw=3) + circle(50, 51, 8, GOLD)


def membrane(accent=BLUE) -> str:
    return rect(40, 9, 20, 82, PALE, 3) + ''.join(circle(50, y, 5, WHITE) for y in (22, 40, 58, 76)) + arrow(8, 31, 39, 31, accent, 2, 6) + arrow(61, 70, 92, 70, TEAL, 2, 6)


def cell_shape(fill=PALE) -> str:
    return path('M15 51 C15 26 31 12 52 14 C76 9 91 28 85 48 C95 70 73 91 51 84 C29 94 10 75 15 51 Z', fill=fill, stroke=INK, sw=2)


def chromosome() -> str:
    return path('M28 12 C70 24 30 38 72 50 C30 62 70 76 28 88', stroke=TEAL, sw=4) + path('M72 12 C30 24 70 38 28 50 C70 62 30 76 72 88', stroke=BLUE, sw=4) + ''.join(line(36 + (i % 2) * 28, 18 + i * 13, 64 - (i % 2) * 28, 18 + i * 13, GOLD, 2) for i in range(6))


def dna_ladder() -> str:
    return path('M25 10 C75 25 25 40 75 55 C25 70 75 85 25 94', stroke=TEAL, sw=4) + path('M75 10 C25 25 75 40 25 55 C75 70 25 85 75 94', stroke=BLUE, sw=4) + ''.join(line(31 if i % 2 else 69, 15 + i * 13, 69 if i % 2 else 31, 15 + i * 13, GOLD, 2) for i in range(7))


def circuit(kind='resistor') -> str:
    body = line(7, 50, 22, 50) + line(78, 50, 93, 50)
    if kind == 'resistor':
        body += path('M22 50 L30 37 L38 63 L46 37 L54 63 L62 37 L70 63 L78 50', stroke=RED, sw=3)
    elif kind == 'capacitor':
        body += line(43, 30, 43, 70, INK, 4) + line(57, 30, 57, 70, INK, 4)
    else:
        body += circle(50, 50, 22, PALE) + arrow(37, 50, 63, 50, TEAL, 3, 7)
    return body


def wave(kind='sine') -> str:
    if kind == 'packet':
        return axes(path('M15 76 C22 65 25 30 34 30 C43 30 48 75 58 75 C68 75 73 33 83 25', stroke=BLUE, sw=3))
    if kind == 'standing':
        return axes(path('M15 50 Q25 18 35 50 T55 50 T75 50 T92 50', stroke=TEAL, sw=3))
    return axes(path('M14 50 C25 20 36 80 48 50 S72 20 92 50', stroke=BLUE, sw=3))


def lattice(kind='square') -> str:
    if kind == 'hex':
        return molecule_ring(6, (50, 50), 25, BLUE) + molecule_ring(6, (50, 50), 12, TEAL)
    if kind == 'amorphous':
        return dots([(18,24),(37,17),(63,26),(82,20),(26,49),(49,43),(73,53),(17,76),(41,69),(66,80),(87,70)], 5, BLUE) + ''.join(line(x, y, x+14, y+8, TEAL, 1) for x, y in ((18,24),(37,17),(63,26),(26,49),(49,43),(73,53),(17,76)))
    return ''.join(line(x, 20, x, 80, BLUE, 1) + line(20, y, 80, y, BLUE, 1) for x in (20,40,60,80) for y in (20,40,60,80)) + dots([(20,20),(40,20),(60,20),(80,20),(20,40),(40,40),(60,40),(80,40),(20,60),(40,60),(60,60),(80,60),(20,80),(40,80),(60,80),(80,80)], 4, TEAL)


def machine(kind='gear') -> str:
    if kind == 'gear':
        return circle(34, 50, 22, PALE) + circle(34, 50, 8, GOLD) + ''.join(line(34, 50, 34 + 18 * __import__('math').cos(i * __import__('math').pi / 4), 50 + 18 * __import__('math').sin(i * __import__('math').pi / 4), TEAL, 3) for i in range(8)) + circle(69, 50, 14, BLUE) + circle(69, 50, 5, GOLD)
    if kind == 'bearing':
        return circle(50, 50, 35, 'none') + circle(50, 50, 23, 'none') + ''.join(circle(50 + 29 * __import__('math').cos(i * __import__('math').pi / 4), 50 + 29 * __import__('math').sin(i * __import__('math').pi / 4), 5, BLUE) for i in range(8)) + circle(50, 50, 10, GOLD)
    return rect(15, 28, 70, 44, PALE, 5) + line(28, 50, 72, 50, TEAL, 5) + circle(28, 50, 9, GOLD) + circle(72, 50, 9, BLUE)


def map_tile(kind='contour') -> str:
    body = rect(8, 11, 84, 78, PALE, 2)
    if kind == 'contour':
        return body + curve('M12 28 Q30 18 48 28 T88 24 M10 50 Q30 40 52 51 T90 46 M12 72 Q34 62 56 73 T89 69', BLUE, 3)
    if kind == 'raster':
        return body + ''.join(rect(14 + c * 15, 18 + r * 15, 14, 14, (BLUE, TEAL, GOLD, PALE)[(r + c) % 4], 0) for r in range(4) for c in range(5))
    return body + path('M12 70 L35 43 L52 57 L75 22 L89 70 Z', TEAL) + path('M15 70 L45 61 L63 70 L89 56', BLUE, 3)


def data_chart(kind='bars') -> str:
    if kind == 'roc':
        return axes(path('M14 84 C18 78 22 67 31 61 C43 53 57 42 72 32 C80 26 86 17 91 12', stroke=RED, sw=3) + path('M14 84 L91 12', stroke=BLUE, sw=1))
    if kind == 'matrix':
        return rect(17, 17, 66, 66, WHITE, 2) + ''.join(rect(20 + c*15, 20 + r*15, 12, 12, (BLUE, TEAL, GOLD, RED)[(r*3+c) % 4], 0) for r in range(4) for c in range(4))
    return axes(''.join(rect(22 + i*14, 84-h, 8, h, c, 1) for i, (h,c) in enumerate(((34,BLUE),(52,TEAL),(26,GOLD),(64,RED),(43,BLUE)))))


def clinical_curve(kind='dose') -> str:
    if kind == 'survival':
        return axes(path('M14 20 L30 20 L30 38 L45 38 L45 55 L63 55 L63 72 L91 72', stroke=BLUE, sw=3), 'time', 'survival')
    if kind == 'dose':
        return axes(path('M14 80 C35 80 37 78 47 70 C58 61 56 30 90 18', stroke=RED, sw=3), 'dose', 'response')
    return axes(path('M14 75 C23 31 36 65 45 38 S72 46 90 18', stroke=TEAL, sw=3), 'time', 'signal')


# Each tuple is (symbol key, Chinese label).  The English labels below are
# explicit so scientific abbreviations and compound terms remain stable.
ADDITIONAL_DEFINITIONS = {
    'chemistry': [
        'chem_thermometer:温度计','chem_solid_phase:固相反应','chem_liquid_liquid:液液萃取','chem_pcr_tube:PCR 反应管','chem_pcr_cycle:PCR 循环','chem_dna:DNA 双螺旋','chem_rna:RNA 链','chem_sds_page:SDS-PAGE','chem_tlc_plate:薄层色谱板','chem_uv_vis:紫外可见光谱','chem_ir_spectrum:红外光谱','chem_fume_hood:通风橱','chem_glovebox:手套箱','chem_gas_flow:气体流量','chem_pressure_reactor:压力反应器','chem_photoreactor:光反应器','chem_microwave:微波反应器','chem_magnetic_sep:磁分离','chem_filter_paper:滤纸','chem_crystallization:结晶过程','chem_buffer:缓冲溶液','chem_osmometer:渗透压计','chem_kinetics:反应动力学','chem_arrhenius:阿伦尼乌斯图','chem_electrophoresis:电泳','chem_binding_curve:结合曲线','chem_isotherm:吸附等温线','chem_molarity:摩尔浓度','chem_stoichiometry:化学计量','chem_reaction_network:反应网络',
    ],
    'physics': [
        'phys_kinetic_energy:动能示意','phys_potential_well:势阱','phys_vector:矢量分解','phys_wave_packet:波包','phys_fourier:傅里叶谱','phys_electric_circuit:电路回路','phys_current_density:电流密度','phys_gauss:高斯定律','phys_capacitor_charge:电容充电','phys_rlc:RLC 电路','phys_em_wave:电磁波','phys_bloch:布洛赫球','phys_harmonic:简谐振动','phys_spring_mass:弹簧质量系统','phys_projectile_range:抛体射程','phys_pressure:压强分布','phys_bernoulli:伯努利流线','phys_reynolds:雷诺数','phys_heatmap:物理场热图','phys_blackbody:黑体辐射','phys_radiation:辐射通量','phys_doppler:多普勒效应','phys_polarization_ellipse:偏振椭圆','phys_fresnel:菲涅耳反射','phys_microscope:显微镜光路','phys_telescope:望远镜光路','phys_neutrino:中微子示意','phys_decay:放射性衰变','phys_feynman:费曼图','phys_detector_array:探测器阵列',
    ],
    'materials': [
        'mat_unit_cell:晶胞结构','mat_amorphous:非晶结构','mat_nanofiber:纳米纤维','mat_nanoplatelet:纳米片','mat_core_shell:核壳颗粒','mat_micropattern:微图案','mat_surface_roughness:表面粗糙度','mat_contact_angle:接触角','mat_wettability:润湿性','mat_diffusion_profile:扩散剖面','mat_phase_field:相场分布','mat_tga:热重曲线','mat_dma:动态力学分析','mat_thermal_conductivity:热导率','mat_electrical_resistivity:电阻率','mat_hardness:硬度测试','mat_toughness:断裂韧性','mat_compression:压缩测试','mat_shear:剪切测试','mat_tribology:摩擦磨损','mat_powder_bed:粉末床','mat_electrospinning:静电纺丝','mat_solgel:溶胶凝胶','mat_spray_coating:喷涂涂层','mat_plasma_treatment:等离子处理','mat_etching:刻蚀','mat_ion_implant:离子注入','mat_laser_cladding:激光熔覆','mat_melt_spinning:熔体纺丝','mat_molecular_dynamics:分子动力学',
    ],
    'engineering': [
        'eng_heat_sink:散热器','eng_radiator:换热散热片','eng_pump_curve:泵性能曲线','eng_valve_symbol:过程阀符号','eng_pipe_network:管网','eng_cfd_mesh:CFD 网格','eng_stress_field:应力场','eng_modal_test:模态测试','eng_vibration:振动监测','eng_gearbox:齿轮箱','eng_differential:差速器','eng_brake:制动器','eng_clutch:离合器','eng_spring_damper:弹簧阻尼器','eng_rolling_contact:滚动接触','eng_wind_farm:风电场','eng_solar_tracker:太阳能跟踪器','eng_battery_bms:电池管理系统','eng_can_bus:CAN 总线','eng_iot_gateway:物联网网关','eng_robot_gripper:机器人夹爪','eng_machine_vision:机器视觉','eng_lidar:激光雷达','eng_torque_sensor:扭矩传感器','eng_encoder:编码器','eng_servo:伺服电机','eng_thermal_camera:热成像相机','eng_3d_scan:三维扫描','eng_fault_tree:故障树','eng_fmea:FMEA 分析',
    ],
    'earth-environment': [
        'earth_geology_column:地层柱状图','earth_magma:岩浆房','earth_volcanic_arc:火山弧','earth_seismic_wave:地震波','earth_seismometer:地震仪','earth_gully:沟蚀','earth_sand_dune:沙丘','earth_hurricane:飓风','earth_rain_gauge:雨量计','earth_weather_radar:天气雷达','earth_solar_radiation:太阳辐射','earth_ozone:臭氧层','earth_aerosol:气溶胶','earth_pm25:PM2.5 颗粒','earth_wastewater:废水处理','earth_bioremediation:生物修复','earth_compost:堆肥','earth_landfill:填埋场','earth_recycling:资源回收','earth_forest_carbon:森林碳汇','earth_species_network:物种网络','earth_food_web:食物网','earth_phytoplankton:浮游植物','earth_ocean_acidification:海洋酸化','earth_thermal_front:海洋锋面','earth_tide:潮汐','earth_soil_moisture:土壤水分','earth_erosion_control:水土保持','earth_urban_growth:城市扩张','earth_biodiversity_index:生物多样性指数',
    ],
    'computing-math': [
        'math_data_frame:数据框','math_table:数据表','math_feature_vector:特征向量','math_kernel:核函数','math_regression:回归模型','math_confusion_matrix:混淆矩阵','math_roc:ROC 曲线','math_pr_curve:PR 曲线','math_clustering_map:聚类映射','math_embedding_space:嵌入空间','math_attention_map:注意力图','math_tokenizer:分词器','math_language_model:语言模型','math_prompt:提示词','math_rag:检索增强生成','math_vector_db:向量数据库','math_api_call:API 调用','math_pipeline:数据管线','math_container_image:容器镜像','math_kubernetes:容器编排','math_monitor:监控面板','math_log:运行日志','math_unit_test:单元测试','math_version_control:版本控制','math_branch:代码分支','math_ci:持续集成','math_graph_search:图搜索','math_shortest_path:最短路径','math_integral:积分曲线','math_probability_dist:概率分布',
    ],
    'medicine': [
        'med_cell:细胞','med_tissue:组织切片','med_organoid:类器官','med_stem_cell:干细胞','med_tcell:T 细胞','med_bcell:B 细胞','med_macrophage:巨噬细胞','med_neutrophil:中性粒细胞','med_dendritic:树突状细胞','med_complement:补体系统','med_blood_brain_barrier:血脑屏障','med_synaptic:突触结构','med_eeg:脑电图','med_ophthalmoscope:检眼镜','med_dermatoscope:皮肤镜','med_biopsy:活检','med_histology:组织学','med_culture_plate:细胞培养板','med_flow_cytometry:流式细胞术','med_pcr:PCR 检测','med_sequencer:测序仪','med_drug_target:药物靶点','med_pk_curve:药代动力学曲线','med_dose_response:剂量反应','med_placebo:安慰剂对照','med_blind_trial:盲法试验','med_randomization:随机分组','med_survival_curve:生存曲线','med_cohort_flow:队列流程','med_risk_score:风险评分',
    ],
}


ADDITIONAL_ENGLISH = {
    key: value for key, value in [
        ('chem_thermometer','Thermometer'),('chem_solid_phase','Solid-phase reaction'),('chem_liquid_liquid','Liquid-liquid extraction'),('chem_pcr_tube','PCR tube'),('chem_pcr_cycle','PCR cycle'),('chem_dna','DNA double helix'),('chem_rna','RNA strand'),('chem_sds_page','SDS-PAGE'),('chem_tlc_plate','TLC plate'),('chem_uv_vis','UV-visible spectrum'),('chem_ir_spectrum','IR spectrum'),('chem_fume_hood','Fume hood'),('chem_glovebox','Glovebox'),('chem_gas_flow','Gas flow'),('chem_pressure_reactor','Pressure reactor'),('chem_photoreactor','Photoreactor'),('chem_microwave','Microwave reactor'),('chem_magnetic_sep','Magnetic separation'),('chem_filter_paper','Filter paper'),('chem_crystallization','Crystallization'),('chem_buffer','Buffer solution'),('chem_osmometer','Osmometer'),('chem_kinetics','Reaction kinetics'),('chem_arrhenius','Arrhenius plot'),('chem_electrophoresis','Electrophoresis'),('chem_binding_curve','Binding curve'),('chem_isotherm','Adsorption isotherm'),('chem_molarity','Molarity'),('chem_stoichiometry','Stoichiometry'),('chem_reaction_network','Reaction network'),
        ('phys_kinetic_energy','Kinetic energy'),('phys_potential_well','Potential well'),('phys_vector','Vector decomposition'),('phys_wave_packet','Wave packet'),('phys_fourier','Fourier spectrum'),('phys_electric_circuit','Electric circuit'),('phys_current_density','Current density'),('phys_gauss','Gauss law'),('phys_capacitor_charge','Capacitor charging'),('phys_rlc','RLC circuit'),('phys_em_wave','Electromagnetic wave'),('phys_bloch','Bloch sphere'),('phys_harmonic','Simple harmonic motion'),('phys_spring_mass','Mass-spring system'),('phys_projectile_range','Projectile range'),('phys_pressure','Pressure field'),('phys_bernoulli','Bernoulli streamlines'),('phys_reynolds','Reynolds number'),('phys_heatmap','Physical-field heatmap'),('phys_blackbody','Blackbody radiation'),('phys_radiation','Radiative flux'),('phys_doppler','Doppler effect'),('phys_polarization_ellipse','Polarization ellipse'),('phys_fresnel','Fresnel reflection'),('phys_microscope','Microscope ray path'),('phys_telescope','Telescope ray path'),('phys_neutrino','Neutrino schematic'),('phys_decay','Radioactive decay'),('phys_feynman','Feynman diagram'),('phys_detector_array','Detector array'),
        ('mat_unit_cell','Unit cell'),('mat_amorphous','Amorphous structure'),('mat_nanofiber','Nanofiber'),('mat_nanoplatelet','Nanoplatelet'),('mat_core_shell','Core-shell particle'),('mat_micropattern','Micropattern'),('mat_surface_roughness','Surface roughness'),('mat_contact_angle','Contact angle'),('mat_wettability','Wettability'),('mat_diffusion_profile','Diffusion profile'),('mat_phase_field','Phase field'),('mat_tga','Thermogravimetric curve'),('mat_dma','Dynamic mechanical analysis'),('mat_thermal_conductivity','Thermal conductivity'),('mat_electrical_resistivity','Electrical resistivity'),('mat_hardness','Hardness test'),('mat_toughness','Fracture toughness'),('mat_compression','Compression test'),('mat_shear','Shear test'),('mat_tribology','Tribology'),('mat_powder_bed','Powder bed'),('mat_electrospinning','Electrospinning'),('mat_solgel','Sol-gel process'),('mat_spray_coating','Spray coating'),('mat_plasma_treatment','Plasma treatment'),('mat_etching','Etching'),('mat_ion_implant','Ion implantation'),('mat_laser_cladding','Laser cladding'),('mat_melt_spinning','Melt spinning'),('mat_molecular_dynamics','Molecular dynamics'),
        ('eng_heat_sink','Heat sink'),('eng_radiator','Radiator'),('eng_pump_curve','Pump curve'),('eng_valve_symbol','Process valve'),('eng_pipe_network','Pipe network'),('eng_cfd_mesh','CFD mesh'),('eng_stress_field','Stress field'),('eng_modal_test','Modal test'),('eng_vibration','Vibration monitor'),('eng_gearbox','Gearbox'),('eng_differential','Differential gear'),('eng_brake','Brake'),('eng_clutch','Clutch'),('eng_spring_damper','Spring damper'),('eng_rolling_contact','Rolling contact'),('eng_wind_farm','Wind farm'),('eng_solar_tracker','Solar tracker'),('eng_battery_bms','Battery management system'),('eng_can_bus','CAN bus'),('eng_iot_gateway','IoT gateway'),('eng_robot_gripper','Robot gripper'),('eng_machine_vision','Machine vision'),('eng_lidar','LiDAR'),('eng_torque_sensor','Torque sensor'),('eng_encoder','Encoder'),('eng_servo','Servo motor'),('eng_thermal_camera','Thermal camera'),('eng_3d_scan','3D scan'),('eng_fault_tree','Fault tree'),('eng_fmea','FMEA analysis'),
        ('earth_geology_column','Geology column'),('earth_magma','Magma chamber'),('earth_volcanic_arc','Volcanic arc'),('earth_seismic_wave','Seismic wave'),('earth_seismometer','Seismometer'),('earth_gully','Gully erosion'),('earth_sand_dune','Sand dune'),('earth_hurricane','Hurricane'),('earth_rain_gauge','Rain gauge'),('earth_weather_radar','Weather radar'),('earth_solar_radiation','Solar radiation'),('earth_ozone','Ozone layer'),('earth_aerosol','Aerosol'),('earth_pm25','PM2.5 particles'),('earth_wastewater','Wastewater treatment'),('earth_bioremediation','Bioremediation'),('earth_compost','Compost'),('earth_landfill','Landfill'),('earth_recycling','Recycling'),('earth_forest_carbon','Forest carbon sink'),('earth_species_network','Species network'),('earth_food_web','Food web'),('earth_phytoplankton','Phytoplankton'),('earth_ocean_acidification','Ocean acidification'),('earth_thermal_front','Ocean thermal front'),('earth_tide','Tide'),('earth_soil_moisture','Soil moisture'),('earth_erosion_control','Erosion control'),('earth_urban_growth','Urban growth'),('earth_biodiversity_index','Biodiversity index'),
        ('math_data_frame','Data frame'),('math_table','Data table'),('math_feature_vector','Feature vector'),('math_kernel','Kernel function'),('math_regression','Regression model'),('math_confusion_matrix','Confusion matrix'),('math_roc','ROC curve'),('math_pr_curve','PR curve'),('math_clustering_map','Clustering map'),('math_embedding_space','Embedding space'),('math_attention_map','Attention map'),('math_tokenizer','Tokenizer'),('math_language_model','Language model'),('math_prompt','Prompt'),('math_rag','Retrieval augmented generation'),('math_vector_db','Vector database'),('math_api_call','API call'),('math_pipeline','Data pipeline'),('math_container_image','Container image'),('math_kubernetes','Kubernetes'),('math_monitor','Monitoring dashboard'),('math_log','Run log'),('math_unit_test','Unit test'),('math_version_control','Version control'),('math_branch','Code branch'),('math_ci','Continuous integration'),('math_graph_search','Graph search'),('math_shortest_path','Shortest path'),('math_integral','Integral curve'),('math_probability_dist','Probability distribution'),
        ('med_cell','Cell'),('med_tissue','Tissue section'),('med_organoid','Organoid'),('med_stem_cell','Stem cell'),('med_tcell','T cell'),('med_bcell','B cell'),('med_macrophage','Macrophage'),('med_neutrophil','Neutrophil'),('med_dendritic','Dendritic cell'),('med_complement','Complement system'),('med_blood_brain_barrier','Blood-brain barrier'),('med_synaptic','Synapse'),('med_eeg','EEG'),('med_ophthalmoscope','Ophthalmoscope'),('med_dermatoscope','Dermatoscope'),('med_biopsy','Biopsy'),('med_histology','Histology'),('med_culture_plate','Cell culture plate'),('med_flow_cytometry','Flow cytometry'),('med_pcr','PCR assay'),('med_sequencer','Sequencer'),('med_drug_target','Drug target'),('med_pk_curve','Pharmacokinetic curve'),('med_dose_response','Dose-response'),('med_placebo','Placebo control'),('med_blind_trial','Blinded trial'),('med_randomization','Randomization'),('med_survival_curve','Survival curve'),('med_cohort_flow','Cohort flow'),('med_risk_score','Risk score'),
    ]
}


def _icon_for(key: str) -> str:
    """Map each new semantic key to a recognisable vector motif."""
    if key.startswith('chem_'):
        if any(x in key for x in ('dna','rna')): return dna_ladder()
        if any(x in key for x in ('spectrum','arrhenius','kinetics','binding','isotherm','titration')): return spectrum([(22,24,BLUE),(38,46,TEAL),(54,31,GOLD),(70,62,RED)])
        if any(x in key for x in ('network','solid_phase','liquid_liquid','reaction')): return flow_box(RED, TEAL)
        if any(x in key for x in ('molecule','pcr_cycle','electrophoresis')): return molecule_ring(6, (50,50), 28, TEAL)
        return rect(18, 18, 64, 67, PALE, 4) + line(25, 38, 75, 38, BLUE, 3) + line(25, 58, 75, 58, TEAL, 3) + circle(50, 74, 8, GOLD) + arrow(50, 10, 50, 29, RED, 2, 6)
    if key.startswith('phys_'):
        if any(x in key for x in ('wave','fourier','harmonic','doppler','phonon')): return wave('packet' if 'packet' in key else 'sine')
        if any(x in key for x in ('circuit','capacitor','rlc','current')): return circuit('capacitor' if 'capacitor' in key else 'resistor')
        if any(x in key for x in ('vector','field','gauss','pressure','reynolds')): return axes(''.join(arrow(x, y, x+14, y-9, TEAL, 2, 5) for x in (25,50,75) for y in (30,52,74)))
        if any(x in key for x in ('microscope','telescope','fresnel','detector','ray')): return lens_path()
        if any(x in key for x in ('quantum','neutrino','decay','feynman','bloch')): return molecule_ring(3, (50,50), 28, GOLD) + arrow(50, 12, 50, 28, RED, 2, 5)
        return axes(path('M14 73 L32 49 L48 61 L68 28 L91 18', stroke=BLUE, sw=3) + circle(48,61,4,GOLD))
    if key.startswith('mat_'):
        if any(x in key for x in ('lattice','unit_cell','amorphous','nanofiber','nanoplatelet','core_shell')): return lattice('amorphous' if 'amorphous' in key else ('hex' if 'nanoplatelet' in key else 'square'))
        if any(x in key for x in ('curve','tga','dma','conductivity','resistivity','hardness','toughness','compression','shear')): return axes(path('M14 78 C24 74 32 60 42 52 C55 42 61 32 91 18', stroke=RED, sw=3) + circle(61,32,4,GOLD))
        if any(x in key for x in ('coating','etching','implant','spinning','electro','solgel','plasma','powder')): return flow_box(BLUE, GOLD)
        if any(x in key for x in ('roughness','contact','wettability','phase','diffusion')): return rect(10, 18, 80, 62, PALE, 2) + curve('M14 52 Q24 24 35 53 T56 52 T76 52 T88 41', TEAL, 3) + arrow(50, 86, 50, 67, RED, 2, 5)
        return rect(12, 16, 76, 68, PALE, 3) + dots([(25,30),(44,26),(68,35),(31,54),(52,47),(76,59),(36,73),(62,74)], 7, BLUE) + circle(52,47,5,GOLD)
    if key.startswith('eng_'):
        if any(x in key for x in ('gear','differential','clutch','brake','rolling')): return machine('gear')
        if any(x in key for x in ('pump','valve','pipe','network','cfd','stress')): return flow_box(TEAL, RED)
        if any(x in key for x in ('sensor','encoder','camera','lidar','vision','monitor')): return screen(17, 22, 66, 48, TEAL) + circle(50, 57, 9, GOLD) + arrow(8, 57, 22, 57, BLUE, 2, 5)
        if any(x in key for x in ('wind','solar','battery','bms','bus','gateway')): return circle(50, 50, 30, PALE) + arrow(50, 50, 50, 17, RED, 3, 7) + arrow(50, 50, 80, 50, TEAL, 3, 7) + circle(50, 50, 6, GOLD)
        return machine('motor')
    if key.startswith('earth_'):
        if any(x in key for x in ('map','urban','biodiversity','species','food','landfill','recycling')): return map_tile('raster' if 'urban' in key else 'contour')
        if any(x in key for x in ('wave','seismic','radar','rain','tide','thermal')): return wave('standing')
        if any(x in key for x in ('ozone','aerosol','pm25','solar','hurricane','magma','volcanic')): return circle(50, 50, 32, PALE) + circle(50, 50, 13, GOLD) + ''.join(arrow(50, 50, 50 + 31*__import__('math').cos(i*__import__('math').pi/4), 50 + 31*__import__('math').sin(i*__import__('math').pi/4), RED if i%2 else BLUE, 2, 5) for i in range(8))
        return flow_box(BLUE, TEAL)
    if key.startswith('math_'):
        if any(x in key for x in ('matrix','confusion','roc','pr_curve','regression','probability','integral')): return data_chart('matrix' if 'matrix' in key else ('roc' if any(x in key for x in ('roc','pr_curve')) else 'bars'))
        if any(x in key for x in ('graph','path','search','attention','embedding','vector')): return molecule_ring(5, (50,50), 28, TEAL) + ''.join(line(50,50,x,y,BLUE,2) for x,y in ((18,30),(82,30),(22,76),(78,76)))
        if any(x in key for x in ('token','language','prompt','rag','api','pipeline')): return flow_box(TEAL, GOLD)
        return rect(16, 17, 68, 66, PALE, 3) + text('f(x)', 50, 49, 18, TEAL) + arrow(28, 65, 72, 65, BLUE, 2, 6)
    if key.startswith('med_'):
        if any(x in key for x in ('cell','tcell','bcell','macrophage','neutrophil','dendritic','stem','organoid')): return cell_shape(BLUE) + circle(50, 48, 15, TEAL) + dots([(30,35),(68,32),(31,68),(70,66)], 5, GOLD)
        if any(x in key for x in ('curve','dose','survival','pk','risk','eeg')): return clinical_curve('survival' if 'survival' in key else ('dose' if 'dose' in key else 'signal'))
        if any(x in key for x in ('dna','gene','chromosome','sequencer','pcr')): return chromosome()
        if any(x in key for x in ('trial','random','placebo','cohort','flow')): return flow_box(BLUE, RED)
        return rect(18, 18, 64, 66, PALE, 4) + circle(50, 45, 17, TEAL) + line(50, 62, 50, 82, RED, 3) + line(35, 72, 65, 72, BLUE, 3)
    return rect(18, 18, 64, 66, PALE, 3)


def lens_path() -> str:
    return path('M29 12 Q14 50 29 88 Q50 77 71 88 Q86 50 71 12 Q50 23 29 12 Z', PALE) + arrow(5, 50, 28, 50, RED, 2, 6) + arrow(72, 50, 95, 50, TEAL, 2, 6) + line(50, 20, 50, 80, GOLD, 2)


ADDITIONAL_SYMBOLS = {key: _icon_for(key) for values in ADDITIONAL_DEFINITIONS.values() for key in (item.split(':', 1)[0] for item in values)}

