import pytest
from scene_templates import TEMPLATES, make_template
from template_library import DETAILS, RECOMMENDED

def test_all_templates_have_curated_usage_and_limitations():
    assert len(TEMPLATES) >= 80
    for t in TEMPLATES:
        assert t['usage'], f"Missing usage for {t['id']}"
        assert t['includes'], f"Missing includes for {t['id']}"
        assert t['limitations'], f"Missing limitations for {t['id']}"

def test_recommended_templates_are_valid_and_featured():
    assert len(RECOMMENDED) >= 12
    for tid in RECOMMENDED:
        t = next((x for x in TEMPLATES if x['id'] == tid), None)
        assert t is not None, f"Recommended template {tid} not in TEMPLATES"
        assert t['recommended'] is True
        assert t['featured'] is True

def test_legend_glyph_rendering():
    from biology_glyphs import symbol
    for rel in ['activates', 'inhibits', 'binds', 'converts', 'transports', 'sequence']:
        svg = symbol('process', '#1F4E79', f'legend_{rel}', '#1F4E79', 1)
        assert svg and '<g' in svg and '</g>' in svg
