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
    return asset
