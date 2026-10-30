"""Regression tests for the server architecture fixes.

Run with: python -m pytest tests/test_architecture.py -q
"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
from email.message import Message
from pathlib import Path

import app_server
import framework
import assist_guide
import layout_contract


class ConfigTests(unittest.TestCase):
    def test_font_uses_top_level_and_syncs_legacy_copy(self):
        cfg = app_server.normalize_config({"font": "Arial", "qa": {"font": "Times"}})
        self.assertEqual(cfg["font"], "Arial")
        self.assertEqual(cfg["qa"]["font"], "Arial")

    def test_font_falls_back_to_legacy_copy(self):
        cfg = app_server.normalize_config({"qa": {"font": "SimSun"}})
        self.assertEqual(cfg["font"], "SimSun")

    def test_malformed_sections_do_not_crash(self):
        cfg = app_server.normalize_config({
            "text": None, "image": "nope", "vision": 3, "qa": "x",
            "vectorize": [], "inpaint": None, "canvas": "bad", "ocr": "auto",
        })
        self.assertEqual(cfg["text"], {})
        self.assertIn("size", cfg["image"])
        self.assertEqual(cfg["vision"], {})
        self.assertEqual(cfg["canvas"], [1280, 900])
        self.assertEqual(cfg["ocr"]["mode"], "auto")

    def test_tiny_canvas_is_replaced(self):
        cfg = app_server.normalize_config({"canvas": [10, 10], "canvas_user": True})
        self.assertEqual(cfg["canvas"], [1280, 900])

    def test_default_illustration_mode_is_canonical(self):
        self.assertEqual(app_server.normalize_config({})["illustration_mode"], "image")
        cfg = app_server.normalize_config({
            "default_illustration_mode": "vector",
            "illustration_mode": "image",
        })
        self.assertEqual(cfg["default_illustration_mode"], "vector")
        self.assertEqual(cfg["illustration_mode"], "vector")
        legacy = app_server.normalize_config({"illustration_mode": "vector"})
        self.assertEqual(legacy["default_illustration_mode"], "vector")

    def test_ui_aliases_are_migrated_and_removed(self):
        cfg = app_server.normalize_config({
            "text_model": {"base_url": "http://x/v1", "model": "m"},
            "image_model": {"base_url": "http://i/v1", "model": "im"},
            "vision_model": {"base_url": "http://v/v1", "model": "vm"},
        })
        self.assertEqual(cfg["text"]["model"], "m")
        self.assertEqual(cfg["image"]["model"], "im")
        self.assertEqual(cfg["vision"]["model"], "vm")
        for alias in ("text_model", "image_model", "vision_model"):
            self.assertNotIn(alias, cfg)

    def test_public_config_never_returns_api_keys(self):
        raw = app_server.normalize_config({
            "text": {"base_url": "http://x/v1", "model": "m", "api_key": "secret-1"},
            "image": {"base_url": "http://x/v1", "model": "i", "api_key": "secret-2"},
            "vision": {"base_url": "http://x/v1", "model": "v"},
        })
        public = app_server.public_config(raw)
        blob = json.dumps(public, ensure_ascii=False)
        self.assertNotIn("secret-1", blob)
        self.assertNotIn("secret-2", blob)
        self.assertEqual(public["text"]["api_key"], "")
        self.assertTrue(public["text"]["api_key_set"])
        self.assertFalse(public["vision"]["api_key_set"])
        # Masking must not mutate the stored config.
        self.assertEqual(raw["text"]["api_key"], "secret-1")

    def test_deep_merge_preserves_unmentioned_nested_keys(self):
        base = {"text": {"base_url": "http://x", "api_key": "k", "model": "m"},
                "qa": {"max_diff": 0.5}}
        merged = app_server._deep_merge(base, {"text": {"model": "m2"},
                                               "qa": {"max_diff": 0.7}})
        self.assertEqual(merged["text"]["base_url"], "http://x")
        self.assertEqual(merged["text"]["api_key"], "k")
        self.assertEqual(merged["text"]["model"], "m2")
        self.assertEqual(merged["qa"]["max_diff"], 0.7)

    def test_font_is_stripped_of_svg_breakers(self):
        cfg = app_server.normalize_config({"font": 'Bad" onload="x'})
        self.assertNotIn('"', cfg["font"])
        self.assertNotIn("=", cfg["font"])
        self.assertEqual(cfg["qa"]["font"], cfg["font"])

    def test_style_colors_are_whitelisted(self):
        style = app_server.sanitize_style({
            "archetype": "closed_loop",
            "palette": {"primary": "#112233", "accent": 'red" onload="x'},
        })
        self.assertEqual(style["palette"], {"primary": "#112233"})
        self.assertEqual(style["archetype"], "closed_loop")
        self.assertEqual(app_server.sanitize_style("bad"), {})

    def test_audit_gap_is_not_a_figure_defect(self):
        self.assertTrue(app_server._audit_gap([
            {"kind": "vision-unavailable", "severity": "high", "message": "x"}]))
        self.assertFalse(app_server._audit_gap([
            {"kind": "vision", "severity": "high", "message": "x"}]))


class JobPathTests(unittest.TestCase):
    def setUp(self):
        self._old = app_server.JOBS_DIR
        self._tmp = tempfile.TemporaryDirectory()
        app_server.JOBS_DIR = Path(self._tmp.name)

    def tearDown(self):
        app_server.JOBS_DIR = self._old
        self._tmp.cleanup()

    def test_rejects_traversal_and_absolute_ids(self):
        for bad in ("../escape", "a/b", r"C:\Windows", "..", "", "x" * 80, "a b"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    app_server.job_paths(bad)

    def test_accepts_generated_ids(self):
        path = app_server.job_paths("j_abc123-XYZ")
        self.assertTrue(path.is_dir())
        self.assertEqual(path.parent, Path(self._tmp.name))

    def test_save_meta_is_atomic_under_concurrency(self):
        job = {"id": "j_concurrent", "status": "completed", "blob": "x" * 5000}
        errors = []

        def writer(index):
            try:
                for _ in range(25):
                    job["index"] = index
                    app_server._save_meta(job)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        meta = json.loads((Path(self._tmp.name) / "j_concurrent" / "meta.json")
                          .read_text(encoding="utf-8"))
        self.assertEqual(meta["id"], "j_concurrent")
        leftovers = list((Path(self._tmp.name) / "j_concurrent").glob("*.tmp"))
        self.assertEqual(leftovers, [])


class LayoutTests(unittest.TestCase):
    def test_missing_boxes_are_filled_without_moving_existing(self):
        spec = {"canvas": [1000, 700], "entities": [
            {"id": "a", "bbox": [100, 100, 200, 120]},
            {"id": "b"},
        ]}
        app_server.fill_missing_boxes(spec)
        self.assertEqual(spec["entities"][0]["bbox"], [100, 100, 200, 120])
        self.assertEqual(len(spec["entities"][1]["bbox"]), 4)
        self.assertGreater(spec["entities"][1]["bbox"][0], 0)

    def test_fully_unplaced_spec_is_left_for_arrange(self):
        spec = {"canvas": [1000, 700], "entities": [{"id": "a"}, {"id": "b"}]}
        app_server.fill_missing_boxes(spec)
        self.assertNotIn("bbox", spec["entities"][0])

    def test_row_layout_spans_the_canvas(self):
        import compose
        scene = {"canvas": [1200, 600], "layout": "row",
                 "entities": [{"id": f"e{i}", "label": f"Step {i}"} for i in range(3)]}
        placed = compose.arrange(scene)
        ys = [e["bbox"][1] for e in placed["entities"]]
        xs = [e["bbox"][0] for e in placed["entities"]]
        self.assertEqual(len(set(ys)), 1)
        self.assertLess(min(xs), 100)
        self.assertGreater(max(xs), 700)

    def test_icon_prompts_produce_distinct_glyphs(self):
        entities = [
            {"label": "Sample preparation", "prompt": "microcentrifuge tube and pipette"},
            {"label": "Separation", "prompt": "chromatographic column with bands"},
            {"label": "Detection", "prompt": "benchtop detector with a peak trace"},
            {"label": "Tumor cell", "prompt": "cell with nucleus and receptors"},
        ]
        glyphs = {framework.entity_glyph(e, 50, 50, 78, "#3F5A6B") for e in entities}
        self.assertEqual(len(glyphs), len(entities))

    def test_repair_scene_keeps_icon_and_layout_metadata(self):
        import compose
        scene = {
            "canvas": [1200, 600], "lock_layout": True, "layout": "row",
            "entities": [{
                "id": "a", "label": "Sample preparation",
                "prompt": "microcentrifuge tube", "glyph": "tube",
                "bbox": [60, 80, 400, 180], "label_dx": 3, "label_dy": -2,
            }],
            "connectors": [],
        }
        repaired = compose.repair_scene(scene, {"canvas": [1200, 600], "canvas_user": True})
        entity = repaired["entities"][0]
        self.assertEqual(entity["prompt"], "microcentrifuge tube")
        self.assertEqual(entity["glyph"], "tube")
        self.assertEqual(entity["label_dx"], 3)
        self.assertTrue(repaired["lock_layout"])


class PromptFixTests(unittest.TestCase):
    def setUp(self):
        self._old_jobs = app_server.JOBS_DIR
        self._tmp = tempfile.TemporaryDirectory()
        app_server.JOBS_DIR = Path(self._tmp.name)

    def tearDown(self):
        app_server.JOBS_DIR = self._old_jobs
        self._tmp.cleanup()

    def test_source_config_keeps_canvas_and_mode(self):
        cfg = app_server._inherit_source_config({}, {
            "canvas": [1200, 600], "canvas_user": False,
            "illustration_mode": "vector", "font": "Arial",
            "style_dna": {"palette": {"primary": "#112233"}},
        })
        self.assertEqual(cfg["canvas"], [1200, 600])
        self.assertTrue(cfg["canvas_user"])
        self.assertEqual(cfg["illustration_mode"], "vector")
        self.assertEqual(cfg["font"], "Arial")

    def test_prompt_autofix_uses_the_audit_instruction(self):
        captured = {}
        old_run, old_revise = app_server._run_job, app_server._revise_text
        app_server._run_job = lambda job, text, cfg: captured.update(
            text=text, canvas=cfg.get("canvas"), mode=cfg.get("illustration_mode"))
        app_server._revise_text = lambda text, instruction, cfg: "REWRITTEN: " + instruction
        job = {"id": "j_promptfix", "status": "queued", "stages": []}
        source = {"id": "j_src", "text": "old brief", "report": {"mode": "plan"},
                  "canvas": [900, 700], "illustration_mode": "vector"}
        try:
            app_server._run_autofix(job, source, "fix the arrows", {})
        finally:
            app_server._run_job, app_server._revise_text = old_run, old_revise
        self.assertIn("fix the arrows", captured["text"])
        self.assertEqual(captured["canvas"], [900, 700])
        self.assertEqual(captured["mode"], "vector")


class PromptGuardTests(unittest.TestCase):
    def test_model_cannot_switch_signal_pathway_to_closed_loop(self):
        self.assertTrue(assist_guide._contradicts_layout(
            "采用闭环反馈回路", "signal_pathway", "4:3"))
        self.assertTrue(assist_guide._contradicts_layout(
            "A closed-loop feedback system", "signal_pathway", "4:3"))
        self.assertFalse(assist_guide._contradicts_layout(
            "left-to-right S-shaped signaling pathway", "signal_pathway", "4:3"))

    def test_template_keeps_requested_horizontal_s_layout(self):
        note = assist_guide._layout_note("画成左到右轻微 S 形流程", "signal_pathway")
        self.assertIn("S 形", note)
        self.assertIn("左到右", note)


class LayoutContractTests(unittest.TestCase):
    original = ("细胞外囊泡调控软骨修复的信号通路，画成左到右轻微 S 形流程，4:3 横版。"
                "主路径：Ligand secretion → Membrane receptor binding → "
                "Intracellular kinase cascade → Transcription factor nuclear entry → "
                "Cartilage matrix synthesis phenotype。")

    def test_author_contract_beats_rewritten_prompt(self):
        contract = layout_contract.build(self.original, "采用 closed-loop 闭环版式，纵向排列")
        self.assertEqual(contract["archetype"], "signal_pathway")
        self.assertEqual(contract["layout"], "horizontal_s")
        self.assertEqual(contract["ratio"], "4:3")
        self.assertGreaterEqual(len(contract["stages"]), 5)
        self.assertFalse(contract["mentions_feedback"])

    def test_wrong_template_is_a_high_finding(self):
        contract = layout_contract.build(self.original, "")
        findings = layout_contract.adherence_findings(
            contract, {"framework": True, "spec": {"layout": "vertical"}},
            ["A · SENSING", "B · INFERENCE", "C · ACTUATION"],
            lambda kind, severity, message, suggestion: {
                "kind": kind, "severity": severity, "message": message,
                "suggestion": suggestion})
        self.assertGreaterEqual(len(findings), 2)
        self.assertTrue(all(f["severity"] == "high" for f in findings))
        self.assertTrue(any("框架" in f["message"] or "布局" in f["message"]
                            for f in findings))


class _FakeServer:
    def __init__(self, port):
        self.server_address = ("127.0.0.1", port)


class OriginTests(unittest.TestCase):
    def handler(self, host, origin=None):
        handler = object.__new__(app_server.Handler)
        handler.headers = Message()
        if host is not None:
            handler.headers["Host"] = host
        if origin is not None:
            handler.headers["Origin"] = origin
        handler.server = _FakeServer(8777)
        return handler

    def test_accepts_same_origin(self):
        self.assertTrue(self.handler("127.0.0.1:8777")._origin_allowed())
        self.assertTrue(self.handler("localhost:8777", "http://localhost:8777")
                        ._origin_allowed())

    def test_rejects_foreign_host_and_origin(self):
        self.assertFalse(self.handler("evil.example:8777")._origin_allowed())
        self.assertFalse(self.handler("127.0.0.1:8777", "http://evil.example")
                         ._origin_allowed())
        self.assertFalse(self.handler(None)._origin_allowed())


if __name__ == "__main__":
    unittest.main()
