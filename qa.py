"""Structural and raster QA for generated SVG."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


def _extra_browsers() -> list[str]:
    """Per-user installs the fixed list misses (Chrome user-level, Edge via
    WindowsApps, Chromium forks like Brave/Vivaldi)."""
    local = os.environ.get("LOCALAPPDATA")
    out: list[str] = []
    if local:
        out += [
            str(Path(local) / "Google/Chrome/Application/chrome.exe"),
            str(Path(local) / "Chromium/Application/chrome.exe"),
        ]
    if os.name == "nt":
        out += [
            r"C:\Program Files\Chromium\Application\chrome.exe",
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
        ]
    return out


def structural(svg: bytes) -> dict:
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    root = ET.fromstring(svg)
    counts: dict[str, int] = {}
    forbidden = []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        counts[tag] = counts.get(tag, 0) + 1
        if tag in ("script", "image", "foreignobject", "iframe", "audio", "video"):
            forbidden.append(tag)
    vector = sum(counts.get(t, 0) for t in
                 ("path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "use"))
    return {
        "elements": counts,
        "vector_objects": vector,
        "text_objects": counts.get("text", 0),
        "forbidden": forbidden,
        "viewBox": root.get("viewBox"),
        "ok": not forbidden and vector > 0,
    }


def find_browser(config: dict | None = None) -> str | None:
    override = ((config or {}).get("qa") or {}).get("browser")
    if override and Path(override).is_file():
        return override
    env = os.environ.get("CELL_FIGURE_BROWSER")
    if env and Path(env).is_file():
        return env
    for candidate in BROWSERS + _extra_browsers():
        if Path(candidate).is_file():
            return candidate
    return None


def rasterize(svg: bytes, width: int, height: int, config: dict | None = None,
              scale: float = 1.0) -> bytes | None:
    """Render the SVG headlessly. `scale` > 1 supersamples for print DPI:
    a 1600px figure exported at 400dpi (scale≈2.8) comes out print-sized."""
    browser = find_browser(config)
    if not browser:
        return None
    scale = max(0.25, min(4.0, float(scale or 1.0)))
    # DSF multiplies the window size, so pass the base dimensions and let the
    # scale factor do the supersampling; multiplying both double-counts.
    out_w = max(1, int(width))
    out_h = max(1, int(height))
    with tempfile.TemporaryDirectory(prefix="svgqa-") as tmp:
        svg_path = Path(tmp) / "figure.svg"
        png_path = Path(tmp) / "figure.png"
        svg_path.write_bytes(svg)
        argv = [
            browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            # A private profile per call: concurrent previews/exports using the
            # default profile intermittently fail to start or share state.
            f"--user-data-dir={Path(tmp) / 'profile'}",
            "--no-first-run", "--no-default-browser-check",
            f"--force-device-scale-factor={scale}",
            f"--window-size={out_w},{out_h}",
            "--virtual-time-budget=1500",
            f"--screenshot={png_path}",
            svg_path.as_uri(),
        ]
        try:
            subprocess.run(argv, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if not png_path.is_file() or png_path.stat().st_size == 0:
            return None
        return png_path.read_bytes()


def compare(reference_png: bytes, rendered_png: bytes) -> dict:
    ref = cv2.imdecode(np.frombuffer(reference_png, np.uint8), cv2.IMREAD_COLOR)
    out = cv2.imdecode(np.frombuffer(rendered_png, np.uint8), cv2.IMREAD_COLOR)
    if ref is None or out is None:
        return {"available": False}
    if out.shape[:2] != ref.shape[:2]:
        out = cv2.resize(out, (ref.shape[1], ref.shape[0]), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(ref, out).astype(np.float32)
    gray = diff.mean(axis=2)
    return {
        "available": True,
        "mean_abs_diff": round(float(gray.mean()) / 255.0, 4),
        "changed_ratio": round(float((gray > 24).mean()), 4),
        "pixels": int(gray.size),
    }


def run(svg: bytes, reference_png: bytes | None, width: int, height: int,
        config: dict) -> dict:
    report = {"structural": structural(svg)}
    max_diff = float(((config.get("qa") or {}).get("max_diff", 0.45)))
    if reference_png:
        rendered = rasterize(svg, width, height, config)
        if rendered:
            diff = compare(reference_png, rendered)
            report["raster"] = diff
            if diff.get("available"):
                report["visual_ok"] = diff["changed_ratio"] <= max_diff
        else:
            report["raster"] = {"available": False, "reason": "no browser"}
    report["passed"] = bool(report["structural"]["ok"] and report.get("visual_ok", True))
    return report
