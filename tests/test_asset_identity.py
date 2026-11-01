"""Reproduce the mislabelled balance and untranslated screenshot examples."""
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from online_asset_sources import source_path,online_svg


def test_balance_is_a_balance_and_unknown_sources_never_substitute():
    path=source_path('balance')
    assert 'analytical_balance' in path.name
    _,meta=online_svg('balance')
    assert meta['source_file']=='scale.svg' and meta['source_url'].endswith('/scale.svg')
    assert 'process_chemical' not in str(path)
    with pytest.raises(ValueError,match='对应图片'):source_path('earth_ice_core')
    with pytest.raises(ValueError,match='对应图片'):source_path('arbitrary_unreviewed_object')
    manifest=json.loads((ROOT/'resource-packs/chemistry/manifest.json').read_text(encoding='utf8'))
    old=next(a for a in manifest['assets'] if a['id']=='chemistry_balance')
    assert old['catalog_status']=='quarantined'
    balance=next(a for a in manifest['assets'] if a['id']=='chemistry_verified_chem_analytical_balance')
    assert balance['label_zh']=='分析天平' and balance['label_en']=='analytical balance'


def test_all_available_art_has_two_languages_and_exact_source_metadata():
    items=json.loads((ROOT/'assets/bioicons/manifest.json').read_text(encoding='utf8'))
    for path in (ROOT/'resource-packs').glob('*/manifest.json'):
        manifest=json.loads(path.read_text(encoding='utf8'))
        for a in manifest['assets']:
            assert hashlib.sha256((path.parent/a['file']).read_bytes()).hexdigest()==a['sha256']
        items+=manifest['assets']
    available=[a for a in items if a.get('catalog_status')=='source-matched']
    assert available
    for a in available:
        assert re.search('[\u4e00-\u9fff]',a['label_zh']),a['asset_id']
        assert not re.search('[A-Za-z]{2}',a['label_zh']),a['label_zh']
        assert not re.search('[\u4e00-\u9fff]',a['label_en']),a['label_en']
        assert a['label_zh']!=a['label_en']
        assert unquote(a['source_url'].split('/')[-1])==a['source_file']


def test_reported_screenshot_names_have_complete_translations():
    items={a['asset_id']:a for a in json.loads((ROOT/'assets/bioicons/manifest.json').read_text(encoding='utf8'))}
    for aid,zh,en in [('bio_tight_junction_2','紧密连接','tight junction'),
       ('bio_DBCLS_Cardiac_Myocytes','心肌细胞','cardiac myocytes'),
       ('biox_ewaoz_redbloodcell_e106c69f','红细胞','red blood cell'),
       ('biox_marnie_maddock_simple_cardiomyocyte_e25492f6','心肌细胞','cardiomyocyte'),
       ('biox_servier_emptycell_3d_1_2d2d2874','空白细胞','empty cell')]:
        a=items[aid]
        assert a['catalog_status']=='source-matched'
        assert zh in a['label_zh'] and en in a['label_en'].lower()


def test_whole_catalog_scientific_phrases_and_ambiguous_art():
    items=json.loads((ROOT/'assets/bioicons/manifest.json').read_text(encoding='utf8'))
    for path in (ROOT/'resource-packs').glob('*/manifest.json'):
        items+=json.loads(path.read_text(encoding='utf8'))['assets']
    available=[a for a in items if a.get('catalog_status')=='source-matched']
    for a in available:
        assert '隼' not in a['label_zh'],a['asset_id']
        if 'radio-tag' in a['source_file']:
            assert '放射性标记' in a['label_zh'] and '无线电' not in a['label_zh']
        if a['source_file']=='terminal.svg':assert a['label_zh']=='终端'
        if a['source_file']=='rice.svg':assert a['label_zh']=='米饭'
    by_file={}
    for a in items:by_file.setdefault(a.get('source_file'),[]).append(a)
    assert all(a['catalog_status']=='quarantined' for filename in
        ('nucleotide-a-ul.svg','hypotonic-erythrocyte-2.svg',
         'hydrophobic-droplet-hydrophilic-surface.svg','hydrophilic-droplet-hydrophobic-surface.svg')
        for a in by_file[filename])
    tubes=[a for a in available if a['source_file'] in ('falcon_15.svg','falcon_15_empty.svg','50_falcon.svg')]
    assert tubes and all('离心管' in a['label_zh'] for a in tubes)
