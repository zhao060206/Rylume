"""Component asset catalog for Cell Figure Studio scene library.

Provides categorized biological and scientific visual primitives and authentic vector artwork for:
- 细胞与微环境 (Cells & Microenvironment)
- 膜结构与受体 (Membranes, Channels & Receptors)
- 细胞器与囊泡 (Organelles & Vesicles)
- 激酶、酶与分子 (Kinases, Enzymes & Signaling)
- 核酸与转录调控 (Nucleic Acids & Transcription)
- 实验器材与流程 (Lab Apparatus & Workflows)
"""
from __future__ import annotations

NATIVE_CATEGORIES = [
    {
        "id": "cells",
        "name": "细胞与微环境",
        "items": [
            {"type": "cell", "label": "完整细胞", "default_dim": [25.0, 23.0]},
            {"type": "tumor_cell", "label": "肿瘤细胞", "default_dim": [25.0, 23.0]},
            {"type": "immune_cell", "label": "免疫细胞 (T/NK/巨噬)", "default_dim": [21.0, 21.0]},
            {"type": "fibroblast", "label": "成纤维细胞 (CAF)", "default_dim": [28.0, 16.0]},
            {"type": "endothelial", "label": "血管内皮细胞", "default_dim": [26.0, 16.0]},
            {"type": "pathogen", "label": "病原体 / 病毒", "default_dim": [18.0, 18.0]},
        ],
    },
    {
        "id": "membranes",
        "name": "膜结构与受体",
        "items": [
            {"type": "membrane", "label": "质膜双分子层", "default_dim": [100.0, 10.0]},
            {"type": "nuclear_pore", "label": "核孔", "default_dim": [7.0, 9.0]},
            {"type": "receptor", "label": "单体膜受体", "default_dim": [14.0, 19.0]},
            {"type": "receptor_dimer", "label": "二聚体受体", "default_dim": [22.0, 21.0]},
            {"type": "gpcr", "label": "七次跨膜受体 (GPCR)", "default_dim": [18.0, 19.0]},
            {"type": "ligand", "label": "配体 / 细胞因子", "default_dim": [12.0, 9.0]},
        ],
    },
    {
        "id": "organelles",
        "name": "细胞器与囊泡",
        "items": [
            {"type": "nucleus", "label": "细胞核", "default_dim": [52.0, 36.0]},
            {"type": "mitochondrion", "label": "线粒体", "default_dim": [26.0, 17.0]},
            {"type": "golgi", "label": "高尔基体", "default_dim": [23.0, 19.0]},
            {"type": "er", "label": "内质网", "default_dim": [27.0, 20.0]},
            {"type": "vesicle", "label": "外泌体 / 胞外囊泡", "default_dim": [16.0, 16.0]},
            {"type": "mvb", "label": "多囊泡体 (MVB)", "default_dim": [28.0, 28.0]},
            {"type": "vesicle_fusion", "label": "膜融合释放", "default_dim": [26.0, 22.0]},
        ],
    },
    {
        "id": "proteins",
        "name": "激酶、酶与分子",
        "items": [
            {"type": "kinase", "label": "激酶 (活性/磷酸化)", "default_dim": [18.0, 13.0]},
            {"type": "protein", "label": "胞质效应蛋白", "default_dim": [18.0, 13.0]},
            {"type": "lipid", "label": "膜结合磷脂 (PIP2/PIP3)", "default_dim": [11.0, 8.0]},
            {"type": "complex", "label": "多蛋白复合物", "default_dim": [22.0, 16.0]},
            {"type": "domain", "label": "功能结构域", "default_dim": [18.0, 10.0]},
        ],
    },
    {
        "id": "nucleic",
        "name": "核酸与转录调控",
        "items": [
            {"type": "tf", "label": "转录因子", "default_dim": [17.0, 14.0]},
            {"type": "dna", "label": "DNA 双螺旋 / 启动子", "default_dim": [32.0, 12.0]},
            {"type": "mrna", "label": "mRNA 转录本", "default_dim": [24.0, 8.0]},
        ],
    },
    {
        "id": "apparatus",
        "name": "实验器材与流程",
        "items": [
            {"type": "process", "label": "流程步骤框", "default_dim": [27.0, 17.0]},
            {"type": "collagen", "label": "胶原纤维束", "default_dim": [25.0, 26.0]},
            {"type": "tissue", "label": "组织切片 / 屏障", "default_dim": [34.0, 29.0]},
            {"type": "text", "label": "文本标注", "default_dim": [28.0, 3.0]},
        ],
    },
]

ASSET_CATEGORIES = NATIVE_CATEGORIES

ASSET_DOMAINS = [
    {'id':'biology','title':'生物学','available':True},
    {'id':'materials','title':'材料科学','available':False},
    {'id':'chemistry','title':'化学','available':False},
    {'id':'engineering','title':'工程技术','available':False},
]

def _asset_category(item):
    """Preserve upstream identity while grouping lab equipment by its use."""
    raw=item.get('category','科研插画')
    category=CATEGORY_NORMALIZE.get(raw,raw)
    name=item.get('asset_id','').lower()
    equipment=('flask','beaker','pipette','syringe','centrifug','microscope','test_tube',
               'tube_rack','measuring','condenser','funnel','reagent_bottle','glass_slide','cap_pipet')
    if any(word in name for word in equipment):return '实验器材与流程'
    if category=='细胞器与囊泡' and any(word in name for word in ('enzyme','protein_','zincfinger')):
        return '激酶、酶与分子'
    if 'emptycell' in name or 'emtpycell' in name:return '细胞与微环境'
    return category

CATEGORY_NORMALIZE = {
    '免疫与血液': '免疫与血液',
    '细胞类型与微环境': '细胞与微环境',
    '组织与细胞外基质': '细胞与微环境',
    '细胞与微环境': '细胞与微环境',
    '膜受体与转运蛋白': '膜结构与受体',
    '受体与通道': '膜结构与受体',
    '膜结构与区室': '膜结构与受体',
    '膜结构与运输': '膜结构与受体',
    '膜结构与受体': '膜结构与受体',
    '细胞与细胞器': '细胞器与囊泡',
    '囊泡与细胞器': '细胞器与囊泡',
    '细胞器与囊泡': '细胞器与囊泡',
    '激酶与信号分子': '激酶、酶与分子',
    '激酶、酶与分子': '激酶、酶与分子',
    '转录因子与核酸': '核酸与转录调控',
    '核酸与基因表达': '核酸与转录调控',
    '染色质与遗传': '核酸与转录调控',
    '核酸与转录调控': '核酸与转录调控',
    '实验器材': '实验器材与流程',
    '实验器材与流程': '实验器材与流程',
    '病原体与病毒': '病原体与病毒',
    '科研插画': '细胞与微环境',
}

TYPE_CORRECTIONS = {
    'bio_mitochondrium_1': 'mitochondrion',
    'bio_mitochondrium_blue': 'mitochondrion',
    'bio_nucleus': 'nucleus',
    'bio_nucleus_closeup': 'nucleus',
    'bio_golgi_2d_1': 'golgi',
    'bio_endoplasmatic_reticulum_rough': 'er',
    'bio_endoplasmatic_reticulum_small': 'er',
    'bio_cell_complete': 'cell',
    'bio_emptycell_oval': 'cell',
    'bio_emptycell_half_1': 'cell',
    'bio_membrane_2d_bluelight': 'membrane',
    'bio_membrane_3d_bluelight': 'membrane',
    'bio_lipid_blue': 'lipid',
    'bio_rna': 'mrna',
    'bio_tRNA': 'mrna',
    'bio_dna_double_stranded_ribbon': 'dna',
    'bio_dna_1': 'dna',
    'bio_dna_nucleotides_forked': 'dna',
    'bio_plasmid': 'dna',
    'bio_7helix_receptor_membrane': 'gpcr',
    'bio_channel_membrane_blue': 'receptor',
    'bio_carrier_protein_membrane_1': 'receptor',
    'bio_channel_lid_ions_membrane': 'receptor',
    'bio_calciumsensing_receptor': 'receptor',
    'bio_enzyme_blue': 'kinase',
    'bio_enzyme_green': 'kinase',
    'bio_enzyme_orange': 'kinase',
}


TYPE_CORRECTIONS.update({
    'bio_antibody':'antibody', 'bio_igG_immunoglobulin':'antibody',
    'bio_igM_immunoglobulin':'antibody', 'bio_antibody_ligand_1':'antibody',
    'bio_fibrin_1':'collagen', 'bio_endocytosis_2d':'process',
    'bio_exocytosis_2d':'process', 'bio_phagocytosis_2d':'process',
    'bio_transkription':'process', 'bio_translation':'process',
    'bio_ribosome_translation':'complex',
    'bio_channel_membrane_blue':'channel', 'bio_channel_lid_ions_membrane':'channel',
    'bio_carrier_protein_membrane_1':'protein',
    'bio_enzyme_blue':'protein', 'bio_enzyme_green':'protein', 'bio_enzyme_orange':'protein',
})


def asset_catalog():
    """Return categorized assets for UI palette display."""
    from scientific_library import library
    bio_items = []
    for aid, item in library().items():
        copy_item = dict(item)
        copy_item['category'] = _asset_category(copy_item)
        copy_item.setdefault('domain','biology')
        if aid in TYPE_CORRECTIONS:
            copy_item['type'] = TYPE_CORRECTIONS[aid]
        bio_items.append(copy_item)
    
    # Return structured categories with both native and high-fidelity assets
    cat_order = [
        ("cells", "细胞与微环境"),
        ("membranes", "膜结构与受体"),
        ("organelles", "细胞器与囊泡"),
        ("proteins", "激酶、酶与分子"),
        ("nucleic", "核酸与转录调控"),
        ("apparatus", "实验器材与流程"),
    ]
    
    known_names={name for _,name in cat_order}
    for raw in dict.fromkeys(b['category'] for b in bio_items):
        if raw not in known_names:
            cat_order.append(('extra_'+str(len(cat_order)), raw));known_names.add(raw)
    result = []
    for cid, cname in cat_order:
        native_group = next((c for c in NATIVE_CATEGORIES if c["name"] == cname), {"items": []})
        native_items = []
        for n in native_group["items"]:
            item_copy = dict(n)
            item_copy.setdefault("thumbnail", f"/ui/library/native_{item_copy['type']}.svg")
            item_copy.setdefault("license", "原生矢量")
            item_copy.setdefault("category", cname)
            item_copy['domain'] = 'biology'
            native_items.append(item_copy)
        matching_bio = [b for b in bio_items if b["category"] == cname and b['domain']=='biology']
        items = native_items + matching_bio
        for item in items:item['category_id']=cid
        result.append({"id": cid, "name": cname, "domain":'biology', "items": items})
    for domain in dict.fromkeys(a['domain'] for a in bio_items if a['domain']!='biology'):
        for category in dict.fromkeys(a['category'] for a in bio_items if a['domain']==domain):
            items=[{**a,'category_id':domain+'_'+str(len(result))} for a in bio_items if a['domain']==domain and a['category']==category]
            result.append({'id':domain+'_'+str(len(result)),'name':category,'domain':domain,'items':items})
    return result
