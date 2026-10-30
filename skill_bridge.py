"""Bridge between the app job store and the original skill's export code.

The vendored `postprocess.py` is the original MIT-licensed skill code; it expects
a `job.json` in the task directory with the skill's schema. This module creates
that compatibility file and exposes three operations:

  export_svg(job_dir, font)   original skill export: font override + validation
  visual_check(...)           render raw vs delivered SVG and compare
  export_ppt(job_dir, font)   native PPTX (paths + editable text)
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    VENDOR = Path(getattr(sys, "_MEIPASS", HERE)) / "vendor"
else:
    VENDOR = HERE / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

import postprocess  # noqa: E402  (vendored original skill code)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(job_dir, job_id: str, font: str) -> dict:
    """Write the skill-compatible job.json if it does not exist yet."""
    job_dir = Path(job_dir).resolve()
    svg = job_dir / "result.svg"
    if not svg.is_file():
        raise FileNotFoundError("result.svg missing")
    compat = {
        "version": 1,
        "state": "received",
        "service": "/api/cell-figure-plus",
        "job_id": "cfp_" + hashlib.sha256(job_id.encode("utf-8")).hexdigest()[:24],
        "charged_credits": 20,
        "thread_id": "00000000-0000-4000-8000-000000000000",
        "svg": str(svg),
        "svg_sha256": _sha(svg),
        "font_family": font or "Times New Roman",
        "application": "svg",
        "ppt_delivery": None,
        "conversion": "pending",
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    target = job_dir / "job.json"
    if not target.is_file():
        target.write_text(json.dumps(compat, ensure_ascii=False, indent=2), encoding="utf-8")
    return compat


def export_svg(job_dir, font: str) -> dict:
    return postprocess.export_svg(Path(job_dir).resolve(), font_family=font)


def _canvas(svg: Path) -> tuple[int, int]:
    try:
        root = ET.fromstring(svg.read_bytes())
        view = root.get("viewBox", "")
        parts = [float(v) for v in view.replace(",", " ").split() if v]
        if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
            return int(parts[2]), int(parts[3])
        width = float(root.get("width", "1280").replace("px", ""))
        height = float(root.get("height", "900").replace("px", ""))
        return int(width), int(height)
    except Exception:
        return 1280, 900


def visual_check(delivered, raw, config: dict) -> dict:
    from qa import compare, rasterize
    delivered, raw = Path(delivered), Path(raw)
    width, height = _canvas(delivered)
    left = rasterize(raw.read_bytes(), width, height, config)
    right = rasterize(delivered.read_bytes(), width, height, config)
    if not left or not right:
        return {"available": False, "reason": "no browser"}
    result = compare(left, right)
    result["checked"] = bool(result.get("available") and result.get("changed_ratio", 1) <= 0.25)
    return result


def export_ppt(job_dir, font: str, progress=None) -> dict:
    import ppt_native
    job_dir = Path(job_dir).resolve()
    receipt_path = job_dir / "svg-output.json"
    svg = job_dir / "result.svg"
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        candidate = Path(receipt.get("svg", ""))
        if candidate.is_file():
            svg = candidate
    output = job_dir / "deliverables" / ("ppt-" + uuid.uuid4().hex[:12])
    return ppt_native.build(svg, output, font=font or "Times New Roman", progress=progress)
