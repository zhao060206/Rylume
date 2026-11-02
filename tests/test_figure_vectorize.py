"""High-fidelity raster import keeps paths editable and never embeds a bitmap."""
import base64
import io

from PIL import Image, ImageDraw, ImageFont

import figure_vectorize as vector
from scene_render import render_scene
from test_figure_imports import ready, upload
from test_scene_api import studio


def sample_png():
    image = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((35, 55, 145, 125), radius=8, fill="#DDEBEB", outline="#315D69", width=2)
    draw.line((145, 90, 255, 90), fill="#315D69", width=3)
    draw.polygon(((255, 90), (242, 83), (242, 97)), fill="#315D69")
    draw.rounded_rectangle((255, 55, 370, 125), radius=8, fill="#EDF0DD", outline="#657047", width=2)
    font = ImageFont.truetype("arial.ttf", 18)
    draw.text((57, 79), "Input", font=font, fill="#17252A")
    draw.text((276, 79), "Output", font=font, fill="#17252A")
    out = io.BytesIO(); image.save(out, format="PNG")
    return out.getvalue()


def observation():
    return {"objects": [
        {"id": "input_text", "kind": "text", "label": "Input", "x": .13, "y": .37, "w": .18, "h": .15, "fill": "#17252A", "font_size_pt": 9},
        {"id": "output_text", "kind": "text", "label": "Output", "x": .68, "y": .37, "w": .18, "h": .15, "fill": "#17252A", "font_size_pt": 9},
    ]}, "vision", []


def test_raster_becomes_ordered_vector_groups_and_real_text(monkeypatch):
    monkeypatch.setattr(vector, "_observation", lambda *args: observation())
    scene, report = vector.reconstruct(sample_png(), "sample.png", {})
    assert report["source_paths"] == report["vector_paths"] > 0
    assert report["removed_text_regions"] == 2 and report["texts"] == 2
    assert report["raster_embedded"] is False
    groups = [o for o in scene["objects"] if o["role"] == "context"]
    assert len(groups) == report["vector_groups"]
    assert all(o.get("asset_snapshot") and not o.get("illustration") for o in groups)
    assert [o["label"] for o in scene["objects"] if o["type"] == "text"] == ["Input", "Output"]
    svg = render_scene(scene)
    assert "<image" not in svg and "Input" in svg and "Output" in svg
    quality = vector.fidelity_report(sample_png(), svg)
    assert quality["available"] and quality["foreground_similarity"] >=99
    assert report['outline_labels']==2
    assert 'native_resolution' in quality['method']


def test_vector_mode_runs_through_real_candidate_api(studio, monkeypatch):
    monkeypatch.setattr(vector, "_observation", lambda *args: observation())
    row = upload(studio, sample_png(), "Raster figure.png")
    endpoint = "/api/figure-imports/" + row["id"]
    studio(endpoint + "/convert", {"mode": "vector"})
    row = ready(studio, row["id"])
    assert row["state"] == "ready", row
    _, candidate = studio(endpoint + "/candidate")
    assert candidate["report"]["image_blocks"] == 0
    assert candidate["report"]["vector_paths"] > 0
    assert candidate["report"]["fidelity"]["foreground_similarity"] >=99
    assert "<image" not in candidate["svg"]
    _, accepted = studio(endpoint + "/accept", {"run": candidate["run"]})
    _, document = studio("/api/jobs/" + accepted["job_id"] + "/scene")
    target = next(o for o in document["scene"]["objects"] if o["id"] == "input_text")
    code, changed = studio("/api/jobs/" + accepted["job_id"] + "/scene", {
        "base_revision": 1, "operations": [{"op": "update", "id": target["id"], "changes": {"label": "Editable input"}}]}, "PATCH")
    assert code == 200 and "Editable input" in changed["svg"]
    from scene_render import uses_text_appearance
    edited=next(o for o in changed['scene']['objects'] if o['id']=='input_text')
    unchanged=next(o for o in changed['scene']['objects'] if o['id']=='output_text')
    assert not uses_text_appearance(edited) and uses_text_appearance(unchanged)
    assert '<text ' in changed['svg']


def test_local_ocr_fallback_has_boxes_and_does_not_need_a_model(monkeypatch):
    class Engine:
        def __call__(self, image):
            row = [[[50, 60], [140, 60], [140, 90], [50, 90]], "Input", .96]
            return [row], None
    monkeypatch.setattr("text_ocr._get_engine", lambda: Engine())
    value, warnings = vector.local_text_observation(sample_png())
    assert value["objects"][0]["label"] == "Input"
    assert 0 < value["objects"][0]["x"] < value["objects"][0]["w"] < 1
    assert warnings == []


def test_below_target_candidate_cannot_be_accepted(studio,monkeypatch):
    monkeypatch.setattr(vector,'_observation',lambda *args:observation())
    monkeypatch.setattr(vector,'fidelity_report',lambda *args:{'available':True,'foreground_similarity':98.9,'target_met':False})
    row=upload(studio,sample_png(),'Below-target.png');endpoint='/api/figure-imports/'+row['id']
    studio(endpoint+'/convert',{'mode':'vector'});row=ready(studio,row['id'])
    assert row['state']=='ready'
    code,result=studio(endpoint+'/accept',{'run':row['run']})
    assert code==400 and '99%' in result['error']
    assert not studio('/api/jobs')[1]['jobs']


def test_local_residual_corrections_reject_a_grossly_wrong_trace():
    import pytest
    from vector_fidelity import correction_paths
    source=io.BytesIO();Image.new('RGB',(100,100),'red').save(source,format='PNG')
    wrong='<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="blue"/></svg>'
    with pytest.raises(ValueError,match='差异过大'):
        correction_paths(source.getvalue(),wrong)
