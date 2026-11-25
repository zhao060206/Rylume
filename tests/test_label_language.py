"""Step 8: one label language per figure, and supplemented structure objects are marked."""
import json
import pathlib

import scene_planner
from scene_document import empty_scene, normalize_scene

CONFIG = {"text": {"model": "fake", "base_url": "unused"}}
ZH_TEXT = "EGF 结合 EGFR，随后激活 RAS"


def _spec(rel_label="binding", extra_objects=()):
    return {"title": "信号", "layout": "network", "compartments": [],
            "objects": [{"id": "egf", "type": "protein", "label": "EGF", "evidence": "EGF"},
                        {"id": "egfr", "type": "protein", "label": "EGFR", "evidence": "EGFR"},
                        {"id": "ras", "type": "protein", "label": "RAS", "evidence": "RAS"},
                        *extra_objects],
            "relations": [{"id": "r1", "source": "egf", "target": "egfr", "type": "binds",
                           "label": rel_label, "evidence": "结合"},
                          {"id": "r2", "source": "egfr", "target": "ras", "type": "activates",
                           "label": "激活", "evidence": "激活"}],
            "unresolved": []}


def _plan(monkeypatch, spec, text=ZH_TEXT, config=CONFIG):
    seen = []

    def fake(cfg, messages, *a, **k):
        seen.append(json.loads(messages[1]["content"]))
        return json.loads(json.dumps(spec)), 0.1

    monkeypatch.setattr(scene_planner, "_request", fake)
    scene, info = scene_planner.plan_scene(text, config)
    return scene, info, seen


def _language_notes(scene):
    return [u for u in scene["unresolved"] if u.startswith("标签语言不统一")]


def test_mixed_language_plan_reports_language_note(monkeypatch):
    scene, _, seen = _plan(monkeypatch, _spec("binding"))
    notes = _language_notes(scene)
    assert len(notes) == 1 and "binding" in notes[0] and "中文" in notes[0]
    # Symbols such as EGFR / RAS are never counted as English labels.
    assert "EGFR" not in notes[0] and "RAS" not in notes[0]
    assert seen[0]["label_language"] == "zh"
    # The note only reports; labels are not auto-translated.
    assert {r["id"]: r.get("label") for r in scene["relations"]}["r1"] == "binding"


def test_consistent_language_plan_has_no_note(monkeypatch):
    scene, _, _ = _plan(monkeypatch, _spec("结合"))
    assert not _language_notes(scene)


def test_config_label_language_overrides_text(monkeypatch):
    scene, _, seen = _plan(monkeypatch, _spec("结合"), config={**CONFIG, "label_language": "en"})
    assert seen[0]["label_language"] == "en"
    notes = _language_notes(scene)
    assert len(notes) == 1 and "英文" in notes[0] and "激活" in notes[0]


def test_target_language_detection():
    assert scene_planner._target_label_language(ZH_TEXT, {}) == "zh"
    assert scene_planner._target_label_language("EGF binds EGFR and activates RAS", {}) == "en"
    for symbol in ("EGFR", "PI3K", "mTORC1", "p-ERK", "Ras", "Wnt", "Myc"):
        assert scene_planner._label_language(symbol) is None, symbol
    for word in ("binding", "Cytoplasm", "EGF binding"):
        assert scene_planner._label_language(word) == "en", word


def test_supplemented_structure_is_marked_without_retry(monkeypatch):
    pore = {"id": "pore", "type": "nuclear_pore", "label": "核孔", "evidence": ""}
    scene, info, seen = _plan(monkeypatch, _spec("结合", [pore]))
    assert info["attempts"] == 1 and len(seen) == 1
    objects = {o["id"]: o for o in scene["objects"]}
    assert objects["pore"].get("supplement") is True
    assert not any(objects[i].get("supplement") for i in ("egf", "egfr", "ras"))
    assert any(u.startswith("补充对象") and "核孔" in u for u in scene["unresolved"])
    assert not any("核孔 缺少可定位的原文依据" in u for u in scene["unresolved"])


def test_model_supplement_flag_is_dropped_when_text_supports_object(monkeypatch):
    spec = _spec("结合")
    spec["objects"][0]["supplement"] = True
    scene, _, _ = _plan(monkeypatch, spec)
    assert not {o["id"]: o for o in scene["objects"]}["egf"].get("supplement")


def test_normalize_keeps_only_boolean_supplement():
    scene = empty_scene(source_text="A", width_mm=180, height_mm=120)
    scene["objects"] = [{"id": "a", "type": "protein", "label": "A", "x": 10, "y": 10, "w": 20, "h": 10,
                         "supplement": True},
                        {"id": "b", "type": "protein", "label": "B", "x": 50, "y": 10, "w": 20, "h": 10,
                         "supplement": "yes"}]
    out = {o["id"]: o for o in normalize_scene(scene)["objects"]}
    assert out["a"].get("supplement") is True
    assert "supplement" not in out["b"]


def test_prompt_and_layer_panel_expose_the_rules():
    assert "不要中英混用" in scene_planner.PLANNER_INSTRUCTION
    assert '"supplement":true' in scene_planner.PLANNER_INSTRUCTION
    assert "默认短英文标签" not in scene_planner.PLANNER_INSTRUCTION
    root = pathlib.Path(__file__).resolve().parents[1] / "ui"
    app = (root / "canvas-app.js").read_text(encoding="utf-8")
    assert "layer-supplement" in app and "op:'remove',id:o.id" in app
    for css in ("studio.css", "workbench-ui.css"):
        assert ".layer-supplement" in (root / css).read_text(encoding="utf-8")
