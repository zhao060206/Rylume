"""Defect review for generated figures.

Checks the things a human reviewer looks for, not just pixel equality:

  occlusion  labels over entities, labels over labels, entity boxes overlapping
  garbled    empty text, replacement glyphs, missing/extra text in PPTX
  shift      labels outside the canvas, labels detached from their entity,
             changed pixel regions between SVG and PowerPoint

Every finding carries a kind, severity, message and optional bbox.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

VERSION = 3


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _canvas(root):
    parts = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox", "")) if v]
    if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
        return parts[2], parts[3]
    return _num(root.get("width"), 1280), _num(root.get("height"), 900)


_FONT_CACHE = {}


def _font(size: float, bold: bool = False):
    key = (round(size, 1), bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    from PIL import ImageFont
    candidates = [
        r"C:\Windows\Fonts\timesbd.ttf" if bold else r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        "DejaVuSerif.ttf",
    ]
    font = None
    for path in candidates:
        try:
            font = ImageFont.truetype(path, max(6, int(round(size))))
            break
        except Exception:
            continue
    _FONT_CACHE[key] = font
    return font


def _text_metrics(text: str, size: float, bold: bool = False):
    font = _font(size, bold)
    if font is not None:
        try:
            x0, y0, x1, y1 = font.getbbox(text)
            return float(x0), float(y0), float(x1 - x0), float(y1 - y0)
        except Exception:
            pass
    width = len(text) * size * 0.55
    return 0.0, -size * 0.78, width, size * 1.02


def _matmul(m, n):
    a, b, c, d, e, f = m
    na, nb, nc, nd, ne, nf = n
    return (a * na + c * nb, b * na + d * nb,
            a * nc + c * nd, b * nc + d * nd,
            a * ne + c * nf + e, b * ne + d * nf + f)


def _matrix(text):
    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
    if not text:
        return a, b, c, d, e, f
    for name, args in re.findall(r"(translate|scale|matrix|rotate)\s*\(([^)]*)\)", text):
        vals = [float(v) for v in re.findall(r"-?[\d.]+(?:e-?\d+)?", args)]
        if name == "translate" and vals:
            tx = vals[0]
            ty = vals[1] if len(vals) > 1 else 0.0
            e, f = e + a * tx + c * ty, f + b * tx + d * ty
        elif name == "scale" and vals:
            sx = vals[0]
            sy = vals[1] if len(vals) > 1 else sx
            a, b, c, d = a * sx, b * sx, c * sy, d * sy
        elif name == "rotate" and vals:
            rad = math.radians(vals[0])
            ca, sa = math.cos(rad), math.sin(rad)
            if len(vals) >= 3:
                cx, cy = vals[1], vals[2]
                e, f = e + a * cx + c * cy, f + b * cx + d * cy
                a, b, c, d = (a * ca + c * sa, b * ca + d * sa,
                              -a * sa + c * ca, -b * sa + d * ca)
                e, f = e - a * cx - c * cy, f - b * cx - d * cy
            else:
                a, b, c, d = (a * ca + c * sa, b * ca + d * sa,
                              -a * sa + c * ca, -b * sa + d * ca)
        elif name == "matrix" and len(vals) == 6:
            a, b, c, d, e, f = _matmul((a, b, c, d, e, f), tuple(vals))
    return a, b, c, d, e, f


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def _box_global(m, x, y, w, h):
    pts = [_apply(m, px, py) for px, py in ((x, y), (x + w, y), (x + w, y + h), (x, y + h))]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _text_boxes(root):
    canvas_w, canvas_h = _canvas(root)
    found = []

    def visit(node, matrix):
        for child in node:
            tag = child.tag.split("}")[-1].lower()
            if tag in ("defs", "clippath", "marker", "style", "metadata"):
                continue
            local = _matrix(child.get("transform"))
            combined = _matmul(matrix, local)
            if tag == "text":
                container = None
                custom_box = child.get("data-box")
                if custom_box:
                    try:
                        bx, by, bw, bh = [float(v) for v in str(custom_box).split(",")]
                        container = _box_global(combined, bx, by, bw, bh)
                    except ValueError:
                        container = None
                size = _num(child.get("font-size"), 18)
                x = _num(child.get("x"), 0)
                y = _num(child.get("y"), 0)
                bold = (child.get("font-weight") or "").lower() in ("bold", "700", "800", "900")
                anchor = child.get("text-anchor", "start")
                tspans = [c for c in child if c.tag.split("}")[-1].lower() == "tspan"]
                lines = []
                if tspans:
                    baseline = y
                    for span in tspans:
                        dy = _num(span.get("dy"), 0)
                        baseline += dy
                        lines.append(("".join(span.itertext()).strip(), baseline))
                else:
                    lines.append(("".join(child.itertext()).strip(), y))
                custom = child.get("data-bbox")
                if custom and len(lines) == 1:
                    try:
                        bx, by, bw, bh = [float(v) for v in str(custom).split(",")]
                    except ValueError:
                        bx = by = bw = bh = None
                    if bw is not None:
                        text = lines[0][0]
                        found.append({
                            "text": text, "x": bx, "y": by, "w": bw, "h": bh,
                            "x2": bx + bw, "y2": by + bh, "size": size,
                            "arc": child.get("data-arc") == "1",
                            "data_bbox": custom,
                            "container": container,
                            "overflow": bool(container and (
                                bx < container[0] - 1.5 or by < container[1] - 1.5 or
                                bx + bw > container[2] + 1.5 or by + bh > container[3] + 1.5)),
                            "outside": bx < -1 or by < -1 or bx + bw > canvas_w + 1
                                       or by + bh > canvas_h + 1,
                        })
                        continue
                for text, baseline in lines:
                    ox, oy, width, height = _text_metrics(text, size, bold)
                    left = x + ox
                    if anchor == "middle":
                        left -= width / 2
                    elif anchor == "end":
                        left -= width
                    top = baseline + oy
                    corners = [(left, top), (left + width, top),
                               (left + width, top + height), (left, top + height)]
                    pts = [_apply(combined, px, py) for px, py in corners]
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    x1, x2 = min(xs), max(xs)
                    y1, y2 = min(ys), max(ys)
                    found.append({
                        "text": text, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1,
                        "x2": x2, "y2": y2, "size": size,
                        "container": container,
                        "overflow": bool(container and (
                            x1 < container[0] - 1.5 or y1 < container[1] - 1.5 or
                            x2 > container[2] + 1.5 or y2 > container[3] + 1.5)),
                        "outside": x1 < -1 or y1 < -1 or x2 > canvas_w + 1 or y2 > canvas_h + 1,
                    })
            elif tag in ("g", "svg", "a"):
                visit(child, combined)

    visit(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    return found


def _area(box):
    return max(0.0, box["w"]) * max(0.0, box["h"])


def _overlap_area(a, b):
    w = min(a["x2"], b["x2"]) - max(a["x"], b["x"])
    h = min(a["y2"], b["y2"]) - max(a["y"], b["y"])
    return max(0.0, w) * max(0.0, h)


def _significant(a, b):
    area = _overlap_area(a, b)
    if area <= 4:
        return False
    smaller = min(_area(a), _area(b))
    if smaller <= 0:
        return False
    # Touching boxes are normal; only flag a real visual collision.
    return area >= min(120.0, smaller * 0.28)


def _entity_boxes(scene):
    rows = []
    for entity in (scene or {}).get("entities") or []:
        box = entity.get("content_bbox") or entity.get("bbox") or [0, 0, 0, 0]
        rows.append({"id": entity.get("id"), "label": entity.get("label"),
                     "x": box[0], "y": box[1], "w": box[2], "h": box[3],
                     "x2": box[0] + box[2], "y2": box[1] + box[3]})
    return rows


def _rect_edges(root):
    """Axis-aligned bboxes of real containers (panels, cards, ribbons)."""
    rects = []

    def visit(node, matrix):
        for child in node:
            tag = child.tag.split("}")[-1].lower()
            if tag in ("defs", "clippath", "marker", "style", "metadata"):
                continue
            local = _matrix(child.get("transform"))
            combined = _matmul(matrix, local)
            if tag == "rect":
                w = _num(child.get("width"), 0.0)
                h = _num(child.get("height"), 0.0)
                if w >= 24 and h >= 14:
                    x1, y1, x2, y2 = _box_global(
                        combined, _num(child.get("x"), 0.0), _num(child.get("y"), 0.0), w, h)
                    if x2 - x1 >= 24 and y2 - y1 >= 14:
                        rects.append((x1, y1, x2, y2))
            elif tag in ("g", "svg", "a"):
                visit(child, combined)

    visit(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    return rects


def _rect_distance(rect, px, py):
    x1, y1, x2, y2 = rect
    if x1 - 0.5 <= px <= x2 + 0.5 and y1 - 0.5 <= py <= y2 + 0.5:
        return min(abs(px - x1), abs(px - x2), abs(py - y1), abs(py - y2))
    dx = max(x1 - px, 0.0, px - x2)
    dy = max(y1 - py, 0.0, py - y2)
    return math.hypot(dx, dy)


def _path_endpoint(d):
    if not d:
        return None
    matches = list(re.finditer(r"[MLCQSTmlcqst]", d))
    if not matches:
        return None
    tail = d[matches[-1].end():]
    nums = re.findall(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", tail)
    if len(nums) < 2:
        return None
    return float(nums[-2]), float(nums[-1])


def _arrows(root):
    rows = []

    def visit(node, matrix):
        for child in node:
            tag = child.tag.split("}")[-1].lower()
            if tag in ("defs", "clippath", "marker", "style", "metadata"):
                continue
            local = _matrix(child.get("transform"))
            combined = _matmul(matrix, local)
            marker = child.get("marker-end") or ""
            if marker and "arr-" in marker:
                point = None
                if tag == "line":
                    point = (_num(child.get("x2"), 0.0), _num(child.get("y2"), 0.0))
                elif tag in ("path", "polyline"):
                    point = _path_endpoint(child.get("d"))
                if point:
                    x, y = _apply(combined, point[0], point[1])
                    rows.append((x, y, tag))
            if tag in ("g", "svg", "a"):
                visit(child, combined)

    visit(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    return rows


def _arrow_findings(root):
    rects = _rect_edges(root)
    found = []
    if not rects:
        return found
    for x, y, _tag in _arrows(root):
        gap = min(_rect_distance(rect, x, y) for rect in rects)
        if gap > 14.0:
            found.append({
                "kind": "shift", "severity": "high",
                "message": f"箭头终点悬空：({x:.0f},{y:.0f}) 未连接到任何框线",
                "box": [x - 4, y - 4, 8, 8],
            })
        if len(found) >= 12:
            break
    return found


def _clip_paths(root):
    clips = {}

    def visit(node):
        for child in node:
            tag = child.tag.split("}")[-1].lower()
            if tag == "clippath":
                items = []
                for el in child:
                    etag = el.tag.split("}")[-1].lower()
                    if etag == "rect":
                        w = _num(el.get("width"), 0.0)
                        h = _num(el.get("height"), 0.0)
                        if w > 4 and h > 4:
                            items.append(("rect", (_num(el.get("x"), 0.0), _num(el.get("y"), 0.0),
                                                   w, h)))
                    elif etag == "circle":
                        r = _num(el.get("r"), 0.0)
                        if r > 4:
                            items.append(("circle", (_num(el.get("cx"), 0.0), _num(el.get("cy"), 0.0), r)))
                    elif etag == "ellipse":
                        rx = _num(el.get("rx"), 0.0)
                        ry = _num(el.get("ry"), 0.0)
                        if rx > 4 and ry > 4:
                            items.append(("ellipse", (_num(el.get("cx"), 0.0), _num(el.get("cy"), 0.0),
                                                      rx, ry)))
                cid = child.get("id") or ""
                if cid:
                    clips[cid] = items
            visit(child)

    visit(root)
    return clips


def _point_inside_clips(clips, x, y):
    if not clips:
        return True
    for kind, geom in clips:
        if kind == "rect":
            if geom[0] <= x <= geom[0] + geom[2] and geom[1] <= y <= geom[1] + geom[3]:
                return True
        elif kind == "circle":
            cx, cy, r = geom
            if math.hypot(x - cx, y - cy) <= r + 0.5:
                return True
        else:
            cx, cy, rx, ry = geom
            if rx > 0 and ry > 0 and ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.02:
                return True
    return False


def _text_clips(root, texts):
    clips = _clip_paths(root)
    visited = [0]

    def visit(node, matrix, refs):
        for child in node:
            tag = child.tag.split("}")[-1].lower()
            if tag in ("defs", "marker", "style", "metadata", "clippath"):
                continue
            local = _matmul(matrix, _matrix(child.get("transform")))
            ref = child.get("clip-path") or ""
            m = re.search(r"url\(#([^)]+)\)", ref)
            child_refs = clips.get(m.group(1)) if m else refs
            if tag == "text":
                text = "".join(child.itertext()).strip()
                for entry in texts:
                    if entry["text"] == text and entry.get("_clips") is None:
                        entry["_x"] = _num(child.get("x"), 0.0)
                        entry["_y"] = _num(child.get("y"), 0.0)
                        entry["_bold"] = (child.get("font-weight") or "").lower() in ("bold", "700", "800", "900")
                        entry["_anchor"] = child.get("text-anchor", "start")
                        if child_refs:
                            if entry.get("arc") and entry.get("data_bbox"):
                                # Arc text lives on a textPath whose coordinates are
                                # not a straight baseline box; the renderer declares
                                # a conservative on-canvas bbox we trust here.
                                try:
                                    bx, by, bw, bh = [float(v) for v in entry["data_bbox"].split(",")]
                                    pts = [(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)]
                                    inside = all(_point_inside_clips(child_refs, px, py) for px, py in pts)
                                    entry["_inside_clip"] = inside
                                    entry["_clips"] = child_refs
                                    break
                                except (ValueError, AttributeError):
                                    pass
                            ox, oy, width, height = _text_metrics(
                                text, entry["size"], entry.get("_bold", False))
                            left = entry["_x"] + ox
                            if entry["_anchor"] == "middle":
                                left -= width / 2
                            elif entry["_anchor"] == "end":
                                left -= width
                            top = entry["_y"] + oy
                            pts = [(left, top), (left + width, top),
                                   (left + width, top + height), (left, top + height)]
                            inside = True
                            for px, py in pts:
                                gx, gy = _apply(local, px, py)
                                if not _point_inside_clips(child_refs, gx, gy):
                                    inside = False
                                    break
                            entry["_inside_clip"] = inside
                        entry["_clips"] = child_refs
                        break
            elif tag in ("g", "svg", "a"):
                visit(child, local, child_refs)

    visit(root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), [])

    # Second pass with the measured AABB (review geometry) for any text we
    # missed; catches tspan-wrapped and nested paths on complex figures.
    for entry in texts:
        if entry.get("_clips") is None:
            continue
        if entry.get("_inside_clip") is False:
            continue
        refs = entry["_clips"]
        if entry.get("arc") and entry.get("data_bbox"):
            try:
                bx, by, bw, bh = [float(v) for v in entry["data_bbox"].split(",")]
                pts = [(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)]
            except (ValueError, AttributeError):
                pts = []
        else:
            pts = [(entry["x"], entry["y"]), (entry["x2"], entry["y"]),
                   (entry["x2"], entry["y2"]), (entry["x"], entry["y2"])]
        if pts and not all(_point_inside_clips(refs, px, py) for px, py in pts):
            entry["_inside_clip"] = False


def _framework_findings(root, texts, canvas_w, canvas_h):
    found = []
    title = None
    for t in texts:
        if t.get("arc"):
            continue
        if t["size"] >= 20 and t["w"] >= 220 and t["y"] < 140:
            if title is None or t["size"] > title["size"]:
                title = t
    if title is None:
        return found
    rect = None
    for items in _clip_paths(root).values():
        for item in items:
            if item[0] != "rect":
                continue
            _, (x, y, w, h) = item
            if w >= canvas_w * 0.6 and x < canvas_w * 0.2 and x + w > canvas_w * 0.8:
                if y > 8 and h < canvas_h * 0.35:
                    rect = (x, y, x + w, y + h)
    if rect and (title["x"] < rect[0] - 0.5 or title["x2"] > rect[2] + 0.5):
        found.append({"kind": "overflow", "severity": "high",
                      "message": f"标题超出视窗卡片：{title['text'][:40]}",
                      "box": [title["x"], title["y"], title["w"], title["h"]]})
    top = None
    for items in _clip_paths(root).values():
        for item in items:
            if item[0] == "rect":
                _, (x, y, w, h) = item
                if y > title["y"] + 30 and 40 <= h <= 150 and w >= 300 and (top is None or y < top[1]):
                    top = (x, y, x + w, y + h)
    if top is None:
        return found
    for t in texts:
        if t is title or t.get("arc"):
            continue
        if t["size"] < 14 or t["y"] < 100 or t["y"] > top[1] + 20:
            continue
        if t["y2"] < top[1] - 6:
            found.append({"kind": "shift", "severity": "high",
                          "message": f"标签位于层标题之上（疑似被虚线分隔线截断）：{t['text'][:30]}",
                          "box": [t["x"], t["y"], t["w"], t["h"]]})
        elif t["y"] < top[1] and t["y2"] > top[1] + 6:
            continue
    return found


def findings(svg_bytes: bytes, scene: dict | None = None) -> list[dict]:
    try:
        root = ET.fromstring(svg_bytes)
    except Exception as exc:
        return [{"kind": "garbled", "severity": "high", "message": f"SVG 无法解析：{exc}"}]
    texts = _text_boxes(root)
    canvas_w, canvas_h = _canvas(root)
    _text_clips(root, texts)
    entities = _entity_boxes(scene)
    found: list[dict] = []

    for t in texts:
        if not t["text"]:
            continue
        if any(ch in t["text"] for ch in ("\ufffd", "□", "�")):
            found.append({"kind": "garbled", "severity": "high",
                          "message": f"文本疑似乱码：{t['text'][:40]}",
                          "box": [t["x"], t["y"], t["w"], t["h"]]})
        if t["outside"]:
            found.append({"kind": "shift", "severity": "high",
                          "message": f"标签超出画布：{t['text'][:30]}",
                          "box": [t["x"], t["y"], t["w"], t["h"]]})
        if t.get("overflow"):
            found.append({"kind": "overflow", "severity": "high",
                          "message": f"文字溢出容器：{t['text'][:30]}",
                          "box": [t["x"], t["y"], t["w"], t["h"]]})

    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            if a.get("arc") and b.get("arc"):
                continue
            if a.get("arc") or b.get("arc"):
                area = _overlap_area(a, b)
                smaller = min(_area(a), _area(b))
                if smaller <= 0 or area < min(400.0, smaller * 0.55):
                    continue
                if a.get("size", 12) < 8.8 or b.get("size", 12) < 8.8:
                    continue
            if _significant(a, b):
                found.append({"kind": "occlusion", "severity": "high",
                              "message": f"标签互相遮挡：{a['text'][:20]} / {b['text'][:20]}",
                              "box": [a["x"], a["y"], a["w"], a["h"]]})

    for i, a in enumerate(entities):
        for b in entities[i + 1:]:
            if _significant(a, b):
                found.append({"kind": "occlusion", "severity": "high",
                              "message": f"实体框重叠：{a['id']} / {b['id']}",
                              "box": [a["x"], a["y"], a["w"], a["h"]]})

    for entity in entities:
        label = entity.get("label")
        if not label:
            continue
        match = next((t for t in texts if t["text"] == label), None)
        if not match:
            continue
        for other in entities:
            if other["id"] == entity["id"]:
                gap = match["y"] - other["y2"]
                if gap < -4:
                    found.append({"kind": "shift", "severity": "medium",
                                  "message": f"标签 {label} 与实体距离过近或压住实体",
                                  "box": [match["x"], match["y"], match["w"], match["h"]]})
                break
            if _significant(match, other):
                found.append({"kind": "occlusion", "severity": "high",
                              "message": f"标签 {label} 遮挡实体 {other['id']}",
                              "box": [match["x"], match["y"], match["w"], match["h"]]})
                break
    # Card fill check: a full-width strip whose text only covers its left
    # third is the "five empty bars" failure mode, not a publication figure.
    for node in root.iter():
        if node.tag.split("}")[-1].lower() != "rect":
            continue
        try:
            rx, ry = float(node.get("x") or 0), float(node.get("y") or 0)
            rw, rh = float(node.get("width") or 0), float(node.get("height") or 0)
            radius = float(node.get("rx") or 0)
        except (TypeError, ValueError):
            continue
        if radius <= 1 or rw < canvas_w * 0.50 or not (60 <= rh <= 320):
            continue
        inside = [t for t in texts
                  if t.get("w") and t.get("h")
                  and rx <= t["x"] + t["w"] / 2 <= rx + rw
                  and ry <= t["y"] + t["h"] / 2 <= ry + rh]
        if not inside:
            continue
        span = max(t["x2"] for t in inside) - min(t["x"] for t in inside)
        if span < rw * 0.45:
            found.append({"kind": "layout", "severity": "high",
                          "message": f"卡片内容只占宽度的 {span / rw:.0%}，右侧大面积空白",
                          "box": [rx, ry, rw, rh]})
    found.extend(_clip_findings(texts))
    found.extend(_framework_findings(root, texts, canvas_w, canvas_h))
    found.extend(_required_layer_findings(root))
    found.extend(_arrow_findings(root))
    return found


def _clip_findings(texts):
    found = []
    for t in texts:
        if t.get("_clips") and t.get("_inside_clip") is False:
            found.append({"kind": "overflow", "severity": "high",
                          "message": f"文字被视窗裁切：{t['text'][:40]}",
                          "box": [t["x"], t["y"], t["w"], t["h"]]})
    return found


def _required_layer_findings(root):
    """Structural completeness: a figure built from named panels must show
    every panel's heading. Panels whose heading is missing or clipped into
    blank space are the failure mode users see as '整个面板消失'."""
    ids = set()
    texts = []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        gid = node.get("id")
        if tag == "g" and gid:
            ids.add(gid)
        elif tag == "text":
            texts.append((node.get("id") or "", "".join(node.itertext()).strip()))
    found = []
    for gid, label in (("layer-sensing", "A ·"),
                       ("layer-core", "B ·"),
                       ("layer-embodiment", "C ·")):
        if gid in ids and not any(t[1].startswith(label) for t in texts):
            found.append({"kind": "shift", "severity": "high",
                          "message": f"面板标题丢失或被裁切：{gid} 应有以 {label} 开头的标题"})
    return found


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _svg_texts(svg_bytes: bytes) -> list[str]:
    root = ET.fromstring(svg_bytes)
    rows = []
    for node in root.iter():
        if node.tag.split("}")[-1].lower() != "text":
            continue
        tspans = [child for child in node
                  if child.tag.split("}")[-1].lower() == "tspan"
                  and "".join(child.itertext()).strip()]
        if tspans:
            # PowerPoint turns each visual line into its own paragraph.
            value = "\n".join("".join(child.itertext()) for child in tspans)
        else:
            value = "".join(node.itertext())
        value = _norm_text(value)
        if value:
            rows.append(value)
    return rows


def _ppt_texts(pptx_path) -> list[str]:
    from pptx import Presentation
    presentation = Presentation(str(pptx_path))
    rows = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                value = _norm_text(shape.text_frame.text)
                if value:
                    rows.append(value)
    return rows


def compare_texts(svg_bytes: bytes, pptx_path) -> list[dict]:
    try:
        svg_rows = sorted(_svg_texts(svg_bytes))
        ppt_rows = sorted(_ppt_texts(pptx_path))
    except Exception as exc:
        return [{"kind": "garbled", "severity": "medium", "message": f"PPT 文本读取失败：{exc}"}]
    found = []
    if svg_rows != ppt_rows:
        missing = [x for x in svg_rows if x not in ppt_rows]
        extra = [x for x in ppt_rows if x not in svg_rows]
        if missing:
            found.append({"kind": "garbled", "severity": "high",
                          "message": "PPT 缺少文本：" + "、".join(missing[:6])})
        if extra:
            found.append({"kind": "garbled", "severity": "high",
                          "message": "PPT 多出文本：" + "、".join(extra[:6])})
    return found


def diff_regions(svg_png: bytes, ppt_png: bytes) -> tuple[list[dict], bytes | None]:
    left = cv2.imdecode(np.frombuffer(svg_png, np.uint8), cv2.IMREAD_COLOR)
    right = cv2.imdecode(np.frombuffer(ppt_png, np.uint8), cv2.IMREAD_COLOR)
    if left is None or right is None:
        return [], None
    if right.shape[:2] != left.shape[:2]:
        right = cv2.resize(right, (left.shape[1], left.shape[0]), interpolation=cv2.INTER_AREA)
    diff = cv2.absdiff(left, right).mean(axis=2)
    mask = (diff > 28).astype(np.uint8) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    found = []
    heat = right.copy()
    heat[mask > 0] = (0, 0, 255)
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if area < 40:
            continue
        if len(found) < 8:
            found.append({"kind": "shift", "severity": "low",
                          "message": f"PPT 与 SVG 在 ({x},{y}) 有 {area}px 差异",
                          "box": [int(x), int(y), int(w), int(h)]})
    blended = cv2.addWeighted(right, 0.55, heat, 0.45, 0)
    ok, encoded = cv2.imencode(".png", blended)
    return found, (encoded.tobytes() if ok else None)
