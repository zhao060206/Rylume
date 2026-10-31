import json
from pathlib import Path

from asset_language import english_asset_label, ensure_bilingual

ROOT=Path(__file__).resolve().parents[1]

def test_all_bundled_assets_have_bilingual_labels():
    manifests=list((ROOT/'resource-packs').glob('*/manifest.json'))+[ROOT/'assets/bioicons/manifest.json']
    total=0
    for path in manifests:
        data=json.loads(path.read_text(encoding='utf8'))
        items=data if isinstance(data,list) else data['assets']
        for item in items:
            ensure_bilingual(item);assert item['label'] and item['label_en']
            assert isinstance(item['label_en'],str) and len(item['label_en'])<=120
            total+=1
    assert total>=2200

def test_semantic_fallbacks_match_asset_identity():
    assert english_asset_label({'asset_id':'chemistry_chem_catalyst'})=='Catalyst'
    assert english_asset_label({'asset_id':'medicine_med_mri'})=='MRI'
    assert english_asset_label({'asset_id':'earth_environment_earth_land_cover'})=='Land-cover class'
