"""Cell Figure Studio - local desktop app server.

Serves the OpenDesign-generated UI and wraps pipeline.py behind a small JSON API.

  GET  /api/state
  POST /api/config
  POST /api/test            {"target": "text"|"image"|"ocr"}
  POST /api/generate        {"text": "...", "mode": "plan"}
  GET  /api/jobs
  GET  /api/jobs/{id}
  GET  /api/jobs/{id}/svg
  GET  /api/jobs/{id}/download?format=svg|png
  POST /api/open-config-dir
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import math
import os
import re
import sys
import threading
import time
import traceback
import urllib.request
import uuid
import webbrowser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import layout_contract
import pipeline
import qa
import review
import skill_bridge
import scene_service
from studio_storage import get_data_dir

from product_identity import PRODUCT_DISPLAY, PRODUCT_VERSION, WINDOW_TITLE
import onboarding_state
import document_assistant

APP_VERSION = PRODUCT_VERSION

FROZEN = getattr(sys, "frozen", False)
BASE_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
DATA_DIR = get_data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
JOBS_DIR = DATA_DIR / "studio-jobs"
EXPORT_DIR = DATA_DIR / "exports"
UI_DIR = BUNDLE_DIR / "ui"

MODES = [
    {"id": "placeholder", "name": "占位测试", "hint": "不调用模型，验证流程与导出"},
    {"id": "plan", "name": "布局规划", "hint": "模型出布局 JSON，原生文字可编辑"},
    {"id": "svg", "name": "直出 SVG", "hint": "模型直接写 SVG，适合简单框图"},
    {"id": "image", "name": "生图 + 矢量化", "hint": "生图、OCR、去字、矢量化、回填"},
]

STAGE_PLANS = {
    # research is part of the auto pipeline when literature is enabled; listed
    # here so the UI shows it in the right order instead of appended last.
    "auto": ["start", "research", "plan_scene", "generate", "assemble", "qa"],
    "compose": ["start", "research", "plan_scene", "generate", "assemble", "qa"],
    "placeholder": ["start", "render"],
    "svg": ["start", "svg", "validate"],
    "plan": ["start", "plan", "render"],
    "image": ["start", "generate", "ocr", "remove_text", "vectorize",
              "inject_text", "cleanup", "merge", "qa"],
}

STAGE_WEIGHTS = {
    "start": 2, "research": 12, "plan_scene": 10, "generate": 55, "assemble": 15, "qa": 10,
    "ocr": 7, "remove_text": 5, "vectorize": 12,
    "inject_text": 5, "cleanup": 2, "merge": 2,
    "plan": 60, "render": 35, "svg": 85, "validate": 10,
}

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
PPT_START_LOCK = threading.Lock()
SERVER: ThreadingHTTPServer | None = None
SAVE_LOCK = threading.Lock()
LAST_SAVE_DIR: str | None = None
SAVED_PATHS: set[str] = set()
REVIEW_VERSION = review.VERSION


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "429" in text:
        return "模型服务太忙（429），请稍等一会儿，点「再试一次」"
    if "503" in text or "Service Unavailable" in text:
        return "生图服务暂时不可用（503）。请稍后点「再试一次」；若要马上绘图，可切到「矢量可编辑」。"
    if "生图服务不可用" in text or isinstance(exc, pipeline.ImageServiceError):
        return "生图服务连不上（连接被拒绝或上游报错）。请确认生图服务已启动后点「再试一次」；若要马上出图，可切到「矢量可编辑」。"
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "模型响应超时，请点「再试一次」"
    if "HTTP 400" in text or "HTTP Error 400" in text:
        return "生图请求被拒绝（400）。请稍后重试；若持续失败，请切到「矢量可编辑」。"
    return f"{type(exc).__name__}: {text}"[:300]


def _vision_unavailable(exc: Exception) -> dict:
    """Audit-gap note: the vision model could not run this round.

    This is not a figure defect, but it must never be reported as a clean
    audit either: the job ends "unverified" and cannot be accepted until a
    model-backed recheck succeeds."""
    return {
        "kind": "vision-unavailable",
        "severity": "high",
        "message": f"视觉模型审查未执行：{type(exc).__name__}: {exc}"[:300],
        "suggestion": "在设置中检查视觉模型的 Base URL / Model / API Key，然后重新审查",
    }


def _audit_gap(findings: list[dict]) -> bool:
    return any(f.get("kind") == "vision-unavailable" for f in findings)


class StudioHTTPServer(ThreadingHTTPServer):
    """On Windows SO_REUSEADDR lets two processes bind one address, so a
    stale zombie silently swallows every request. Fail the bind instead and
    let main() probe the port and pick the next one."""
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


# ------------------------------------------------------------------ config


def _dict_or_empty(value) -> dict:
    return dict(value) if isinstance(value, dict) else {}


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def sanitize_style(style) -> dict:
    """Keep only render-safe colour values from model/reference DNA."""
    if not isinstance(style, dict):
        return {}
    out = dict(style)
    palette = out.get("palette")
    if isinstance(palette, dict):
        clean = {k: v for k, v in palette.items()
                 if isinstance(v, str) and HEX_COLOR_RE.fullmatch(v)}
        if clean:
            out["palette"] = clean
        else:
            out.pop("palette", None)
    elif palette is not None:
        out.pop("palette", None)
    return out


def normalize_config(config: dict) -> dict:
    """Accept both config schemas and never crash on a malformed section."""
    if not isinstance(config, dict):
        config = {}
    for key in ("qa", "vectorize", "inpaint"):
        config[key] = _dict_or_empty(config.get(key))
    # UI aliases -> canonical sections (canonical wins when both exist)
    for canonical, alias in (("text", "text_model"), ("image", "image_model"),
                             ("vision", "vision_model")):
        value = config.get(canonical)
        if not isinstance(value, dict) or not value:
            value = config.get(alias)
        config[canonical] = _dict_or_empty(value)
        config.pop(alias, None)

    ocr_value = config.get("ocr")
    if isinstance(ocr_value, str):
        mode = ocr_value.strip().lower()
        config["ocr"] = {"mode": "off" if mode == "off" else "auto"}
    else:
        config["ocr"] = _dict_or_empty(ocr_value)

    quality_value = str(config.get("quality") or "hd").lower()
    if quality_value in ("high", "hd", "高清"):
        quality_value = "hd"
    elif quality_value in ("standard", "fast", "标准"):
        quality_value = "standard"
    else:
        quality_value = "hd"
    config["quality"] = quality_value

    qa = config["qa"]
    # config["font"] is authoritative; qa.font is only the legacy copy.
    font = str(config.get("font") or qa.get("font") or "Times New Roman")
    font = re.sub(r'[^A-Za-z0-9 \-,._\u4e00-\u9fff]', "", font).strip()[:80] or "Times New Roman"
    config["font"] = font
    qa["font"] = font

    incoming_canvas = config.get("canvas")
    try:
        if isinstance(incoming_canvas, (list, tuple)) and len(incoming_canvas) >= 2:
            width, height = int(incoming_canvas[0]), int(incoming_canvas[1])
            if width < 200 or height < 200:
                raise ValueError("canvas too small")
            config["canvas"] = [width, height]
            # Do not force canvas_user here: only an explicit user choice
            # should pin the canvas, otherwise saving settings freezes the
            # per-renderer defaults.
            config.setdefault("canvas_user", bool(config.get("canvas_user")))
            qa["canvas_width"], qa["canvas_height"] = width, height
        elif qa.get("canvas_width") and qa.get("canvas_height"):
            config["canvas"] = [int(qa["canvas_width"]), int(qa["canvas_height"])]
        else:
            config["canvas"] = [1280, 900]
            qa["canvas_width"], qa["canvas_height"] = 1280, 900
    except (TypeError, ValueError):
        config["canvas"] = [1280, 900]
        qa["canvas_width"], qa["canvas_height"] = 1280, 900

    image = config["image"]
    if not image.get("size"):
        image["size"] = "1536x1024" if quality_value == "hd" else "1024x1024"
    qa.setdefault("max_diff", 0.45)
    qa.setdefault("min_path_area", 6)
    vec = config["vectorize"]
    vec.setdefault("engine", "hifi")
    vec.setdefault("colors", 32 if quality_value == "hd" else 24)
    vec.setdefault("speckle", 40)
    vec.setdefault("epsilon", 0.8)
    vec.setdefault("max_side", 1600)
    config["inpaint"] = _dict_or_empty(config.get("inpaint"))
    config["inpaint"].setdefault("radius", 7)

    ocr = config["ocr"]
    ocr_mode = str(ocr.get("mode") or "").lower()
    if ocr_mode not in ("auto", "off"):
        ocr_mode = "off" if ocr.get("provider") == "none" else "auto"
    ocr["mode"] = ocr_mode
    if ocr_mode == "off":
        ocr["provider"] = "none"
    elif ocr.get("provider") not in ("paddle", "vision"):
        text_cfg = config["text"]
        has_ocr_model = bool(ocr.get("base_url") and ocr.get("model"))
        has_text_model = bool(text_cfg.get("base_url") and text_cfg.get("model"))
        ocr["provider"] = "vision" if (has_ocr_model or has_text_model) else "none"
    render_mode = str(config.get("render_mode") or "compose").lower()
    config["render_mode"] = render_mode if render_mode in ("compose", "fidelity", "vector") else "compose"
    if "style_dna" in config:
        config["style_dna"] = sanitize_style(config.get("style_dna"))
    profile = config.get("style_profile")
    if isinstance(profile, dict):
        colors = [c for c in (profile.get("palette") or [])
                  if isinstance(c, str) and HEX_COLOR_RE.fullmatch(c)]
        if colors:
            profile["palette"] = colors
        else:
            profile.pop("palette", None)
    config.setdefault("mode", "auto")
    if not config.get("default_illustration_mode"):
        config["default_illustration_mode"] = (
            "vector" if str(config.get("illustration_mode") or "").lower() == "vector"
            else "image")
    config["default_illustration_mode"] = (
        "vector" if str(config.get("default_illustration_mode")).lower() == "vector"
        else "image")
    config["illustration_mode"] = config["default_illustration_mode"]
    return config


def public_config(config: dict) -> dict:
    """Config for the UI: never expose API keys, keep sections as objects."""
    out = dict(config)
    for key in ("text", "image", "vision"):
        section = _dict_or_empty(config.get(key))
        if section.get("api_key"):
            section["api_key_set"] = True
            section["api_key"] = ""
        else:
            section["api_key_set"] = False
        out[key] = section
        out[key + "_model"] = section
    ocr = config.get("ocr")
    out["ocr"] = _dict_or_empty(ocr) if not isinstance(ocr, str) else {"mode": ocr}
    out["ocr_mode"] = out["ocr"].get("mode", "auto")
    out["quality"] = "hd" if config.get("quality") == "hd" else "standard"
    out["render_mode"] = config.get("render_mode", "compose")
    return out


def load_config() -> dict:
    if CONFIG_PATH.is_file():
        try:
            return normalize_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig")))
        except Exception:
            pass
    return normalize_config({"mode": "placeholder"})


CONFIG_LOCK = threading.RLock()


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def safe_replace(src: Path | str, dst: Path | str) -> None:
    try:
        from studio_storage import durable_replace
        durable_replace(src, dst)
    except OSError:
        # Preserve the original and any recovery journal on a real write error.
        raise


def save_config(config: dict) -> None:
    config = normalize_config(config)
    temp = CONFIG_PATH.with_name(CONFIG_PATH.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    safe_replace(temp, CONFIG_PATH)


# ------------------------------------------------------------------ jobs


def _now() -> float:
    return time.time()


LOG_LOCK = threading.Lock()


def _log_event(event: str, **fields) -> None:
    """Append one JSON line to logs/studio.jsonl (5 MB x 3, never secrets).

    Logging must never break a job: every failure path is swallowed.
    """
    try:
        payload = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                   "event": event}
        for key, value in fields.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
            else:
                payload[key] = str(value)[:200]
        log_dir = DATA_DIR
        path = log_dir / "studio.log"
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        with LOG_LOCK:
            if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
                for index in (2, 1):
                    older = log_dir / f"studio.{index}.log"
                    newer = log_dir / f"studio.{index + 1}.log"
                    if older.exists():
                        os.replace(older, newer)
                os.replace(path, log_dir / "studio.1.log")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
    except Exception:
        pass


def effective_illustration_mode(config: dict) -> str:
    """One source of truth for image vs vector.

    Explicit config wins; an unset value falls back to the documented default
    (image). The API must never silently turn "unset" into vector while the UI
    shows image.
    """
    raw = config.get("illustration_mode")
    if raw is None or str(raw).strip() == "":
        raw = config.get("default_illustration_mode") or "image"
    return "image" if str(raw).strip().lower() == "image" else "vector"


JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_JOB_LOCKS: dict[str, threading.Lock] = {}
_JOB_LOCKS_GUARD = threading.Lock()


def _job_lock(job_id: str) -> threading.Lock:
    with _JOB_LOCKS_GUARD:
        return _JOB_LOCKS.setdefault(job_id, threading.Lock())


def job_paths(job_id: str) -> Path:
    """Resolve a job folder, rejecting traversal and absolute ids."""
    name = str(job_id or "")
    if not JOB_ID_RE.fullmatch(name):
        raise ValueError("非法的任务 ID")
    path = JOBS_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_meta(job: dict) -> None:
    """Write meta atomically so a reader never sees a half-written JSON file."""
    job_id = job.get("id")
    if not JOB_ID_RE.fullmatch(str(job_id or "")):
        return
    folder = job_paths(job_id)
    with _job_lock(job_id):
        # The job dict is mutated by its worker thread; serialize a shallow
        # snapshot and retry if a nested list/dict changed mid-dump.
        meta = {k: v for k, v in dict(job).items() if k != "svg"}
        data = ""
        for _ in range(4):
            try:
                data = json.dumps(meta, ensure_ascii=False, indent=2)
                break
            except (RuntimeError, ValueError):
                time.sleep(0.01)
                meta = {k: v for k, v in dict(job).items() if k != "svg"}
        if not data:
            return
        temp = folder / f"meta.json.{uuid.uuid4().hex}.tmp"
        try:
            temp.write_text(data, encoding="utf-8")
            safe_replace(temp, folder / "meta.json")
        finally:
            if temp.exists():
                temp.unlink(missing_ok=True)


def _set_stage(job: dict, name: str, detail: str | None) -> None:
    stages = job.setdefault("stages", [])
    for stage in stages:
        if stage["state"] == "running" and stage["name"] != name:
            stage["state"] = "done"
    existing = next((s for s in stages if s["name"] == name), None)
    label = pipeline.STAGE_LABELS.get(name, name)
    if existing:
        if existing["state"] != "running":
            job["stage_started"] = _now()
        existing["state"] = "running"
        existing["detail"] = detail
        existing["label"] = label
    else:
        stages.append({"name": name, "label": label, "state": "running", "detail": detail})
        job["stage_started"] = _now()
    job["stage"] = name
    job["message"] = label + ("：" + detail if detail else "…")
    _save_meta(job)


class JobCancelled(Exception):
    pass


def _create_job(text: str, config: dict) -> dict:
    if config.get("scene_engine") == "v2":
        return scene_service.create_job(sys.modules[__name__], text, config)
    mode = "auto"
    # Unify the unset mode: renderers disagree about what None means (compose
    # draws rasters, framework/archetype draw rasters, ring draws vectors).
    illustration_mode = effective_illustration_mode(config)
    original_text = str(config.get("original_text") or text)
    reference_layout = (config.get("reference_layout")
                        or (config.get("style_dna") or {}).get("layout_analysis"))
    contract = layout_contract.build(original_text, text,
                                     reference_layout=reference_layout)
    job = {
        "id": "j_" + uuid.uuid4().hex[:12],
        "title": text[:60],
        "text": text,
        "original_text": original_text,
        "layout_contract": contract,
        "mode": mode,
        "status": "queued",
        "progress": 0,
        "message": "准备任务…",
        "created": _now(),
        "stages": [{"name": n, "label": pipeline.STAGE_LABELS.get(n, n),
                    "state": "pending", "detail": None}
                   for n in (["start", "generate", "assemble", "qa"]
                             if illustration_mode == "image" else STAGE_PLANS[mode])
                   # research only runs when literature is enabled
                   if not (n == "research" and not bool((config.get("literature") or {}).get("enabled")))],
        "error": None,
        "report": None,
        "svg_path": None,
        "canvas": config.get("canvas"),
        "viewport_shape": config.get("viewport_shape"),
        "illustration_mode": illustration_mode,
        "archetype": config.get("archetype"),
        "canvas_mm": config.get("canvas_mm"),
        "dpi": config.get("dpi"),
        "font": config.get("font"),
        "palette_name": config.get("palette_name"),
        "literature_enabled": bool((config.get("literature") or {}).get("enabled")),
        # Keep the user's reference-image DNA and learned style with the job so
        # retry/revise rebuild the same look instead of silently defaulting.
        "style_dna": config.get("style_dna"),
        "style_profile": config.get("style_profile"),
        "design_brief": config.get("design_brief"),
    }
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    try:
        _save_meta(job)
        threading.Thread(target=_run_job, args=(job, text, config), daemon=True).start()
    except Exception:
        with JOBS_LOCK:
            JOBS.pop(job["id"], None)
        raise
    return job


def _run_job(job: dict, text: str, config: dict) -> None:
    started = _now()
    try:
        job["status"] = "processing"
        _save_meta(job)
        _log_event("job_start", job_id=job["id"], mode=job.get("mode"),
                   illustration_mode=job.get("illustration_mode"),
                   canvas=job.get("canvas"))

        def on_stage(name: str, detail: str | None = None) -> None:
            if job.get("cancel_requested"):
                raise JobCancelled()
            if name == "qa" and detail and "第" in detail:
                match = re.search(r"第\s*(\d+)\s*/?\s*(\d*)", detail)
                if match:
                    rnd = int(match.group(1))
                    job["progress_override"] = min(97.0, 88.0 + 9.0 * (rnd - 1) / 10.0)
            _set_stage(job, name, detail)

        lit = config.get("literature") or {}
        if lit.get("enabled"):
            try:
                import literature
                research = literature.research_for_generation(
                    job.get("original_text") or text, config, on_stage=on_stage)
                if research.get("ok"):
                    config["style_profile"] = research.get("profile") or {}
                    config["design_brief"] = research.get("brief") or ""
                    job["research"] = {
                        "count": research.get("count"),
                        "live_count": research.get("live_count"),
                        "analyzed": research.get("analyzed_count") or 0,
                        "direct_count": research.get("direct_count") or 0,
                        "style_count": research.get("style_count") or 0,
                        "figure_kind": research.get("figure_kind") or "other",
                        "thumbs": research.get("figures") or [],
                        "sources": research.get("sources"),
                        "figure_types": research.get("figure_types"),
                        "rules": (research.get("rules") or [])[:6],
                    }
                else:
                    job["research"] = {"count": 0, "error": research.get("reason")}
            except Exception as exc:
                job["research"] = {"count": 0, "error": f"{type(exc).__name__}: {exc}"[:200]}
            _save_meta(job)
        svg, report = pipeline.render(text=text, image=None, config=config, on_stage=on_stage)
        if job.get("cancel_requested"):
            raise JobCancelled()
        report["research"] = job.get("research") or {}
        paths = job_paths(job["id"])
        (paths / "result.svg").write_bytes(svg)
        (paths / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        job["svg_path"] = str(paths / "result.svg")
        job["report"] = report
        job["export_audit"] = {"svg": _svg_audit(job["svg_path"])}
        font = str(config.get("font") or "Times New Roman")
        has_raster = b"<image" in svg
        if report.get("fidelity") or has_raster:
            job["deliverable_svg"] = job["svg_path"]
            job["visual_check"] = {"checked": True,
                                   "mode": "illustrated" if has_raster else "fidelity"}
        else:
            try:
                skill_bridge.prepare(paths, job["id"], font)
                exported = skill_bridge.export_svg(paths, font)
                job["deliverable_svg"] = exported.get("svg")
                job["visual_check"] = skill_bridge.visual_check(
                    exported.get("svg"), paths / "result.svg", config)
            except Exception as exc:
                job["export_error"] = f"{type(exc).__name__}: {exc}"[:500]
        delivered = Path(job.get("deliverable_svg") or job["svg_path"])
        try:
            width, height = _svg_size(delivered.read_bytes())
            preview = qa.rasterize(delivered.read_bytes(), width, height, config)
            if preview:
                (paths / "preview.png").write_bytes(preview)
                job["preview_png"] = str(paths / "preview.png")
            job["visual_checks"] = _visual_checks(delivered, report, bool(preview))
            job["visual_findings"] = review.findings(delivered.read_bytes(),
                                                     report.get("scene_data"))
            for extra in ((report.get("rework") or {}).get("residual_findings") or []):
                if extra.get("kind") in ("vision", "vision-unavailable") and all(
                        f.get("message") != extra.get("message") for f in job["visual_findings"]):
                    job["visual_findings"].append(extra)
            job["model_review"] = (report.get("rework") or {}).get("model_review") or {}
            if not job["model_review"]:
                try:
                    import model_review
                    context = {"kind": report.get("mode") or job.get("mode"),
                               "title": _figure_title(job),
                               "canvas": job.get("canvas"),
                               "scene_plate": bool(report.get("scene_template")),
                               **_layout_context(report, job),
                               "entities": [e.get("label") for e in
                                            (report.get("scene_data") or {}).get("entities") or []]}
                    model_findings, model_meta = model_review.review_figure(
                        delivered.read_bytes(), config, context)
                    job["model_review"] = model_meta
                    for extra in model_findings:
                        if all(f.get("message") != extra.get("message") for f in job["visual_findings"]):
                            job["visual_findings"].append(extra)
                except Exception as exc:
                    job["visual_findings"].append(_vision_unavailable(exc))
            if report.get("raster"):
                job["visual_findings"] = _drop_ocr_contradicted(
                    job["visual_findings"], job.get("layout_contract") or {},
                    report.get("ocr_texts") or [])
            job["visual_findings"].extend(
                _adherence_findings(job, report, delivered.read_bytes()))
            job["review_version"] = REVIEW_VERSION
            blocking = [f for f in job["visual_findings"]
                        if f.get("severity") in ("high", "medium")
                        and f.get("kind") != "vision-unavailable"]
            # A missing browser preview must not fail an otherwise clean figure:
            # it means the pixel comparison could not run, not that the figure
            # is broken. Report it, and let findings decide the verdict.
            if blocking:
                job["visual_state"] = "failed"
                # Automatic rework: chain one auto-fix job. The child runs the
                # fix→render→re-audit loop; the UI follows it automatically.
                if not job.get("auto_fix") and not job.get("next_job"):
                    try:
                        child = _revision_job(
                            job, _auto_fix_instruction(blocking), dict(config),
                            title_suffix="自动返工", auto_fix=True)
                        job["next_job"] = child["id"]
                    except Exception as exc:
                        print(f"auto-rework chain failed: {exc}", file=sys.stderr)
            elif not job["visual_checks"]["passed"]:
                job["visual_state"] = "failed"
                job["visual_checks"]["note"] = (
                    "图形内容自检未通过：" + str(job["visual_checks"].get("error") or "输出为空"))
            else:
                job["visual_state"] = "unverified" if _audit_gap(job["visual_findings"]) else "passed"
                if not job["visual_checks"].get("preview"):
                    job["visual_checks"]["note"] = (
                        "预览未生成（本机未找到浏览器），像素检查未执行；以几何与模型审查为准。")
                if job["visual_state"] == "unverified":
                    job["visual_checks"]["note"] = (
                        "视觉模型审查未执行，本图只通过了本地几何检查；恢复模型连接后需重新审查。")
        except Exception as exc:
            job["visual_state"] = "failed"
            job["visual_checks"] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
            # Do not lose the rework loop's residual defects when the final
            # audit itself crashes; otherwise confirm sees an empty list.
            residual = (report.get("rework") or {}).get("residual_findings") or []
            existing = job.get("visual_findings") or []
            for finding in residual:
                if all(f.get("message") != finding.get("message") for f in existing):
                    existing.append(finding)
            job["visual_findings"] = existing
        if job.get("cancel_requested"):
            raise JobCancelled()
        job["status"] = "completed"
        for stage in job.get("stages", []):
            stage["state"] = "done"
        job["progress"] = 100
        job["duration"] = round(_now() - started, 2)
    except JobCancelled:
        job["status"] = "cancelled"
        job["message"] = "已取消"
        job["duration"] = round(_now() - started, 2)
        _log_event("job_cancelled", job_id=job["id"], duration=job["duration"])
        for stage in job.get("stages", []):
            if stage.get("state") == "running":
                stage["state"] = "cancelled"
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = _friendly_error(exc)
        job["duration"] = round(_now() - started, 2)
        _log_event("job_failed", job_id=job["id"], duration=job["duration"],
                   error_type=type(exc).__name__, error=str(exc)[:300])
        for stage in job.get("stages", []):
            if stage.get("state") == "running":
                stage["state"] = "failed"
        print(traceback.format_exc(), file=sys.stderr)
    finally:
        if job.get("status") == "completed":
            _log_event("job_done", job_id=job["id"], duration=job.get("duration"),
                       visual_state=job.get("visual_state"))
        _save_meta(job)

REVISE_SPEC_INSTRUCTION = """你是顶刊科研插图的结构化编辑。下面给出当前图的 JSON 规格和用户的修改指令。
优先返回一个“最小修改补丁”，只列出需要改的字段，其余字段逐字保留：
{"changes": [{"path": "title", "value": "新的标题"},
             {"path": "rings[2].segments[0].label", "value": "新的标签"}]}
规则：
1. path 用点号和数组下标；只改用户明确要求的部分，不要重写未提及的 label/caption；
2. 不得新增或删除科学事实、数值、材料或实验结论；
3. 圆环图的环数/段数/label_mode/style 可按指令修改，不要强行凑成固定 4/6/8；
4. 如果必须整体重排，才返回完整 JSON 规格（保持 schema）；
5. 只输出 JSON，不要 markdown、不要解释。

当前规格：
{spec}

用户修改指令：
{instruction}
"""


def _auto_fix_instruction(findings: list[dict]) -> str:
    """Turn the audit's own findings into the repair brief for _revise_spec.

    The vision reviewer already says exactly what is wrong and how to fix it
    (message + suggestion); feeding that back verbatim gives the editor model
    an actionable, minimal-scope instruction instead of a vague "fix it".
    """
    lines = ["请逐条修复下面审查发现的问题。每个问题都给出修改建议，按建议修改规格，"
             "不要改动与问题无关的字段，不要改变科学事实。"]
    for index, f in enumerate(findings, 1):
        severity = str(f.get("severity") or "medium").upper()
        message = str(f.get("message") or "").strip()
        suggestion = str(f.get("suggestion") or "").strip()
        lines.append(f"{index}. [{severity}] {message}")
        if suggestion:
            lines.append(f"   修改建议：{suggestion}")
    return "\n".join(lines)

REVISE_TEXT_INSTRUCTION = "你是 Cell / Nature / Science 的科研绘图编辑。保持科学事实、实体和关系不变，只按用户的修改指令改写下面的绘图描述。输出修改后的完整中文描述，不要解释，不要 markdown。"


def _svg_png_assets(svg_bytes: bytes) -> list[bytes]:
    import base64
    out = []
    for match in re.finditer(rb'href="data:image/png;base64,([^"]+)"', svg_bytes):
        try:
            out.append(base64.b64decode(match.group(1)))
        except Exception:
            continue
    return out


def _svg_audit(path) -> dict:
    """Count what the delivered SVG actually contains (raster vs editable text)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(Path(path).read_bytes())
    except Exception:
        return {"ok": False}
    images = texts = 0
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag == "image":
            images += 1
        elif tag in ("text", "tspan", "textPath"):
            texts += 1
    return {"ok": True, "images": images, "texts": texts,
            "bytes": Path(path).stat().st_size}


def _pptx_audit(path) -> dict:
    """Count pictures and text runs on the first slide of a PPTX."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as package:
            slide = package.read("ppt/slides/slide1.xml")
            media = [n for n in package.namelist() if n.startswith("ppt/media/")]
    except Exception:
        return {"ok": False}
    return {"ok": True, "pictures": slide.count(b"<p:pic"),
            "texts": slide.count(b"<a:t>"), "media": len(media),
            "bytes": Path(path).stat().st_size}


def _revision_kind(source: dict) -> str:
    report = source.get("report") or {}
    if report.get("ring"):
        return "ring"
    if report.get("framework"):
        return "framework"
    if report.get("archetype"):
        return "archetype"
    if report.get("scene_data"):
        return "compose"
    return "prompt"


def _merge_spec(base, patch):
    if not isinstance(patch, dict):
        return base
    out = dict(base) if isinstance(base, dict) else {}
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_spec(out[key], value)
        elif isinstance(value, list):
            out[key] = value
        elif value is not None:
            out[key] = value
    return out


def _spec_change_actions(before, after) -> list[str]:
    """Human-readable audit of what an editor patch actually changed."""
    def clip(value, n=90):
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:n] + ("…" if len(text) > n else "")
    out: list[str] = []
    if not isinstance(before, dict) or not isinstance(after, dict):
        return out
    for key in ("title", "subtitle"):
        if before.get(key) != after.get(key):
            out.append(f"{key}: {clip(before.get(key))} → {clip(after.get(key))}")
    old = before.get("stages") or []
    new = after.get("stages") or []
    for i in range(max(len(old), len(new))):
        a = old[i] if i < len(old) and isinstance(old[i], dict) else {}
        b = new[i] if i < len(new) and isinstance(new[i], dict) else {}
        for key in ("label", "caption", "prompt"):
            if a.get(key) != b.get(key):
                out.append(f"stage {i + 1} {key}: {clip(a.get(key))} → {clip(b.get(key))}")
        if len(out) >= 12:
            break
    return out[:12]


def _set_spec_path(root, path: str, value) -> bool:
    tokens = []
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", str(path)):
        if part.startswith("["):
            tokens.append(int(part[1:-1]))
        else:
            tokens.append(part)
    if not tokens:
        return False
    cur = root
    for index, token in enumerate(tokens[:-1]):
        nxt = tokens[index + 1]
        if isinstance(token, int):
            if not isinstance(cur, list):
                return False
            while len(cur) <= token:
                cur.append({} if not isinstance(nxt, int) else [])
            cur = cur[token]
        else:
            if not isinstance(cur, dict):
                return False
            if token not in cur or cur[token] is None:
                cur[token] = [] if isinstance(nxt, int) else {}
            cur = cur[token]
    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(cur, list):
            return False
        while len(cur) <= last:
            cur.append(None)
        cur[last] = value
    else:
        if not isinstance(cur, dict):
            return False
        cur[last] = value
    return True


def _revise_spec(spec: dict, instruction: str, config: dict) -> dict:
    last_error = None
    raw = None
    for attempt in range(2):
        try:
            raw = pipeline.chat_json(config, [
                {"role": "system", "content": "你是顶刊科研插图的结构化编辑。只输出修改后的完整 JSON 规格，不要解释、不要问候。"},
                {"role": "user", "content": REVISE_SPEC_INSTRUCTION.replace(
                    "{spec}", json.dumps(spec, ensure_ascii=False)).replace("{instruction}", instruction)},
            ], temperature=0.2, max_tokens=6000, reasoning_effort="high",
               timeout=420, allow_fallback=False)
            break
        except Exception as exc:
            last_error = exc
            if attempt < 1:
                time.sleep(4)
    if raw is None:
        raise RuntimeError(str(last_error)[:400])
    if isinstance(raw, list):
        raw = {"changes": raw}
    if not isinstance(raw, dict):
        return spec
    if isinstance(raw.get("changes"), list):
        revised = json.loads(json.dumps(spec))
        applied = 0
        for change in raw["changes"]:
            if isinstance(change, dict) and "path" in change:
                if _set_spec_path(revised, change.get("path"), change.get("value")):
                    applied += 1
        if applied:
            return revised
    if isinstance(raw.get("spec"), dict):
        raw = raw["spec"]
    return _merge_spec(spec, raw)


def _revise_text(text: str, instruction: str, config: dict) -> str:
    raw = pipeline._chat(config, [
        {"role": "system", "content": REVISE_TEXT_INSTRUCTION},
        {"role": "user", "content": "原描述：\n" + text[:6000] + "\n\n修改指令：\n" + instruction},
    ], temperature=0.25, max_tokens=1600, reasoning_effort="high", timeout=600)
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw[:8000] or text


def _revision_assets(source: dict, kind: str) -> dict:
    import compose
    svg_path = Path(source.get("deliverable_svg") or source.get("svg_path") or "")
    if not svg_path.is_file():
        return {}
    # Only entities that actually got an <image> in the delivered SVG can be
    # recovered; match by order of appearance so id↔png never shifts when the
    # renderer capped or skipped some entities.
    pngs = _svg_png_assets(svg_path.read_bytes())
    report = source.get("report") or {}
    assets = {}
    if kind == "ring":
        if pngs:
            assets["hero"] = compose.asset_image(pngs[0])
    elif kind == "framework":
        # build_framework_svg renders at most the first 4 embodied entities.
        ids = [e.get("id") for e in (report.get("spec") or {}).get("embodied_entities") or []][:4]
        for key, png in zip(ids, pngs):
            if key is not None:
                assets[key] = compose.asset_image(png)
    elif kind == "archetype":
        for index, png in enumerate(pngs):
            assets[index] = compose.asset_image(png)
    elif kind == "compose":
        entities = (report.get("scene_data") or {}).get("entities") or []
        # compose_svg emits one <image> per entity that had an asset, in z
        # order; ids without assets are not in the SVG, so zip against the
        # asset-backed subset only.
        ids = [e.get("id") for e in sorted(entities, key=lambda e: e.get("z", 0))
               if e.get("id")]
        for key, png in zip(ids, pngs):
            assets[key] = compose.asset_image(png)
    return assets


def _strip_suffix(title: str) -> str:
    text = str(title or "图")
    # Jobs created from an optimized prompt carry the whole brief as their
    # title; use the first "图表主题" line for the job list instead.
    if text.lstrip().startswith("【绘图提示词】"):
        match = re.search(r"图表主题[:：]\s*([^\n（(]+)", text)
        if match:
            text = match.group(1).strip()
    for suffix in (" · AI修改 · 自动修复", " · AI修改", " · 自动修复"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def _inherit_source_config(config: dict, source: dict) -> dict:
    """Keep the source job's look and canvas for revisions/repairs.

    A later global settings change must not restyle an existing figure, and a
    prompt-kind job (legacy plan/fidelity fallback) has no spec to carry these
    fields, so config inheritance has to happen before its early branch.
    """
    config["illustration_mode"] = ("image"
                                  if str(source.get("illustration_mode") or "") == "image"
                                  else "vector")
    for key in ("style_dna", "style_profile", "design_brief",
                "viewport_shape", "archetype",
                "palette_name", "canvas_mm", "dpi", "font"):
        if source.get(key) is not None:
            config[key] = source[key]
    if source.get("canvas"):
        config["canvas"] = source["canvas"]
        config["canvas_user"] = True
    return config


def _revision_job(source: dict, instruction: str, config: dict,
                  title_suffix: str = "AI修改", auto_fix: bool = False) -> dict:
    job = {
        "id": "j_" + uuid.uuid4().hex[:12],
        "title": (_strip_suffix(source.get("title") or "图") + " · " + title_suffix)[:60],
        "text": source.get("text") or source.get("title") or "",
        "mode": source.get("mode") or "auto",
        "status": "queued",
        "progress": 0,
        "message": "准备修改…",
        "created": _now(),
        "auto_fix": auto_fix,
        "stages": [{"name": n, "label": pipeline.STAGE_LABELS.get(n, n),
                    "state": "pending", "detail": None}
                   for n in ("start", "plan_scene", "assemble", "qa")],
        "error": None,
        "report": None,
        "svg_path": None,
        "canvas": source.get("canvas"),
        "canvas_mm": source.get("canvas_mm"),
        "dpi": source.get("dpi"),
        "font": source.get("font"),
        "viewport_shape": source.get("viewport_shape"),
        "illustration_mode": ("image"
                              if str(source.get("illustration_mode") or "") == "image"
                              else "vector"),
        "archetype": source.get("archetype"),
        "palette_name": source.get("palette_name"),
        "style_dna": source.get("style_dna"),
        "style_profile": source.get("style_profile"),
        "design_brief": source.get("design_brief"),
        "research": source.get("research"),
        "original_text": source.get("original_text") or source.get("text") or "",
        "layout_contract": source.get("layout_contract") or {},
        "revision_of": source.get("id"),
        "revision_instruction": instruction,
    }
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    try:
        _save_meta(job)
        target = _run_autofix if auto_fix else _run_revision
        threading.Thread(target=target, args=(job, source, instruction, config),
                         daemon=True).start()
    except Exception:
        with JOBS_LOCK:
            JOBS.pop(job["id"], None)
        raise
    return job


def _ensure_vector_assets(kind: str, spec: dict, assets: dict, config: dict) -> dict:
    """Vector revisions need glyph assets too; PNG extraction only recovers
    raster assets, which vector figures do not contain."""
    if assets or kind == "compose":
        return assets
    import framework
    palette = (config.get("style_dna") or {}).get("palette") or {}
    color = palette.get("primary", "#3F5A6B")

    def glyph(meta):
        if not isinstance(meta, dict):
            meta = {"label": str(meta)}
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
               + framework.entity_glyph(meta, 50, 50, 78, color) + '</svg>').encode("utf-8")
        return (svg, 100.0, 100.0)

    if kind == "framework":
        for entity in spec.get("embodied_entities") or []:
            assets[entity.get("id")] = glyph(entity)
    elif kind == "archetype":
        for index, stage in enumerate(spec.get("stages") or []):
            assets[index] = glyph(stage)
    elif kind == "ring":
        assets["hero"] = glyph(spec.get("core") or {"label": "core"})
    return assets


def fill_missing_boxes(spec: dict) -> dict:
    """Place entities that lost their bbox without moving the ones that kept it."""
    entities = [e for e in (spec.get("entities") or []) if isinstance(e, dict)]
    missing = [e for e in entities if not e.get("bbox")]
    if not missing or len(missing) == len(entities):
        return spec  # a fully unplaced spec is the caller's arrange() job
    try:
        canvas = [float(v) for v in (spec.get("canvas") or [1400, 1000])[:2]]
        cw, ch = canvas
        boxes = [e["bbox"] for e in entities if e.get("bbox")]
        bottom = max(float(b[1]) + float(b[3]) for b in boxes)
    except (TypeError, ValueError, IndexError):
        return spec
    margin, gap = 40.0, 20.0
    height = max(90.0, min(160.0, ch - bottom - margin))
    y = bottom + gap if bottom + gap + height <= ch - margin else max(margin, ch - margin - height)
    width = max(80.0, (cw - 2 * margin - gap * (len(missing) - 1)) / len(missing))
    for index, entity in enumerate(missing):
        entity["bbox"] = [margin + index * (width + gap), y, width, height]
    return spec


def _render_kind(kind: str, spec: dict, report: dict, assets: dict,
                 canvas: list, shape: str, font: str, config: dict):
    """Render one spec for any figure kind. Returns (svg, scene_data, spec_used)."""
    import compose
    assets = _ensure_vector_assets(kind, spec, assets, config)
    if kind == "ring":
        import ring_render
        used = ring_render._ring_spec(spec)
        report["spec"] = used
        svg = ring_render.build_ring_svg(used, font, canvas=canvas, viewport_shape=shape,
                                         palette=ring_render._palette(config), assets=assets)
        return svg, None, used
    if kind == "framework":
        import framework
        dna = (config.get("style_dna") or {}).get("palette") or {}
        svg = framework.build_framework_svg(spec, assets, font, canvas=canvas,
                                            viewport_shape=shape, palette=dna)
        return svg, None, spec
    if kind == "archetype":
        import archetypes_render
        atype = report.get("archetype") or spec.get("archetype") or "signal_pathway"
        palette = archetypes_render._palette(config, atype)
        scene_path = report.get("scene_template")
        if scene_path and Path(scene_path).exists():
            # Re-renders after a repair round must keep the painted plate; a fresh
            # per-entity asset dict would silently drop back to the vector bands.
            assets["scene"] = compose.asset_image(Path(scene_path).read_bytes())
        svg = archetypes_render.RENDERERS[atype](spec, assets, canvas, shape, palette)
        return svg, None, spec
    import compose
    import framework
    cfg = dict(config)
    cfg["canvas"] = canvas
    cfg["canvas_user"] = True
    # Keep already-laid-out boxes on revisions; only grid-arrange the entities
    # that lost their box, so one patched item cannot reflow the whole figure.
    fill_missing_boxes(spec)
    has_boxes = all(e.get("bbox") for e in (spec.get("entities") or []))
    scene = compose.repair_scene(spec, cfg)
    if not has_boxes:
        scene = compose.arrange(scene)
    vector_mode = str(config.get("illustration_mode") or "") == "vector"
    scene["vector_glyphs"] = vector_mode
    palette = scene.get("palette") or {}
    for entity in scene.get("entities") or []:
        if not vector_mode and entity["id"] in assets:
            continue
        # In vector mode the glyph is derived from label/prompt, so always
        # rebuild it: a repair patch that rewrites the icon prompt must show.
        glyph = framework.entity_glyph(
            entity, 50, 50, 78, palette.get("primary", "#3F5A6B"))
        glyph_svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                     + glyph + '</svg>').encode("utf-8")
        assets[entity["id"]] = (glyph_svg, 100.0, 100.0)
    scene_data = {"canvas": scene.get("canvas"),
                  "entities": scene.get("entities"),
                  "connectors": scene.get("connectors") or [],
                  "labels": scene.get("labels") or [],
                  "layout": scene.get("layout"),
                  "lock_layout": scene.get("lock_layout", False),
                  "title": scene.get("title"),
                  "subtitle": scene.get("subtitle"),
                  "vector_glyphs": vector_mode}
    svg = compose.compose_svg(scene, assets, font)
    return svg, scene_data, scene


def _run_autofix(job: dict, source: dict, instruction: str, config: dict) -> None:
    """Fix → re-render → re-audit, up to 10 rounds or clean.

    This is the loop the UI promises: the audit's own findings become the
    repair brief every round, and the figure is re-checked from scratch after
    each patch. Stops early when no high remains or the spec stops changing.
    """
    started = _now()
    try:
        job["status"] = "processing"
        _save_meta(job)
        _set_stage(job, "start", "AI 正在按审查结论逐轮修复")
        kind = _revision_kind(source)
        _inherit_source_config(config, source)
        # A repair loop is interactive: keep each review bounded so one slow
        # gateway cannot hold the whole job for many minutes per round.
        vision_cfg = dict(config.get("vision") or {})
        try:
            vision_cfg["timeout"] = min(float(vision_cfg.get("timeout") or 180), 60)
        except (TypeError, ValueError):
            vision_cfg["timeout"] = 60
        config["vision"] = vision_cfg
        # The audit that triggered this repair is the authoritative issue
        # list. Seed it into round 1 so a re-render whose fresh review happens
        # to pass cannot silently skip every fix (the "changed=false" bug).
        seed_findings = [
            f for f in (source.get("visual_findings") or [])
            if isinstance(f, dict)
            and f.get("severity") in ("high", "medium")
            and f.get("kind") != "vision-unavailable"
        ]
        report = dict(source.get("report") or {})
        report.pop("rework", None)
        contract = source.get("layout_contract") or {}
        expected = contract.get("archetype")
        actual = report.get("archetype") or ("closed_loop" if report.get("framework") else "")
        if expected and actual and expected != actual:
            # The previous renderer was the wrong archetype; patching its spec
            # cannot recover the author's layout. Regenerate from the brief.
            cfg = dict(config)
            cfg["archetype"] = expected
            cfg["layout_contract"] = contract
            original = source.get("original_text") or source.get("text") or ""
            _run_job(job, original, cfg)
            return
        if kind == "prompt":
            cfg = dict(config)
            cfg["literature"] = {"enabled": False}
            text = source.get("text") or ""
            try:
                # Turn the audit findings into a text revision instead of
                # silently regenerating the same broken brief.
                text = _revise_text(text, instruction, cfg)
            except Exception:
                pass
            job["text"] = text
            _run_job(job, text, cfg)
            return

        base = report.get("spec") or (report.get("scene_data") if kind == "compose" else {})
        if not base:
            raise RuntimeError("没有可编辑的结构化规格")
        original_spec = copy.deepcopy(base)

        job["progress_override"] = 6.0
        job["message"] = "第 1 轮：生成修复补丁"
        _set_stage(job, "plan_scene", "第 1 轮：生成修复补丁")
        if kind == "archetype":
            # Plate repairs are usually deterministic (label size, plate scale).
            # Do not spend a 7-minute editor timeout before trying the cheap
            # patch; the loop below still calls the editor for semantic fixes.
            current = base
        else:
            try:
                current = _revise_spec(base, instruction, config)
            except Exception:
                # Rate-limited editor: start from the source spec and let the
                # deterministic geometry pass do the first round instead.
                current = base
        assets = _revision_assets(source, kind)
        shape = source.get("viewport_shape") or "rect"
        canvas = source.get("canvas")
        src = Path(source.get("deliverable_svg") or source.get("svg_path") or "")
        if not canvas and src.is_file():
            canvas = list(_svg_size(src.read_bytes()))
        canvas = list(canvas or [1400, 1400])
        font = str(config.get("font") or "Times New Roman")
        try:
            original_svg = src.read_bytes() if src.is_file() else b""
        except Exception:
            original_svg = b""

        import model_review
        import rework
        # Auto-fix is a foreground user action; cap the loop so a stubborn
        # review cannot leave the UI "processing" for tens of minutes.
        max_rounds = 3
        history: list[dict] = []
        findings: list[dict] = []
        final_svg = b""
        scene_data = None
        meta: dict = {}
        meta_history: list[dict] = []
        for rnd in range(1, max_rounds + 1):
            if job.get("cancel_requested"):
                raise JobCancelled()
            job["progress_override"] = min(96.0, 8.0 + 88.0 * (rnd - 1) / max_rounds)
            job["message"] = f"第 {rnd}/{max_rounds} 轮：重渲染并重新审查"
            _save_meta(job)
            _set_stage(job, "qa", f"第 {rnd}/{max_rounds} 轮：重渲染并重新审查")
            round_spec = copy.deepcopy(current)
            svg, scene_data, current = _render_kind(
                kind, current, report, assets, canvas, shape, font, config)
            final_svg = svg
            local = review.findings(svg, scene_data)
            try:
                model_findings, meta = model_review.review_figure(svg, config, {
                    "kind": kind, "title": _figure_title(source), "canvas": canvas,
                    "scene_plate": bool(report.get("scene_template")),
                    "ocr_texts": review._svg_texts(svg),
                    **_layout_context({"spec": current}, job),
                    "entities": [e.get("label") for e in
                                 (scene_data or {}).get("entities") or []]})
            except Exception as exc:
                model_findings = [_vision_unavailable(exc)]
            meta_history.append({"round": rnd, **meta})
            findings = local + [f for f in model_findings
                                if all(g.get("message") != f.get("message") for g in local)]
            if rnd == 1 and seed_findings:
                known = {str(f.get("message") or "") for f in findings}
                findings += [f for f in seed_findings
                             if str(f.get("message") or "") not in known]
            blocking = [f for f in findings
                        if f.get("severity") in ("high", "medium")
                        and f.get("kind") != "vision-unavailable"]
            history.append({"round": rnd, "issues_count": len(findings),
                            "high_count": sum(1 for f in blocking
                                              if f.get("severity") == "high"),
                            "blocking_count": len(blocking),
                            "local_count": len(local),
                            "model_count": len(model_findings),
                            "model_verdict": meta.get("verdict"),
                            "status": ("clean" if not blocking and not _audit_gap(findings)
                                       else "audit-unavailable" if not blocking
                                       else "repairing")})
            if not blocking:
                break
            if rnd >= max_rounds:
                break
            if kind == "compose" and local:
                current, acts = rework.repair_scene_step(current, local)
                history[-1]["actions"] = acts
            if kind == "archetype":
                # Fast deterministic plate repair first; it mutates the spec in
                # place (e.g. _plate_label_scale) and visibly changes pixels.
                acts = model_review.heuristic_fix(current, blocking)
                if acts:
                    seed_findings = []
                    history[-1]["actions"] = acts
                    continue
                # The reviewer may report a semantic issue that has no rule in
                # heuristic_fix. Still make a visible, deterministic adjustment
                # instead of rebuilding an identical plate and claiming a fix.
                scale = float(current.get("_plate_label_scale") or 1.0)
                plate = float(current.get("_plate_scale") or 1.0)
                current["_plate_label_scale"] = round(min(1.35, scale + 0.06), 3)
                current["_plate_scale"] = round(min(1.10, plate + 0.02), 3)
                seed_findings = []
                history[-1]["actions"] = [
                    f"按审查结论微调图版比例（标签 {current['_plate_label_scale']:.2f}×）"
                ]
                continue
            try:
                patched = _revise_spec(current, _auto_fix_instruction(blocking), config)
            except Exception as exc:
                # A rate-limited or malformed editor reply must not abort the
                # loop; fall through to the deterministic geometry repair.
                history[-1]["editor_error"] = f"{type(exc).__name__}: {exc}"[:300]
                patched = current
            if json.dumps(patched, sort_keys=True, ensure_ascii=False) == \
                    json.dumps(current, sort_keys=True, ensure_ascii=False):
                # Editor model produced no change; deterministic geometry pass.
                acts = model_review.heuristic_fix(current, blocking)
                if acts:
                    history[-1]["actions"] = acts
                    continue
                history[-1]["status"] = "unresolved"
                break
            actions = _spec_change_actions(round_spec, patched)
            history[-1]["planner_patch"] = True
            history[-1]["actions"] = actions or ["编辑模型返回了补丁（字段级差异未记录）"]
            current = patched

        report["revision"] = {"of": source.get("id"), "instruction": instruction,
                              "mode": "auto-fix", "kind": kind}
        report["spec"] = current
        if scene_data:
            report["scene_data"] = scene_data
        report["rework"] = {
            "rounds_executed": len(history), "max_rounds": max_rounds,
            "clean": (not any(
                f.get("severity") in ("high", "medium")
                and f.get("kind") != "vision-unavailable" for f in findings)
                and not _audit_gap(findings)),
            "residual_findings": findings, "history": history,
            "mode": "auto-fix",
            "duration_sec": round(_now() - started, 2),
            "stopped_reason": ("audit_unavailable" if (
                not any(f.get("severity") in ("high", "medium")
                        and f.get("kind") != "vision-unavailable" for f in findings)
                and _audit_gap(findings)) else
                "clean" if not any(
                    f.get("severity") in ("high", "medium")
                    and f.get("kind") != "vision-unavailable" for f in findings) else
                ("max_rounds" if len(history) >= max_rounds else "no_progress")),
            "review_version": REVIEW_VERSION,
            "model_review": {"model": (meta or {}).get("model"), "rounds": meta_history},
            "changed": original_spec != current,
            "spec_changed": original_spec != current,
            "before_findings": source.get("visual_findings") or [],
            "after_findings": findings,
            "fix_actions": [action for entry in history
                            for action in (entry.get("actions") or [])],
        }
        paths = job_paths(job["id"])
        (paths / "result.svg").write_bytes(final_svg)
        report["bytes"] = len(final_svg)
        (paths / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        job["svg_path"] = str(paths / "result.svg")
        job["deliverable_svg"] = job["svg_path"]
        job["report"] = report
        findings.extend(_adherence_findings(job, report, final_svg))
        job["visual_findings"] = findings
        job["model_review"] = {"model": (meta or {}).get("model"), "rounds": meta_history}
        job["review_version"] = REVIEW_VERSION
        blocking = [f for f in findings
                    if f.get("severity") in ("high", "medium")
                    and f.get("kind") != "vision-unavailable"]
        job["visual_state"] = ("failed" if blocking else
                               ("unverified" if _audit_gap(findings) else "passed"))
        width, height = _svg_size(final_svg)
        preview = qa.rasterize(final_svg, width, height, config)
        job["visual_checks"] = {"passed": not blocking and not _audit_gap(findings),
                                "preview": bool(preview),
                                "texts": 0, "paths": 0, "images": 0, "markers": 0,
                                "mode": "vector"}
        if preview:
            (paths / "preview.png").write_bytes(preview)
            job["preview_png"] = str(paths / "preview.png")
        if job.get("cancel_requested"):
            raise JobCancelled()
        job["status"] = "completed"
        job["progress"] = 100
        job["duration"] = round(_now() - started, 2)
        for stage in job.get("stages", []):
            stage["state"] = "done"
    except JobCancelled:
        job["status"] = "cancelled"
        job["message"] = "已取消"
        job["duration"] = round(_now() - started, 2)
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = _friendly_error(exc)
        print(traceback.format_exc(), file=sys.stderr)
    finally:
        _save_meta(job)


def _run_revision(job: dict, source: dict, instruction: str, config: dict) -> None:
    import compose
    started = _now()
    try:
        job["status"] = "processing"
        _save_meta(job)
        _set_stage(job, "start", "AI 正在理解修改指令（思考强度 high）")
        kind = _revision_kind(source)
        _inherit_source_config(config, source)
        if kind == "prompt":
            new_text = _revise_text(source.get("text") or "", instruction, config)
            job["revision_text"] = new_text
            job["text"] = new_text
            cfg = dict(config)
            cfg["literature"] = {"enabled": False}
            _run_job(job, new_text, cfg)
            return

        report = dict(source.get("report") or {})
        # Never inherit the previous version's audit record: those findings
        # describe the old SVG, not the revision we are about to render.
        report.pop("rework", None)
        spec = report.get("spec") or (report.get("scene_data") if kind == "compose" else {})
        if not spec:
            raise RuntimeError("没有可编辑的结构化规格")
        if job.get("cancel_requested"):
            raise JobCancelled()
        _set_stage(job, "plan_scene", "生成修改后的版式规格")
        revised = _revise_spec(spec, instruction, config)
        if isinstance(revised, dict):
            # A manual edit is allowed to move things; the deterministic
            # generation lock would undo the user's requested layout change.
            revised["lock_layout"] = False
        if job.get("cancel_requested"):
            raise JobCancelled()
        report["revision"] = {"of": source.get("id"), "instruction": instruction,
                              "mode": "spec", "kind": kind}
        report["spec"] = revised
        _set_stage(job, "assemble", "重新绘制矢量图")
        assets = _revision_assets(source, kind)
        assets = _ensure_vector_assets(kind, revised, assets, config)
        shape = source.get("viewport_shape") or "rect"
        canvas = source.get("canvas")
        source_svg = Path(source.get("deliverable_svg") or source.get("svg_path") or "")
        if not canvas and source_svg.is_file():
            canvas = list(_svg_size(source_svg.read_bytes()))
        canvas = list(canvas or [1400, 1400])
        font = str(config.get("font") or "Times New Roman")
        pre_audited = None
        if kind == "ring":
            import ring_render
            palette = ring_render._palette(config)
            spec = ring_render._ring_spec(revised)
            report["spec"] = spec
            svg = ring_render.build_ring_svg(spec, font, canvas=canvas, viewport_shape=shape,
                                             palette=palette, assets=assets)
        elif kind == "framework":
            import framework
            dna = (config.get("style_dna") or {}).get("palette") or {}
            svg = framework.build_framework_svg(revised, assets, font, canvas=canvas,
                                                viewport_shape=shape, palette=dna)
        elif kind == "archetype":
            import archetypes_render
            atype = report.get("archetype") or source.get("archetype") or "signal_pathway"
            palette = archetypes_render._palette(config, atype)
            scene_path = report.get("scene_template")
            if scene_path and Path(scene_path).exists():
                # Keep the painted plate on spec revisions; otherwise the
                # revision silently falls back to the vector band layout.
                assets["scene"] = compose.asset_image(Path(scene_path).read_bytes())
            svg = archetypes_render.RENDERERS[atype](revised, assets, canvas, shape, palette)
        else:
            import compose
            cfg = dict(config)
            cfg["canvas"] = canvas
            cfg["canvas_user"] = True
            # A revision starts from real, already-laid-out boxes. Re-running
            # the auto-grid would silently change the whole composition when
            # the user only asked to move one label.
            fill_missing_boxes(revised)
            has_boxes = all(e.get("bbox") for e in (revised.get("entities") or []))
            scene = compose.repair_scene(revised, cfg)
            if not has_boxes:
                scene = compose.arrange(scene)
            # The source SVG may be pure vector (no embedded rasters), so
            # _revision_assets yields nothing. Draw the same vector glyphs the
            # original compose pass used instead of dropping every entity.
            import framework
            palette = scene.get("palette") or {}
            vector_mode = str(config.get("illustration_mode") or "") == "vector"
            scene["vector_glyphs"] = vector_mode
            for entity in scene.get("entities") or []:
                if not vector_mode and entity["id"] in assets:
                    continue
                glyph = framework.entity_glyph(
                    entity, 50, 50, 78, palette.get("primary", "#3F5A6B"))
                glyph_svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                             + glyph + '</svg>').encode("utf-8")
                assets[entity["id"]] = (glyph_svg, 100.0, 100.0)
            _set_stage(job, "qa", "自动修复几何冲突并逐轮审查")
            import rework
            def _rev_stage(name, detail=None):
                if job.get("cancel_requested"):
                    raise JobCancelled()
                _set_stage(job, name, detail)

            def _refresh_assets(scene_now, current):
                if str(config.get("illustration_mode") or "") != "vector":
                    return current
                palette_now = scene_now.get("palette") or {}
                color = palette_now.get("primary", "#3F5A6B")
                rebuilt = {}
                for item in scene_now.get("entities") or []:
                    glyph = framework.entity_glyph(item, 50, 50, 78, color)
                    rebuilt[item["id"]] = (
                        ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                         + glyph + '</svg>').encode("utf-8"), 100.0, 100.0)
                return rebuilt

            svg, scene, rework_report = rework.run_rework_loop(
                scene, assets, font, compose.compose_svg, max_rounds=10, config=cfg,
                context={"kind": "compose", "canvas": scene.get("canvas"),
                         "entities": [e.get("label") for e in scene.get("entities") or []],
                         "connectors": [c.get("label") for c in scene.get("connectors") or []]},
                on_stage=_rev_stage, assets_fn=_refresh_assets)
            report["rework"] = rework_report
            report["scene_data"] = {"canvas": scene.get("canvas"),
                                    "entities": scene.get("entities"),
                                    "connectors": scene.get("connectors") or [],
                                    "labels": scene.get("labels") or [],
                                    "layout": scene.get("layout"),
                                    "lock_layout": scene.get("lock_layout", False),
                                    "title": scene.get("title"),
                                    "subtitle": scene.get("subtitle"),
                                    "vector_glyphs": vector_mode}
            pre_audited = rework_report.get("residual_findings") or []
        if job.get("cancel_requested"):
            raise JobCancelled()
        _set_stage(job, "qa", "像素级复核修改结果")
        if pre_audited is not None:
            findings = list(pre_audited)
        else:
            findings = review.findings(svg, report.get("scene_data") if kind == "compose" else None)
            for extra in ((report.get("rework") or {}).get("residual_findings") or []):
                if extra.get("kind") in ("vision", "vision-unavailable") and all(
                        f.get("message") != extra.get("message") for f in findings):
                    findings.append(extra)
        if pre_audited is None:
            try:
                import model_review
                model_findings, model_meta = model_review.review_figure(
                    svg, config, {"kind": kind, "title": _figure_title(source),
                                  "canvas": canvas,
                                  **_layout_context(report, job),
                                  "entities": [e.get("label") for e in
                                               (report.get("scene_data") or {}).get("entities") or []]})
                job["model_review"] = model_meta
                for extra in model_findings:
                    if all(f.get("message") != extra.get("message") for f in findings):
                        findings.append(extra)
            except Exception as exc:
                findings.append(_vision_unavailable(exc))
        else:
            job["model_review"] = (report.get("rework") or {}).get("model_review") or {}
        if pre_audited is None:
            blocking_now = [f for f in findings
                            if f.get("severity") in ("high", "medium")
                            and f.get("kind") != "vision-unavailable"]
            report["rework"] = {"rounds_executed": 1, "max_rounds": 10,
                                "clean": not blocking_now, "residual_findings": findings,
                                "history": [{"round": 1, "issues_count": len(findings),
                                             "status": "clean" if not findings else "repairing"}]}
        else:
            report["rework"] = dict(report.get("rework") or {})
            report["rework"]["residual_findings"] = findings
        paths = job_paths(job["id"])
        (paths / "result.svg").write_bytes(svg)
        report["bytes"] = len(svg)
        (paths / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        job["svg_path"] = str(paths / "result.svg")
        job["deliverable_svg"] = job["svg_path"]
        job["report"] = report
        findings.extend(_adherence_findings(job, report, svg))
        job["visual_findings"] = findings
        job["review_version"] = REVIEW_VERSION
        blocking = [f for f in findings
                    if f.get("severity") in ("high", "medium")
                    and f.get("kind") != "vision-unavailable"]
        job["visual_state"] = ("failed" if blocking else
                               ("unverified" if _audit_gap(findings) else "passed"))
        # A manual edit that still leaves blocking findings gets the same
        # automatic rework chain as a fresh generation.
        if blocking and not job.get("auto_fix") and not job.get("next_job"):
            try:
                child = _revision_job(
                    job, _auto_fix_instruction(blocking), dict(config),
                    title_suffix="自动返工", auto_fix=True)
                job["next_job"] = child["id"]
            except Exception as exc:
                print(f"auto-rework chain failed: {exc}", file=sys.stderr)
        width, height = _svg_size(svg)
        preview = qa.rasterize(svg, width, height, config)
        job["visual_checks"] = {"passed": not blocking and not _audit_gap(findings),
                                "preview": bool(preview),
                                "texts": 0, "paths": 0, "images": 0, "markers": 0,
                                "mode": "vector"}
        if preview:
            (paths / "preview.png").write_bytes(preview)
            job["preview_png"] = str(paths / "preview.png")
        if job.get("cancel_requested"):
            raise JobCancelled()
        job["status"] = "completed"
        job["progress"] = 100
        job["duration"] = round(_now() - started, 2)
        for stage in job.get("stages", []):
            stage["state"] = "done"
    except JobCancelled:
        job["status"] = "cancelled"
        job["message"] = "已取消"
        job["duration"] = round(_now() - started, 2)
        for stage in job.get("stages", []):
            if stage.get("state") == "running":
                stage["state"] = "cancelled"
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = _friendly_error(exc)
        print(traceback.format_exc(), file=sys.stderr)
    finally:
        _save_meta(job)


def _figure_title(job: dict) -> str:
    """Title actually rendered in the figure, not the original brief."""
    report = job.get("report") or {}
    scene = report.get("scene_data") or {}
    spec = report.get("spec") or {}
    return str(scene.get("title") or spec.get("title") or job.get("title") or "")


def _layout_context(report: dict, job: dict | None = None) -> dict:
    spec = report.get("spec") or {}
    scene = report.get("scene_data") or {}
    contract = (job or {}).get("layout_contract") or report.get("layout_contract") or {}
    return {"layout": contract.get("layout") or spec.get("layout") or scene.get("layout"),
            "regions": contract.get("regions") or spec.get("regions") or scene.get("regions") or [],
            "stages": contract.get("stages") or [s.get("label") for s in (spec.get("stages") or [])],
            "ocr_texts": report.get("ocr_texts") or []}


def _adherence_findings(job: dict, report: dict, svg: bytes) -> list[dict]:
    contract = job.get("layout_contract") or {}
    if not contract:
        return []
    try:
        if report.get("raster"):
            texts = list(report.get("ocr_texts") or [])
        else:
            texts = review._svg_texts(svg)
    except Exception:
        texts = []

    def finding(kind, severity, message, suggestion):
        return {"kind": kind, "severity": severity,
                "message": message, "suggestion": suggestion}

    return layout_contract.adherence_findings(contract, report or {}, texts, finding)


def _drop_ocr_contradicted(findings: list[dict], contract: dict,
                          ocr_texts: list[str]) -> list[dict]:
    stages = [str(s) for s in (contract.get("stages") or []) if str(s).strip()]
    if not stages or not ocr_texts:
        return findings
    import text_ocr
    present, missing = text_ocr.labels_present(stages, ocr_texts)
    if not present:
        return findings
    joined_ocr = "".join(text_ocr._normalize(text) for text in ocr_texts)
    out = []
    for finding in findings:
        message = str(finding.get("message") or "")
        low = message.lower()
        claims_missing = any(word in message for word in
                             ("缺少", "缺失", "未显示", "没有显示", "完全缺失", "丢失"))
        if claims_missing and not missing:
            # OCR confirms every required stage label is on the canvas; a
            # "missing stage/content" claim is contradicted by the transcript.
            if any(word in message for word in ("阶段", "步骤", "内容", "最后")):
                continue
        if claims_missing and any(
                text_ocr._normalize(stage) in joined_ocr
                and stage.lower() in low for stage in present):
            continue
        out.append(finding)
    return out


def _public_job(job: dict) -> dict:
    created = job.get("created")
    stamp = created or ""
    status = job["status"]
    stages = job.get("stages", [])
    progress = 100 if status == "completed" else 0
    if status in ("queued", "processing"):
        base = sum(STAGE_WEIGHTS.get(s["name"], 3) for s in stages if s["state"] == "done")
        running = next((s for s in stages if s["state"] == "running"), None)
        if running:
            weight = STAGE_WEIGHTS.get(running["name"], 3)
            elapsed_stage = _now() - job.get("stage_started", _now())
            # Image generation is a single long call. Advance by a capped
            # time-based curve, not a fake "90%" that sits there for minutes.
            scale = 35.0 if running["name"] == "generate" else 4.0
            target = min(96.0, base + weight * (1.0 - math.exp(-elapsed_stage / scale)))
        else:
            target = min(5.0, base + 1.0)
        shown = float(job.get("display_progress", 0.0))
        progress = shown + (target - shown) * 0.30 if target >= shown else target
        job["display_progress"] = progress
    override = job.get("progress_override")
    if override is not None and status in ("queued", "processing"):
        progress = max(progress, min(99.0, float(override)))
    elapsed = job.get("duration")
    if elapsed is None and created:
        elapsed = max(0.0, _now() - created)
    message = job.get("message") or ""
    if status == "completed":
        message = "完成"
    elif status == "failed":
        message = job.get("error") or "生成失败"
    visual = job.get("visual_state", "pending")
    if status in ("queued", "processing"):
        delivery = "in_progress"
    elif status in ("failed", "cancelled"):
        delivery = "failed"
    elif visual == "confirmed":
        delivery = "confirmed"
    elif visual == "failed":
        delivery = "needs_repair"
    elif visual == "unverified":
        delivery = "unverified"
    elif visual == "passed":
        delivery = "ready"
    else:
        delivery = "review_pending"
    audit = job.get("export_audit") or {}
    if any((audit.get(k) or {}).get("ok") is False for k in ("svg", "pptx")):
        delivery = "blocked"
    scene_audit=(job.get('report') or {}).get('scene_audit') or {}
    is_scene=job.get('scene_engine')=='v2'
    author_confirmed=is_scene and job.get('author_confirmed_revision')==job.get('scene_revision') and bool(job.get('scene_revision'))
    if is_scene and status=='completed':
        delivery='confirmed' if author_confirmed else 'needs_repair' if scene_audit.get('errors') else 'draft'
    return {
        "id": job["id"],
        "progress": round(progress, 1),
        "message": message,
        "elapsed": round(elapsed or 0, 1),
        "elapsed_ms": int((elapsed or 0) * 1000),
        "job_id": job["id"],
        "created_at": stamp,
        "title": _figure_title(job) or "未命名图版",
        "text": job.get("text") or "",
        "original_text": job.get("original_text") or "",
        "layout_contract": job.get("layout_contract") or {},
        "mode": job.get("mode", "auto"),
        "status": status,
        "created": job.get("created"),
        "duration": job.get("duration"),
        "canvas": job.get("canvas"),
        "canvas_mm": job.get("canvas_mm"),
        "dpi": job.get("dpi"),
        "font": job.get("font"),
        "viewport_shape": job.get("viewport_shape"),
        "literature_enabled": job.get("literature_enabled"),
        "stages": job.get("stages", []),
        "report": job.get("report"),
        "error": job.get("error"),
        "export_error": job.get("export_error"),
        "visual_check": job.get("visual_check"),
        "svg_url": f"/api/jobs/{job['id']}/svg" if job.get("svg_path") else None,
        "download_svg": f"/api/jobs/{job['id']}/download?format=svg" if job.get("svg_path") else None,
        "download_png": f"/api/jobs/{job['id']}/download?format=png" if job.get("svg_path") else None,
        "download_pptx": f"/api/jobs/{job['id']}/download?format=pptx" if job.get("ppt") else None,
        "preview_url": f"/api/jobs/{job['id']}/preview.png" if job.get("preview_png") else None,
        "comparison_url": f"/api/jobs/{job['id']}/comparison.png" if job.get("comparison_png") else None,
        "visual_state": job.get("visual_state", "pending"),
        "delivery_state": delivery,
        "visual_checks": job.get("visual_checks"),
        "visual_findings": job.get("visual_findings") or [],
        "review_version": job.get("review_version"),
        "reviewed_at": job.get("reviewed_at"),
        "model_review": job.get("model_review") or {},
        "legacy": job.get("review_version") != REVIEW_VERSION,
        "ppt_visual": job.get("ppt_visual"),
        "export_audit": job.get("export_audit"),
        "diff_url": f"/api/jobs/{job['id']}/diff.png" if job.get("diff_png") else None,
        "research": job.get("research"),
        "illustration_mode": job.get("illustration_mode"),
        "illustration_result": job.get("illustration_result"),
        "reference_id": job.get("reference_id"),
        "draft_source_id": job.get("draft_source_id"),
        "generation_brief": job.get("generation_brief"),
        "next_job": job.get("next_job"),
        "scene_engine": job.get("scene_engine"),
        "archived": bool(job.get("archived", False)),
        "collection": job.get("collection", ""),
        "generation_state": status if is_scene else None,
        "check_state": scene_audit.get('status','not_started') if is_scene else None,
        "author_state": ('confirmed' if author_confirmed else 'pending') if is_scene else None,
        "scene_revision": job.get("scene_revision"),
        "scene_exports": job.get("scene_exports") or [],
        "author_confirmed_revision": job.get("author_confirmed_revision"),
        "revision_of": job.get("revision_of"),
    }


def _normalize_job_meta(meta: dict) -> dict:
    """Fill fields introduced after old jobs were written, so the UI does not
    need a different fallback for every legacy schema."""
    research = meta.get("research")
    if isinstance(research, dict):
        research.setdefault("direct_count", 0)
        research.setdefault("style_count", 0)
        research.setdefault("live_count", 0)
        if "analyzed_count" not in research:
            research["analyzed"] = research.get("live_count") or 0
        if not isinstance(research.get("thumbs"), list):
            research["thumbs"] = []
        meta["research"] = research
    elif research is not None:
        meta["research"] = {"count": 0, "live_count": 0, "analyzed": 0,
                            "direct_count": 0, "style_count": 0, "thumbs": []}
    meta.setdefault("model_review", {})
    ppt_state = meta.get("ppt_export")
    if isinstance(ppt_state, dict) and ppt_state.get("state") == "running":
        ppt_state["state"] = "failed"
        ppt_state["stage"] = "上次导出被中断"
        ppt_state["error"] = "上次导出被中断，请重新导出"
    report = meta.get("report")
    if isinstance(report, dict):
        rework = report.get("rework")
        if isinstance(rework, dict):
            rework.setdefault("mode", "legacy")
            rework.setdefault("duration_sec", None)
    return meta


def _recheck_legacy_job(meta: dict) -> None:
    """Old jobs were audited by an earlier, noisy review pass. Re-run the
    current pixel review once so the recent list does not show false alarms."""
    if meta.get('scene_engine')=='v2':
        return
    if meta.get("status") != "completed" or meta.get("visual_state") == "confirmed":
        return
    if meta.get("review_version") == REVIEW_VERSION:
        # Older builds bumped the version after a local-only pass and called
        # it "passed". Mark those honestly so they cannot be accepted without
        # a model-backed recheck.
        if (not meta.get("model_review") and meta.get("review_scope") != "local-only"
                and meta.get("confirmed_at") is None
                and meta.get("visual_state") in ("passed", "failed")):
            blocking = any(f.get("severity") in ("high", "medium")
                           and f.get("kind") != "vision-unavailable"
                           for f in (meta.get("visual_findings") or []))
            meta["visual_state"] = "failed" if blocking else "unverified"
            meta["review_scope"] = "local-only"
            _save_meta(meta)
        return
    target = meta.get("deliverable_svg") or meta.get("svg_path")
    if not target or not Path(target).is_file():
        return
    try:
        import review
        scene = (meta.get("report") or {}).get("scene_data")
        findings = review.findings(Path(target).read_bytes(), scene)
    except Exception:
        return
    meta["visual_findings"] = findings
    meta["review_version"] = REVIEW_VERSION
    meta["review_scope"] = "local-only"
    blocking = any(f.get("severity") in ("high", "medium")
                   and f.get("kind") != "vision-unavailable" for f in findings)
    meta["visual_state"] = "failed" if blocking else "unverified"
    _save_meta(meta)


def _load_jobs() -> None:
    if not JOBS_DIR.is_dir():
        return
    folders = [p for p in JOBS_DIR.iterdir() if p.is_dir()]
    for folder in sorted(folders, key=lambda p: p.stat().st_mtime, reverse=True):
        meta_path = folder / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                continue
            if not meta.get("id") and JOB_ID_RE.fullmatch(folder.name):
                meta["id"] = folder.name
            if not JOB_ID_RE.fullmatch(str(meta.get("id") or "")):
                continue
            if meta.get("status") in ("queued", "processing"):
                meta["status"] = "error"
                meta["message"] = "上次运行被中断，请重新生成"
                meta["error"] = "interrupted"
                _save_meta(meta)
            if (folder / "result.svg").is_file():
                meta["svg_path"] = str(folder / "result.svg")
            snapshot = json.dumps(meta, sort_keys=True, ensure_ascii=False)
            _normalize_job_meta(meta)
            if json.dumps(meta, sort_keys=True, ensure_ascii=False) != snapshot:
                _save_meta(meta)
            _recheck_legacy_job(meta)
            with JOBS_LOCK:
                JOBS[meta["id"]] = meta
        except Exception as exc:
            print(f"skip unreadable job {folder.name}: {exc}", file=sys.stderr)
            continue
    # Repair dangling auto-rework links left by an interrupted child. Without
    # this, clicking the finished parent follows a dead job and shows nothing.
    for job in list(JOBS.values()):
        child_id = job.get("next_job")
        if not child_id:
            continue
        child = JOBS.get(child_id)
        usable = bool(child and (child.get("svg_path")
                                 or child.get("status") in ("queued", "processing")))
        if not usable:
            job["next_job"] = None
            _save_meta(job)


# ------------------------------------------------------------------ test helpers


def _endpoint(base_url: str, suffix: str) -> str:
    base = base_url.rstrip("/")
    return base + suffix if base.endswith("/v1") else base + "/v1" + suffix


def _key(section: dict) -> str:
    if section.get("api_key"):
        return str(section["api_key"])
    env = section.get("api_key_env")
    return os.environ.get(env, "") if env else ""


def test_target(config: dict, target: str) -> dict:
    started = _now()

    def finish(ok, message, **extra):
        return {"ok": ok, "target": target, "message": message,
                "latency_ms": int((_now() - started) * 1000), **extra}

    section = config.get(target) if target in ("text", "image", "ocr", "vision") else None
    fallback = False
    if target in ("ocr", "vision") and (not section or not section.get("base_url")):
        section = config.get("text") or {}
        fallback = True
    if not section or not section.get("base_url"):
        return finish(False, "未配置（可选）", configured=False)
    configured = True
    base = section["base_url"]
    key = _key(section)
    try:
        if target == "image":
            # A /v1/models probe only proves the port is open. Draw one tiny
            # image so a broken bridge/model is caught here, not 8 minutes into
            # a real job.
            from io import BytesIO
            from PIL import Image
            data = pipeline.generate_raw(
                "A single flat teal circle centered on a pure white background, "
                "minimal scientific icon, no text, no border", config)
            with Image.open(BytesIO(data)) as image:
                image.verify()
            with Image.open(BytesIO(data)) as image:
                width, height = image.size
            if len(data) < 1024 or width < 64 or height < 64:
                return finish(False, f"生图返回内容异常（{width}×{height}，{len(data)} 字节）")
            return finish(True, f"生图正常（{width}×{height}，{len(data) // 1024} KB）",
                          status=200, url=base, configured=configured,
                          width=width, height=height)
        payload = {
            "model": section.get("model") or "default",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        request = urllib.request.Request(
            _endpoint(base, "/chat/completions"),
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}" if key else ""},
            method="POST")
        with urllib.request.urlopen(request, timeout=20) as response:
            message = "复用文本模型，连接正常" if fallback else "连接正常"
            return finish(True, message, status=response.status, url=base,
                          configured=configured)
    except urllib.error.HTTPError as exc:
        if target == "image" and exc.code == 404:
            return finish(True, "服务可达（未提供 /models）", status=404, url=base,
                          configured=True)
        message = f"HTTP {exc.code}"
        try:
            message += " " + exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        return finish(False, message[:300])
    except Exception as exc:
        return finish(False, str(exc)[:300])


def _canvas_from_prompt(text: str):
    """Read the canvas suggested by an AI-expanded prompt so the preview and
    the actual render agree instead of silently keeping the old ratio."""
    dimensions = re.search(r"(\d{3,4})\s*[×xX*]\s*(\d{3,4})", text or "")
    if dimensions:
        width, height = int(dimensions.group(1)), int(dimensions.group(2))
        if 320 <= width <= 8000 and 320 <= height <= 8000:
            return [width, height]
    ratio = re.search(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", text or "")
    if ratio:
        w, h = int(ratio.group(1)), int(ratio.group(2))
        for key, size in (("16:9", [1600, 900]), ("4:3", [1440, 1080]),
                          ("3:2", [1536, 1024]), ("1:1", [1200, 1200]),
                          ("3:4", [900, 1200]), ("2:1", [1600, 800])):
            if (w, h) == tuple(int(v) for v in key.split(":")):
                return size
    return None


def _svg_size(data: bytes) -> tuple[int, int]:
    try:
        root = ET.fromstring(data)
        parts = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox", "0 0 1280 900")) if v]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return int(parts[2]), int(parts[3])
        return int(float(root.get("width", 1280))), int(float(root.get("height", 900)))
    except Exception:
        return 1280, 900


def _visual_checks(svg_path: Path, report: dict, has_preview: bool) -> dict:
    try:
        root = ET.fromstring(svg_path.read_bytes())
    except Exception as exc:
        return {"passed": False, "error": f"SVG parse: {exc}"[:200]}
    counts = {}
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        counts[tag] = counts.get(tag, 0) + 1
    texts = counts.get("text", 0)
    paths = counts.get("path", 0) + counts.get("rect", 0) + counts.get("circle", 0) + counts.get("ellipse", 0)
    images = counts.get("image", 0)
    markers = counts.get("marker", 0) + counts.get("line", 0)
    # A full-canvas white rect is the paper, not figure content.
    try:
        view = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox", "")) if v]
        cw, ch = (view[2], view[3]) if len(view) == 4 else (1280.0, 900.0)
    except (TypeError, ValueError, IndexError):
        cw, ch = 1280.0, 900.0
    for node in root.iter():
        if node.tag.split("}")[-1].lower() != "rect":
            continue
        try:
            x, y = float(node.get("x") or 0), float(node.get("y") or 0)
            w, h = float(node.get("width") or 0), float(node.get("height") or 0)
        except (TypeError, ValueError):
            continue
        if x <= 1 and y <= 1 and w >= cw * 0.95 and h >= ch * 0.95:
            paths = max(0, paths - 1)
    illustrated = images > 0
    # Content presence decides; a missing preview is reported separately and
    # no longer fails the whole check (handled by the caller).
    passed = bool(texts > 0 or illustrated or paths >= 4)
    return {"passed": passed, "texts": texts, "paths": paths, "images": images,
            "markers": markers, "preview": has_preview,
            "mode": "illustrated" if illustrated else "vector"}


def _comparison_page(svg_preview: Path, ppt_preview: Path, output: Path) -> bool:
    try:
        from PIL import Image, ImageDraw
        left = Image.open(svg_preview).convert("RGB")
        right = Image.open(ppt_preview).convert("RGB")
        target_w = 900
        def fit(image):
            scale = target_w / image.width
            return image.resize((target_w, max(1, int(image.height * scale))), Image.LANCZOS)
        left, right = fit(left), fit(right)
        gap, header = 24, 34
        canvas = Image.new("RGB", (target_w * 2 + gap, max(left.height, right.height) + header),
                           "#ffffff")
        draw = ImageDraw.Draw(canvas)
        draw.text((8, 8), "SVG", fill="#102a33")
        draw.text((target_w + gap + 8, 8), "PowerPoint", fill="#102a33")
        canvas.paste(left, (0, header))
        canvas.paste(right, (target_w + gap, header))
        canvas.save(output)
        return True
    except Exception:
        return False


def _png_for(job: dict, config: dict, dpi: int | None = None) -> bytes | None:
    svg_path = Path(job.get("deliverable_svg") or job["svg_path"])
    svg = svg_path.read_bytes()
    try:
        root = ET.fromstring(svg)
        view = root.get("viewBox", "")
        parts = [float(v) for v in re.split(r"[\s,]+", view) if v]
        width, height = (int(parts[2]), int(parts[3])) if len(parts) == 4 else (1280, 900)
    except Exception:
        width, height = 1280, 900
    # Physical export: the figure was authored in millimetres; honour the job's
    # DPI so 180mm @ 400dpi really is ~2835px, not the viewBox 1600px.
    mm = job.get("canvas_mm")
    scale = 1.0
    if dpi and dpi >= 150:
        base_dpi = job.get("dpi") or dpi
        if mm and len(mm) == 2 and mm[0] and mm[1]:
            target_w = float(mm[0]) / 25.4 * dpi
            scale = max(0.25, min(4.0, target_w / max(1, width)))
        else:
            scale = max(0.25, min(4.0, dpi / 200.0))
    cached = svg_path.with_name(
        svg_path.stem + (".png" if scale == 1.0 else f".dpi{int(round(scale * 100))}.png"))
    fresh = cached.is_file() and cached.stat().st_mtime >= svg_path.stat().st_mtime
    if fresh:
        return cached.read_bytes()
    png = qa.rasterize(svg, width, height, config, scale=scale)
    if png:
        temp = cached.with_name(cached.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            temp.write_bytes(png)
            os.replace(temp, cached)
        except OSError:
            temp.unlink(missing_ok=True)
    return png


# ------------------------------------------------------------- save as


def _safe_filename(text: str, ext: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", str(text or "Figure"))
    value = re.sub(r"\s+", " ", value).strip(" .")[:48]
    # Windows device names are not valid file stems even with an extension.
    if value.split(".", 1)[0].upper() in {
            "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
            "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3",
            "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}:
        value = "Figure-" + value
    return f"{value or 'Figure'}.{ext}"


def _pdf_for(job: dict, config: dict) -> bytes:
    """Export the same figure the preview shows, not a stale raster cache."""
    svg_path = Path(job.get("deliverable_svg") or job["svg_path"])
    svg = svg_path.read_bytes()
    width, height = _svg_size(svg)
    import qa
    dpi = int(job.get("dpi") or 300)
    mm = job.get("canvas_mm") or []
    scale = 1.0
    if mm and len(mm) == 2 and mm[0] and mm[1]:
        target_width = float(mm[0]) / 25.4 * dpi
        scale = max(0.25, min(4.0, target_width / max(1, width)))
    png = qa.rasterize(svg, width, height, config, scale=scale)
    if not png:
        raise RuntimeError("无法渲染 PDF 预览")
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(fitz.Rect(0, 0, width, height), stream=png)
    return doc.tobytes()


def _auto_export_path(job: dict, filename: str) -> Path:
    """Return a writable, non-destructive path for one export.

    The web UI must never depend on a native modal dialog: WebView2 can hide
    it behind the host window and the HTTP request then waits forever. Export
    files therefore land in a predictable per-job folder, and the UI shows the
    exact path with Open / Reveal actions.
    """
    folder = EXPORT_DIR / str(job.get("id") or "job")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        folder = Path.home() / "Pictures" / "CellFigureStudio" / str(job.get("id") or "job")
        folder.mkdir(parents=True, exist_ok=True)
    stem, ext = os.path.splitext(filename)
    candidate = folder / filename
    index = 2
    while candidate.exists():
        candidate = folder / f"{stem}-{index}{ext}"
        index += 1
    return candidate


def _native_save_as(default_name: str, ext: str) -> str | None:
    """Native Windows Save As dialog; returns the chosen path or None."""
    global LAST_SAVE_DIR
    import ctypes
    from ctypes import wintypes

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", wintypes.LPVOID),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    folder = LAST_SAVE_DIR if LAST_SAVE_DIR and Path(LAST_SAVE_DIR).is_dir() else None
    if not folder:
        desktop = Path.home() / "Desktop"
        folder = str(desktop if desktop.is_dir() else Path.home())
    buffer = ctypes.create_unicode_buffer(str(Path(folder) / default_name), 2048)
    label = {"svg": "SVG 矢量图", "png": "PNG 图片", "pdf": "PDF 文档",
             "pptx": "PowerPoint 演示文稿"}.get(ext, ext.upper())
    sep = chr(0)
    filter_text = (f"{label} (*.{ext}){sep}*.{ext}{sep}"
                   f"所有文件 (*.*){sep}*.*{sep}{sep}")
    flags = 0x00000002 | 0x00000008 | 0x00000800 | 0x00080000 | 0x00800000
    with SAVE_LOCK:
        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        try:
            ofn.hwndOwner = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
        except Exception:
            ofn.hwndOwner = None
        ofn.lpstrFilter = filter_text
        ofn.nFilterIndex = 1
        ofn.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
        ofn.nMaxFile = len(buffer)
        ofn.lpstrInitialDir = folder
        ofn.lpstrTitle = "保存科研图"
        ofn.lpstrDefExt = ext
        ofn.Flags = flags
        try:
            ok = ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn))
        except Exception:
            return None
        if not ok:
            return None
        path = str(buffer.value).strip()
        if not path:
            return None
        LAST_SAVE_DIR = str(Path(path).parent)
        if not path.lower().endswith("." + ext.lower()):
            path += "." + ext.lower()
        return path


def _export_payload(job: dict, fmt: str, config: dict, dpi: int | None = None):
    fmt = fmt.lower()
    if fmt == "svg":
        source = Path(job.get("deliverable_svg") or job.get("svg_path") or "")
        if not source.is_file():
            raise FileNotFoundError("结果还没有准备好")
        return source, "svg"
    if fmt == "png":
        data = _png_for(job, config, dpi=dpi)
        if not data:
            raise RuntimeError("PNG 渲染失败，请检查本机浏览器")
        return data, "png"
    if fmt == "pdf":
        return _pdf_for(job, config), "pdf"
    if fmt in ("pptx", "ppt"):
        ppt = job.get("ppt") or {}
        source = Path(str(ppt.get("pptx") or ""))
        if not source.is_file():
            raise FileNotFoundError("还没有生成 PPTX，请先点击导出 PPTX")
        return source, "pptx"
    raise ValueError("不支持的格式")


# ------------------------------------------------------------------ HTTP


def _job_asset_url(job: dict, kind: str) -> str | None:
    key = {"comparison": "comparison_png", "diff": "diff_png"}.get(kind, "")
    if job.get(key):
        suffix = {"comparison": "comparison.png", "diff": "diff.png"}[kind]
        return f"/api/jobs/{job['id']}/{suffix}"
    return None


def _ppt_status(job: dict) -> dict:
    state = job.get("ppt_export") or {}
    return {
        "state": state.get("state", "idle"),
        "pct": state.get("pct", 0.0),
        "stage": state.get("stage", ""),
        "eta": state.get("eta"),
        "elapsed": state.get("elapsed", 0.0),
        "nodes": state.get("nodes"),
        "error": state.get("error"),
        "comparison_url": _job_asset_url(job, "comparison"),
        "diff_url": _job_asset_url(job, "diff"),
        "ppt_visual": job.get("ppt_visual"),
        "download_url": (f"/api/jobs/{job['id']}/download?format=pptx"
                         if (job.get("ppt") or {}).get("pptx") else None),
    }


def _ppt_worker(job: dict) -> None:
    paths = job_paths(job["id"])
    # Prefer the font the figure was generated with so a mid-session settings
    # change does not silently re-typeset old exports.
    font = str(job.get("font") or load_config().get("font") or "Times New Roman")
    state = job["ppt_export"]

    def ticker():
        while state.get("state") == "running":
            preview_start = state.get("preview_start")
            if preview_start:
                now = _now()
                estimate = max(6.0, float(state.get("preview_est") or 20.0))
                spent = now - preview_start
                pct = min(0.985, 0.86 + 0.125 * min(1.0, spent / estimate))
                state.update({
                    "pct": round(pct * 100, 1),
                    "stage": "PowerPoint 渲染预览",
                    "eta": max(1, round(estimate - spent)),
                    "elapsed": round(now - state["started"], 1),
                })
            time.sleep(1.0)

    threading.Thread(target=ticker, daemon=True).start()

    def progress(frac: float, stage: str, total: int | None = None) -> None:
        now = _now()
        elapsed = now - state["started"]
        if total:
            state["nodes"] = int(total)
        state["pct"] = round(min(99.0, frac * 100), 1)
        state["stage"] = stage
        state["elapsed"] = round(elapsed, 1)
        nodes = state.get("nodes") or 1000
        preview_est = min(240.0, max(10.0, 8.0 + nodes * 0.03))
        if frac >= 0.86:
            if not state.get("preview_start"):
                state["preview_start"] = now
                state["preview_est"] = preview_est
            state["eta"] = max(1, round(preview_est - (now - state["preview_start"])))
        else:
            state["eta"] = max(1, round(elapsed * (0.86 - max(frac, 0.01)) / max(frac, 0.01)
                                       + preview_est))

    try:
        source_svg = Path(job.get("deliverable_svg") or job["svg_path"]).read_bytes()
        if b"<image" not in source_svg:
            # The vendored SVG post-processor rejects raster content; figures
            # in illustration mode go straight to the native PPTX builder.
            skill_bridge.prepare(paths, job["id"], font)
            if not (paths / "svg-output.json").is_file():
                skill_bridge.export_svg(paths, font)
        result = skill_bridge.export_ppt(paths, font, progress=progress)
        job["ppt"] = result
        audit = dict(job.get("export_audit") or {})
        audit["pptx"] = _pptx_audit(result.get("pptx"))
        svg_audit = audit.get("svg") or {}
        if audit["pptx"].get("ok") and svg_audit.get("ok"):
            expected_images = int(svg_audit.get("images") or 0)
            expected_texts = int(svg_audit.get("texts") or 0)
            if (audit["pptx"].get("pictures") != expected_images
                    or audit["pptx"].get("texts") != expected_texts):
                audit["pptx"]["mismatch"] = {
                    "svg_images": expected_images,
                    "svg_texts": expected_texts,
                }
                audit["pptx"]["ok"] = False
        job["export_audit"] = audit
        progress(0.97, "生成 SVG / PPT 比对图")
        ppt_preview = result.get("preview")
        svg_preview = job.get("preview_png")
        if ppt_preview and svg_preview and Path(ppt_preview).is_file():
            comparison = paths / "comparison.png"
            if _comparison_page(Path(svg_preview), Path(ppt_preview), comparison):
                job["comparison_png"] = str(comparison)
            job["ppt_visual"] = qa.compare(Path(svg_preview).read_bytes(),
                                           Path(ppt_preview).read_bytes())
            ppt_findings = review.compare_texts(
                Path(job.get("deliverable_svg") or job["svg_path"]).read_bytes(),
                result.get("pptx"))
            diff_findings, heat = review.diff_regions(
                Path(svg_preview).read_bytes(), Path(ppt_preview).read_bytes())
            if heat:
                (paths / "diff.png").write_bytes(heat)
                job["diff_png"] = str(paths / "diff.png")
            if len(diff_findings) > 2:
                # Per-region pixel noise from font rasterisation drowns the
                # real findings; keep one low-level summary instead.
                visual = job.get("ppt_visual") or {}
                diff_findings = [{
                    "kind": "layout", "severity": "low",
                    "message": (f"PPT 与 SVG 有 {len(diff_findings)} 处像素差异"
                                f"（平均差 {float(visual.get('mean_abs_diff') or 0):.3f}），"
                                "多为字体渲染差异"),
                    "suggestion": "如需逐像素一致，可在 PowerPoint 中确认字体已安装",
                }]
            job["visual_findings"] = ((job.get("visual_findings") or [])
                                      + ppt_findings + diff_findings)
            if any(f.get("severity") == "high" for f in ppt_findings):
                job["visual_state"] = "failed"
        state.update({"state": "done", "pct": 100.0, "stage": "导出完成",
                      "eta": 0, "elapsed": round(_now() - state["started"], 1)})
    except Exception as exc:
        state.update({"state": "failed", "error": f"{type(exc).__name__}: {exc}"[:600],
                      "stage": "导出失败", "eta": None})
    _save_meta(job)


class Handler(BaseHTTPRequestHandler):
    server_version = "Rylume/2.9"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _send(self, code, body: bytes, content_type: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, payload):
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _origin_allowed(self) -> bool:
        """Reject DNS-rebinding and cross-site requests.

        The studio only ever binds to loopback, so a Host that is not one of
        our own loopback names is an attack or a misconfiguration. Browsers
        send Origin for cross-site POSTs; same-origin requests may omit it.
        """
        try:
            port = self.server.server_address[1]
        except Exception:
            return False
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in hosts:
            return False
        origin = (self.headers.get("Origin") or "").strip().lower().rstrip("/")
        if origin and origin not in {f"http://{h}" for h in hosts}:
            return False
        return True

    def _body(self) -> dict:
        # Cache the parsed body: every POST must consume Content-Length even
        # when the handler ignores it, otherwise keep-alive connections get
        # their next request line corrupted (the browser then sees 501).
        if hasattr(self, "_body_cache"):
            return self._body_cache
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            length = -1
        if length <= 0:
            self._body_cache = {}
            return self._body_cache
        if length > 24 * 1024 * 1024:
            # Not draining the body would corrupt the next keep-alive
            # request; close the connection instead.
            self.close_connection = True
            self._body_cache = {}
            return self._body_cache
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except Exception:
            try:
                parsed = json.loads(raw.decode("gb18030"))
            except Exception:
                parsed = {}
        self._body_cache = parsed if isinstance(parsed, dict) else {}
        return self._body_cache

    # ---- GET ----

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/") and not self._origin_allowed():
            return self._json(403, {"ok": False, "error": "forbidden host"})

        if path in ("", "/", "/index.html"):
            return self._serve_file(UI_DIR / "canvas-studio.html", "text/html; charset=utf-8")
        if path in ("/legacy", "/legacy/", "/legacy/index.html"):
            return self._serve_file(UI_DIR / "index.html", "text/html; charset=utf-8")
        if document_assistant.dispatch(self, "GET", path, sys.modules[__name__]):
            return
        if onboarding_state.dispatch(self, "GET", path, sys.modules[__name__]):
            return
        if path.startswith("/api/") and scene_service.dispatch(self, "GET", path, sys.modules[__name__]):
            return
        if path.startswith("/ui/"):
            target = (UI_DIR / path[4:]).resolve()
            if UI_DIR.resolve() in target.parents and target.is_file():
                return self._serve_file(target)
            return self._json(404, {"ok": False, "error": "not found"})

        if path == "/api/state":
            with JOBS_LOCK:
                jobs = sorted(JOBS.values(), key=lambda j: j.get("created", 0), reverse=True)[:30]
                return self._json(200, {
                    "ok": True,
                    "config": public_config(load_config()),
                    "modes": MODES,
                    "jobs": [_public_job(j) for j in jobs],
                    "version": APP_VERSION,
                })

        if path == "/api/archetypes":
            import archetypes
            return self._json(200, {"ok": True, "archetypes": archetypes.ARCHETYPE_DESCRIPTIONS})

        if path == "/api/jobs":
            from urllib.parse import parse_qs
            query=parse_qs(self.path.split('?',1)[1] if '?' in self.path else '')
            try:
                limit=max(1,min(1000,int((query.get('limit') or [50])[0])))
            except ValueError:
                return self._json(400,{'ok':False,'error':'任务数量无效'})
            with JOBS_LOCK:
                jobs = sorted(JOBS.values(), key=lambda j: j.get("created", 0), reverse=True)[:limit]
                return self._json(200, {"ok": True, "jobs": [_public_job(j) for j in jobs]})

        if path == "/api/research/figure":
            from urllib.parse import parse_qs
            query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            rel = (query.get("path") or [""])[0]
            try:
                import literature
                root = literature.RESEARCH_DIR.resolve()
                target = (root / rel).resolve()
                if root != target and root not in target.parents:
                    return self._json(403, {"ok": False, "error": "forbidden"})
                if not target.is_file():
                    return self._json(404, {"ok": False, "error": "not found"})
                suffix = target.suffix.lower()
                mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
                    suffix, "application/octet-stream")
                return self._send(200, target.read_bytes(), mime)
            except Exception as exc:
                return self._json(500, {"ok": False, "error": str(exc)[:200]})

        ppt_status_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/ppt-status", path)
        if ppt_status_match:
            job = JOBS.get(ppt_status_match.group(1))
            if not job:
                return self._json(404, {"ok": False, "error": "job not found"})
            return self._json(200, {"ok": True, **_ppt_status(job)})

        asset_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/(preview\.png|comparison\.png|diff\.png)", path)
        if asset_match:
            job = JOBS.get(asset_match.group(1))
            key = {"preview.png": "preview_png", "comparison.png": "comparison_png",
                   "diff.png": "diff_png"}[asset_match.group(2)]
            if not job or not job.get(key) or not Path(job[key]).is_file():
                return self._json(404, {"ok": False, "error": "asset not ready"})
            return self._send(200, Path(job[key]).read_bytes(), "image/png")

        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)(/svg|/download)?", path)
        if match:
            job_id, suffix = match.group(1), match.group(2)
            job = JOBS.get(job_id)
            if not job:
                return self._json(404, {"ok": False, "error": "job not found"})
            if not suffix:
                return self._json(200, {**_public_job(job), "ok": True})
            if not job.get("svg_path") or not Path(job["svg_path"]).is_file():
                return self._json(409, {"ok": False, "error": "result not ready"})
            if suffix == "/svg":
                source = Path(job.get("deliverable_svg") or job["svg_path"])
                if not source.is_file():
                    source = Path(job["svg_path"])
                if not source.is_file():
                    return self._json(409, {"ok": False, "error": "result not ready"})
                return self._send(200, source.read_bytes(), "image/svg+xml")
            fmt = "svg"
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            if "format=pptx" in query:
                ppt = job.get("ppt") or {}
                path = Path(str(ppt.get("pptx") or ""))
                if not path.is_file():
                    return self._json(409, {"ok": False, "error": "还没有生成 PPTX"})
                return self._send(200, path.read_bytes(),
                                  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                  {"Content-Disposition": f'attachment; filename="{job_id}.pptx"'})
            if "format=pdf" in query:
                try:
                    data = _pdf_for(job, load_config())
                except Exception as exc:
                    return self._json(500, {"ok": False,
                                            "error": f"PDF 导出失败：{exc}"[:300]})
                return self._send(200, data, "application/pdf",
                                  {"Content-Disposition": f'attachment; filename="{job_id}.pdf"'})
            if "format=png" in query:
                fmt = "png"
            if fmt == "png":
                png = _png_for(job, load_config())
                if not png:
                    return self._json(503, {"ok": False, "error": "没有可用的浏览器渲染 PNG"})
                return self._send(200, png, "image/png",
                                  {"Content-Disposition": f'attachment; filename="{job_id}.png"'})
            # Same deliverable the preview and save-as use; job["svg_path"] is
            # the raw render and can differ (font normalization, postprocess).
            source = Path(job.get("deliverable_svg") or job["svg_path"])
            if not source.is_file():
                source = Path(job["svg_path"])
            if not source.is_file():
                return self._json(409, {"ok": False, "error": "result not ready"})
            return self._send(200, source.read_bytes(), "image/svg+xml",
                              {"Content-Disposition": f'attachment; filename="{job_id}.svg"'})

        return self._json(404, {"ok": False, "error": "not found"})

    def _serve_file(self, path: Path, content_type: str | None = None):
        if not path.is_file():
            return self._json(404, {"ok": False, "error": f"missing {path.name}"})
        suffix = path.suffix.lower()
        types = {".html": "text/html; charset=utf-8", ".css": "text/css",
                 ".js": "application/javascript", ".svg": "image/svg+xml",
                 ".png": "image/png", ".woff2": "font/woff2", ".json": "application/json"}
        return self._send(200, path.read_bytes(),
                          content_type or types.get(suffix, "application/octet-stream"))

    def do_PATCH(self):  # noqa: N802
        return self._scene_mutation('PATCH')

    def do_PUT(self):  # noqa: N802
        return self._scene_mutation('PUT')

    def _scene_mutation(self, method):
        if hasattr(self, "_body_cache"):
            del self._body_cache
        self._body()
        if not self._origin_allowed():
            return self._json(403, {"ok": False, "error": "forbidden origin"})
        if (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower() != "application/json":
            return self._json(415, {"ok": False, "error": "只接受 application/json"})
        if not scene_service.dispatch(self, method, self.path.split("?", 1)[0], sys.modules[__name__]):
            return self._json(404, {"ok": False, "error": "not found"})

    # ---- POST ----

    def do_POST(self):  # noqa: N802
        # Handler instances are reused across keep-alive requests, so the
        # cached body must be dropped before draining this request.
        if hasattr(self, "_body_cache"):
            del self._body_cache
        self._body()  # always drain the request body
        if not self._origin_allowed():
            return self._json(403, {"ok": False, "error": "forbidden origin"})
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            return self._json(415, {"ok": False, "error": "只接受 application/json"})
        path = self.path.split("?", 1)[0]
        if document_assistant.dispatch(self, "POST", path, sys.modules[__name__]):
            return
        if onboarding_state.dispatch(self, "POST", path, sys.modules[__name__]):
            return
        if scene_service.dispatch(self, "POST", path, sys.modules[__name__]):
            return
        try:
            if path == "/api/config":
                config = self._body()
                if not isinstance(config, dict):
                    return self._json(400, {"ok": False, "error": "config must be an object"})
                # Merge over the stored config: a partial payload (for example
                # only {"quality": "hd"}) must never wipe model endpoints/keys.
                with CONFIG_LOCK:
                    stored = load_config()
                    patch = dict(config)
                    # UI aliases are derived, never stored; keeping stale
                    # copies makes a later save resurrect an old endpoint.
                    for alias in ("text_model", "image_model", "vision_model"):
                        patch.pop(alias, None)
                    merged = _deep_merge(stored, patch)
                    for key in ("text", "image", "vision"):
                        section = merged.get(key)
                        if not isinstance(section, dict):
                            continue
                        incoming = patch.get(key)
                        if not isinstance(incoming, dict):
                            continue
                        if incoming.get("api_key_clear"):
                            section["api_key"] = ""
                        elif "api_key" in incoming and not str(incoming.get("api_key") or ""):
                            # The UI cannot show a stored key, so an empty
                            # field means "unchanged", not "delete".
                            section["api_key"] = (stored.get(key) or {}).get("api_key", "")
                        section.pop("api_key_clear", None)
                        section.pop("api_key_set", None)
                    save_config(merged)
                    merged = load_config()
                return self._json(200, {"ok": True, "config": public_config(merged)})

            if path == "/api/test":
                body = self._body()
                target = str(body.get("target", "text"))
                config = load_config()
                override = body.get("config")
                if isinstance(override, dict):
                    # Test the values currently typed in Settings, before they
                    # are saved. Empty key fields keep the stored secret.
                    patch = dict(override)
                    for alias in ("text_model", "image_model", "vision_model"):
                        patch.pop(alias, None)
                    merged = _deep_merge(config, patch)
                    for key in ("text", "image", "vision"):
                        section = merged.get(key)
                        if isinstance(section, dict) and not section.get("api_key"):
                            section["api_key"] = (config.get(key) or {}).get("api_key", "")
                        if isinstance(section, dict):
                            section.pop("api_key_set", None)
                            section.pop("api_key_clear", None)
                    config = normalize_config(merged)
                if target == "all":
                    results = [test_target(config, "text"), test_target(config, "image"),
                               test_target(config, "vision")]
                    labels = {"text": "文本模型", "image": "图像模型", "vision": "视觉模型"}
                    for item in results:
                        item["label"] = labels.get(item.get("target", ""), "")
                        _log_event("test", target=item.get("target"), ok=item.get("ok"),
                                   latency_ms=item.get("latency_ms"),
                                   message=str(item.get("message") or "")[:120])
                    required = [r for r in results
                                if r.get("target") != "vision" or r.get("configured")]
                    return self._json(200, {"ok": all(r["ok"] for r in required),
                                            "results": results})
                result = test_target(config, target)
                _log_event("test", target=target, ok=result.get("ok"),
                           latency_ms=result.get("latency_ms"),
                           message=str(result.get("message") or "")[:120])
                return self._json(200, result)

            if path == "/api/optimize":
                body = self._body()
                text = str(body.get("text") or "").strip()
                if not text:
                    return self._json(400, {"ok": False, "error": "请先写一句描述"})
                if len(text) > 4000:
                    return self._json(413, {"ok": False, "error": "描述太长，请控制在 4000 字以内"})
                body_canvas = body.get("canvas")
                canvas_hint = None
                if isinstance(body_canvas, (list, tuple)) and len(body_canvas) >= 2:
                    try:
                        canvas_hint = [int(body_canvas[0]), int(body_canvas[1])]
                    except (TypeError, ValueError):
                        canvas_hint = None
                try:
                    dna = body.get('style_dna') or {}
                    style_hint = str(dna.get('reference_summary') or dna.get('visual_style_summary') or '')[:1200] if isinstance(dna,dict) else ''
                    optimized = pipeline.optimize_brief(text, load_config(), canvas=canvas_hint, style=style_hint)
                except Exception as exc:
                    return self._json(400, {"ok": False, "error": str(exc)[:400]})
                return self._json(200, {"ok": True, "text": optimized, "original": text,
                                        "canvas": _canvas_from_prompt(optimized)})

            if path == "/api/assist/clarify":
                body = self._body()
                text = str(body.get("text") or "").strip()
                if not text:
                    return self._json(400, {"ok": False, "error": "请先输入科研绘图需求描述"})
                if len(text) > 4000:
                    return self._json(413, {"ok": False, "error": "描述太长，请控制在 4000 字以内"})
                try:
                    import assist_guide
                    cards = assist_guide.generate_clarification_cards(
                        text, load_config(), reference=body.get("style_dna"),
                        image=body.get("image"))
                    return self._json(200, {"ok": True, "data": cards})
                except Exception as exc:
                    return self._json(400, {"ok": False, "error": str(exc)[:400]})

            if path == "/api/assist/compose-prompt":
                body = self._body()
                text = str(body.get("text") or "").strip()
                if not text:
                    return self._json(400, {"ok": False, "error": "请先输入科研绘图需求描述"})
                answers = body.get("answers") or {}
                try:
                    import assist_guide
                    enhanced, canvas, illus = assist_guide.compose_enhanced_prompt(
                        text, answers, load_config(), style_dna=body.get("style_dna"))
                    return self._json(200, {"ok": True, "enhanced_text": enhanced,
                                            "canvas": canvas, "illustration_mode": illus})
                except Exception as exc:
                    return self._json(400, {"ok": False, "error": str(exc)[:400]})

            if path == "/api/analyze-reference-deep":
                body = self._body()
                image = str(body.get("image") or "")
                if not image.startswith("data:image/"):
                    return self._json(400, {"ok": False, "error": "参考图格式无效"})
                if len(image) > 16 * 1024 * 1024:
                    return self._json(413, {"ok": False, "error": "参考图不能超过 10MB"})
                try:
                    import archetypes
                    dna = archetypes.extract_reference_style(image, load_config())
                    return self._json(200, {"ok": True, "style_dna": dna})
                except Exception as exc:
                    return self._json(400, {"ok": False, "error": str(exc)[:500]})

            if path == "/api/archetypes":
                import archetypes
                return self._json(200, {"ok": True, "archetypes": archetypes.ARCHETYPE_DESCRIPTIONS})

            if path == "/api/analyze-image":
                body = self._body()
                text = str(body.get("text") or "").strip()
                image = str(body.get("image") or "")
                if not text:
                    return self._json(400, {"ok": False, "error": "先写一句描述，再按参考图优化"})
                if not image.startswith("data:image/"):
                    return self._json(400, {"ok": False, "error": "参考图格式无效"})
                if len(image) > 16 * 1024 * 1024:
                    return self._json(413, {"ok": False, "error": "参考图不能超过 10MB"})
                config = load_config()
                try:
                    style, summary = pipeline.analyze_image(image, config)
                    optimized = pipeline.optimize_brief(text, config, style=summary)
                except Exception as exc:
                    return self._json(400, {"ok": False, "error": str(exc)[:500]})
                return self._json(200, {"ok": True, "style": style,
                                        "style_summary": summary, "text": optimized,
                                        "original": text})

            if path == "/api/generate":
                body = self._body()
                text = str(body.get("text") or "").strip()
                if not text:
                    return self._json(400, {"ok": False, "error": "请先输入科研内容"})
                if len(text) > 4000:
                    return self._json(413, {"ok": False, "error": "描述太长，请控制在 4000 字以内"})
                config = load_config()
                mode = "auto"
                config["mode"] = mode
                original_text = str(body.get("original_text") or text)
                reference_layout = (body.get("reference_layout")
                                    or (body.get("style_dna") or {}).get("layout_analysis"))
                config["reference_layout"] = reference_layout or {}
                config["reference_layout_mode"] = str(body.get("reference_layout_mode") or "")
                contract = layout_contract.build(original_text, text,
                                                 reference_layout=reference_layout)
                config["original_text"] = original_text
                config["layout_contract"] = contract
                if contract.get("archetype"):
                    # The author's own wording wins over a rewritten prompt.
                    config["archetype"] = contract["archetype"]
                if body.get("canvas"):
                    try:
                        width, height = int(body["canvas"][0]), int(body["canvas"][1])
                        if 320 <= width <= 8000 and 320 <= height <= 8000:
                            config["canvas"] = [width, height]
                            config["canvas_user"] = True
                    except (TypeError, ValueError, IndexError):
                        pass
                if body.get("canvas_mm"):
                    try:
                        mm = [float(body["canvas_mm"][0]), float(body["canvas_mm"][1])]
                        if all(10 <= value <= 2000 for value in mm):
                            config["canvas_mm"] = mm
                    except (TypeError, ValueError, IndexError):
                        pass
                if body.get("dpi"):
                    try:
                        dpi = int(body["dpi"])
                        if 72 <= dpi <= 1200:
                            config["dpi"] = dpi
                    except (TypeError, ValueError):
                        pass
                if str(body.get("viewport_shape") or "") in ("rect", "card", "circle", "ellipse"):
                    config["viewport_shape"] = body["viewport_shape"]
                if body.get("style_dna"):
                    config["style_dna"] = sanitize_style(body["style_dna"])
                if body.get("archetype") and not contract.get("archetype"):
                    config["archetype"] = str(body["archetype"])
                config["literature"] = {"enabled": bool(body.get("literature"))}
                # Image mode builds the figure from per-object generated
                # assets; it is not a one-shot whole-figure raster.
                if "illustration_mode" in body:
                    illum = str(body.get("illustration_mode") or "").lower()
                    config["illustration_mode"] = "image" if illum == "image" else "vector"
                else:
                    config["illustration_mode"] = effective_illustration_mode(config)
                illustration_mode = config["illustration_mode"]
                if body.get("palette"):
                    config["palette_name"] = str(body["palette"])
                    try:
                        import archetypes_render
                        preset = archetypes_render.PALETTES.get(str(body["palette"]))
                        if preset:
                            dna = dict(config.get("style_dna") or {})
                            dna["palette"] = preset
                            config["style_dna"] = dna
                    except Exception:
                        pass
                render_text = text
                prompt_contract = layout_contract.build(text)
                if contract.get("archetype") and prompt_contract.get("archetype")                         and contract["archetype"] != prompt_contract["archetype"]:
                    render_text = original_text
                elif contract.get("layout") and prompt_contract.get("layout")                         and contract["layout"] != prompt_contract["layout"]:
                    render_text = original_text
                job = _create_job(render_text, config)
                return self._json(200, {"ok": True, "job_id": job["id"]})

            if path == "/api/open-config-dir":
                try:
                    os.startfile(str(BASE_DIR))  # type: ignore[attr-defined]
                except Exception:
                    pass
                return self._json(200, {"ok": True, "path": str(BASE_DIR)})

            confirm_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/confirm", path)
            if confirm_match:
                job = JOBS.get(confirm_match.group(1))
                if not job:
                    return self._json(404, {"ok": False, "error": "job not found"})
                if not job.get("preview_png") and not (
                        job.get("deliverable_svg") or job.get("svg_path")):
                    return self._json(409, {"ok": False, "error": "预览还没准备好"})
                checks = job.get("visual_checks")
                if job.get("visual_state") == "failed" or (
                        isinstance(checks, dict) and checks.get("passed") is False):
                    return self._json(409, {
                        "ok": False,
                        "error": "本地自检未通过，不能验收；请点「重新审查」或重新生成"})
                blocking = [f for f in (job.get("visual_findings") or [])
                            if f.get("severity") in ("high", "medium")
                            and f.get("kind") != "vision-unavailable"]
                if blocking:
                    return self._json(409, {
                        "ok": False,
                        "error": f"还有 {len(blocking)} 处硬伤/警告未修复，先跑自动修复或重新审查"})
                if job.get("visual_state") == "unverified" or _audit_gap(job.get("visual_findings") or []):
                    return self._json(409, {
                        "ok": False,
                        "error": "视觉模型审查未完成，本图只通过了本地几何检查；请检查模型设置后重新审查"})
                job["visual_state"] = "confirmed"
                job["confirmed_at"] = time.time()
                if not job.get("preview_png"):
                    job["confirmed_without_preview"] = True
                _save_meta(job)
                return self._json(200, {"ok": True, "visual_state": "confirmed"})

            ppt_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/ppt", path)
            if ppt_match:
                job = JOBS.get(ppt_match.group(1))
                if not job:
                    return self._json(404, {"ok": False, "error": "job not found"})
                if not job.get("svg_path"):
                    return self._json(409, {"ok": False, "error": "结果还没准备好"})
                with PPT_START_LOCK:
                    state = job.get("ppt_export") or {}
                    if state.get("state") == "running":
                        return self._json(200, {"ok": True, "started": True,
                                                "status": _ppt_status(job)})
                    ppt_info = job.get("ppt") or {}
                    if ppt_info.get("pptx") and Path(str(ppt_info.get("pptx"))).is_file():
                        return self._json(200, {"ok": True, **ppt_info,
                                                "comparison_url": _job_asset_url(job, "comparison"),
                                                "diff_url": _job_asset_url(job, "diff"),
                                                "ppt_visual": job.get("ppt_visual")})
                    job["ppt_export"] = {"state": "running", "pct": 0.0,
                                         "stage": "准备导出", "eta": None,
                                         "started": _now(), "elapsed": 0.0}
                    threading.Thread(target=_ppt_worker, args=(job,), daemon=True).start()
                return self._json(200, {"ok": True, "started": True,
                                        "status": _ppt_status(job)})

            ppt_status_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/ppt-status", path)
            if ppt_status_match:
                job = JOBS.get(ppt_status_match.group(1))
                if not job:
                    return self._json(404, {"ok": False, "error": "job not found"})
                return self._json(200, {"ok": True, **_ppt_status(job)})

            retry_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/retry", path)
            if retry_match:
                src = JOBS.get(retry_match.group(1))
                if not src or not src.get("text"):
                    return self._json(404, {"ok": False, "error": "job not found"})
                cfg = load_config()
                cfg["mode"] = "auto"
                if src.get("canvas"):
                    cfg["canvas"] = src["canvas"]
                    cfg["canvas_user"] = True
                if src.get("viewport_shape"):
                    cfg["viewport_shape"] = src["viewport_shape"]
                if src.get("archetype"):
                    cfg["archetype"] = src["archetype"]
                cfg["illustration_mode"] = ("image"
                                            if str(src.get("illustration_mode") or "") == "image"
                                            else "vector")
                cfg["literature"] = {"enabled": bool(src.get("literature_enabled"))}
                # Restore the original job's visual identity first; a palette
                # preset only fills in when the source had no saved DNA.
                if src.get("style_dna"):
                    cfg["style_dna"] = src["style_dna"]
                elif src.get("palette_name"):
                    try:
                        import archetypes_render
                        preset = archetypes_render.PALETTES.get(str(src["palette_name"]))
                        if preset:
                            cfg["style_dna"] = {"palette": preset}
                    except Exception:
                        pass
                if src.get("style_profile"):
                    cfg["style_profile"] = src["style_profile"]
                if src.get("design_brief"):
                    cfg["design_brief"] = src["design_brief"]
                for key in ("canvas_mm", "dpi", "font"):
                    if src.get(key) is not None:
                        cfg[key] = src[key]
                # Retry must obey the author's original wording, not the AI
                # prompt generated from it; otherwise the contract rebuild sees
                # translated stage names and flags its own output as drift.
                cfg["original_text"] = src.get("original_text") or src["text"]
                cfg["layout_contract"] = (src.get("layout_contract")
                                          or layout_contract.build(cfg["original_text"], src["text"]))
                job = _create_job(src["text"], cfg)
                return self._json(200, {"ok": True, "job_id": job["id"]})

            cancel_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/cancel", path)
            if cancel_match:
                job = JOBS.get(cancel_match.group(1))
                if not job:
                    return self._json(404, {"ok": False, "error": "job not found"})
                if job.get("status") in ("queued", "processing"):
                    job["cancel_requested"] = True
                    job["message"] = "正在取消…"
                    _save_meta(job)
                return self._json(200, {"ok": True, "cancel_requested": True})

            pdf_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/pdf", path)
            if pdf_match:
                job = JOBS.get(pdf_match.group(1))
                if not job:
                    return self._json(404, {"ok": False, "error": "job not found"})
                if job.get("status") != "completed":
                    return self._json(409, {"ok": False, "error": "图还没有生成完成"})
                target = Path(job.get("deliverable_svg") or job.get("svg_path") or "")
                if not target.is_file():
                    return self._json(409, {"ok": False, "error": "结果还没准备好"})
                try:
                    pdf = _pdf_for(job, load_config())
                    download = "attachment" if (self.path.split("?", 1)[1] if "?" in self.path else "").find("download=1") >= 0 else "inline"
                    return self._send(200, pdf, "application/pdf",
                                      {"Content-Disposition": f'{download}; filename="{job["id"]}.pdf"'})
                except Exception as exc:
                    return self._json(500, {"ok": False, "error": str(exc)[:300]})

            save_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/save-as", path)
            if save_match:
                job = JOBS.get(save_match.group(1))
                if not job:
                    return self._json(404, {"ok": False, "error": "job not found"})
                body = self._body()
                fmt = str(body.get("format") or "svg").lower()
                if fmt in ("pptx", "ppt") and \
                        (job.get("ppt_export") or {}).get("state") == "running":
                    return self._json(409, {"ok": False, "error": "PPTX 还在导出，请稍后再保存"})
                try:
                    dpi = None
                    try:
                        dpi = int(body.get("dpi") or 0) or None
                    except (TypeError, ValueError):
                        dpi = None
                    if dpi and job.get("dpi") != dpi:
                        job["dpi"] = dpi
                        _save_meta(job)
                    source, ext = _export_payload(job, fmt, load_config(), dpi=dpi)
                except FileNotFoundError as exc:
                    return self._json(409, {"ok": False, "error": str(exc)})
                except ValueError as exc:
                    return self._json(400, {"ok": False, "error": str(exc)})
                except Exception as exc:
                    return self._json(500, {"ok": False,
                                            "error": f"{type(exc).__name__}: {exc}"[:300]})
                default_name = _safe_filename(_figure_title(job) or job.get("title") or "Figure", ext)
                requested = str(body.get("path") or "").strip()
                dest = Path(requested) if requested else _auto_export_path(job, default_name)
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    temp = dest.with_name(dest.name + "." + uuid.uuid4().hex + ".tmp")
                    try:
                        if isinstance(source, bytes):
                            temp.write_bytes(source)
                        else:
                            import shutil
                            shutil.copyfile(source, temp)
                        safe_replace(temp, dest)
                    finally:
                        temp.unlink(missing_ok=True)
                except Exception as exc:
                    return self._json(500, {"ok": False,
                                            "error": f"{type(exc).__name__}: {exc}"[:300]})
                SAVED_PATHS.add(str(dest.resolve()))
                return self._json(200, {"ok": True, "path": str(dest),
                                        "folder": str(dest.parent)})

            if path == "/api/reveal":
                body = self._body()
                raw = str(body.get("path") or "").strip()
                action = str(body.get("action") or "select").lower()
                if not raw or len(raw) > 4096 or chr(0) in raw:
                    return self._json(400, {"ok": False, "error": "路径无效"})
                target = Path(raw)
                if target.suffix.lower() not in (".svg", ".png", ".pptx", ".pdf"):
                    return self._json(400, {"ok": False, "error": "只能打开导出的图形文件"})
                try:
                    resolved = target.resolve(strict=True)
                except (OSError, RuntimeError):
                    return self._json(404, {"ok": False, "error": "文件不存在"})
                if not resolved.is_file():
                    return self._json(404, {"ok": False, "error": "文件不存在"})
                roots = [JOBS_DIR.resolve(), EXPORT_DIR.resolve(), (BASE_DIR / "输出").resolve(),
                         (Path.home() / "Desktop").resolve(),
                         (Path.home() / "Downloads").resolve(),
                         (Path.home() / "Documents").resolve()]
                allowed = str(resolved) in SAVED_PATHS
                if not allowed:
                    for root in roots:
                        try:
                            if os.path.commonpath([str(resolved), str(root)]) == str(root):
                                allowed = True
                                break
                        except ValueError:
                            continue
                if not allowed:
                    return self._json(403, {"ok": False, "error": "路径不在允许范围内"})
                try:
                    if action == "open":
                        os.startfile(str(resolved))
                    else:
                        import subprocess
                        subprocess.Popen(["explorer", "/select,", str(resolved)])
                    return self._json(200, {"ok": True})
                except Exception as exc:
                    return self._json(500, {"ok": False, "error": str(exc)[:200]})

            revise_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/revise", path)
            if revise_match:
                body = self._body()
                instruction = str(body.get("instruction") or "").strip()
                if not instruction:
                    return self._json(400, {"ok": False, "error": "请先输入修改指令"})
                source = JOBS.get(revise_match.group(1))
                if not source:
                    return self._json(404, {"ok": False, "error": "job not found"})
                if source.get("status") != "completed" or not (
                        source.get("svg_path") or source.get("deliverable_svg")):
                    return self._json(409, {"ok": False, "error": "这张图还没有生成完成"})
                job = _revision_job(source, instruction, load_config())
                return self._json(200, {"ok": True, "job_id": job["id"]})

            autofix_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/auto-fix", path)
            if autofix_match:
                source = JOBS.get(autofix_match.group(1))
                if not source:
                    return self._json(404, {"ok": False, "error": "job not found"})
                if source.get("status") != "completed" or not (
                        source.get("svg_path") or source.get("deliverable_svg")):
                    return self._json(409, {"ok": False, "error": "这张图还没有生成完成"})
                findings = [f for f in (source.get("visual_findings") or [])
                            if f.get("kind") != "vision-unavailable"]
                if not findings:
                    return self._json(409, {"ok": False, "error": "没有可修复的审查问题"})
                # The audit's own findings become the repair brief: the vision
                # reviewer already states what is wrong and how to fix it.
                instruction = _auto_fix_instruction(findings)
                job = _revision_job(source, instruction, load_config(),
                                    title_suffix="自动修复", auto_fix=True)
                return self._json(200, {"ok": True, "job_id": job["id"],
                                        "fix_targets": len(findings)})

            recheck_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/recheck", path)
            if recheck_match:
                job = JOBS.get(recheck_match.group(1))
                if not job:
                    return self._json(404, {"ok": False, "error": "job not found"})
                if job.get("status") != "completed":
                    return self._json(409, {"ok": False, "error": "这张图还没有生成完成"})
                target = Path(job.get("deliverable_svg") or job.get("svg_path") or "")
                if not target.is_file():
                    return self._json(409, {"ok": False, "error": "结果还没有准备好"})
                try:
                    findings = review.findings(
                        target.read_bytes(), (job.get("report") or {}).get("scene_data"))
                except Exception as exc:
                    return self._json(500, {"ok": False,
                                            "error": f"{type(exc).__name__}: {exc}"[:300]})
                try:
                    import model_review
                    cfg = load_config()
                    model_findings, model_meta = model_review.review_figure(
                        target.read_bytes(), cfg,
                        {"kind": (job.get("report") or {}).get("mode") or job.get("mode"),
                         "title": _figure_title(job), "canvas": job.get("canvas"),
                         **_layout_context(job.get("report") or {}, job),
                         "scene_plate": bool((job.get("report") or {}).get("scene_template")),
                         "entities": [e.get("label") for e in
                                      ((job.get("report") or {}).get("scene_data") or {}).get("entities") or []]})
                    job["model_review"] = model_meta
                    for extra in model_findings:
                        if all(f.get("message") != extra.get("message") for f in findings):
                            findings.append(extra)
                except Exception as exc:
                    findings.append(_vision_unavailable(exc))
                report_now = job.get("report") or {}
                if report_now.get("raster"):
                    findings = _drop_ocr_contradicted(
                        findings, job.get("layout_contract") or {},
                        report_now.get("ocr_texts") or [])
                if (job.get("layout_contract") or {}).get("layout") == "horizontal_s":
                    # S-shaped flow is a deliberate horizontal arrangement, not
                    # evidence of an unbalanced left-heavy composition.
                    findings = [f for f in findings if not (
                        f.get("kind") == "vision" and any(word in str(f.get("message") or "")
                        for word in ("偏左", "重心失衡", "右侧空白", "右侧留白")))]
                findings.extend(_adherence_findings(
                    job, report_now, target.read_bytes()))
                job["visual_findings"] = findings
                job["review_version"] = REVIEW_VERSION
                job["reviewed_at"] = _now()
                blocking = [f for f in findings
                            if f.get("severity") in ("high", "medium")
                            and f.get("kind") != "vision-unavailable"]
                gap = _audit_gap(findings)
                if job.get("visual_state") == "confirmed":
                    # Re-auditing a delivered figure must be able to revoke
                    # acceptance; otherwise a later outage silently keeps it
                    # "verified" while the UI shows the new hard findings.
                    if blocking:
                        job["visual_state"] = "failed"
                        job["confirmed_at"] = None
                    elif gap:
                        job["visual_state"] = "unverified"
                        job["confirmed_at"] = None
                else:
                    job["visual_state"] = ("failed" if blocking else
                                           ("unverified" if gap else "passed"))
                _save_meta(job)
                return self._json(200, {"ok": True, "findings": findings,
                                        "visual_state": job.get("visual_state"),
                                        "reviewed_at": job.get("reviewed_at"),
                                        "legacy": False})

            if path == "/api/flash":
                try:
                    import ctypes
                    from ctypes import wintypes

                    class FLASHWINFO(ctypes.Structure):
                        _fields_ = [("cbSize", wintypes.UINT),
                                    ("hwnd", wintypes.HWND),
                                    ("dwFlags", wintypes.DWORD),
                                    ("uCount", wintypes.UINT),
                                    ("dwTimeout", wintypes.DWORD)]

                    hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
                    if hwnd:
                        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x0000000F, 5, 0)
                        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
                    return self._json(200, {"ok": True})
                except Exception as exc:
                    return self._json(200, {"ok": False, "error": str(exc)[:120]})

            delete_match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/delete", path)
            if delete_match:
                jid = delete_match.group(1)
                with JOBS_LOCK:
                    job = JOBS.get(jid)
                    if job and job.get("status") in ("queued", "processing"):
                        return self._json(409, {"ok": False,
                                                "error": "任务进行中，请先取消再删除"})
                    if job and (job.get("ppt_export") or {}).get("state") == "running":
                        return self._json(409, {"ok": False,
                                                "error": "PPTX 正在导出，完成后再删除"})
                    if any(child.get("revision_of") == jid
                           and child.get("status") in ("queued", "processing")
                           for child in JOBS.values()):
                        return self._json(409, {"ok": False,
                                                "error": "这张图正在被修改，请等修改任务结束后再删除"})
                    job = JOBS.pop(jid, None)
                    for parent in JOBS.values():
                        if parent.get("next_job") == jid:
                            parent["next_job"] = None
                if job:
                    import shutil
                    p = job_paths(jid)
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                return self._json(200, {"ok": True, "deleted": jid})

            if path == "/api/jobs/clear":
                with JOBS_LOCK:
                    active_sources = {job.get("revision_of") for job in JOBS.values()
                                      if job.get("status") in ("queued", "processing")
                                      and job.get("revision_of")}
                    removed = [jid for jid, job in JOBS.items()
                               if job.get("status") in ("completed", "failed", "cancelled", "error")
                               and jid not in active_sources
                               and (job.get("ppt_export") or {}).get("state") != "running"]
                    for jid in removed:
                        JOBS.pop(jid, None)
                    for parent in JOBS.values():
                        if parent.get("next_job") in removed:
                            parent["next_job"] = None
                import shutil
                for jid in removed:
                    try:
                        p = job_paths(jid)
                    except ValueError:
                        continue
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                return self._json(200, {"ok": True, "removed": len(removed)})

            if path == "/api/open-folder":
                body = self._body()
                kind = str(body.get("kind") or "output")
                job_id = str(body.get("job_id") or "")
                if kind == "config":
                    target = CONFIG_PATH.parent
                elif kind == "job" and job_id:
                    if job_id not in JOBS:
                        return self._json(404, {"ok": False, "error": "job not found"})
                    try:
                        target = job_paths(job_id)
                    except ValueError as exc:
                        return self._json(400, {"ok": False, "error": str(exc)})
                else:
                    target = JOBS_DIR
                try:
                    os.startfile(str(target))
                    return self._json(200, {"ok": True, "path": str(target)})
                except Exception as exc:
                    return self._json(500, {"ok": False, "error": str(exc)[:200]})

            if path == "/api/quit":
                def shutdown():
                    time.sleep(0.4)
                    if SERVER is not None:
                        SERVER.shutdown()
                threading.Thread(target=shutdown, daemon=True).start()
                return self._json(200, {"ok": True})

            return self._json(404, {"ok": False, "error": "not found"})
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "invalid JSON"})
        except Exception as exc:
            return self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})




def _is_our_server(host: str, port: int) -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://{host}:{port}/api/state", timeout=1.2) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8", "ignore"))
            return bool(payload.get("ok")) and "modes" in payload and "jobs" in payload
    except Exception:
        return False


def _activate_existing_window() -> bool:
    """Bring the running native window to the foreground on Windows."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if WINDOW_TITLE in buffer.value:
                    found.append(hwnd)
            return True

        user32.EnumWindows(callback, 0)
        if not found:
            return False
        hwnd = found[0]
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _stop_stale_server(host: str, port: int) -> None:
    """Ask a headless/stale instance to quit so a fresh window can bind."""
    try:
        import urllib.request
        request = urllib.request.Request(
            f"http://{host}:{port}/api/quit", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(request, timeout=3).read()
    except Exception:
        pass


def _style_native_titlebar() -> None:
    """Match the native caption to the graphite editor chrome."""
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
        if not hwnd:
            return
        dark = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
        caption = ctypes.c_int(0x00252918)   # COLORREF 0x00BBGGRR -> #182925
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
        border = ctypes.c_int(0x00252918)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), 4)
        text = ctypes.c_int(0x00F0EEED)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text), 4)
    except Exception:
        pass


def _maximize_window_by_title() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_TITLE)
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 3)   # SW_MAXIMIZE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _message_box(text: str, caption: str = WINDOW_TITLE) -> None:
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, caption, 0x40)
    except Exception:
        print(f"{caption}: {text}", file=sys.stderr)


def _enable_dpi_awareness() -> None:
    """Without this WebView2 lays out in DIPs while WinForms reports physical
    pixels: at 150% scaling the page renders 1.5x wider than the window and the
    right-hand dock is clipped off-screen."""
    if os.name != "nt":
        return
    try:
        import ctypes
        try:
            hr = ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v1
        except Exception:
            hr = ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _screen_work_area() -> tuple[int, int]:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        return 1600, 1000


def main() -> int:
    global SERVER, DATA_DIR, CONFIG_PATH, JOBS_DIR, EXPORT_DIR
    global UPDATE_PLAN, UPDATE_NONCE, RESTART_ARGS
    parser = argparse.ArgumentParser()
    parser.add_argument('--update-plan',help=argparse.SUPPRESS)
    parser.add_argument('--update-nonce',help=argparse.SUPPRESS)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8779)
    parser.add_argument("--open", action="store_true", help="(legacy) open in browser")
    parser.add_argument("--no-window", action="store_true",
                        help="Run the HTTP service only, without a native window")
    parser.add_argument("--smoke-test", action="store_true",
                        help="Open the native window briefly, then exit")
    parser.add_argument("--data-dir", help="Override the shared per-user data directory")
    parser.add_argument("--no-migrate", action="store_true", help="Start an isolated data directory without legacy import")
    args = parser.parse_args()
    UPDATE_PLAN,UPDATE_NONCE=args.update_plan,args.update_nonce
    DATA_DIR = get_data_dir(args.data_dir)
    CONFIG_PATH = DATA_DIR / "config.json"
    JOBS_DIR = DATA_DIR / "studio-jobs"
    EXPORT_DIR = DATA_DIR / "exports"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _enable_dpi_awareness()

    if FROZEN:
        log = (DATA_DIR / "studio.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = log
        sys.stderr = log

    # If this workspace is already running, focus its window instead of
    # spawning a second server or a browser tab.
    if _is_our_server(args.host, args.port):
        if _activate_existing_window():
            return 0
        _message_box("理象 Rylume 已经在运行，但未能定位到窗口。\n"
                     "请在任务栏中切换回已有窗口。")
        return 0

    port = args.port
    server = None
    for _ in range(20):
        try:
            server = StudioHTTPServer((args.host, port), Handler)
            break
        except OSError:
            if _is_our_server(args.host, port):
                if _activate_existing_window():
                    return 0
                _message_box("理象 Rylume 已经在运行，但未能定位到窗口。\n"
                             "请在任务栏中切换回已有窗口。")
                return 0
            port += 1
    if server is None:
        _message_box("无法启动本地服务：端口均被占用。")
        return 1

    # Only the process that owns the port may read and migrate the job store;
    # a second instance returning early must not rewrite meta files.
    from studio_storage import prepare_data_dir, acquire_instance_lock, recover_pending_replacements
    try:
        instance_lock = acquire_instance_lock(DATA_DIR)
    except RuntimeError as exc:
        server.server_close()
        _message_box(str(exc))
        return 1
    import atexit
    atexit.register(instance_lock.release)
    recover_pending_replacements(DATA_DIR)
    legacy_dirs = [] if args.no_migrate else [Path.home() / "Desktop" / "CellFigureStudio", BASE_DIR]
    prepare_data_dir(DATA_DIR, legacy_dirs=legacy_dirs)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.is_file():
        save_config({"mode": "auto", "default_illustration_mode": "vector"})
    _load_jobs()

    SERVER = server
    RESTART_ARGS=['--host',args.host,'--port',str(port),'--data-dir',str(DATA_DIR),'--no-migrate']
    if args.no_window:RESTART_ARGS.append('--no-window')
    from resource_packs import configure
    configure(DATA_DIR)
    url = f"http://{args.host}:{port}/"
    print(f"{PRODUCT_DISPLAY} on {url}", file=sys.stderr)

    if args.no_window:
        try:
            SERVER.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            SERVER.server_close()
        return 0

    threading.Thread(target=SERVER.serve_forever, daemon=True).start()

    try:
        import webview

        screen_w, screen_h = _screen_work_area()
        win_w = max(1100, min(1560, screen_w - 120))
        win_h = max(720, min(1000, screen_h - 140))
        window = webview.create_window(
            WINDOW_TITLE,
            url,
            width=win_w,
            height=win_h,
            min_size=(1000, 640),
            maximized=True,
            background_color="#f0f0ed",
            text_select=False,
        )
        def _nudge_native_window():
            # WebView2 occasionally paints its first frame black until the
            # host window is resized. Nudge it once after load.
            time.sleep(0.9)
            try:
                width, height = int(window.width), int(window.height)
                window.resize(max(800, width - 2), max(600, height - 2))
                time.sleep(0.35)
                window.resize(width, height)
                time.sleep(0.2)
                try:
                    window.maximize()
                except Exception:
                    _maximize_window_by_title()
                time.sleep(0.2)
                _style_native_titlebar()
            except Exception:
                try:
                    window.evaluate_js('window.dispatchEvent(new Event("resize"))')
                except Exception:
                    pass

        threading.Thread(target=_nudge_native_window, daemon=True).start()
        if args.smoke_test:
            threading.Timer(4.0, window.destroy).start()
        # Recovery drafts and asset preferences must survive a desktop restart.
        # Keep the profile scoped to the selected data directory, including QA.
        webview.start(gui="edgechromium", private_mode=False,
                      storage_path=str(DATA_DIR / "webview-profile"))
        return 0
    except Exception as exc:
        print(f"Native window failed ({type(exc).__name__}: {exc}); falling back to browser",
              file=sys.stderr)
        if args.smoke_test:
            SERVER.shutdown()
            SERVER.server_close()
            return 1
        webbrowser.open(url)
        try:
            SERVER.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            SERVER.server_close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

