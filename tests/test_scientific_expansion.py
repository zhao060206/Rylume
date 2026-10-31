"""Comprehensive validation for expanded scientific asset catalog, 22 templates, and export contracts."""
import os
import zipfile
from pathlib import Path
import pytest

from scene_assets import asset_catalog
from scene_document import OBJECT_TYPES, empty_scene, normalize_scene
from scene_export import export_scene
from scene_render import render_scene
from scene_templates import TEMPLATES, COLORWAYS, make_template, apply_template
from scientific_library import library, glyph

ROOT = Path(__file__).resolve().parents[1]

def test_asset_catalog_completeness():
    cats = asset_catalog()
    assert len(cats) >= 6
    total_items = sum(len(c["items"]) for c in cats)
    assert total_items >= 100
    lib_items = library()
    assert len(lib_items) >= 65

    for c in cats:
        assert c["name"]
        for item in c["items"]:
            assert item["type"] in OBJECT_TYPES, f"Type {item['type']} not in OBJECT_TYPES"
            thumbnail=item["thumbnail"]
            # Downloaded discipline packs expose an API URL whose file lives
            # in the user's data directory; bundled assets use ui/library.
            if thumbnail.startswith('/api/resources/file/'):
                assert item.get('pack_id') and item.get('domain')
            else:
                thumb = ROOT / thumbnail.lstrip("/")
                assert thumb.exists(), f"Thumbnail missing: {thumb}"
                assert thumb.stat().st_size > 50

def test_all_22_templates_instantiate_and_render():
    assert len(TEMPLATES) >= 22
    for t in TEMPLATES:
        scene = make_template(t["id"])
        assert scene["objects"], f"Template {t['id']} has no objects"
        assert scene["style"]["template"] == t["id"]
        svg = render_scene(scene)
        assert svg.startswith("<svg") and svg.endswith("</svg>")
        assert f'data-revision="{scene["revision"]}"' in svg

def test_all_8_colorways_apply_cleanly():
    assert len(COLORWAYS) >= 8
    for c in COLORWAYS:
        scene = make_template("signal_relay", colorway=c["id"])
        assert scene["style"]["colorway"] == c["id"]
        assert scene["style"]["palette"] == c["palette"]
        svg = render_scene(scene)
        assert c["palette"]["primary"].upper() in svg.upper()

def test_full_export_of_template_with_bioicons_to_all_formats(tmp_path):
    scene = empty_scene("Template & Asset Export Test", width_mm=180, height_mm=120)
    scene["objects"] = [
        {"id": "t1", "entity_id": "e1", "type": "immune_cell", "label": "T 细胞", "asset_id": "bio_t_lymphocyte", "x": 20, "y": 20, "w": 25, "h": 25},
        {"id": "m1", "entity_id": "e2", "type": "immune_cell", "label": "巨噬细胞", "asset_id": "bio_macrophage", "x": 60, "y": 20, "w": 28, "h": 25},
        {"id": "d1", "entity_id": "e3", "type": "dna", "label": "启动子 DNA", "asset_id": "bio_dna_double_stranded_ribbon", "x": 110, "y": 20, "w": 40, "h": 18},
    ]
    scene["relations"] = [
        {"id": "r1", "source": "t1", "target": "m1", "type": "activates", "label": "共刺激"}
    ]
    scene = normalize_scene(scene)
    
    for fmt in ("svg", "pdf", "png", "pptx"):
        dest = tmp_path / f"export.{fmt}"
        res = export_scene(scene, fmt, dest)
        assert dest.exists() and dest.stat().st_size > 1000
        assert res["raster_objects"] == []
    
    with zipfile.ZipFile(tmp_path / "export.pptx") as z:
        assert not any(n.startswith("ppt/media/") for n in z.namelist())
        slide = z.read("ppt/slides/slide1.xml").decode()
        assert "custGeom" in slide
        assert "共刺激" in slide or "activates" in slide
