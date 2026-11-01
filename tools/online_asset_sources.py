"""Offline cache and provenance for third-party scientific SVG sources.

The builder never invents a replacement drawing when an external source is
selected. It imports a CC BY 4.0 SVG from the checked-in ScanSci cache,
sanitises only unsafe SVG constructs, and records the original URL in the
asset metadata. This keeps builds reproducible while making attribution
visible to authors.
"""
from __future__ import annotations

import copy
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from resource_packs import safe_svg

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / 'assets' / 'online-sources' / 'scansci'
# Pin the source revisions so attribution remains reproducible after upstream
# repositories move their default branches.
SOURCE_BASE = 'https://github.com/Rimagination/scansci-svg/blob/f4dd394eb0797681fcfdf43f230483dcf8c144ac/skill/assets/library/'
LICENSE_URL = 'https://creativecommons.org/licenses/by/4.0/'
MDI_ROOT = ROOT / 'assets' / 'online-sources' / 'mdi'
MDI_BASE = 'https://github.com/Templarian/MaterialDesign/blob/2424e748e0cc63ab7b9c095a099b9fe239b737c0/svg/'
MDI_LICENSE_URL = 'https://www.apache.org/licenses/LICENSE-2.0'

SAFE_ATTRS = {
    'viewBox','x','y','x1','y1','x2','y2','cx','cy','r','rx','ry','width','height',
    'd','points','transform','fill','stroke','stroke-width','stroke-linecap',
    'stroke-linejoin','fill-rule','opacity','fill-opacity','stroke-opacity',
    'font-size','font-family','font-weight','text-anchor','dominant-baseline'
}
SAFE_TAGS = {'svg','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan'}


def _candidate_files(key: str) -> list[str]:
    """Return a varied, domain-appropriate set of online drawings."""
    k = key.lower()
    files = [p.name for p in SOURCE_ROOT.glob('*.svg')]
    def starts(*prefixes): return [p for p in files if p.startswith(prefixes)]
    if k.startswith('chem_') or k in {'beaker','flask','tube','burette','condenser','funnel','round_flask','molecule','benzene','catalyst','electrode','battery','chromatogram','stirrer','balance','droplet','crystal','column'}:
        pool = starts('lab_', 'process_chemical', 'mat_small_molecules', 'mat_crystals')
    elif k.startswith('phys_') or k in {'lens','mirror','laser','prism','slit','screen','atom','wave','magnet','coil','pendulum','spring','mass','charge','capacitor','resistor','detector','polarizer'}:
        pool = starts('lab_diffraction','lab_spectroscopy','process_physical','astro_','info_')
    elif k.startswith('mat_') or k in {'particle','lattice','vacancy','dislocation','layers','graphene','nanotube','polymer','composite','pore','membrane','grain','fiber','film','substrate','tensile','fracture','powder'}:
        pool = starts('mat_','lab_electron_microscopy','process_physical')
    elif k.startswith('eng_') or k in {'pump','valve','pipe','tank','turbine','gear','motor','sensor','chip','actuator','robot','heat_exchanger','filter','compressor','fan','nozzle','piston','truss'}:
        pool = starts('eng_','built_','info_')
    elif k.startswith('earth_') or k in {'mountain','river','aquifer','soil','cloud','rain','sun','volcano','tree','leaf','wetland','ocean','sediment','glacier','watershed','pollutant','station','satellite'}:
        pool = starts('geo_','env_','atm_','water_','hazard_','map_')
    elif k.startswith('math_') or k.startswith('computing') or k in {'database','server','neuron','network','tree_graph','tensor','matrix','embedding','gpu','dataset','loss','optimizer','decision','mesh','field','code','split','chip'}:
        pool = starts('info_','process_','lab_')
    elif k.startswith('med_') or k in {'heart','lung','brain','kidney','liver','vessel','capillary','syringe','tablet','ultrasound','mri','ecg','patient','hospital','stethoscope','biomarker','cohort','iv'}:
        pool = starts('anatomy_','cell_','microbe_','people_','lab_molecular_assays')
    else:
        pool = files
    return sorted(pool or files)


def source_path(key: str) -> Path:
    mapping_path = ROOT / 'assets' / 'online-sources' / 'mdi-mapping.json'
    if mapping_path.exists():
        try:
            mapped = __import__('json').loads(mapping_path.read_text(encoding='utf8')).get(key)
            candidate = MDI_ROOT / str(mapped)
            if mapped and candidate.is_file():
                return candidate
        except (OSError, ValueError, TypeError):
            pass
    candidates = _candidate_files(key)
    # Stable, deterministic spread across the online library prevents every
    # item in a discipline from becoming the same thumbnail.
    idx = int(hashlib.sha256(key.encode('utf8')).hexdigest()[:8], 16) % len(candidates)
    return SOURCE_ROOT / candidates[idx]


def _sanitise(raw: str) -> str:
    root = ET.fromstring(raw)
    root.tag = 'svg'
    if not root.get('viewBox'):
        root.set('viewBox', f"0 0 {root.get('width','100')} {root.get('height','100')}")
    def walk(node):
        for child in list(node):
            tag = child.tag.split('}')[-1]
            if tag not in SAFE_TAGS:
                node.remove(child)
                continue
            child.tag = tag
            for attr in list(child.attrib):
                value = str(child.attrib[attr])
                if attr not in SAFE_ATTRS or re.search(r'(?i)(url\s*\(|javascript:|https?:|data:|NaN|Infinity)', value):
                    if attr == 'fill' and value.lower().startswith('url('):
                        child.set('fill', '#DFEDF1')
                    else:
                        child.attrib.pop(attr, None)
            walk(child)
    walk(root)
    for attr in list(root.attrib):
        if attr not in SAFE_ATTRS: root.attrib.pop(attr, None)
    root.set('xmlns', 'http://www.w3.org/2000/svg')
    return safe_svg(ET.tostring(root, encoding='unicode'))


def online_svg(key: str) -> tuple[str, dict]:
    path = source_path(key)
    content = _sanitise(path.read_text(encoding='utf8'))
    is_mdi = path.parent.resolve() == MDI_ROOT.resolve()
    meta = {
        'author': 'Pictogrammers / Material Design Icons' if is_mdi else 'ScanSci contributors',
        'license': 'Apache-2.0' if is_mdi else 'CC BY 4.0',
        'license_url': MDI_LICENSE_URL if is_mdi else LICENSE_URL,
        'source_url': (MDI_BASE if is_mdi else SOURCE_BASE) + path.name,
        'modifications': ('Imported from the online Material Design Icons library and sanitised for safe local editing.' if is_mdi else 'Imported from the online ScanSci SVG library and sanitised for safe local editing.'),
        'source_file': path.name,
        'source_kind': 'online-open-license',
    }
    return content, meta

