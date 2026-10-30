"""Deterministic layout spec -> editable SVG.

The `plan` pipeline mode asks a chat model for a JSON spec in this shape, then
renders it here. Everything in the output is a real <text> or a vector shape,
so it stays editable in Illustrator/PowerPoint.

Spec:
  {
    "canvas": [1280, 900],
    "title": "optional",
    "panels": [{"label": "A", "bbox": [40, 80, 520, 620]}],
    "nodes": [
      {"id": "tumor", "label": "Tumor cell", "bbox": [100, 300, 200, 90],
       "shape": "rounded|rect|ellipse", "fill": "#e8f5f1", "stroke": "#0f766e",
       "text_color": "#0f2d3a", "font_size": 20}
    ],
    "edges": [
      {"from": "tumor", "to": "caf", "label": "TGF-beta", "style": "solid|dashed",
       "arrow": true, "color": "#0f766e"}
    ],
    "notes": [{"text": "Hypothesis", "x": 60, "y": 740, "size": 16}]
  }
"""

from __future__ import annotations

import math
import re
import textwrap
import xml.etree.ElementTree as ET


def _esc(value: str) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _num(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bbox(item: dict, default=(0, 0, 160, 80)) -> tuple[float, float, float, float]:
    raw = item.get("bbox") or default
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raw = default
    x, y, w, h = (_num(v, d) for v, d in zip(raw, default))
    return x, y, max(1.0, w), max(1.0, h)


def _wrap_label(text: str, box_w: float, font_size: float, max_lines: int = 4) -> list[str]:
    if not text:
        return []
    per_char = font_size * 0.56
    width = max(4, int(box_w / per_char))
    return textwrap.wrap(str(text), width=width)[:max_lines]


def _node_svg(node: dict) -> list[str]:
    x, y, w, h = _bbox(node)
    shape = (node.get("shape") or "rounded").lower()
    fill = node.get("fill") or "#eef4f7"
    stroke = node.get("stroke") or "#0f766e"
    sw = _num(node.get("stroke_width"), 2.5)
    out = []
    if shape == "ellipse":
        out.append(f'<ellipse cx="{x + w / 2:.2f}" cy="{y + h / 2:.2f}" '
                   f'rx="{w / 2:.2f}" ry="{h / 2:.2f}" fill="{fill}" stroke="{stroke}" '
                   f'stroke-width="{sw}"/>')
    else:
        rx = min(w, h) * 0.16 if shape == "rounded" else 0
        out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                   f'rx="{rx:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')

    font_size = _num(node.get("font_size"), max(12.0, min(28.0, h * 0.24)))
    color = node.get("text_color") or "#102a33"
    lines = _wrap_label(node.get("label", ""), w - 16, font_size)
    if lines:
        line_h = font_size * 1.25
        total = line_h * len(lines)
        start = y + h / 2 - total / 2 + font_size
        for index, line in enumerate(lines):
            out.append(
                f'<text x="{x + w / 2:.2f}" y="{start + index * line_h:.2f}" '
                f'font-family="{_esc(node.get("font_family", "__FONT__"))}" '
                f'font-size="{font_size:.2f}" text-anchor="middle" '
                f'fill="{color}">{_esc(line)}</text>')
    return out


def _anchor(node: dict, target: dict) -> tuple[float, float]:
    ax, ay, aw, ah = _bbox(node)
    bx, by, bw, bh = _bbox(target)
    acx, acy = ax + aw / 2, ay + ah / 2
    bcx, bcy = bx + bw / 2, by + bh / 2
    dx, dy = bcx - acx, bcy - acy
    if dx == 0 and dy == 0:
        return acx, acy
    # clip the exit point to the source box edge
    scale_x = (aw / 2) / abs(dx) if dx else math.inf
    scale_y = (ah / 2) / abs(dy) if dy else math.inf
    scale = min(scale_x, scale_y)
    return acx + dx * scale, acy + dy * scale


def _edge_svg(edge: dict, nodes: dict[str, dict]) -> list[str]:
    src, dst = nodes.get(edge.get("from")), nodes.get(edge.get("to"))
    if not src or not dst:
        return []
    x1, y1 = _anchor(src, dst)
    x2, y2 = _anchor(dst, src)
    color = edge.get("color") or "#0f766e"
    width = _num(edge.get("width"), 2.5)
    dash = ' stroke-dasharray="7 5"' if (edge.get("style") or "solid") == "dashed" else ""
    marker = ' marker-end="url(#arrow)"' if edge.get("arrow", True) else ""
    out = [f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
           f'stroke="{color}" stroke-width="{width}"{dash}{marker}/>']
    label = edge.get("label")
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 8
        out.append(f'<text x="{mx:.2f}" y="{my:.2f}" text-anchor="middle" '
                   f'font-family="__FONT__" font-size="15" fill="{color}">{_esc(label)}</text>')
    return out


def center_spec(spec: dict) -> dict:
    """Translate nodes/panels so the drawing sits in the visual centre."""
    canvas = spec.get("canvas") or [1280, 900]
    cw, ch = _num(canvas[0], 1280), _num(canvas[1], 900)
    boxes = []
    for node in spec.get("nodes") or []:
        boxes.append(_bbox(node))
    for panel in spec.get("panels") or []:
        boxes.append(_bbox(panel))
    if not boxes:
        return spec
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[0] + b[2] for b in boxes)
    y2 = max(b[1] + b[3] for b in boxes)
    dy = (88 + ch - 60) / 2 - (y1 + y2) / 2
    dx = cw / 2 - (x1 + x2) / 2
    dx = max(40 - x1, min(dx, cw - 40 - x2))
    if abs(dx) < 0.5 and abs(dy) < 0.5:
        return spec
    for item in (spec.get("nodes") or []) + (spec.get("panels") or []):
        box = item.get("bbox")
        if isinstance(box, (list, tuple)) and len(box) >= 4:
            item["bbox"] = [box[0] + dx, box[1] + dy, box[2], box[3]]
    for note in spec.get("notes") or []:
        note["x"] = _num(note.get("x"), 40) + dx
        note["y"] = _num(note.get("y"), ch - 30) + dy
    return spec


def render(spec: dict, *, font: str = "Times New Roman") -> bytes:
    canvas = spec.get("canvas") or [1280, 900]
    cw, ch = (_num(canvas[0], 1280), _num(canvas[1], 900)) if len(canvas) >= 2 else (1280.0, 900.0)
    cw, ch = max(200.0, cw), max(150.0, ch)

    body: list[str] = [
        f'<rect x="0" y="0" width="{cw:.0f}" height="{ch:.0f}" fill="#ffffff"/>'
    ]

    for panel in spec.get("panels") or []:
        x, y, w, h = _bbox(panel)
        body.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
                    f'fill="none" stroke="#c7d3de" stroke-width="1.5" stroke-dasharray="6 6"/>')
        if panel.get("label"):
            body.append(f'<text x="{x + 12:.2f}" y="{y + 26:.2f}" font-family="{_esc(font)}" '
                        f'font-size="20" font-weight="700" fill="#33475b">'
                        f'{_esc(panel["label"])}</text>')

    if spec.get("title"):
        body.append(f'<text x="48" y="52" font-family="{_esc(font)}" font-size="28" '
                    f'font-weight="700" fill="#0f2d3a">{_esc(spec["title"])}</text>')

    nodes = {str(n.get("id", i)): n for i, n in enumerate(spec.get("nodes") or [])}
    for node in nodes.values():
        body.extend(_node_svg(node))

    for edge in spec.get("edges") or []:
        body.extend(_edge_svg(edge, nodes))

    for note in spec.get("notes") or []:
        body.append(f'<text x="{_num(note.get("x"), 40):.2f}" y="{_num(note.get("y"), ch - 30):.2f}" '
                    f'font-family="{_esc(font)}" font-size="{_num(note.get("size"), 16):.0f}" '
                    f'fill="#5b6b7a">{_esc(note.get("text", ""))}</text>')

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{cw:.0f}" height="{ch:.0f}" viewBox="0 0 {cw:.0f} {ch:.0f}">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#0f766e"/>
    </marker>
  </defs>
  {chr(10).join("  " + line for line in body)}
</svg>
'''
    return svg.replace("__FONT__", _esc(font)).encode("utf-8")


def repair_spec(spec: dict) -> dict:
    """Fill ids, clamp boxes into the canvas, drop dangling edges."""
    canvas = spec.get("canvas") or [1280, 900]
    cw, ch = _num(canvas[0], 1280), _num(canvas[1], 900)
    fixed_nodes = []
    ids = set()
    for index, node in enumerate(spec.get("nodes") or []):
        node = dict(node)
        node.setdefault("id", f"node{index + 1}")
        if node["id"] in ids:
            node["id"] = f"{node['id']}{index}"
        ids.add(node["id"])
        x, y, w, h = _bbox(node)
        node["bbox"] = [max(0, min(x, cw - 4)), max(0, min(y, ch - 4)),
                        min(w, cw), min(h, ch)]
        fixed_nodes.append(node)
    spec = dict(spec)
    spec["nodes"] = fixed_nodes
    spec["edges"] = [e for e in (spec.get("edges") or [])
                     if e.get("from") in ids and e.get("to") in ids]
    return spec
