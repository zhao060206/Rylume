import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path
from PIL import Image, ImageDraw
import pytest

import app_server
import layout_contract
import scene_planner
from biology_glyphs import symbol
from scene_document import empty_scene, normalize_scene
from test_scene_api import studio


def test_mitosis_archetype_never_routes_to_framework():
    text = "真核细胞有丝分裂全周期闭环流线图"
    arch = layout_contract.archetype_of(text)
    assert arch == "process_pipeline", f"Expected process_pipeline, got {arch}"


def test_mitosis_phases_produce_unique_biological_vector_symbols():
    phases = [
        "Interphase", "Prophase", "Prometaphase", "Metaphase",
        "Anaphase", "Telophase", "Cytokinesis", "Apoptotic"
    ]
    hashes = {}
    for p in phases:
        svg_content = symbol("cell", "#2563EB", p)
        # Check basic SVG validity
        assert "<ellipse" in svg_content or "<path" in svg_content
        h = hashlib.sha256(svg_content.encode("utf-8")).hexdigest()
        hashes[p] = h

    # Every phase must be distinct
    assert len(set(hashes.values())) == len(phases)

    # Check characteristic structures
    interphase_svg = symbol("cell", "#2563EB", "Interphase")
    assert "M 35 48" in interphase_svg  # chromatin mesh

    prophase_svg = symbol("cell", "#2563EB", "Prophase")
    assert "stroke-dasharray" not in prophase_svg  # envelope remains intact until prometaphase

    metaphase_svg = symbol("cell", "#2563EB", "Metaphase")
    assert "#10B981" in metaphase_svg  # green mitotic spindle fibers
    assert "#BE185D" in metaphase_svg  # magenta equatorial chromosomes

    anaphase_svg = symbol("cell", "#2563EB", "Anaphase")
    assert "#34D399" in anaphase_svg  # central spindle midzone

    telophase_svg = symbol("cell", "#2563EB", "Telophase")
    assert "#EA580C" in telophase_svg  # contractile ring furrow

    cytokinesis_svg = symbol("cell", "#2563EB", "Cytokinesis")
    assert cytokinesis_svg.count("<ellipse cx=\"25.00") >= 1  # 2 daughter nuclei


def test_generate_mitosis_from_canvas_draft_preserves_layout_and_enriches(studio, monkeypatch):
    """User draws draft on canvas with 6 boxes -> AI generates editable cells at exact positions."""
    # Create a draft scene with 6 boxes representing 6 stages
    draft = empty_scene(source_text="草稿测试", width_mm=180, height_mm=120)
    draft["layout"] = "process"
    stages = [
        ("c1", "间期", 15, 20),
        ("c2", "前期", 65, 20),
        ("c3", "中期", 115, 20),
        ("c4", "后期", 115, 70),
        ("c5", "末期", 65, 70),
        ("c6", "胞质分裂", 15, 70),
    ]
    draft["objects"] = [
        {"id": cid, "type": "process", "label": lbl, "x": x, "y": y, "w": 30, "h": 26, "evidence": lbl}
        for cid, lbl, x, y in stages
    ]
    draft["relations"] = [
        {"id": "r1", "source": "c1", "target": "c2", "type": "sequence"},
        {"id": "r2", "source": "c2", "target": "c3", "type": "sequence"},
        {"id": "r3", "source": "c3", "target": "c4", "type": "sequence"},
        {"id": "r4", "source": "c4", "target": "c5", "type": "sequence"},
        {"id": "r5", "source": "c5", "target": "c6", "type": "sequence"},
        {"id": "r6", "source": "c6", "target": "c1", "type": "sequence"},
    ]
    draft = normalize_scene(draft)

    # First commit as a blank/sketch job
    code, blank_res = studio("/api/scene/blank", {})
    assert code == 200
    sketch_id = blank_res["job_id"]

    code, save_res = studio(f"/api/jobs/{sketch_id}/scene", {
        "base_revision": 1,
        "operations": [
            {"op": "replace", "scene": draft}
        ]
    }, "PATCH")
    assert code == 200

    # Now generate from this draft
    body = {
        "text": "真核细胞有丝分裂全周期闭环流线图：间期启动，经历前期、中期、后期、末期并闭环完成胞质分裂",
        "sketch_job_id": sketch_id,
        "base_revision": save_res["revision"]
    }

    # Mock plan_scene to simulate LLM returning enriched mitosis semantic spec
    def mock_plan(text, config, **kw):
        s = empty_scene(source_text=text, width_mm=180, height_mm=120)
        s["layout"] = "process"
        phase_map = [
            ("c1", "间期", "interphase"),
            ("c2", "前期", "prophase"),
            ("c3", "中期", "metaphase"),
            ("c4", "后期", "anaphase"),
            ("c5", "末期", "telophase"),
            ("c6", "胞质分裂", "cytokinesis"),
        ]
        s["objects"] = [
            {"id": cid, "type": "cell", "label": lbl, "state": st, "evidence": lbl}
            for cid, lbl, st in phase_map
        ]
        s["relations"] = draft["relations"]
        s["requirements"] = {"objects": [c[0] for c in phase_map], "relations": ["r1", "r2", "r3", "r4", "r5", "r6"]}
        return s, {"method": "mock_plan"}

    monkeypatch.setattr(scene_planner, "plan_scene", mock_plan)

    code, gen_res = studio("/api/generate", body)
    assert code == 200, gen_res
    new_job_id = gen_res["job_id"]

    # Wait for completion
    for _ in range(100):
        import time
        code, job = studio(f"/api/jobs/{new_job_id}")
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.02)
    assert job["status"] == "completed", job

    # Load the resulting scene document
    code, doc = studio(f"/api/jobs/{new_job_id}/scene")
    assert code == 200
    objs = doc["scene"]["objects"]
    assert len(objs) == 6

    # Verify positions (x, y, w, h) from draft are PRESERVED
    assert objs[0]["x"] == 15 and objs[0]["y"] == 20
    assert objs[1]["x"] == 65 and objs[1]["y"] == 20
    assert objs[2]["x"] == 115 and objs[2]["y"] == 20
    assert objs[3]["x"] == 115 and objs[3]["y"] == 70
    assert objs[4]["x"] == 65 and objs[4]["y"] == 70
    assert objs[5]["x"] == 15 and objs[5]["y"] == 70

    # Verify types are enriched to cell with distinctive states
    assert objs[0]["state"] == "interphase" and objs[0]["type"] == "cell"
    assert objs[1]["state"] == "prophase" and objs[1]["type"] == "cell"
    assert objs[2]["state"] == "metaphase" and objs[2]["type"] == "cell"
    assert objs[3]["state"] == "anaphase" and objs[3]["type"] == "cell"
    assert objs[4]["state"] == "telophase" and objs[4]["type"] == "cell"
    assert objs[5]["state"] == "cytokinesis" and objs[5]["type"] == "cell"

    # Verify no engineering jargon leaked
    svg = doc["svg"]
    for bad in ("LATENT", "PRIORS", "u_mitosis", "SENSING", "ROBOTIC", "X-NET"):
        assert bad not in svg

    # Verify that cells can be dragged/moved on canvas
    code, moved = studio(f"/api/jobs/{new_job_id}/scene", {
        "base_revision": doc["revision"],
        "operations": [
            {"op": "update", "id": "c1", "changes": {"x": 22, "y": 25, "label": "G1/S 间期"}}
        ]
    }, "PATCH")
    assert code == 200
    assert moved["scene"]["objects"][0]["x"] == 22
    assert moved["scene"]["objects"][0]["label"] == "G1/S 间期"

    # Export to PPTX
    code, pptx_res = studio(f"/api/jobs/{new_job_id}/save-as", {
        "format": "pptx",
        "revision": moved["revision"]
    })
    assert code == 200
    assert Path(pptx_res["path"]).exists()
