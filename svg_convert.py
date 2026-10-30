"""Raster asset -> SVG conversion.

The image model makes the artwork; this module only converts each isolated
asset into clean vector paths. Two engines:

  llm      a vision-capable text model rewrites the image as SVG (best fidelity
           for organic shapes, keeps the image model's composition)
  vtracer  local spline vectorizer, always available

The conversion prompt forbids <image>, base64, scripts and text: labels are
added later by the layout layer.
"""

from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

import pipeline
import qa
import vectorizer

CONVERT_PROMPT = """你是图像转 SVG 的专家。把用户上传的这一张单个科研插画素材重绘成干净的 SVG。

要求：
1. 只输出一个 SVG 文档，不要 markdown、不要解释。
2. viewBox 用 0 0 {width} {height}，比例与原图一致。
3. 用 path / ellipse / circle / rect / line 重绘主体，保留原图的配色、描边粗细、关键内部结构（细胞核、细胞器、纹理走向、器官轮廓等）。
4. 背景透明或纯白；不要 <image>、不要 base64、不要脚本、不要外链。
5. 不要任何 <text>：所有标签由排版层重新添加。
6. 不要添加原图没有的元素；不要过度简化到失去可辨认性；渐变用相近纯色替代，不要阴影、滤镜、3D。
7. 输出必须能通过 XML 解析，所有坐标是明确数字。
"""


def _strip_text(svg: bytes) -> bytes:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag.split("}")[-1].lower() == "text":
                parent.remove(child)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _size(png: bytes) -> tuple[int, int]:
    image = Image.open(io.BytesIO(png))
    return image.size


def _llm_convert(png: bytes, config: dict) -> bytes:
    vision = config.get("vision") or {}
    text = config.get("text") or {}
    source = vision if (vision.get("base_url") and vision.get("model")) else text
    if not (source.get("base_url") and source.get("model")):
        raise RuntimeError("no vision/text model configured")
    width, height = _size(png)
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    payload = {
        "model": source["model"],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": CONVERT_PROMPT.format(width=width, height=height)},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "temperature": 0,
    }
    response = pipeline._post_json(
        pipeline._endpoint(source["base_url"], "/chat/completions"),
        pipeline._api_key(source), payload, timeout=180)
    raw = response["choices"][0]["message"]["content"]
    svg = pipeline._strip_fences(raw).encode("utf-8")
    svg = _strip_text(svg)
    pipeline._check_svg(svg)
    return svg


def _starvector(png: bytes, config: dict) -> bytes:
    import json
    import urllib.request
    section = config.get("vectorize") or {}
    url = str(section.get("starvector_url") or "http://127.0.0.1:8790").rstrip("/")
    payload = {"image": base64.b64encode(png).decode("ascii"),
               "max_length": int(section.get("max_length", 4000))}
    request = urllib.request.Request(
        url + "/vectorize", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=300) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok") or not result.get("svg"):
        raise RuntimeError(str(result.get("error") or "StarVector failed")[:300])
    svg = _strip_text(result["svg"].encode("utf-8"))
    pipeline._check_svg(svg)
    return svg


PRESETS = {
    # Faithful trace: thin layers, fine splines, keeps feather-level detail.
    "detail": dict(color_precision=8, layer_difference=12, filter_speckle=4,
                   path_precision=3, length_threshold=3.0, corner_threshold=50),
    # Balanced trace: merges near-identical layers, ~40% fewer paths.
    "balanced": dict(color_precision=8, layer_difference=16, filter_speckle=6,
                     path_precision=2, length_threshold=3.0, corner_threshold=55),
}


def _flatten(png: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    flat = Image.new("RGB", image.size, "white")
    flat.paste(image, mask=image.split()[3])
    return flat


def _prepare(png: bytes, max_side: int = 1024, colors: int = 24) -> bytes:
    """Flatten transparency, cap resolution, snap near-whites, quantize.

    The image model returns smooth gradients and anti-aliased edges; quantizing
    to a clean palette before tracing keeps vtracer from spending hundreds of
    near-identical layers on them, while leaving the artwork colors intact.
    """
    flat = _flatten(png)
    if max(flat.size) > max_side:
        flat.thumbnail((max_side, max_side), Image.LANCZOS)
    arr = np.array(flat)
    snap = (arr >= 246).all(axis=2)
    arr = arr.copy()
    arr[snap] = 255
    palette = Image.fromarray(arr).quantize(
        colors=colors, method=Image.MEDIANCUT, dither=Image.NONE).convert("RGB")
    # Median-cut can turn pure white into #FEFEFE; tracing that leaves faint
    # 1px slivers around every asset. Force the top of the palette to white.
    cleaned = np.array(palette)
    cleaned[(cleaned >= 250).all(axis=2)] = 255
    palette = Image.fromarray(cleaned)
    buffer = io.BytesIO()
    palette.save(buffer, "PNG")
    return buffer.getvalue()


def _strip_background(svg: bytes, width: float, height: float) -> bytes:
    """Drop the full-canvas white path vtracer emits.

    Left in place it would paint over connectors and neighbouring assets.
    """
    try:
        from svgpathtools import parse_path
    except Exception:
        return svg
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    parents = [root] + [n for n in root.iter()
                        if n.tag.split("}")[-1] == "g"]
    for parent in parents:
        for child in list(parent):
            if child.tag.split("}")[-1] != "path" or not child.get("d"):
                continue
            fill = (child.get("fill") or "").strip().lower()
            white = fill in ("#fff", "#ffffff", "#fefefe", "white")
            d = child.get("d", "")
            try:
                x0, x1, y0, y1 = parse_path(d).bbox()
            except Exception:
                continue
            ww = (x1 - x0) / max(1.0, width)
            hh = (y1 - y0) / max(1.0, height)
            # vtracer's base layer is inset a pixel or two, so a strict 97%
            # test misses it. Large near-white fills are visually identical to
            # the white canvas; a short full-canvas path is the base itself.
            if white and ww >= 0.6 and hh >= 0.6:
                parent.remove(child)
            elif ww >= 0.92 and hh >= 0.92 and len(d) < 400:
                parent.remove(child)
    # Hairlines that hug the canvas edge are tracing residue; interior thin
    # structures (jaw bones, ischium) have a higher fill ratio and stay.
    for parent in parents:
        for child in list(parent):
            if child.tag.split("}")[-1] != "path" or not child.get("d"):
                continue
            try:
                path = parse_path(child.get("d"))
                x0, x1, y0, y1 = path.bbox()
                area = abs(path.area())
            except Exception:
                continue
            w, h = x1 - x0, y1 - y0
            if max(w, h) < max(width, height) * 0.2:
                continue
            touches_edge = (x0 < 3 or y0 < 3 or x1 > width - 3 or y1 > height - 3)
            if touches_edge and w > 0 and h > 0 and 0 < area / (w * h) < 0.05:
                parent.remove(child)
    # vtracer rounds pure white to #FEFEFE; the one-value difference is
    # invisible as fill, but its outline shows against a white canvas.
    for el in root.iter():
        fill = (el.get("fill") or "").strip().lower()
        if re.fullmatch(r"#[0-9a-f]{6}", fill):
            channels = [int(fill[i:i + 2], 16) for i in (1, 3, 5)]
            if min(channels) >= 250:
                el.set("fill", "#ffffff")
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _fidelity(svg: bytes, png: bytes, config: dict) -> float | None:
    """Rasterize the trace and compare it with the source asset.

    Lower is better. Returns None when no browser is available.
    """
    try:
        width, height = _size(png)
        rendered = qa.rasterize(svg, width, height, config)
        if not rendered:
            return None
        report = qa.compare(png, rendered)
        if not report.get("available"):
            return None
        return round(report["changed_ratio"] * 0.75
                     + report["mean_abs_diff"] * 0.25, 5)
    except Exception:
        return None


def _hifi(png: bytes, config: dict) -> tuple[bytes, str]:
    """Trace the prepared asset twice and keep the measured best.

    The choice is scored against the actual artwork rather than guessed, and
    the winning score travels back in the pipeline report.
    """
    quality = "high" if (config.get("quality") or "hd") in ("hd", "high") else "standard"
    prepared = _prepare(png)
    width, height = Image.open(io.BytesIO(prepared)).size
    candidates = []
    for name, overrides in PRESETS.items():
        try:
            svg, _ = vectorizer.vectorize_vtracer(
                prepared, quality=quality, overrides=overrides)
        except Exception:
            continue
        svg = _strip_background(svg, width, height)
        candidates.append((_fidelity(svg, prepared, config), svg, name))
    if not candidates:
        svg, _ = vectorizer.vectorize(prepared, engine="vtracer", quality=quality)
        svg = _strip_background(svg, width, height)
        return svg, "vtracer"
    scored = [c for c in candidates if c[0] is not None]
    if not scored:
        _, svg, name = candidates[0]
        return svg, f"vtracer-hifi:{name}"
    floor = min(c[0] for c in scored) * 1.08
    # Among traces within 8% of the best score, take the smallest document:
    # file size drives PPTX build time, and the visual difference is sub-pixel.
    score, svg, name = min((c for c in scored if c[0] <= floor),
                           key=lambda c: len(c[1]))
    label = f"vtracer-hifi:{name}@{score}"
    return svg, label


def convert(png: bytes, config: dict) -> tuple[bytes, str]:
    engine = (config.get("vectorize") or {}).get("engine", "hifi")
    if engine == "starvector":
        try:
            return _starvector(png, config), "starvector"
        except Exception:
            pass
    if engine == "llm":
        try:
            return _llm_convert(png, config), "llm"
        except Exception:
            pass
    if engine in ("vtracer", "vtracer-fast"):
        quality = "high" if (config.get("quality") or "hd") in ("hd", "high") else "standard"
        prepared = _prepare(png)
        width, height = Image.open(io.BytesIO(prepared)).size
        svg, _ = vectorizer.vectorize(prepared, engine="vtracer", quality=quality)
        svg = _strip_background(svg, width, height)
        return svg, "vtracer"
    return _hifi(png, config)
