"""Tests for scene_render: layouts, connection geometry, glyphs, and rendering."""
import math
from scene_document import empty_scene
from scene_examples import make_example
import scene_render


def test_example_layouts_and_rendering():
    for ex_id in ["egfr", "jak_stat", "tgf_smad", "exosome", "wound", "tme", "nlrp3", "workflow"]:
        scene = make_example(ex_id, width_mm=180, height_mm=120)
        svg = scene_render.render_scene(scene)
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        assert f'viewBox="0 0 {scene["canvas"]["width_mm"]} {scene["canvas"]["height_mm"]}"' in svg
        # Objects and relations should have IDs embedded
        for obj in scene["objects"]:
            if obj.get("visible", True):
                assert f'data-object-id="{obj["id"]}"' in svg
        for rel in scene["relations"]:
            assert f'data-relation-id="{rel["id"]}"' in svg


def test_connection_geometry_ports_and_vectors():
    scene = empty_scene()
    scene["objects"] = [
        {"id": "lig1", "type": "ligand", "label": "EGF", "x": 50, "y": 10, "w": 14, "h": 10},
        {"id": "rec1", "type": "receptor", "label": "EGFR", "x": 48, "y": 30, "w": 18, "h": 20},
        {"id": "kin1", "type": "kinase", "label": "AKT", "x": 90, "y": 60, "w": 18, "h": 14},
    ]
    # Ligand above receptor should automatically use south-to-north ports
    rel1 = {"id": "r1", "source": "lig1", "target": "rec1", "type": "binds"}
    g1 = scene_render.connection_geometry(scene, rel1)
    assert g1["y1"] == 20.0  # south port of lig1 (10 + 10)
    assert g1["y2"] == 30.0  # north port of rec1 (30)
    assert math.isclose(g1["x1"], 57.0)  # center x of lig1
    assert math.isclose(g1["x2"], 57.0)  # center x of rec1

    # Kinase to right should use east-to-west
    rel2 = {"id": "r2", "source": "rec1", "target": "kin1", "type": "activates"}
    g2 = scene_render.connection_geometry(scene, rel2)
    assert g2["x1"] == 48 + 18  # east of rec1
    assert g2["x2"] == 90  # west of kin1


def test_narrow_canvas_reflow():
    # 90mm width single column reflow
    scene = make_example("jak_stat", width_mm=90, height_mm=150)
    assert scene["canvas"]["width_mm"] == 90
    assert scene["canvas"]["height_mm"] == 150
    # Membrane compartment should fit within 90mm
    membrane = next((c for c in scene["compartments"] if c["id"] == "membrane"), None)
    if membrane:
        assert membrane["w"] <= 90
    svg = scene_render.render_scene(scene)
    assert "90" in svg and "150" in svg and "viewBox" in svg


def test_repair_geometry():
    scene = empty_scene()
    # Create two slightly overlapping objects
    scene["objects"] = [
        {"id": "o1", "type": "protein", "label": "A", "x": 50, "y": 50, "w": 20, "h": 14},
        {"id": "o2", "type": "protein", "label": "B", "x": 55, "y": 52, "w": 20, "h": 14},
    ]
    repaired = scene_render.repair_geometry(scene, passes=2)
    # Positions should have nudged to reduce overlap
    assert repaired["objects"][0]["x"] != repaired["objects"][1]["x"]
