"""Stable bilingual labels for every drawable asset.

Labels are metadata, never inferred from the rendered geometry at runtime. The
fallback only turns a reviewed asset id into readable English for older packs.
"""
from __future__ import annotations
import re

_PREFIXES = ('biology_', 'chemistry_', 'physics_', 'materials_', 'engineering_',
             'earth_environment_', 'computing_math_', 'medicine_', 'bio_',
             'chem_', 'phys_', 'mat_', 'eng_', 'earth_', 'math_', 'med_')
_ACRONYMS = {
    'dna':'DNA','rna':'RNA','mrna':'mRNA','trna':'tRNA','gpcr':'GPCR','rtk':'RTK',
    'hplc':'HPLC','nmr':'NMR','gc':'GC','ct':'CT','mri':'MRI','pet':'PET',
    'ecg':'ECG','sem':'SEM','tem':'TEM','afm':'AFM','xrd':'XRD','cvd':'CVD',
    'pid':'PID','plc':'PLC','scada':'SCADA','gis':'GIS','api':'API','gpu':'GPU',
    'cnn':'CNN','gan':'GAN','rl':'RL','fem':'FEM','ode':'ODE','fft':'FFT',
    'svm':'SVM','agv':'AGV','hvac':'HVAC','hmi':'HMI','nmr':'NMR',
}
_OVERRIDES = {
    'chemistry_chem_catalyst':'Catalyst',
    'earth_environment_earth_land_cover':'Land-cover class',
    'earth_environment_reservoir':'Reservoir',
    'physics_eng_grid':'Power grid',
}

def _humanize(value: str) -> str:
    value = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(value))
    value = re.sub(r'[^A-Za-z0-9]+', ' ', value).strip()
    words=[]
    for word in value.split():
        lower=word.lower();words.append(_ACRONYMS.get(lower, lower))
    if words and not words[0].isupper():words[0]=words[0].capitalize()
    return ' '.join(words)

def _strip_domain_prefix(value: str) -> str:
    """Remove internal discipline prefixes before exposing an English label."""
    value=str(value)
    prefixes=('biology_','chemistry_','physics_','materials_','engineering_',
              'earth_environment_','computing_math_','medicine_',
              'chem_','phys_','mat_','eng_','earth_','math_','med_','bio_')
    changed=True
    while changed:
        changed=False
        for prefix in prefixes:
            if value.lower().startswith(prefix):
                value=value[len(prefix):];changed=True;break
    return value

def english_asset_label(asset: dict) -> str:
    explicit=str(asset.get('label_en') or '').strip()
    if explicit:return explicit
    aid=str(asset.get('asset_id') or asset.get('id') or '').lower()
    if aid in _OVERRIDES:return _OVERRIDES[aid]
    changed=True
    while changed:
        changed=False
        for prefix in _PREFIXES:
            if aid.startswith(prefix):aid=aid[len(prefix):];changed=True;break
    keywords=asset.get('keywords') or []
    if isinstance(keywords,str):keywords=[keywords]
    candidates=[_strip_domain_prefix(str(x)) for x in keywords if re.search(r'[A-Za-z]',str(x))]
    value=candidates[0] if candidates else _strip_domain_prefix(aid)
    return _humanize(value)

def ensure_bilingual(asset: dict) -> dict:
    asset.setdefault('label_en', english_asset_label(asset))
    asset.setdefault('label_zh',asset.get('label',''))
    categories={'细胞与微环境':'Cells and microenvironment','膜结构与受体':'Membranes and receptors',
      '细胞器与囊泡':'Organelles and vesicles','激酶、酶与分子':'Proteins and enzymes','核酸与转录调控':'Nucleic acids and transcription',
      '实验器材与流程':'Laboratory equipment','免疫与血液':'Immunology and blood','器官与人体系统':'Anatomy and body systems',
      '模式生物':'Model organisms','微生物':'Microorganisms','植物与藻类':'Plants and algae','寄生虫':'Parasites',
      '组织与细胞外基质':'Tissues and extracellular matrix','细胞培养':'Cell culture','肿瘤与病理':'Tumours and pathology',
      '细胞系':'Cell lines','显微与成像':'Microscopy and imaging','基因组与测序':'Genomics and sequencing',
      '多肽与蛋白':'Peptides and proteins','表观遗传':'Epigenetics','细胞外基质':'Extracellular matrix',
      '神经科学':'Neuroscience','分子生物学':'Molecular biology','发育与胚胎':'Development and embryos',
      '化学结构与实验':'Chemical structures and experiments','氨基酸结构':'Amino-acid structures',
      '数据与分析示意':'Data and analysis','实验安全标识':'Laboratory safety','机器学习与计算流程':'Machine learning and computation',
      '医学操作':'Medical procedures','人物与活动':'People and activities','生物信息与计算':'Bioinformatics',
      '分子模拟':'Molecular modelling','计算软件标识':'Scientific software','计算设备':'Computing equipment','纳米材料':'Nanomaterials',
      '组织与细胞间连接':'Tissues and cell junctions','病原体与病毒':'Pathogens and viruses','化学与分子':'Chemistry and molecules'}
    asset.setdefault('category_en',categories.get(asset.get('category'), 'Scientific artwork'))
    if not asset.get('asset_id'):
        native={'cell':'Cell','tumor_cell':'Tumour cell','immune_cell':'Immune cell','fibroblast':'Fibroblast','endothelial':'Endothelial cell',
          'pathogen':'Pathogen','membrane':'Lipid bilayer','nuclear_pore':'Nuclear pore','receptor':'Membrane receptor','receptor_dimer':'Receptor dimer',
          'gpcr':'G protein-coupled receptor','ligand':'Ligand','nucleus':'Nucleus','mitochondrion':'Mitochondrion','golgi':'Golgi apparatus',
          'er':'Endoplasmic reticulum','vesicle':'Extracellular vesicle','mvb':'Multivesicular body','vesicle_fusion':'Membrane fusion',
          'kinase':'Kinase','protein':'Protein','lipid':'Phospholipid','complex':'Protein complex','domain':'Protein domain',
          'tf':'Transcription factor','dna':'DNA double helix','mrna':'Messenger RNA','process':'Process step','collagen':'Collagen fibres',
          'tissue':'Tissue section','text':'Text label'}
        asset['label_en']='Plant cell' if asset.get('state')=='plant_interphase' else native.get(asset['type'],asset['label_en'])
        asset['label_zh']=re.sub(r'\s*\([^)]*[A-Za-z][^)]*\)','',asset['label_zh'])
        for before,after in [('mRNA','信使核糖核酸'),('DNA','脱氧核糖核酸')]:asset['label_zh']=asset['label_zh'].replace(before,after)
    return asset
