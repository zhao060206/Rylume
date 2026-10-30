"""Distinct publication layouts for the non-closed-loop figure archetypes.

Four renderers share one measured card system so that each archetype has a
genuinely different topology instead of falling back to the generic grid:

  signal_pathway     vertical ligand -> receptor -> cascade -> nucleus flow
  process_pipeline   horizontal numbered synthesis / assay stages
  structural_anatomy stacked material / device layers with side callouts
  graphical_abstract problem -> mechanism -> outcome triptych

Each renderer consumes a compact JSON spec produced by the text model and
embeds image-model assets that were traced to editable vectors.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
import time
from pathlib import Path

import compose
import framework
import pipeline
from colorsafe import safe_color

PALETTES = {
    "nature": {"primary": "#0F4D92", "secondary": "#0284C7", "accent": "#D97706", "text": "#0F172A"},
    "cell": {"primary": "#A9713F", "secondary": "#2E8B7A", "accent": "#9333EA", "text": "#1E293B"},
    "acsnano": {"primary": "#0D9488", "secondary": "#2563EB", "accent": "#EA580C", "text": "#0F172A"},
    "minimal": {"primary": "#334155", "secondary": "#64748B", "accent": "#0D9488", "text": "#111827"},
}

ARCHETYPE_NAMES = {
    "signal_pathway": "分子/细胞信号转导通路",
    "process_pipeline": "实验制备与阶段流程",
    "structural_anatomy": "器件分层结构与解剖",
    "graphical_abstract": "论文图形摘要",
}

SPEC_INSTRUCTION = """你是 Cell / Nature / Science / ACS Nano 的资深科研插画编辑。
用户已经选定图型：{archetype_name}（{archetype}）。
请把用户的科研内容拆成该图型专用的结构化 JSON。只输出 JSON，不要解释。

通用结构：
{{
  "title": "英文大标题",
  "subtitle": "一句英文副标题",
  "stages": [
    {{"label": "英文短标签", "caption": "一句英文机制/工艺说明", "prompt": "one isolated ... flat 2D vector scientific illustration, pure white background, no text, no labels", "color": "#RRGGBB"}},
    ...
  ]
}}

图型专属要求：
- signal_pathway：3–6 个阶段，按用户给出的配体→受体→胞内级联→核内效应链展开；用户列出的阶段必须全部保留，不得截断或强行凑成 4 个；label 用完整阶段名（如 Transcription factor nuclear entry），不要缩写成 TF。
- process_pipeline：3–6 个阶段，严格按用户给出的时间/因果顺序排列；用户写的是生物过程就按 ligand binding -> receptor activation -> intracellular cascade -> nuclear effect 展开，用户写的是材料合成才按 precursor -> reaction -> functionalization -> assembly 展开。caption 写该阶段实际发生的生物/化学事件，不要套用模板。
- structural_anatomy：3–6 个阶段，按用户对象的真实空间层级拆分；生物对象用 tissue -> cell -> organelle / domain -> molecular complex，器件对象才用 encapsulation -> electrode -> active layer -> substrate。caption 写该层的组成与功能。
- graphical_abstract：严格 3 个阶段，分别为 Problem / Our strategy / Outcome，caption 写瓶颈、机制与性能收益。

硬性规则：
1. 不得编造用户未提及的分子、材料或实验结论；只做版式与术语规范化。
2. 每个 prompt 只描述一个孤立物体，纯白背景，扁平 2D 矢量，无文字、无标签、无箭头。
3. 所有可见文字放在 label/caption；图中不生成文字。
4. 配色符合用户指定的期刊色系；stages 的 color 用十六进制。
5. 英文拼写准确；label 必须使用用户阶段名的完整英文，不得用 TF/ECM 等缩写，长度不超过 40 个字符。
6. 先判断用户领域：生物医学内容必须使用细胞/分子/组织术语；材料或器件内容才使用材料/器件术语；不得把生物过程写成“传感层/电极/封装”，也不得把器件写成“细胞膜/细胞核”。
7. title/subtitle 必须复述用户的具体对象与过程，禁止使用“Programmable Material Synthesis Pipeline”“Embodied Intelligence System”这类与用户主题无关的通用标题。
"""


def plan_archetype(text: str, config: dict, archetype: str, _retry: int = 0) -> dict:
    name = ARCHETYPE_NAMES.get(archetype, archetype)
    brief = str(config.get("design_brief") or "").strip()
    user_text = text
    if brief:
        user_text = (text + chr(10) + chr(10) + "已发表插图风格约束（必须遵守）："
                     + chr(10) + brief)
    messages = [
        {"role": "system", "content": SPEC_INSTRUCTION.format(archetype_name=name, archetype=archetype)},
        {"role": "user", "content": user_text},
    ]
    try:
        spec = pipeline.chat_json(config, messages, temperature=0.25, max_tokens=2500)
    except Exception:
        raw = pipeline._chat(config, messages, temperature=0.25, max_tokens=2500)
        fixed = pipeline._chat(config, [
            {"role": "system", "content":
             "You repair invalid JSON. Return ONLY one valid JSON object with title, subtitle and stages."},
            {"role": "user", "content": raw[:7000]},
        ], temperature=0)
        spec = pipeline._json_object(fixed)
    spec.setdefault("title", name)
    spec.setdefault("subtitle", "")
    layout, regions = _layout_hints(text)
    spec["layout"] = layout
    spec["regions"] = regions
    stages = []
    for index, item in enumerate(spec.get("stages") or []):
        if not isinstance(item, dict):
            continue
        stages.append({
            "label": str(item.get("label") or f"Stage {index + 1}"),
            "caption": str(item.get("caption") or ""),
            "prompt": str(item.get("prompt") or ""),
            "color": str(item.get("color") or ""),
        })
    spec["stages"] = stages[:6]
    if archetype == "signal_pathway" and len(stages) < 3 and _retry < 1:
        # The planner sometimes collapses a four-step pathway into two
        # "before/after" stages. Retry once with an explicit stage-count rule.
        retry_config = dict(config)
        retry_config["design_brief"] = ((config.get("design_brief") or "") +
            chr(10) + "信号通路必须拆成 3–6 个连续阶段，至少 3 个；每个阶段一个 label，不得合并成前后两张。")
        return plan_archetype(text, retry_config, archetype, _retry=1)
    return spec


def _palette(config: dict, archetype: str) -> dict:
    dna = config.get("style_dna") or {}
    palette = dna.get("palette") if isinstance(dna.get("palette"), dict) else {}
    defaults = {
        "signal_pathway": ("#A9713F", "#2E8B7A", "#9333EA"),
        "process_pipeline": ("#0284C7", "#4F46E5", "#EA580C"),
        "structural_anatomy": ("#1E293B", "#0D9488", "#E11D48"),
        "graphical_abstract": ("#0284C7", "#16A34A", "#DC2626"),
    }[archetype]
    return {
        "primary": safe_color(palette.get("primary"), defaults[0]),
        "secondary": safe_color(palette.get("secondary"), defaults[1]),
        "accent": safe_color(palette.get("accent"), defaults[2]),
        "text": safe_color(palette.get("text"), "#0F172A"),
    }


_HORIZONTAL_RE = re.compile(
    r"左到右|从左到右|左至右|由左至右|横向|左右|left[- ]?to[- ]?right|"
    r"horizontal|S\s*形|S[- ]?shaped|serpentine|蜿蜒", re.I)
_VERTICAL_RE = re.compile(
    r"自上而下|从上到下|由上至下|纵向|竖向|垂直|top[- ]?to[- ]?bottom|"
    r"vertical|上到下", re.I)
_REGION_RE = re.compile(
    r"(\d{1,3})\s*%?\s*[–—\-~至到]\s*(\d{1,3})\s*%\s*"
    r"(?:为|是|：|:)?\s*([^\s；;，,。\n][^；;，,。\n]{1,35})")


def _layout_hints(text: str) -> tuple[str, list[dict]]:
    """Read the user's own spatial instructions instead of assuming a template."""
    value = str(text or "")
    # "不要使用自上而下的四段模板" is a rejection, not a request for vertical.
    cleaned = re.sub(
        r"(?:不要|避免|禁止|不使用|不要用|别用|而非|不是)[^。；;\n]{0,50}?"
        r"(?:自上而下|从上到下|纵向|竖向|vertical|top[- ]?to[- ]?bottom)",
        " ", value, flags=re.I)
    horizontal = bool(_HORIZONTAL_RE.search(cleaned))
    vertical = bool(_VERTICAL_RE.search(cleaned))
    layout = "vertical"
    if horizontal and not vertical:
        layout = "horizontal_s"
    regions = []
    seen = set()
    for match in _REGION_RE.finditer(value):
        try:
            start, end = int(match.group(1)), int(match.group(2))
        except ValueError:
            continue
        label = match.group(3).strip(" ：:，,。")
        if not (0 <= start < end <= 100) or not label:
            continue
        key = (start, end, label.lower())
        if key in seen:
            continue
        seen.add(key)
        regions.append({"start": start, "end": end, "label": label[:40]})
    regions.sort(key=lambda item: item["start"])
    return layout, regions


def _esc(value) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _text(x, y, value, size=15, color="#0F172A", anchor="start", weight="normal",
          italic=False, halo=False, max_width=None):
    style = f' font-weight="{weight}"' if weight != "normal" else ""
    style += ' font-style="italic"' if italic else ""
    if max_width and framework._measure_text(str(value), size, weight == "bold") > max_width:
        style += f' textLength="{max_width:.1f}" lengthAdjust="spacingAndGlyphs"'
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f'font-family="Arial, Helvetica Neue, Microsoft YaHei, sans-serif" '
            f'font-size="{size:.1f}" fill="{color}"{style}'
            + (' paint-order="stroke" stroke="#FFFFFF" stroke-width="2.6" stroke-linejoin="round"' if halo else '') + '>'
            f'{_esc(value)}</text>')


def _wrap(value: str, size: float, max_width: float, max_lines: int = 3) -> list[str]:
    words = str(value or "").split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if not current or framework._measure_text(candidate, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines or [""]


def _asset_group(asset, x, y, w, h) -> str:
    if not asset:
        return ""
    svg, aw, ah = asset
    inner = compose._clean_asset(svg)
    scale = min(w / aw, h / ah) * 0.96
    tx = x + (w - aw * scale) / 2
    ty = y + (h - ah * scale) / 2
    return (f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.5f})">{inner}</g>')


def _asset_or_glyph(asset, label: str, x, y, w, h, color, stage=None) -> str:
    if asset:
        return _asset_group(asset, x, y, w, h)
    size = min(w * 0.62, h * 0.62)
    entity = dict(stage or {})
    entity["label"] = entity.get("label") or label
    return framework.entity_glyph(entity, x + w / 2, y + h / 2, size, color)


def _header(spec, font_size_title, canvas_w, palette):
    # Journal figures do not carry a title inside the artwork; the title belongs
    # in the caption/legend. Keep the metadata for filenames and the UI only.
    return "", 0
    title = spec.get("title") or ""
    subtitle = spec.get("subtitle") or ""
    tsize, tlines = framework._fit_lines(title, canvas_w - 160, 30, 22, max_lines=2)
    ssize, slines = framework._fit_lines(subtitle, canvas_w - 200, 15, 9, max_lines=2)
    y = 52 if len(tlines) == 1 else 40
    out = [_text(canvas_w / 2, y, tlines[0], tsize, palette["text"], "middle", "bold",
                 max_width=canvas_w - 150)]
    for i, line in enumerate(tlines[1:], 1):
        out.append(_text(canvas_w / 2, y + i * (tsize + 2), line, tsize,
                         palette["text"], "middle", "bold", max_width=canvas_w - 150))
    # The subtitle needs a full title em plus its own leading; a fixed 24px
    # gap overlapped the title at 30pt.
    sy = y + (len(tlines) - 1) * (tsize + 2) + tsize + 6
    for i, line in enumerate(slines):
        out.append(_text(canvas_w / 2, sy + i * (ssize + 2), line, ssize, "#475569", "middle"))
    return "".join(out), sy + (len(slines) - 1) * (ssize + 2)


def _card(x, y, w, h, fill, stroke, rx=14, width=1.4):
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
            f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')


def _arrow(x1, y1, x2, y2, color, width=2.2, dashed=False, label=""):
    dash = ' stroke-dasharray="8 5"' if dashed else ""
    out = [f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
           f'stroke="{color}" stroke-width="{width}"{dash} marker-end="url(#fab-arrow-dark)"/>']
    if label:
        out.append(_text((x1 + x2) / 2, (y1 + y2) / 2 - 8, label, 11, color, "middle"))
    return "".join(out)


def _canvas_wrap(content: str, canvas, shape, defs_extra="") -> bytes:
    cw, ch = canvas
    defs = [defs_extra,
            '<marker id="fab-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">'
            '<path d="M0 0 L10 5 L0 10 z" fill="#5E8F7C"/></marker>',
            '<marker id="fab-arrow-dark" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="5.5" markerHeight="5.5" orient="auto-start-reverse">'
            '<path d="M0 0 L10 5 L0 10 z" fill="#33475b"/></marker>',
            '<marker id="fab-arrow-blue" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7.0" markerHeight="7.0" orient="auto-start-reverse">'
            '<path d="M0 0 L10 5 L0 10 z" fill="#2F6DB3"/></marker>']
    shape = (shape or "rect").lower()
    inner = content
    if shape in ("card", "circle", "ellipse"):
        if shape == "card":
            clip = f'<rect x="14" y="14" width="{cw-28:.1f}" height="{ch-28:.1f}" rx="24"/>'
            border = (f'<rect x="14" y="14" width="{cw-28:.1f}" height="{ch-28:.1f}" rx="24" '
                      f'fill="none" stroke="#CBD5E1" stroke-width="1.6"/>')
        elif shape == "circle":
            r = min(cw, ch) / 2 - 14
            clip = f'<circle cx="{cw/2:.1f}" cy="{ch/2:.1f}" r="{r:.1f}"/>'
            border = (f'<circle cx="{cw/2:.1f}" cy="{ch/2:.1f}" r="{r:.1f}" fill="none" '
                      f'stroke="#CBD5E1" stroke-width="1.6"/>')
        else:
            clip = (f'<ellipse cx="{cw/2:.1f}" cy="{ch/2:.1f}" rx="{cw/2-14:.1f}" '
                    f'ry="{ch/2-14:.1f}"/>')
            border = (f'<ellipse cx="{cw/2:.1f}" cy="{ch/2:.1f}" rx="{cw/2-14:.1f}" '
                      f'ry="{ch/2-14:.1f}" fill="none" stroke="#CBD5E1" stroke-width="1.6"/>')
        defs.append(f'<clipPath id="fab-clip">{clip}</clipPath>')
        if shape in ("circle", "ellipse"):
            # Keep the whole layout inside the inscribed rectangle of the
            # actual clip so titles and edge cards are not silently cut.
            if shape == "circle":
                side = (min(cw, ch) - 28) / 1.41421356
                k = min(side / cw, side / ch)
            else:
                k = min((cw - 28) / (cw * 1.41421356),
                        (ch - 28) / (ch * 1.41421356))
            content = (f'<g transform="translate({cw*(1-k)/2:.2f},{ch*(1-k)/2:.2f}) '
                       f'scale({k:.4f})">{content}</g>')
        inner = f'<g clip-path="url(#fab-clip)">{content}</g>'
    else:
        border = ""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw:.0f}" height="{ch:.0f}" '
             f'viewBox="0 0 {cw:.0f} {ch:.0f}">',
             f'<defs>{"".join(defs)}</defs>',
             f'<rect width="{cw:.0f}" height="{ch:.0f}" fill="#FFFFFF"/>',
             inner, border, "</svg>"]
    return (chr(10).join(parts) + chr(10)).encode("utf-8")


def _curve_arrow(x1, y1, cx1, cy1, cx2, cy2, x2, y2, color, width=2.6):
    return (f'<path d="M {x1:.1f} {y1:.1f} C {cx1:.1f} {cy1:.1f} '
            f'{cx2:.1f} {cy2:.1f} {x2:.1f} {y2:.1f}" fill="none" '
            f'stroke="{color}" stroke-width="{width}" marker-end="url(#fab-arrow)"/>')



def _scene_icon(kind: str, cx: float, cy: float, size: float, color: str) -> str:
    """Hand-drawn textbook icon; small enough to sit inside a cell scene."""
    s = size
    out = []
    if kind == "vesicle":
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{s*0.42:.1f}" fill="#FFFFFF" '
                   f'stroke="{color}" stroke-width="{max(1.6,s*0.035):.1f}"/>')
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{s*0.33:.1f}" fill="none" '
                   f'stroke="{color}" stroke-width="1.2" opacity="0.55"/>')
        for i in range(9):
            import math as _m
            a = 2 * _m.pi * i / 9
            out.append(f'<circle cx="{cx + s*0.40*_m.cos(a):.1f}" cy="{cy + s*0.40*_m.sin(a):.1f}" '
                       f'r="{max(1.6,s*0.045):.1f}" fill="{color}" opacity="0.9"/>')
    elif kind == "receptor":
        ym = cy + s * 0.18
        out.append(f'<line x1="{cx-s*0.48:.1f}" y1="{ym:.1f}" x2="{cx+s*0.48:.1f}" y2="{ym:.1f}" '
                   f'stroke="#8FA6B8" stroke-width="{max(2,s*0.05):.1f}"/>')
        for dx in (-0.38, -0.18, 0.18, 0.38):
            out.append(f'<circle cx="{cx+s*dx:.1f}" cy="{ym-s*0.05:.1f}" r="{max(1.4,s*0.035):.1f}" fill="#8FA6B8"/>')
        for dx in (-0.10, 0.10):
            out.append(f'<rect x="{cx+s*dx-s*0.055:.1f}" y="{ym-s*0.20:.1f}" width="{s*0.11:.1f}" '
                       f'height="{s*0.32:.1f}" rx="{s*0.03:.1f}" fill="{color}" opacity="0.9"/>')
        out.append(f'<path d="M {cx:.1f} {ym-s*0.18:.1f} L {cx-s*0.12:.1f} {ym-s*0.38:.1f} '
                   f'M {cx:.1f} {ym-s*0.18:.1f} L {cx+s*0.12:.1f} {ym-s*0.38:.1f}" '
                   f'stroke="{color}" stroke-width="{max(1.8,s*0.045):.1f}" fill="none"/>')
        out.append(f'<circle cx="{cx-s*0.12:.1f}" cy="{ym-s*0.40:.1f}" r="{max(2,s*0.055):.1f}" fill="#E8A33D"/>')
        out.append(f'<circle cx="{cx+s*0.12:.1f}" cy="{ym-s*0.40:.1f}" r="{max(2,s*0.055):.1f}" fill="#E8A33D"/>')
    elif kind == "kinase":
        pts = [(cx-s*0.30, cy+s*0.14), (cx, cy-s*0.16), (cx+s*0.30, cy+s*0.14)]
        for i, (px, py) in enumerate(pts):
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{s*0.155:.1f}" fill="#FFFFFF" '
                       f'stroke="{color}" stroke-width="{max(2,s*0.045):.1f}"/>')
            out.append(_text(px, py+s*0.055, "P", s*0.14, color, "middle", "bold"))
            if i < 2:
                nx, ny = pts[i+1]
                out.append(_arrow(px+s*0.17, py, nx-s*0.17, ny, color, max(1.6,s*0.035)))
    elif kind == "nucleus":
        # A short stretch of nuclear envelope with an open pore; the TF is
        # drawn as a compact diamond passing through the gap.
        xl, xr = cx - s * 0.26, cx + s * 0.26
        y1, y2 = cy - s * 0.46, cy + s * 0.46
        for x in (xl, xr):
            out.append(f'<path d="M {x:.1f} {y1:.1f} L {x:.1f} {cy-s*0.13:.1f}" fill="none" '
                       f'stroke="#8B5CF6" stroke-width="{max(2,s*0.04):.1f}"/>')
            out.append(f'<path d="M {x:.1f} {cy+s*0.13:.1f} L {x:.1f} {y2:.1f}" fill="none" '
                       f'stroke="#8B5CF6" stroke-width="{max(2,s*0.04):.1f}"/>')
            out.append(f'<path d="M {x-s*0.05:.1f} {cy-s*0.13:.1f} Q {x:.1f} {cy-s*0.22:.1f} '
                       f'{x+s*0.05:.1f} {cy-s*0.13:.1f}" fill="#FBF7FF" stroke="#8B5CF6" stroke-width="1.4"/>')
            out.append(f'<path d="M {x-s*0.05:.1f} {cy+s*0.13:.1f} Q {x:.1f} {cy+s*0.22:.1f} '
                       f'{x+s*0.05:.1f} {cy+s*0.13:.1f}" fill="#FBF7FF" stroke="#8B5CF6" stroke-width="1.4"/>')
        out.append(f'<path d="M {cx-s*0.10:.1f} {cy:.1f} L {cx:.1f} {cy-s*0.12:.1f} '
                   f'L {cx+s*0.10:.1f} {cy:.1f} L {cx:.1f} {cy+s*0.12:.1f} Z" '
                   f'fill="#C4B5FD" stroke="#7C3AED" stroke-width="1.4"/>')
        out.append(_arrow(cx-s*0.58, cy, cx-s*0.14, cy, "#64748B", max(1.8,s*0.035)))
        out.append(_arrow(cx+s*0.14, cy, cx+s*0.58, cy, "#64748B", max(1.8,s*0.035)))
    elif kind == "matrix":
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{s*0.24:.1f}" fill="#FFFFFF" '
                   f'stroke="{color}" stroke-width="{max(1.8,s*0.04):.1f}"/>')
        out.append(f'<circle cx="{cx+s*0.05:.1f}" cy="{cy-s*0.03:.1f}" r="{s*0.09:.1f}" fill="{color}" opacity="0.35"/>')
        import math as _m
        for i in range(6):
            a = 2 * _m.pi * i / 6
            x1 = cx + s*0.28*_m.cos(a); y1 = cy + s*0.28*_m.sin(a)
            x2 = cx + s*0.46*_m.cos(a); y2 = cy + s*0.46*_m.sin(a)
            xm = cx + s*0.40*_m.cos(a+0.25); ym = cy + s*0.40*_m.sin(a+0.25)
            out.append(f'<path d="M {x1:.1f} {y1:.1f} Q {xm:.1f} {ym:.1f} {x2:.1f} {y2:.1f}" '
                       f'fill="none" stroke="{color}" stroke-width="1.6" opacity="0.55"/>')
    return "".join(out)


def _vesicle_svg(cx: float, cy: float, r: float = 15.0) -> str:
    """Small double-membrane vesicle with cargo dots, drawn as editable vector."""
    dots = ""
    for dx, dy in ((-5.0, -4.0), (4.0, -2.0), (1.0, 5.0)):
        dots += (f'<circle cx="{cx+dx:.1f}" cy="{cy+dy:.1f}" r="2.1" '
                 f'fill="#C9A45C" opacity="0.9"/>')
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="#F7FBF8" '
            f'fill-opacity="0.82" stroke="#7FA8A0" stroke-width="1.6"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r*0.70:.1f}" fill="none" '
            f'stroke="#A9C8BF" stroke-width="1.2"/>' + dots)


def _matrix_bundle(ix: float, iy: float, iw: float, ih: float) -> str:
    """Editable collagen/ECM fibres in the lower-right extracellular space."""
    out = []
    # Keep the fibrous bed strictly outside the painted cell. The polygon
    # follows the lower-right cell margin; everything inside it is clipped.
    out.append(f'<clipPath id="ecm-clip"><path d="'
               f'M {ix+iw*0.72:.1f} {iy+ih*1.02:.1f} '
               f'L {ix+iw*0.72:.1f} {iy+ih*0.80:.1f} '
               f'L {ix+iw*0.82:.1f} {iy+ih*0.77:.1f} '
               f'L {ix+iw*0.92:.1f} {iy+ih*0.78:.1f} '
               f'L {ix+iw*1.02:.1f} {iy+ih*0.83:.1f} '
               f'L {ix+iw*1.02:.1f} {iy+ih*1.02:.1f} Z"/></clipPath>')
    out.append('<g clip-path="url(#ecm-clip)">')
    rng = random.Random(37)
    # Five collagen bundles, each a three-strand rope. Bundles sweep from the
    # cell surface to the right edge; the spacing is deliberately uneven.
    for b in range(5):
        base_y = 0.805 + b * 0.038
        for j in (-1, 0, 1):
            y0 = iy + ih * (base_y + j * 0.006)
            x0 = ix + iw * (0.735 + 0.014 * (b % 3))
            x1 = ix + iw * (0.985 + 0.018 * (b % 2))
            c1y = y0 - ih * (0.024 + 0.005 * (b % 3))
            c2y = y0 + ih * (0.022 + 0.004 * (b % 2))
            out.append(f'<path d="M {x0:.1f} {y0:.1f} '
                       f'C {x0+iw*0.070:.1f} {c1y:.1f}, '
                       f'{x1-iw*0.090:.1f} {c2y:.1f}, {x1:.1f} {y0+ih*0.012:.1f}" '
                       f'fill="none" stroke="#C49A6C" stroke-width="2.4" '
                       f'stroke-linecap="round" opacity="0.62"/>')
        # A pale central highlight on the middle strand.
        y0 = iy + ih * base_y
        out.append(f'<path d="M {ix+iw*0.745:.1f} {y0-ih*0.003:.1f} '
                   f'C {ix+iw*0.815:.1f} {y0-ih*0.024:.1f}, '
                   f'{ix+iw*0.900:.1f} {y0+ih*0.024:.1f}, {ix+iw*0.990:.1f} {y0+ih*0.010:.1f}" '
                   f'fill="none" stroke="#E9D2B8" stroke-width="1.0" '
                   f'stroke-linecap="round" opacity="0.85"/>')
    # A few loose thin fibrils between the bundles break up the regularity.
    for k in range(6):
        y0 = iy + ih * (0.825 + k * 0.028)
        x0 = ix + iw * (0.755 + 0.020 * (k % 3))
        x1 = ix + iw * (0.930 + 0.020 * (k % 2))
        out.append(f'<path d="M {x0:.1f} {y0:.1f} '
                   f'C {x0+iw*0.055:.1f} {y0-ih*0.018:.1f}, '
                   f'{x1-iw*0.060:.1f} {y0+ih*0.020:.1f}, {x1:.1f} {y0-ih*0.006:.1f}" '
                   f'fill="none" stroke="#D3B18C" stroke-width="1.4" '
                   f'stroke-linecap="round" opacity="0.65"/>')
    # Short cross-links and matrix dots make the mesh feel connected.
    for k in range(8):
        bx = ix + iw * (0.79 + rng.random() * 0.19)
        by = iy + ih * (0.82 + rng.random() * 0.16)
        out.append(f'<path d="M {bx-4:.1f} {by+5:.1f} L {bx+7:.1f} {by-4:.1f}" '
                   f'stroke="#B9895B" stroke-width="1.1" opacity="0.55"/>')
        out.append(f'<circle cx="{bx+iw*0.018:.1f}" cy="{by-ih*0.020:.1f}" r="1.4" '
                   f'fill="#CDB79D" opacity="0.8"/>')
    # Fibronectin / integrin attachment points at the cell-matrix interface.
    for k in range(4):
        gx = ix + iw * (0.725 + 0.026 * k)
        gy = iy + ih * (0.795 + 0.018 * k)
        out.append(f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="4.2" fill="#FFFFFF" '
                   f'stroke="#7E9FB0" stroke-width="1.2"/>')
        out.append(f'<path d="M {gx-6:.1f} {gy+2:.1f} L {gx:.1f} {gy-6:.1f} '
                   f'L {gx+6:.1f} {gy+2:.1f}" fill="none" stroke="#7E9FB0" '
                   f'stroke-width="1.2" stroke-linecap="round"/>')
    out.append('</g>')
    return "".join(out)


def _scene_label(tx, ty, label, caption, anchor, width, color, palette, scale=1.0):
    lines = _wrap(caption or "", 10.5 * scale, width, 2)
    out = [_text(tx, ty, label, 15 * scale, color, anchor, "bold", halo=True)]
    for i, line in enumerate(lines):
        out.append(_text(tx, ty + 17 * scale + i * 13.4 * scale, line,
                         11.2 * scale, "#4B5563", anchor, halo=True))
    return "".join(out)


def _render_signal_plate(spec, asset, canvas, shape, palette):
    """Annotated textbook plate: one painted cell scene plus callout labels."""
    cw, ch = canvas
    stages = spec.get("stages") or []
    label_scale = float(spec.get("_plate_label_scale") or 1.0)
    plate_scale = float(spec.get("_plate_scale") or 1.0)
    plate_spec = dict(spec)
    plate_spec["subtitle"] = str(plate_spec.get("subtitle") or "").replace(
        "A flat vector pathway", "A continuous textbook-style pathway")
    head, head_bottom = _header(plate_spec, 28, cw, palette)
    top = max(head_bottom + 26, 56)
    bottom = ch - 26
    # 3:2 painted scene, large enough to read at 1280x900. The old square
    # box shrank the cell to ~500 px and left a visible panel border.
    iw = min(cw * 0.70 * plate_scale, (bottom - top) * 1.43)
    ih = iw / 1.43
    ix = (cw - iw) / 2.0
    iy = top + ((bottom - top) - ih) / 2.0
    content = [head]
    content.append(_asset_group(asset, ix, iy, iw, ih))
    if spec.get("_with_ecm") and str(spec.get("_plate_mode") or "signal_pathway") == "signal_pathway":
        content.append(_matrix_bundle(ix, iy, iw, ih))

    n = len(stages)
    first_label = str((stages[0].get("label") if stages else "") or "").lower()
    plate_mode = str(spec.get("_plate_mode") or "signal_pathway")
    draw_ev = bool(stages) and plate_mode == "signal_pathway" and (
        "vesic" in str(spec.get("title") or "").lower() or "secret" in first_label)
    if draw_ev:
        content.append(_vesicle_svg(ix + iw * 0.165, iy + ih * 0.550, 20))
    if n <= 5:
        anchors = [((0.165, 0.550) if draw_ev else (0.315, 0.300)), (0.275, 0.335),
                   (0.410, 0.440), (0.735, 0.460), (0.685, 0.810)]
        left_n = min(3, n)
        right_n = max(0, n - left_n)
        left_fracs = [0.12, 0.42, 0.58][:left_n]
        right_fracs = [0.22, 0.62][:right_n]
        if n == 4:
            anchors = [(0.205, 0.155), (0.255, 0.245),
                       (0.420, 0.560), (0.665, 0.500)]
        elif n == 5:
            anchors = [(0.205, 0.155), (0.255, 0.245), (0.340, 0.330),
                       (0.665, 0.500), (0.790, 0.820)]
    else:
        left_n = (n + 1) // 2
        right_n = n - left_n
        if n == 6:
            # Six stages: extracellular -> membrane -> cytoplasm -> pore ->
            # nucleus -> matrix. These targets match the painted cell anatomy.
            anchors = [(0.205, 0.420), (0.270, 0.550), (0.430, 0.520),
                       (0.620, 0.470), (0.700, 0.550), (0.760, 0.820)]
        else:
            if n == 5:
                # Closed textbook cell: receptor on the left membrane, PIP3 in
                # the left cytosol, nucleus right of centre, collagen bottom right.
                anchors = [(0.235, 0.475), (0.255, 0.515), (0.365, 0.500),
                           (0.620, 0.500), (0.775, 0.780)]
            else:
                anchors = []
                for i in range(left_n):
                    anchors.append((0.255 - 0.018 * (i % 2),
                                    0.14 + 0.72 * (i + 0.5) / max(1, left_n)))
                for j in range(right_n):
                    anchors.append((0.720 + 0.022 * (j % 2),
                                    0.30 + 0.58 * (j + 0.5) / max(1, right_n)))
        left_fracs = [0.10 + 0.76 * (i + 0.5) / max(1, left_n) for i in range(left_n)]
        right_fracs = [0.16 + 0.70 * (j + 0.5) / max(1, right_n) for j in range(right_n)]
    colors = ["#2F5D7C", "#3F7A72", "#8A6A3B", "#6B5B7B", "#4E6E63",
              "#B07A45", "#5B7FA3", "#8A6A9E"]
    col_w = max(206.0, (cw - iw) / 2.0 - 12.0)
    layout = []
    for i in range(n):
        if i < left_n:
            lx = 30.0
            ly = iy + ih * left_fracs[i]
            side = "left"
        else:
            lx = cw - 24.0 - col_w
            ly = iy + ih * right_fracs[i - left_n]
            side = "right"
        fx, fy = anchors[i]
        ax, ay = ix + iw * fx, iy + ih * fy
        layout.append((lx, ly, side, ax, ay))

    if n in (4, 5) and plate_mode == "signal_pathway":
        # Editable molecules sit on top of the painted cytosol so the arrows
        # have a real target; the qwen layer supplies tissue texture only.
        kx, ky = layout[2][3], layout[2][4]
        kc = safe_color(stages[2].get("color"), "#2E8B7A")
        # No synthetic PIP3 hexagon: its subcellular placement was impossible
        # to guarantee against the painted cytosol, so the numbered callout
        # carries the stage instead of a misleading molecule glyph.
        # Tyrosine-phosphorylation marks on the receptor tail: small, editable
        # molecular detail that ties the painted receptor to the cascade.
        rx0, ry0 = layout[1][3], layout[1][4]
        for pdx, pdy in ((-18, 25), (0, 31), (18, 25)):
            content.append(f'<circle cx="{rx0+pdx:.1f}" cy="{ry0+pdy:.1f}" r="5.2" '
                           f'fill="#F2913D" stroke="#FFFFFF" stroke-width="1.0"/>')
            content.append(_text(rx0 + pdx, ry0 + pdy + 2.8, "P", 7.2, "#FFFFFF", "middle", "bold"))
        ax0, ay0 = layout[1][3], layout[1][4]
        ax1, ay1 = layout[2][3], layout[2][4]
        nx0, ny0 = layout[3][3], layout[3][4]
        def _curve(x1, y1, x2, y2, bend=0.35, dashed=False, color="#33475B",
                   marker="fab-arrow-dark"):
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0 - abs(x2 - x1) * bend
            dash = ' stroke-dasharray="7 5"' if dashed else ""
            return (f'<path d="M {x1:.1f} {y1:.1f} Q {cx:.1f} {cy:.1f} {x2:.1f} {y2:.1f}" '
                    f'fill="none" stroke="{color}" stroke-width="2.1"{dash} '
                    f'marker-end="url(#{marker})" opacity="0.9"/>')
        if n == 4:
            content.append(_curve(ax0, ay0, ax1, ay1))
            content.append(_curve(ax1, ay1, nx0 - 8, ny0 - 30, bend=0.22))
        if n == 5:
            pass

    for i, stage in enumerate(stages):
        lx, ly, side, ax, ay = layout[i]
        color = safe_color(stage.get("color"), colors[i % len(colors)])
        label = str(stage.get("label") or "")
        if label.strip().lower().endswith("phosphorylation of transcription"):
            label = label.rstrip() + " regulators"
        caption = (stage.get("caption") or "").split(". ")[0]
        if i == 0 and "donor cell" in caption.lower():
            caption = "Extracellular vesicles release ligands into the extracellular space."
        lines = _wrap(label, 13.8 * label_scale, col_w * 0.74, 5)
        content.append(f'<circle cx="{lx+10:.1f}" cy="{ly-4:.1f}" r="11.5" fill="{color}"/>')
        content.append(_text(lx + 11, ly + 0.5, str(i + 1), 12.8 * label_scale,
                             "#FFFFFF", "middle", "bold"))
        tx = lx + 28
        for j, line in enumerate(lines):
            content.append(_text(tx, ly + j * 15.4 * label_scale, line,
                                 13.8 * label_scale, "#111827", "start", "bold", halo=True))
        cy0 = ly + len(lines) * 15.4 * label_scale + 3
        cap_lines = _wrap(caption, 10.4 * label_scale, col_w * 0.72, 6)
        for j, line in enumerate(cap_lines):
            content.append(_text(tx, cy0 + j * 12.8 * label_scale, line,
                                 10.4 * label_scale, "#4B5563", "start", halo=True))
        # No dashed leader: labels sit next to their structures and the old
        # pointers were prone to landing on unrelated painted details.

    if stages and plate_mode == "signal_pathway" and (
            "force" in first_label or "mechanical" in first_label):
        fx, fy = layout[0][3], layout[0][4]
        for dx in (-34.0, 0.0, 34.0):
            content.append(f'<path d="M {fx+dx:.1f} {fy-62:.1f} Q {fx+dx:.1f} {fy-34:.1f} '
                           f'{fx+dx:.1f} {fy-2:.1f}" fill="none" stroke="#2F6DB3" '
                           f'stroke-width="3.0" opacity="0.9" marker-end="url(#fab-arrow-blue)"/>')
    if n == 5 and plate_mode == "signal_pathway":
        kx, ky = layout[2][3], layout[2][4]
        akt_x, akt_y = layout[3][3], layout[3][4]
        mx, my = layout[4][3], layout[4][4]
        # Golgi-derived collagen cargo vesicles at the secretory face.
        content.append(_vesicle_svg(ix + iw * 0.705, iy + ih * 0.735, 15))
        content.append(_vesicle_svg(ix + iw * 0.748, iy + ih * 0.792, 12))
        nuc_x, nuc_y = ix + iw * 0.585, iy + ih * 0.500
        # the callout sits on the right face of the nucleus, but the import
        # arrow still terminates on the left nuclear envelope / pore.
        pore_x, pore_y = nuc_x - iw * 0.135, nuc_y - ih * 0.020
        tf_x, tf_y = pore_x + 38, pore_y + 10
        # explicit TF cargo inside the nucleus, so the import arrow has a target
        content.append(f'<circle cx="{tf_x:.1f}" cy="{tf_y:.1f}" r="10" fill="#FFFFFF" '
                       f'stroke="#6F9E8F" stroke-width="1.4"/>')
        content.append(_text(tf_x, tf_y + 3.2, "TF", 8.5, "#2F5D7C", "middle", "bold"))
        # integrin -> kinase: start on the receptor cytoplasmic tail, not in mid-air
        ax2, ay2 = layout[1][3], layout[1][4]
        ax3, ay3 = layout[2][3], layout[2][4]
        content.append(f'<path d="M {ax2+4:.1f} {ay2+18:.1f} Q {ax2+54:.1f} {ay2+56:.1f}, '
                       f'{ax3-18:.1f} {ay3-6:.1f}" fill="none" stroke="#356B5F" '
                       f'stroke-width="2.8" opacity="0.9" marker-end="url(#fab-arrow)"/>')
        # AKT -> nuclear pore -> TF.
        content.append(f'<path d="M {akt_x-36:.1f} {akt_y-4:.1f} C {akt_x-76:.1f} {akt_y-30:.1f}, '
                       f'{pore_x+22:.1f} {pore_y-28:.1f}, {pore_x-2:.1f} {pore_y:.1f}" fill="none" '
                       f'stroke="#356B5F" stroke-width="3.0" opacity="1" '
                       f'marker-end="url(#fab-arrow)"/>')
        # nuclear output -> matrix: start on the nuclear envelope, not at the
        # AKT label anchor (the old start made the arrow cross the whole cell).
        content.append(f'<path d="M {nuc_x+iw*0.125:.1f} {nuc_y+ih*0.085:.1f} '
                       f'C {nuc_x+iw*0.190:.1f} {nuc_y+ih*0.220:.1f}, '
                       f'{mx-iw*0.105:.1f} {my-ih*0.115:.1f}, {mx-7:.1f} {my-14:.1f}" '
                       f'fill="none" stroke="#356B5F" stroke-width="3.0" opacity="0.98" '
                       f'marker-end="url(#fab-arrow)"/>')
        # The four connectors are deliberately unlabelled: the numbered stage
        # callouts carry the semantics, and tiny floating words only added noise.
    return _canvas_wrap("".join(content), canvas, shape, "")


def _render_signal_scene(spec, assets, canvas, shape, palette):
    """Textbook mechanism figure: one cell, labels around the perimeter."""
    scene = assets.get("scene")
    if scene:
        return _render_signal_plate(spec, scene, canvas, shape, palette)
    cw, ch = canvas
    stages = spec.get("stages") or []
    head, head_bottom = _header(spec, 26, cw, palette)
    content = [head]
    top = max(head_bottom + 34, 150)
    bottom = ch - 24
    cx, cy = cw * 0.58, top + (bottom - top) * 0.50
    rx = min(cw * 0.25, (bottom - top) * 0.44)
    ry = min((bottom - top) * 0.35, rx * 0.72)

    # extracellular matrix, faint and only outside the cell
    for i in range(8):
        yy = bottom - 26 - i * 13
        content.append(f'<path d="M {cw*0.83:.1f} {yy:.1f} Q {cw*0.90:.1f} {yy-10:.1f} '
                       f'{cw*0.96:.1f} {yy+2:.1f}" fill="none" stroke="#BFDCD5" '
                       f'stroke-width="1.4" opacity="0.7"/>')

    cell = (f"M {cx-rx:.1f} {cy:.1f} "
            f"C {cx-rx:.1f} {cy-ry*0.96:.1f}, {cx-rx*0.52:.1f} {cy-ry:.1f}, {cx:.1f} {cy-ry:.1f} "
            f"C {cx+rx*0.52:.1f} {cy-ry:.1f}, {cx+rx:.1f} {cy-ry*0.94:.1f}, {cx+rx:.1f} {cy:.1f} "
            f"C {cx+rx:.1f} {cy+ry*0.94:.1f}, {cx+rx*0.52:.1f} {cy+ry:.1f}, {cx:.1f} {cy+ry:.1f} "
            f"C {cx-rx*0.52:.1f} {cy+ry:.1f}, {cx-rx:.1f} {cy+ry*0.96:.1f}, {cx-rx:.1f} {cy:.1f} Z")
    content.append(f'<path d="{cell}" fill="#FAFDFE" stroke="#DCE7EB" stroke-width="10"/>')
    content.append(f'<path d="{cell}" fill="none" stroke="#7F98A8" stroke-width="2.2"/>')

    # organelles: ER, Golgi and mitochondria, all behind the pathway icons
    nuc_cx, nuc_cy = cx + rx * 0.46, cy + ry * 0.02
    nrx, nry = rx * 0.38, ry * 0.42
    for i in range(5):
        yy = nuc_cy - nry * 0.85 + i * 18
        content.append(f'<path d="M {nuc_cx-nrx*1.35:.1f} {yy:.1f} Q {nuc_cx-nrx*0.9:.1f} {yy-13:.1f} '
                       f'{nuc_cx-nrx*0.45:.1f} {yy+2:.1f}" fill="none" stroke="#B7C9D4" stroke-width="1.6" opacity="0.7"/>')
    for i in range(3):
        gx = nuc_cx - nrx * 1.45 + i * 7
        content.append(f'<path d="M {gx:.1f} {nuc_cy+nry*0.55:.1f} q 10 -9 20 0" fill="none" '
                       f'stroke="#AFC4CF" stroke-width="2" opacity="0.65"/>')
    for (mx, my) in ((cx-rx*0.72, cy+ry*0.28), (cx-rx*0.45, cy-ry*0.38), (cx+rx*0.52, cy+ry*0.62)):
        content.append(f'<ellipse cx="{mx:.1f}" cy="{my:.1f}" rx="24" ry="10" fill="#F2F8FA" '
                       f'stroke="#B7CBD5" stroke-width="1.3" transform="rotate(-18 {mx:.1f} {my:.1f})"/>')
        content.append(f'<path d="M {mx-14:.1f} {my:.1f} q 7 -7 14 0 q 7 7 14 0" fill="none" '
                       f'stroke="#C3D5DE" stroke-width="1.1"/>')

    content.append(f'<ellipse cx="{nuc_cx:.1f}" cy="{nuc_cy:.1f}" rx="{nrx:.1f}" ry="{nry:.1f}" '
                   f'fill="#FBF8FF" stroke="#DDD1F0" stroke-width="9"/>')
    content.append(f'<ellipse cx="{nuc_cx:.1f}" cy="{nuc_cy:.1f}" rx="{nrx:.1f}" ry="{nry:.1f}" '
                   f'fill="none" stroke="#8B5CF6" stroke-width="2.0" opacity="0.72"/>')
    content.append(f'<ellipse cx="{nuc_cx-nrx*0.22:.1f}" cy="{nuc_cy-nry*0.12:.1f}" rx="{nrx*0.30:.1f}" '
                   f'ry="{nry*0.28:.1f}" fill="#8B5CF6" opacity="0.09"/>')
    content.append(_text(nuc_cx, nuc_cy - nry - 14, "Nucleus", 11, "#79659C", "middle", "bold"))
    content.append(_text(cx - rx + 26, cy + ry * 0.66, "Cytoplasm", 11, "#7A8C9B", "start", "bold"))
    content.append(_text(64, top + 48, "Extracellular space", 11, "#7A8C9B", "start", "bold"))
    content.append(_text(cw - 18, bottom - 6, "Cartilage matrix", 11, "#4E8C7F", "end", "bold"))

    anchors = [
        (cx - rx - 112, cy - ry * 0.10),          # 1 vesicle, extracellular
        (cx - rx + 48, cy - ry * 0.62),           # 2 receptor, membrane
        (cx - rx * 0.44, cy + ry * 0.02),         # 3 kinase, cytoplasm
        (nuc_cx - nrx - 24, nuc_cy + nry * 0.02), # 4 nuclear pore
        (cx + rx + 48, cy + ry * 0.66),           # 5 matrix, outside
    ]
    icons = ["vesicle", "receptor", "kinase", "nucleus", "matrix"]
    labels = [
        (54, top + 78, "start", 238),
        (max(330, cx - rx + 22), top + 6, "start", 250),
        (max(340, cx - rx - 18), bottom - 92, "start", 224),
        (nuc_cx - nrx * 0.40, bottom - 92, "middle", 250),
        (cw - 128, bottom - 166, "middle", 236),
    ]
    for i, stage in enumerate(stages[:5]):
        color = safe_color(stage.get("color"), [palette["primary"], palette["secondary"],
                                                palette["accent"], "#8B5CF6", "#4E8C7F"][i])
        ax, ay = anchors[i]
        size = 118.0
        asset = assets.get(i)
        if asset and b"<image" in asset[0]:
            content.append(_asset_group(asset, ax - size * 0.52, ay - size * 0.52, size * 1.04, size * 1.04))
        else:
            content.append(_scene_icon(icons[i], ax, ay, size, color))
        content.append(f'<circle cx="{ax-size*0.40:.1f}" cy="{ay-size*0.40:.1f}" r="10.5" fill="{color}"/>')
        content.append(_text(ax - size * 0.40, ay - size * 0.40 + 4.8, str(i + 1), 10.5, "#FFFFFF", "middle", "bold"))
        tx, ty, anchor, width = labels[i]
        label = f"{i + 1}  {stage.get('label') or ''}"
        caption = (stage.get("caption") or "").split(". ")[0]
        content.append(_scene_label(tx, ty, label, caption, anchor, width, color, palette))

    a = anchors
    content.append(_curve_arrow(a[0][0] + 46, a[0][1] + 4, a[0][0] + 82, a[0][1] - 30,
                                a[1][0] - 80, a[1][1] + 34, a[1][0] - 50, a[1][1] + 2,
                                palette["primary"], 2.2))
    content.append(_curve_arrow(a[1][0] + 54, a[1][1] + 26, a[1][0] + 86, a[1][1] + 64,
                                a[2][0] - 76, a[2][1] - 54, a[2][0] - 54, a[2][1] - 16,
                                palette["secondary"], 2.2))
    content.append(_curve_arrow(a[2][0] + 54, a[2][1] + 6, a[2][0] + 90, a[2][1] + 30,
                                a[3][0] - 48, a[3][1] - 28, a[3][0] - 28, a[3][1] + 2,
                                "#8B5CF6", 2.2))
    content.append(_curve_arrow(nuc_cx + nrx * 0.82, nuc_cy + nry * 0.48,
                                nuc_cx + nrx * 1.12, nuc_cy + nry * 0.80,
                                a[4][0] - 66, a[4][1] - 50, a[4][0] - 44, a[4][1] - 10,
                                "#4E8C7F", 2.2))

    # No leader lines: the numbered callouts sit around the scene and the
    # painted structures are large enough to read without dashed pointers.
    return _canvas_wrap("".join(content), canvas, shape, "")


def _render_signal_horizontal(spec, assets, canvas, shape, palette):
    """Textbook scene for a linear pathway; cards are only a last resort."""
    if assets.get("scene") and not spec.get("_flowchart"):
        return _render_signal_scene(spec, assets, canvas, shape, palette)
    if len(spec.get("stages") or []) <= 5 and not spec.get("_flowchart"):
        return _render_signal_scene(spec, assets, canvas, shape, palette)
    import math as _m
    cw, ch = canvas
    stages = spec.get("stages") or []
    if len(stages) < 2:
        fallback = dict(spec)
        fallback["layout"] = "vertical"
        return _render_signal(fallback, assets, canvas, shape, palette)
    head, head_bottom = _header(spec, 28, cw, palette)
    content = [head]
    top = max(head_bottom + 44, 150)
    bottom = ch - 76
    regions = spec.get("regions") or []
    for region in regions:
        x1 = cw * max(0, region["start"]) / 100.0
        x2 = cw * min(100, region["end"]) / 100.0
        content.append(f'<rect x="{x1:.1f}" y="{top - 30:.1f}" width="{max(1, x2 - x1):.1f}" '
                       f'height="{bottom - top + 36:.1f}" fill="{palette["primary"]}" opacity="0.035"/>')
        content.append(f'<line x1="{x2:.1f}" y1="{top - 30:.1f}" x2="{x2:.1f}" '
                       f'y2="{bottom + 6:.1f}" stroke="#CBD5E1" stroke-width="1" '
                       f'stroke-dasharray="5 4"/>')
        content.append(_text((x1 + x2) / 2, top - 12, region["label"], 11,
                             "#64748B", "middle", "bold"))
    margin, gap = 58.0, 24.0
    n = len(stages)
    card_h = min(245.0, max(185.0, (bottom - top) * 0.40))
    slots = []
    coverage = sum(max(0, r["end"] - r["start"]) for r in regions)
    if regions and n and len(regions) >= 2 and coverage >= 60:
        # Follow the user's percentage bands: one stage per band by default,
        # extra stages extend the last (downstream) band.
        used = regions[:min(n, len(regions))]
        counts = [1] * len(used)
        for _ in range(n - len(used)):
            # Extra stages go where there is the most width per stage; ties
            # prefer the downstream band (nucleus/outcome often has two).
            target = max(range(len(used)),
                         key=lambda i: ((used[i]["end"] - used[i]["start"])
                                        / (counts[i] + 1), i))
            counts[target] += 1
        for region, count in zip(used, counts):
            x0 = cw * max(0, region["start"]) / 100.0 + 14
            x1 = cw * min(100, region["end"]) / 100.0 - 14
            usable = max(90.0, x1 - x0)
            inner_gap = 14.0
            slot_w = max(80.0, (usable - inner_gap * (count - 1)) / count)
            total = slot_w * count + inner_gap * (count - 1)
            start_x = x0 + (usable - total) / 2
            for k in range(count):
                slots.append((start_x + k * (slot_w + inner_gap), slot_w))
    if len(slots) != n:
        slot_w = max(150.0, (cw - 2 * margin - gap * (n - 1)) / n)
        slots = [(margin + index * (slot_w + gap), slot_w) for index in range(n)]
    mid = (top + bottom) / 2
    amp = min(70.0, max(0.0, (bottom - top - card_h) / 2 * 0.35))
    ys = []
    for index in range(n):
        if n == 1:
            offset = 0.0
        else:
            # Gentle left-to-right S: the row stays horizontal, with a small
            # vertical wave instead of jumping between distant rows.
            offset = amp * _m.sin(2 * _m.pi * index / (n - 1))
        ys.append(mid + offset - card_h / 2)
    for index, stage in enumerate(stages):
        x, card_w = slots[index]
        y = ys[index]
        color = safe_color(stage.get("color"), [palette["primary"], palette["secondary"],
                                                palette["accent"], palette["text"]][index % 4])
        content.append(_card(x, y, card_w, card_h, "#FFFFFF", color, 16, 1.5))
        content.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_w:.1f}" height="7" '
                       f'rx="3" fill="{color}"/>')
        content.append(f'<circle cx="{x + 22:.1f}" cy="{y + 27:.1f}" r="12" fill="{color}"/>')
        content.append(_text(x + 22, y + 32, str(index + 1), 12, "#FFFFFF", "middle", "bold"))
        asset_h = card_h * 0.40
        content.append(_asset_or_glyph(assets.get(index), stage.get("label", ""),
                                       x + 12, y + 14, card_w - 24, asset_h, color, stage))
        label_lines = _wrap(stage.get("label") or "", 15, card_w - 24, 2)
        label_y = y + asset_h + 40
        for line_index, line in enumerate(label_lines):
            content.append(_text(x + card_w / 2, label_y + line_index * 17,
                                 line, 15, palette["text"], "middle", "bold"))
        caption_lines = _wrap(stage.get("caption") or "", 11.5, card_w - 22, 2)
        caption_y = label_y + len(label_lines) * 17 + 10
        for line_index, line in enumerate(caption_lines):
            content.append(_text(x + card_w / 2, caption_y + line_index * 15,
                                 line, 11.5, "#475569", "middle"))
        if index < n - 1:
            x1 = x + card_w
            y1 = y + card_h * 0.5
            x2 = slots[index + 1][0]
            y2 = ys[index + 1] + card_h * 0.5
            link_gap = max(8.0, x2 - x1)
            content.append(_curve_arrow(
                x1, y1, x1 + link_gap * 0.45, y1,
                x2 - link_gap * 0.45, y2, x2, y2, color, 3.4))
    return _canvas_wrap("".join(content), canvas, shape, "")


def _compartment(stage: dict) -> str:
    text = (str(stage.get("label") or "") + " " + str(stage.get("caption") or "")).lower()
    if re.search(r"ligand|secretion|secreted|extracellular vesicle|ev|donor cell", text):
        return "extracellular"
    if re.search(r"membrane|receptor|binding|transmembrane", text):
        return "membrane"
    if re.search(r"nuclear|nucleus|transcription|gene|factor", text):
        return "nucleus"
    if re.search(r"kinase|cascade|cytoplasm|phosphoryl", text):
        return "cytoplasm"
    if re.search(r"matrix|phenotype|synthesis|deposition", text):
        return "matrix"
    return "extracellular"


def _render_signal_vertical(spec, assets, canvas, shape, palette):
    """Vertical mechanism figure: compartment bands, large icons, no empty strips."""
    cw, ch = canvas
    stages = spec["stages"][:6]
    head, head_bottom = _header(spec, 30, cw, palette)
    content = [head]
    top = max(head_bottom + 34, 136)
    bottom = ch - 54
    body_h = max(200.0, bottom - top)
    bands = [
        ("extracellular", "Extracellular space", 0.00, 0.20, "#F8FAFC"),
        ("membrane", "Plasma membrane", 0.20, 0.38, "#F1F5F9"),
        ("cytoplasm", "Cytoplasm", 0.38, 0.68, "#F8FAFC"),
        ("nucleus", "Nucleus", 0.68, 0.88, "#FAF7FD"),
        ("matrix", "Extracellular matrix", 0.88, 1.00, "#F8FAFC"),
    ]
    band_map = {key: (label, top + y0 * body_h, top + y1 * body_h)
                for key, label, y0, y1, _fill in bands}
    for key, label, y0, y1, fill in bands:
        y = top + y0 * body_h
        h = (y1 - y0) * body_h
        content.append(f'<rect x="40" y="{y:.1f}" width="{cw - 80:.1f}" height="{h:.1f}" '
                       f'fill="{fill}" stroke="#E2E8F0" stroke-width="0.8"/>')
        content.append(_text(58, y + 19, label, 12, "#94A3B8", "start", "bold"))
    # membrane bilayer
    membrane_y = top + 0.22 * body_h
    content.append(f'<line x1="40" y1="{membrane_y:.1f}" x2="{cw - 40:.1f}" '
                   f'y2="{membrane_y:.1f}" stroke="{palette["secondary"]}" '
                   f'stroke-width="2" stroke-dasharray="8 5"/>')
    # nucleus envelope behind the nuclear stage
    nucleus_y = top + (0.68 + 0.20) * body_h
    content.append(f'<ellipse cx="{cw * 0.33:.1f}" cy="{nucleus_y:.1f}" '
                   f'rx="{min(300, cw * 0.20):.1f}" ry="{min(120, body_h * 0.12):.1f}" '
                   f'fill="{palette["accent"]}" opacity="0.035" stroke="{palette["accent"]}" '
                   f'stroke-width="1.2" stroke-dasharray="7 5"/>')
    grouped = {}
    for index, stage in enumerate(stages):
        grouped.setdefault(_compartment(stage), []).append(index)
    positions = {}
    for key, indexes in grouped.items():
        label, y0, y1 = band_map.get(key, band_map["cytoplasm"])
        usable = max(80.0, (y1 - y0) - 34)
        for slot, index in enumerate(indexes):
            if len(indexes) == 1:
                positions[index] = (y0 + y1) / 2
            else:
                positions[index] = y0 + 17 + usable * (slot + 0.5) / len(indexes)
    icon_x = cw * 0.33
    text_x = icon_x + 150
    text_w = cw - text_x - 70
    for index, stage in enumerate(stages):
        yc = positions.get(index, (top + bottom) / 2)
        color = safe_color(stage.get("color"), [palette["primary"], palette["secondary"],
                                                palette["accent"], palette["text"]][index % 4])
        band_label, band_top, band_bottom = band_map.get(_compartment(stage),
                                                          band_map["cytoplasm"])
        band_h = max(70.0, band_bottom - band_top)
        size = min(132.0, max(72.0, min(body_h * 0.16, band_h * 0.72)))
        content.append(_asset_or_glyph(assets.get(index), stage.get("label", ""),
                                       icon_x - size / 2, yc - size / 2, size, size, color, stage))
        content.append(f'<circle cx="{icon_x - size / 2 + 15:.1f}" cy="{yc - size / 2 + 15:.1f}" '
                       f'r="12" fill="{color}"/>')
        content.append(_text(icon_x - size / 2 + 15, yc - size / 2 + 20, str(index + 1),
                             12, "#FFFFFF", "middle", "bold"))
        content.append(_text(text_x, yc - 8, stage.get("label", ""), 20, color,
                             "start", "bold"))
        lines = _wrap(stage.get("caption"), 13, text_w, 2)
        for li, line in enumerate(lines):
            content.append(_text(text_x, yc + 18 + li * 18, line, 13, "#475569"))
        if index < len(stages) - 1:
            next_y = positions.get(index + 1, yc + 120)
            content.append(_arrow(icon_x, yc + size / 2 + 4, icon_x,
                                  next_y - size / 2 - 6, color, 3.0))
    return _canvas_wrap("".join(content), canvas, shape, "")



def _signal_chip(x, y, w, label, caption, idx, color, palette):
    """One numbered pathway node with its evidence line, never a panel card."""
    lines = _wrap(str(label or ""), 15.2, w - 44, 2) or [""]
    cap_lines = _wrap(str(caption or ""), 10.6, w - 40, 2)
    h = 50 + len(lines) * 19 + (len(cap_lines) * 13.6 if cap_lines else 0)
    h = max(68, h)
    out = [f'<g data-bbox="{x:.1f},{y:.1f},{w:.1f},{h:.1f}">',
           f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="13" '
           f'fill="#FFFFFF" stroke="{color}" stroke-width="1.5"/>',
           f'<rect x="{x:.1f}" y="{y+8:.1f}" width="4" height="{h-16:.1f}" rx="2" fill="{color}"/>',
           f'<circle cx="{x+20:.1f}" cy="{y+19:.1f}" r="10" fill="{color}"/>',
           _text(x + 20, y + 22.8, str(idx), 10.8, "#FFFFFF", "middle", "bold")]
    ty = y + 17
    for i, line in enumerate(lines):
        out.append(_text(x + 40, ty + i * 18.0, line, 15.2,
                         palette["text"], "start", "bold"))
    cy = y + 20 + len(lines) * 17.2
    for i, line in enumerate(cap_lines):
        out.append(_text(x + 38, cy + i * 13.6, line, 10.6, "#4B5563", "start"))
    out.append('</g>')
    return "".join(out), h


def _cyto_texture(cw, ch, top, bottom):
    """A few faint fibres keep the empty cytoplasm from looking unfinished."""
    out = []
    for i, y in enumerate((top + 300, top + 360, top + 430, top + 500)):
        x0 = 40 + (i % 2) * 26
        x1 = cw * 0.34
        out.append(f'<path d="M{x0:.1f},{y:.1f} C{x0+80:.1f},{y-18:.1f} '
                   f'{x1-90:.1f},{y+22:.1f} {x1:.1f},{y+4:.1f}" fill="none" '
                   f'stroke="#D8E3DF" stroke-width="1.3" opacity="0.7"/>')
    return "".join(out)
def _bilayer(cw, y):
    out = [f'<rect x="0" y="{y-2:.1f}" width="{cw}" height="4" fill="#F7EADB" opacity="0.45"/>']
    x = 26
    while x < cw - 20:
        out.append(f'<circle cx="{x:.1f}" cy="{y-12:.1f}" r="5.0" fill="#F4DFC8" '
                   f'stroke="#D8B08C" stroke-width="1.1"/>')
        out.append(f'<line x1="{x:.1f}" y1="{y-7:.1f}" x2="{x:.1f}" y2="{y-2:.1f}" '
                   f'stroke="#D8B08C" stroke-width="1.1"/>')
        out.append(f'<circle cx="{x:.1f}" cy="{y+12:.1f}" r="5.0" fill="#F4DFC8" '
                   f'stroke="#D8B08C" stroke-width="1.1"/>')
        out.append(f'<line x1="{x:.1f}" y1="{y+7:.1f}" x2="{x:.1f}" y2="{y+2:.1f}" '
                   f'stroke="#D8B08C" stroke-width="1.1"/>')
        x += 22
    return "".join(out)


def _receptor(cx, cy, color):
    return "".join([
        f'<rect x="{cx-13:.1f}" y="{cy-36:.1f}" width="11" height="72" rx="5.5" '
        f'fill="#DCE9E4" stroke="{color}" stroke-width="1.5"/>',
        f'<rect x="{cx+2:.1f}" y="{cy-36:.1f}" width="11" height="72" rx="5.5" '
        f'fill="#DCE9E4" stroke="{color}" stroke-width="1.5"/>',
        f'<circle cx="{cx:.1f}" cy="{cy-48:.1f}" r="7.5" fill="#F2C9A8" stroke="#C98F63" stroke-width="1.3"/>',
        f'<circle cx="{cx-14:.1f}" cy="{cy-54:.1f}" r="5.0" fill="#E9B995" opacity="0.9"/>',
    ])


def _nucleus(cx, cy, rx, ry, color):
    out = [f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
           f'fill="#FCF8F3" stroke="#BFA98F" stroke-width="2.2"/>',
           f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx-9:.1f}" ry="{ry-9:.1f}" '
           f'fill="none" stroke="#D8C7B4" stroke-width="1.2"/>',
           f'<ellipse cx="{cx+rx*0.18:.1f}" cy="{cy-ry*0.12:.1f}" rx="{rx*0.32:.1f}" '
           f'ry="{ry*0.30:.1f}" fill="#E7DED3" opacity="0.75"/>']
    for dx, dy in ((-0.55, -0.62), (0.52, -0.58), (-0.62, 0.40), (0.62, 0.34), (0.05, 0.78)):
        out.append(f'<rect x="{cx+dx*rx-5:.1f}" y="{cy+dy*ry-4:.1f}" width="10" height="8" '
                   f'rx="3" fill="#F7F0E7" stroke="#BFA98F" stroke-width="1"/>')
    return "".join(out)



def _cell_body(cw, y0, bottom):
    """A single cell cross-section: extracellular space above, cytoplasm below."""
    return (f'<path d="M 18,{y0:.1f} Q 0,{y0+55:.1f} 22,{y0+125:.1f} '
            f'L 22,{bottom-42:.1f} Q 22,{bottom:.1f} 64,{bottom:.1f} '
            f'L {cw-64:.1f},{bottom:.1f} Q {cw-22:.1f},{bottom:.1f} {cw-22:.1f},{bottom-42:.1f} '
            f'L {cw-22:.1f},{y0+125:.1f} Q {cw:.1f},{y0+55:.1f} {cw-18:.1f},{y0:.1f} Z" '
            f'fill="#FCFAF6" stroke="#D8C7B4" stroke-width="1.4"/>')


def _organelles(cw, bottom, palette):
    """ER, Golgi and mitochondria give the cytoplasm a textbook texture."""
    out = []
    ex, ey = 92, bottom - 205
    for i in range(4):
        out.append(f'<path d="M{ex+i*8:.1f},{ey+i*26:.1f} C{ex+70:.1f},{ey+i*26-16:.1f} '
                   f'{ex+150:.1f},{ey+i*26+16:.1f} {ex+250+i*4:.1f},{ey+i*26:.1f}" '
                   f'fill="none" stroke="#CDB9A6" stroke-width="4" opacity="0.55"/>')
        out.append(f'<path d="M{ex+i*8:.1f},{ey+i*26:.1f} C{ex+70:.1f},{ey+i*26-16:.1f} '
                   f'{ex+150:.1f},{ey+i*26+16:.1f} {ex+250+i*4:.1f},{ey+i*26:.1f}" '
                   f'fill="none" stroke="#F4E9DD" stroke-width="2" opacity="0.9"/>')
    gx, gy = 410, bottom - 138
    for i in range(3):
        out.append(f'<path d="M{gx+i*10:.1f},{gy+i*20:.1f} q 40,-24 80,0" '
                   f'fill="none" stroke="#C9A57E" stroke-width="7" stroke-linecap="round" opacity="0.55"/>')
    for i, (mx, my) in enumerate(((560, bottom - 110), (650, bottom - 150), (730, bottom - 92))):
        out.append(f'<ellipse cx="{mx}" cy="{my}" rx="34" ry="14" fill="#F5E6D6" '
                   f'stroke="#C9A57E" stroke-width="1.2" transform="rotate({-18+i*10} {mx} {my})"/>')
        out.append(f'<path d="M{mx-22},{my} q 11,-8 22,0 q 11,8 22,0" fill="none" '
                   f'stroke="#B98C63" stroke-width="1.2"/>')
    out.append(_text(92, bottom - 218, "ER", 9.5, "#9A8068", "start", "bold"))
    out.append(_text(410, bottom - 152, "Golgi", 9.5, "#9A8068", "start", "bold"))
    return "".join(out)



def _kinase_glyph(x, y, color, label=""):
    out = [f'<g transform="translate({x:.1f},{y:.1f}) scale(1.35) translate({-x:.1f},{-y:.1f})">',
           f'<path d="M{x-30:.1f},{y:.1f} q 0,-24 26,-24 q 18,0 22,16 q 24,2 24,22 '
           f'q 0,22 -26,22 q -10,16 -28,10 q -18,-6 -18,-24 q -24,-2 -24,-22 z" '
           f'fill="#E8F0EE" stroke="{color}" stroke-width="1.8"/>',
           f'<circle cx="{x-2:.1f}" cy="{y-2:.1f}" r="10" fill="{color}" opacity="0.20"/>',
           f'<circle cx="{x+12:.1f}" cy="{y+8:.1f}" r="5" fill="{color}" opacity="0.45"/>',
           '</g>']
    if label:
        out.append(_text(x, y + 40, label, 9.0, color, "middle", "bold"))
    return "".join(out)


def _hex_glyph(x, y, color, label="", font=8.5):
    out = [f'<g transform="translate({x:.1f},{y:.1f}) scale(1.35) translate({-x:.1f},{-y:.1f})">',
           f'<path d="M{x:.1f},{y-18:.1f} l16,-9 16,9 0,18 -16,9 -16,-9 z" '
           f'fill="#F6E7D3" stroke="{color}" stroke-width="1.6"/>',
           '</g>']
    if label:
        out.append(_text(x, y + 3, label, font, "#7A5B3C", "middle", "bold"))
    return "".join(out)


def _cluster_glyph(x, y, color):
    return "".join(f'<circle cx="{x+dx:.1f}" cy="{y+dy:.1f}" r="{r}" fill="{color}" '
                   f'fill-opacity="0.25" stroke="{color}" stroke-width="1.4"/>'
                   for dx, dy, r in ((-12, -6, 9), (10, -2, 11), (-2, 14, 8)))


def _leader(x1, y1, x2, y2):
    return (f'<path d="M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}" fill="none" '
            f'stroke="#8FA3B0" stroke-width="1.1" stroke-dasharray="2 4"/>'
            f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="2.4" fill="#8FA3B0"/>')


def _atlas_label(x, y, label, caption, idx, color, anchor="start", width=300, palette=None):
    lines = _wrap(str(label or ""), 15.2, width - 28, 2) or [""]
    caps = _wrap(str(caption or ""), 10.7, width - 28, 3)
    out = [f'<circle cx="{x+10:.1f}" cy="{y-5:.1f}" r="10" fill="{color}"/>',
           _text(x + 10, y - 1.2, str(idx), 10.8, "#FFFFFF", "middle", "bold")]
    for i, line in enumerate(lines):
        out.append(_text(x + 28, y + i * 18, line, 15.2,
                         (palette or {}).get("text", "#1F2937"), anchor, "bold", halo=True))
    cy = y + len(lines) * 18 + 1
    for i, line in enumerate(caps):
        out.append(_text(x + 28, cy + i * 13.8, line, 10.7, "#4B5563", anchor, "normal", halo=True))
    return "".join(out)



def _cytosol_dots(cw, y0, bottom, nx, ny, nrx, nry):
    """Deterministic molecular crowding; no random state in the renderer."""
    out = []
    for row, gy in enumerate(range(int(y0 + 72), int(bottom - 36), 58)):
        for col, gx in enumerate(range(52 + (row % 2) * 26, int(cw - 48), 64)):
            if ((gx - nx) / max(nrx, 1)) ** 2 + ((gy - ny) / max(nry, 1)) ** 2 < 1.12:
                continue
            if 40 < gx < 930 and bottom - 240 < gy < bottom:
                continue
            r = 1.6 + ((row * 7 + col * 3) % 5) * 0.35
            out.append(f'<circle cx="{gx}" cy="{gy}" r="{r:.1f}" fill="#CBB7A2" opacity="0.22"/>')
    return "".join(out)


def _render_signal_atlas(spec, canvas, shape, palette):
    """Textbook glyph atlas: molecules and arrows, no boxes around the steps."""
    cw, ch = canvas
    stages = spec.get("stages") or []
    if not 4 <= len(stages) <= 6:
        return _render_signal_vertical(spec, {}, canvas, shape, palette)
    head, head_bottom = _header(spec, 30, cw, palette)
    top = max(head_bottom + 26, 108)
    bottom = ch - 30
    h = bottom - top
    y0 = top + h * 0.205
    colors = [str(s.get("color") or "#5E8F7C") for s in stages]
    while len(colors) < len(stages):
        colors.append("#5E8F7C")
    out = [head, _cell_body(cw, y0, bottom), _bilayer(cw, y0)]
    out.append(_organelles(cw, bottom, palette))
    nx, ny = cw * 0.815, y0 + h * 0.475
    nrx, nry = cw * 0.135, h * 0.175
    out.append(_nucleus(nx, ny, nrx, nry, colors[3] if len(colors) > 3 else "#5E8F7C"))
    out.append(_cytosol_dots(cw, y0, bottom, nx, ny, nrx, nry))
    rx = cw * 0.275
    out.append(_receptor(rx, y0, colors[1] if len(colors) > 1 else "#5E8F7C"))
    gx = [rx, cw * 0.380, cw * 0.505, cw * 0.655, cw * 0.735, cw * 0.765]
    gy = [y0 - 48, y0 + h * 0.155, y0 + h * 0.330, y0 + h * 0.500, bottom - h * 0.105, bottom - h * 0.015]
    # Stage glyphs: receptor already drawn; all others are molecule icons.
    glyphs = [(rx, y0 - 48)]
    for i in range(1, len(stages)):
        if i == 1:
            out.append(_kinase_glyph(gx[i], gy[i], colors[i]))
        elif i == 2 and "pip" in " ".join(str(x.get("label") or "") for x in stages).lower():
            out.append(_hex_glyph(gx[i] - 22, gy[i], "#C9A57E", "PIP2"))
            out.append(_hex_glyph(gx[i] + 20, gy[i] + 6, colors[i], "PIP3"))
            out.append(_kinase_glyph(gx[i] + 62, gy[i] + 26, colors[i]))
        elif "nucle" in str(stages[i].get("label") or "").lower():
            pass
        else:
            out.append(_kinase_glyph(gx[i], gy[i], colors[i], "P" if "phospho" in str(stages[i].get("label") or "").lower() else ""))
        glyphs.append((gx[i], gy[i]))
    # Keep the stage-3 PIP pair anchored to its stage glyph.
    label_xy = [(cw * 0.135, top + h * 0.015),
                (cw * 0.180, y0 + h * 0.155),
                (cw * 0.350, y0 + h * 0.430),
                (cw * 0.570, bottom - h * 0.220),
                (cw * 0.620, bottom - h * 0.150),
                (cw * 0.690, bottom - h * 0.045)]
    if len(stages) >= 5:
        label_xy[3] = (cw * 0.545, bottom - h * 0.340)
        label_xy[4] = (cw * 0.635, bottom - h * 0.060)
    for i, st in enumerate(stages):
        lx, ly = label_xy[i]
        out.append(_atlas_label(lx, ly, st.get("label") or "", st.get("caption") or "",
                                i + 1, colors[i], "start", 300, palette))
        # leader from the label area to the matching molecule
        ax, ay = glyphs[i] if i < len(glyphs) else (gx[i], gy[i])
        out.append(_leader(lx + 14, ly + 52, ax, ay))
    # Arrows follow molecules, not box edges.
    pts = [(rx, y0 - 48), (gx[1], gy[1])]
    out.append(_arrow(pts[0][0], pts[0][1] + 50, pts[1][0], pts[1][1] - 30, "#33475B", 2.0))
    out.append(_arrow(gx[1] + 24, gy[1], gx[2] - 34, gy[2] - 8, "#33475B", 2.0))
    out.append(_arrow(gx[2] + 26, gy[2] + 30, gx[3], gy[3] - 26, "#33475B", 2.0))
    out.append(_arrow(gx[3] + 26, gy[3], nx - nrx, ny - nry * 0.20, "#33475B", 2.2))
    if len(stages) > 4:
        out.append(_arrow(nx, ny + nry, gx[4], gy[4] - 24, "#33475B", 2.1))
    if "akt" in " ".join(str(s.get("label") or "") for s in stages).lower():
        out.append(f'<rect x="{nx-30:.1f}" y="{ny+12:.1f}" width="60" height="22" rx="10" '
                   f'fill="#E3EEF7" stroke="#6E9CC4" stroke-width="1.3"/>')
        out.append(_text(nx, ny + 26, "AKT-P", 9.2, "#315E86", "middle", "bold"))
    return _canvas_wrap("".join(out), canvas, shape, "")


def _render_signal_map(spec, canvas, shape, palette):
    """A deterministic textbook pathway map: membrane, nucleus, numbered nodes.

    The painted scene path is deliberately not used here. Qwen-Image renders
    convincing cells but also bakes garbled/clipped labels into the raster;
    this renderer keeps every word editable and every arrow attached.
    """
    cw, ch = canvas
    stages = spec.get("stages") or []
    if not 4 <= len(stages) <= 6:
        return _render_signal_vertical(spec, {}, canvas, shape, palette)
    head, head_bottom = _header(spec, 30, cw, palette)
    top = max(head_bottom + 30, 112)
    bottom = ch - 38
    h = bottom - top
    y0 = top + h * 0.20
    colors = [str(s.get("color") or "#5E8F7C") for s in stages]
    while len(colors) < len(stages):
        colors.append("#5E8F7C")
    out = [head, _cell_body(cw, y0, bottom), _bilayer(cw, y0)]
    out.append(_organelles(cw, bottom, palette))
    rx = cw * 0.275
    out.append(_receptor(rx, y0, colors[1] if len(colors) > 1 else "#5E8F7C"))
    nx, ny = cw * 0.825, y0 + h * 0.47
    nrx, nry = cw * 0.135, h * 0.18
    out.append(_nucleus(nx, ny, nrx, nry, colors[3] if len(colors) > 3 else "#5E8F7C"))

    w = min(292.0, cw * 0.24)
    positions = [(cw * 0.030, top + h * 0.010),
                 (cw * 0.120, y0 + h * 0.080),
                 (cw * 0.310, y0 + h * 0.235),
                 (cw * 0.500, y0 + h * 0.395),
                 (cw * 0.660, bottom - h * 0.105),
                 (cw * 0.760, bottom - h * 0.010)]
    boxes = []
    for i, st in enumerate(stages):
        x, y = positions[i]
        y = min(y, bottom - 76)
        frag, bh = _signal_chip(x, y, w, st.get("label") or "",
                                "", i + 1, colors[i], palette)
        out.append(frag)
        boxes.append((x, y, w, bh))
    # Arrows follow the biological reading order; each starts and ends on a
    # node edge rather than floating in whitespace.
    for i in range(len(boxes) - 1):
        ax, ay, aw, ah = boxes[i]
        bx, by, bw, bh = boxes[i + 1]
        if i == 0:
            x1, y1 = ax + aw * 0.55, ay + ah
            x2, y2 = rx, y0 - 56
        elif i == 1:
            x1, y1 = rx + 12, y0 + 34
            x2, y2 = bx, by + bh * 0.45
        elif i == 2:
            x1, y1 = ax + aw, ay + ah * 0.45
            x2, y2 = bx, by + bh * 0.45
        elif i == 3:
            x1, y1 = ax + aw, ay + ah * 0.45
            x2, y2 = nx - nrx, ny - nry * 0.15
        else:
            x1, y1 = nx, ny + nry
            x2, y2 = bx + bw * 0.5, by
        out.append(_arrow(x1, y1, x2, y2, "#33475B", 2.0))
    # The last node must land on the nucleus, not hang in space.
    if boxes:
        lx, ly, lw, lh = boxes[-1]
        out.append(_arrow(lx + lw, ly + lh * 0.45, nx - nrx, ny - nry * 0.10,
                          "#33475B", 2.2))
    # Molecular marks on the two middle steps, when the labels name them.
    joined = " ".join(str(s.get("label") or "") for s in stages).lower()
    if "pip" in joined:
        qx, qy = boxes[2][0] + w + 18, boxes[2][1] + 8
        for j, lab in enumerate(("PIP2", "PIP3")):
            out.append(f'<path d="M{qx:.1f},{qy+j*30:.1f} l11,-6 11,6 0,12 -11,6 -11,-6 z" '
                       f'fill="#F6E7D3" stroke="#C9A57E" stroke-width="1.2"/>')
            out.append(_text(qx + 11, qy + j * 30 + 13, lab, 8.5, "#7A5B3C", "middle", "bold"))
    if "akt" in joined:
        ax, ay = nx - 34, ny + 18
        out.append(f'<rect x="{ax-26:.1f}" y="{ay-10:.1f}" width="52" height="22" rx="10" '
                   f'fill="#E3EEF7" stroke="#6E9CC4" stroke-width="1.3"/>')
        out.append(_text(ax, ay + 4, "AKT-P", 9.0, "#315E86", "middle", "bold"))
    return _canvas_wrap("".join(out), canvas, shape, "")


def _render_signal(spec, assets, canvas, shape, palette):
    # Deterministic pathway map first: a qwen-painted cell may look good, but
    # it bakes clipped/garbled labels into the raster. Only an explicitly
    # requested flowchart goes to the card/grid renderers.
    stages = spec.get("stages") or []
    if assets.get("scene") and not spec.get("_flowchart"):
        return _render_signal_plate(spec, assets["scene"], canvas, shape, palette)
    if not spec.get("_flowchart") and 4 <= len(stages) <= 6:
        return _render_signal_atlas(spec, canvas, shape, palette)
    if spec.get("layout") == "horizontal_s":
        return _render_signal_horizontal(spec, assets, canvas, shape, palette)
    return _render_signal_vertical(spec, assets, canvas, shape, palette)


def _render_pipeline(spec, assets, canvas, shape, palette):
    if assets.get("scene"):
        return _render_signal_plate(spec, assets["scene"], canvas, shape, palette)
    """Process figures are textbook strips unless a flow chart was requested.

    The old card grid is retained only when layout_contract marked the request
    as an explicit flow chart / boxed diagram. A plain "process" prompt now
    gets one continuous visual sequence: numbered objects connected by arrows,
    with the labels and captions set below the objects, not inside boxes.
    """
    if not spec.get("_flowchart"):
        return _render_pipeline_strip(spec, assets, canvas, shape, palette)
    return _render_pipeline_cards(spec, assets, canvas, shape, palette)


def _render_pipeline_strip(spec, assets, canvas, shape, palette):
    cw, ch = canvas
    stages = spec["stages"][:6]
    head, head_bottom = _header(spec, 30, cw, palette)
    content = [head]
    if not stages:
        return _canvas_wrap("".join(content), canvas, shape, "")
    margin = 48.0
    gap = 26.0
    step = (cw - 2 * margin - gap * (len(stages) - 1)) / len(stages)
    icon_w = min(step * 0.96, 360.0)
    top = max(132.0, head_bottom + 30.0)
    avail = ch - top - 40.0
    icon_h = min(avail * 0.82, icon_w * 1.35)
    # Centre the whole object + label block vertically instead of leaving a
    # large empty band under the captions.
    icon_top = top + max(12.0, (avail - (icon_h + 112.0)) / 2.0)
    baseline = icon_top + icon_h
    colors = [palette["primary"], palette["secondary"], palette["accent"],
              "#7C6AA6", "#4E8C7F", "#B07A45"]
    for index, stage in enumerate(stages):
        cx = margin + step * (index + 0.5) + gap * index
        color = safe_color(stage.get("color"), colors[index % len(colors)])
        x = cx - icon_w / 2.0
        content.append(_asset_or_glyph(assets.get(index), stage["label"],
                                       x, icon_top, icon_w, icon_h, color, stage))
        # Number sits on the object, like a callout in a textbook plate.
        content.append(f'<circle cx="{cx - icon_w * 0.30:.1f}" cy="{icon_top + 8:.1f}" '
                       f'r="13" fill="{color}"/>')
        content.append(_text(cx - icon_w * 0.30, icon_top + 12.5,
                             str(index + 1), 11, "#FFFFFF", "middle", "bold"))
        label_lines = _wrap(stage.get("label") or "", 14.2, step - 12, 2)
        label_y = baseline + 28
        for line_no, line in enumerate(label_lines):
            content.append(_text(cx, label_y + line_no * 17,
                                 line, 14.2, palette["text"], "middle", "bold"))
        caption_lines = _wrap((stage.get("caption") or "").split(". ")[0],
                              10.8, step - 10, 3)
        caption_y = label_y + len(label_lines) * 17 + 3
        for line_no, line in enumerate(caption_lines):
            content.append(_text(cx, caption_y + line_no * 13,
                                 line, 10.8, "#526579", "middle"))
        if index < len(stages) - 1:
            ax1 = cx + icon_w / 2.0 + 5
            ax2 = cx + step + gap - icon_w / 2.0 - 5
            content.append(_arrow(ax1, icon_top + icon_h * 0.52,
                                  ax2, icon_top + icon_h * 0.52,
                                  color, 2.4))
    return _canvas_wrap("".join(content), canvas, shape, "")


def _render_pipeline_cards(spec, assets, canvas, shape, palette):
    cw, ch = canvas
    stages = spec["stages"][:6]
    head, head_bottom = _header(spec, 30, cw, palette)
    content = [head]
    top = max(130, head_bottom + 30)
    gap = 42
    card_w = (cw - 120 - gap * (len(stages) - 1)) / max(1, len(stages))
    vector = not assets
    card_h = min(ch - top - 70, card_w * (0.78 if vector else 1.35))
    spare = ch - top - card_h
    if spare > 60:
        top += min(150.0, max(0.0, (spare - 40.0) * 0.35))
    for index, stage in enumerate(stages):
        x = 60 + index * (card_w + gap)
        y = top
        color = stage.get("color") or [palette["primary"], palette["secondary"],
                                       palette["accent"], "#0D9488"][index % 4]
        color = safe_color(color, palette["primary"])
        content.append(_card(x, y, card_w, card_h, "#FFFFFF", "#E2E8F0", 14, 1.4))
        content.append(f'<rect x="{x}" y="{y}" width="{card_w:.1f}" height="7" rx="3" fill="{color}"/>')
        content.append(f'<circle cx="{x + 24:.1f}" cy="{y + 30:.1f}" r="14" fill="{color}"/>')
        content.append(_text(x + 24, y + 36, str(index + 1), 14, "#FFFFFF", "middle", "bold"))
        asset_h = card_h * (0.42 if vector else 0.48)
        content.append(_asset_or_glyph(assets.get(index), stage["label"], x + 16, y + 52,
                                       card_w - 32, asset_h, color, stage))
        label_y = y + (card_h * 0.66 if vector else card_h * 0.48 + 86)
        content.append(_text(x + 16, label_y, stage["label"], 16, palette["text"],
                             "start", "bold"))
        lines = _wrap(stage.get("caption"), 12, card_w - 32, 3)
        for li, line in enumerate(lines):
            content.append(_text(x + 16, label_y + 22 + li * 16, line, 12, "#475569"))
        if index < len(stages) - 1:
            ax1 = x + card_w + 6
            ax2 = x + card_w + gap - 6
            content.append(_arrow(ax1, y + card_h / 2, ax2, y + card_h / 2, color, 3.0,
                                  label=""))
    return _canvas_wrap("".join(content), canvas, shape, "")


def _render_anatomy(spec, assets, canvas, shape, palette):
    if assets.get("scene"):
        return _render_signal_plate(spec, assets["scene"], canvas, shape, palette)
    if assets:
        # Domain / subunit panels read as one horizontal structural series.
        # The old stack ignored the generated objects entirely and drew empty
        # trapezoid slabs.
        return _render_pipeline_strip(spec, assets, canvas, shape, palette)
    cw, ch = canvas
    stages = spec["stages"][:6]
    head, head_bottom = _header(spec, 30, cw, palette)
    content = [head]
    top = max(140, head_bottom + 34)
    slab_w = min(cw * 0.56, 780)
    slab_x = (cw - slab_w) / 2
    slab_h = min(88, (ch - top - 50) / max(1, len(stages)) - 10)
    for index, stage in enumerate(stages):
        y = top + index * (slab_h + 10)
        color = stage.get("color") or [palette["primary"], palette["secondary"],
                                       palette["accent"], "#0D9488"][index % 4]
        color = safe_color(color, palette["primary"])
        skew = 34
        points = (f'{slab_x},{y} {slab_x+slab_w},{y} '
                  f'{slab_x+slab_w-skew},{y+slab_h} {slab_x-skew},{y+slab_h}')
        content.append(f'<polygon points="{points}" fill="#FFFFFF" stroke="{color}" stroke-width="1.8"/>')
        content.append(f'<polygon points="{points}" fill="{color}" opacity="0.07"/>')
        content.append(_text(slab_x - skew - 18, y + slab_h / 2 + 4,
                             stage["label"], 15, color, "end", "bold"))
        content.append(_text(slab_x + 24, y + slab_h / 2 + 4,
                             stage.get("caption", ""), 12, "#475569"))
        content.append(_text(slab_x + slab_w - 24, y + slab_h - 12,
                             f"L{index + 1}", 11, color, "end", "bold"))
    # callout column
    call_x = slab_x + slab_w + 60
    call_y = top + 6
    content.append(_card(call_x, call_y, cw - call_x - 50, min(160, ch - call_y - 50),
                         "#FFFFFF", palette["accent"], 12, 1.2))
    content.append(_text(call_x + 16, call_y + 26, "Layer function", 13, palette["accent"], "start", "bold"))
    for i, stage in enumerate(stages):
        content.append(_text(call_x + 16, call_y + 50 + i * 24,
                             f"{i+1}. {stage['label']}", 11, "#475569"))
    return _canvas_wrap("".join(content), canvas, shape, "")


def _render_abstract(spec, assets, canvas, shape, palette):
    if assets.get("scene"):
        return _render_signal_plate(spec, assets["scene"], canvas, shape, palette)
    cw, ch = canvas
    stages = spec["stages"][:3]
    head, head_bottom = _header(spec, 30, cw, palette)
    content = [head]
    top = max(140, head_bottom + 30)
    gap = 34
    card_w = (cw - 120 - gap * (len(stages) - 1)) / max(1, len(stages))
    card_h = ch - top - 100
    for index, stage in enumerate(stages):
        x = 60 + index * (card_w + gap)
        y = top
        color = stage.get("color") or [palette["primary"], palette["secondary"], palette["accent"]][index % 3]
        color = safe_color(color, palette["primary"])
        content.append(_card(x, y, card_w, card_h, "#FFFFFF", "#E2E8F0", 16, 1.4))
        content.append(f'<rect x="{x}" y="{y}" width="{card_w:.1f}" height="34" rx="8" fill="{color}"/>')
        content.append(_text(x + 16, y + 23, stage["label"].upper(), 13, "#FFFFFF", "start", "bold"))
        content.append(_asset_or_glyph(assets.get(index), stage["label"], x + 16, y + 48,
                                       card_w - 32, card_h * 0.56, color, stage))
        lines = _wrap(stage.get("caption"), 13, card_w - 36, 4)
        for li, line in enumerate(lines):
            content.append(_text(x + 18, y + card_h * 0.56 + 86 + li * 18, line, 13, "#475569"))
        if index < len(stages) - 1:
            content.append(_arrow(x + card_w + 5, y + card_h / 2,
                                  x + card_w + gap - 5, y + card_h / 2, color, 3.2))
    return _canvas_wrap("".join(content), canvas, shape, "")


RENDERERS = {
    "signal_pathway": _render_signal,
    "process_pipeline": _render_pipeline,
    "structural_anatomy": _render_anatomy,
    "graphical_abstract": _render_abstract,
}


def _contract_stages(existing: list[dict], names: list[str]) -> list[dict]:
    """Keep the author's full stage chain without duplicating bilingual labels.

    A Chinese brief often asks for English labels, so the planner returns
    English panels for Chinese stage names. Prefer the planner's panels when
    they cover the chain, otherwise fill the gaps with contract names.
    """
    def chinese(value: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))

    pool = list(existing)
    if names and all(chinese(n) for n in names):
        same_language = [s for s in pool if chinese(s.get("label"))]
        # Mixed-language output means the model half-translated; keep the
        # language of the author's chain so panels are not duplicated.
        if same_language:
            pool = same_language
    if len(pool) >= len(names) and names:
        return pool[:6]
    ordered, used = [], set()
    for name in names:
        low = str(name).lower()
        tokens = {w for w in re.findall(r"[a-z0-9]+", low) if len(w) > 2}
        match = None
        for index, stage in enumerate(pool):
            if index in used:
                continue
            label = str(stage.get("label") or "").lower()
            if low == label or low in label or label in low:
                match = index
                break
            other = {w for w in re.findall(r"[a-z0-9]+", label) if len(w) > 2}
            if tokens and other and len(tokens & other) / len(tokens | other) >= 0.5:
                match = index
                break
        if match is None:
            ordered.append({"label": name, "caption": "",
                            "prompt": f"one isolated flat 2D vector icon of {name}, "
                                      "pure white background, no text, no labels",
                            "color": ""})
        else:
            ordered.append(pool[match])
            used.add(match)
    return ordered[:6]


def _prepare_scene_png(png: bytes) -> bytes:
    """Crop the square model output to 3:2, whiten the paper background, lift colour."""
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageEnhance
    im = Image.open(BytesIO(png)).convert("RGB")
    w, h = im.size
    target = 1.43
    if w / h > target:
        nw = int(h * target)
        im = im.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
    elif w / h < target:
        nh = int(w / target)
        im = im.crop((0, (h - nh) // 2, w, (h + nh) // 2))
    import numpy as np
    # Paper-cream background is bright and nearly neutral; cell cytoplasm is
    # warmer/more saturated. Whiten only the neutral paper, not the tissue.
    arr = np.asarray(im).astype(np.int16)
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1)
    # Whiten only paper that is connected to the image border. The previous
    # global threshold also erased pale nuclei and other interior structures,
    # leaving a hard white wedge in the nucleus.
    paper = ((mx > 230) & (sat < 0.12)).astype(np.uint8)
    try:
        import cv2
        _, labels = cv2.connectedComponents(paper, connectivity=4)
        border = (set(labels[0, :].tolist()) | set(labels[-1, :].tolist())
                  | set(labels[:, 0].tolist()) | set(labels[:, -1].tolist()))
        border.discard(0)
        paper_mask = np.isin(labels, list(border)) if border else np.zeros_like(paper, dtype=bool)
    except Exception:
        paper_mask = np.zeros_like(paper, dtype=bool)
        paper_mask[:3, :] = paper_mask[-3:, :] = True
        paper_mask[:, :3] = paper_mask[:, -3:] = True
        paper_mask &= paper.astype(bool)
    arr[paper_mask] = 255
    im = Image.fromarray(arr.astype(np.uint8))
    im = ImageEnhance.Color(im).enhance(1.15)
    im = ImageEnhance.Contrast(im).enhance(1.05)
    out = BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _scene_template_path(text: str, spec: dict, style=None) -> Path:
    """Reuse the bundled cartilage plate only for its own topic.

    A cached painting carries specific anatomy (vesicles, collagen fibres); showing
    it under an unrelated pathway would be scientifically wrong. Other topics get
    their own cached plate keyed by title + brief.
    """
    blob = ("scene-v2 " + str(spec.get("_plate_mode") or "") + " " + str(text) + " "
            + str(spec.get("title") or "")).lower()
    if isinstance(style, dict):
        # A reference image with a different layout must not reuse another plate.
        layout = style.get("layout_analysis") or {}
        blob += " " + json.dumps(layout, ensure_ascii=False, sort_keys=True).lower()
    keep = ("cartilage", "chondrocyte", "extracellular vesicle", "exosome", "ev-mediated")
    if spec.get("_plate_mode") == "signal_pathway" and any(word in blob for word in keep):
        name = "signal_scene_template.png"
    elif spec.get("_plate_mode") == "signal_pathway":
        # One clean, text-free Qwen painting is a better default than a new
        # prompt per pathway: the image model otherwise starts drawing its own
        # numbered panels and garbled labels. Anatomy stays generic; the
        # deterministic overlay supplies the pathway-specific callouts.
        name = "signal_scene_generic.png"
    else:
        digest = hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]
        name = f"signal_scene_{digest}.png"
    return Path(__file__).resolve().parent / "assets" / name


def render_archetype(text: str, config: dict, archetype: str, on_stage=None) -> tuple[bytes, dict]:
    def stage(name, detail=None):
        if on_stage:
            on_stage(name, detail)

    report = {"archetype": archetype, "stages": {}}
    stage("plan_scene", f"planning {archetype}")
    spec = plan_archetype(text, config, archetype)
    contract = config.get("layout_contract") or {}
    if contract.get("figure_style"):
        # The contract is deterministic; never let a planner that echoed
        # "top-to-bottom" turn a mechanism into a card grid.
        spec["_flowchart"] = (contract["figure_style"] == "flowchart")
    if contract.get("layout"):
        # The author's spatial instruction beats the rewritten prompt.
        spec["layout"] = contract["layout"]
    if contract.get("stages"):
        spec["stages"] = _contract_stages(spec["stages"], contract["stages"])
    if not spec["stages"]:
        raise RuntimeError("模型没有返回有效的阶段结构")

    palette = _palette(config, archetype)
    suffix = (config.get("style_dna") or {}).get("entity_style_prompt_suffix") or ""
    assets = {}
    engines = {}
    total = len(spec["stages"])
    use_images = config.get("illustration_mode") != "vector"
    spec["_flowchart"] = str(contract.get("figure_style") or "") == "flowchart"
    # Every mechanism / process / anatomy figure is a continuous textbook
    # plate unless the author explicitly asked for a boxed flow chart. Card
    # grids are no longer a silent fallback for any archetype.
    # Only signal pathways use one painted plate. Process / anatomy figures
    # keep per-stage objects: a single generated image tends to draw its own
    # numbered sub-panels, which then fight the labels we overlay.
    scene_mode = bool(use_images and archetype == "signal_pathway"
                      and not spec["_flowchart"])
    if scene_mode:
        # One painted plate is always a landscape composition. Card stacks are
        # forbidden for mechanism figures, even when the prompt says vertical.
        spec["layout"] = "horizontal_s"
        spec["_plate_mode"] = archetype
    if scene_mode:
        # One continuous textbook plate reads better than five isolated icons.
        # The painted cell is cached: regenerating it per job makes label anchors
        # drift and the visual style inconsistent between figures.
        template = _scene_template_path(text, spec, config.get("style_dna"))
        if template.exists():
            stage("generate_scene", "教材底图模板（本地缓存）")
            png = _prepare_scene_png(template.read_bytes())
            engines["scene-template"] = 1
        else:
            stage("generate_scene", f"整幅机制底图：{total} 个阶段")
            labels = " → ".join(str(s.get("label") or "") for s in spec["stages"])
            mode = archetype
            if mode == "signal_pathway":
                subject = ("单细胞信号通路机制图：细胞膜、胞质、细胞核与细胞外空间在同一幅连续场景中，"
                           "配体→受体→胞内级联→核内效应按空间顺序组织")
            elif mode == "process_pipeline":
                subject = ("单幅连续的科学过程图：把用户给出的各个阶段画在同一场景中，"
                           "用空间位置或短箭头表现时间顺序，不要分栏、不要卡片")
            elif mode == "structural_anatomy":
                subject = ("单幅连续的结构解剖图：按用户对象画组织/细胞/结构域的空间层次，"
                           "外层到内层自然过渡，不要堆叠矩形板、不要器件示意图")
            else:
                subject = ("单幅连续的论文图形摘要：问题、策略与结果在同一场景中形成视觉叙事，"
                           "不要三栏卡片")
            scene_prompt = (
                f"科研教材风格的{subject}，横向构图，纯白背景。"
                "参考 BioRender 或生物教材的扁平矢量插画：低饱和粉彩实色填充，"
                "细而均匀的深青色描边，简洁几何形状，线条干净，分区明确；"
                "不要水彩晕染、不要纸纹、不要颗粒、不要渐变、不要阴影、不要3D、不要写实渲染。"
                f"主题：{spec.get('title') or ''}。图注由后期添加，画面不要出现任何阶段文字或编号。"
                + (("按该主题组织真实空间关系：画面左侧是细胞外空间和配体/囊泡来源，"
                    "细胞膜在左缘进入画面，膜上画一个受体复合物（只画一个，不要重复画多个受体），"
                    "配体与受体在同一位置结合；胞质内画内质网、高尔基体、"
                    "线粒体和该通路涉及的激酶/效应蛋白，用短箭头串成级联；"
                    "中右部画一个大的细胞核，核膜有核孔，核内有核仁和淡染色质；"
                    "右下角画该主题对应的效应结构（如细胞外基质纤维束、分泌产物或靶细胞）。"
                    "细胞主体占画面中部偏左，右侧留出干净白位放标签。")
                   if mode == "signal_pathway" else
                   ("主体占画面中部约 70%，四周留出干净白位放编号标签；"
                    "只画用户主题中真实存在的对象，不添加无关细胞器或器件。"))
                + ("不要任何文字、字母、数字、标签、图例、边框、卡片、分栏；"
                   "单幅连续场景，不是信息图；像生物教材的机制插画，而不是信息图模板。")
            )
            ref = config.get("reference_layout") or {}
            if isinstance(ref, dict) and ref:
                scene_prompt += (chr(10) + "参考图排版特征（只学构图，不要复制参考图文字）："
                                 + str(ref.get("composition") or "")
                                 + "；阅读顺序 " + str(ref.get("reading_order") or "")
                                 + "；标签位置 " + str(ref.get("label_position") or ""))
            if suffix:
                scene_prompt += chr(10) + str(suffix)
            scene_cfg = dict(config)
            image_cfg = dict(config.get("image") or {})
            if str(image_cfg.get("size") or "") in ("", "1024x1024"):
                image_cfg["size"] = "1536x1024"
            scene_cfg["image"] = image_cfg
            png = _prepare_scene_png(pipeline.generate_raw(scene_prompt, scene_cfg))
            template.parent.mkdir(parents=True, exist_ok=True)
            template.write_bytes(png)
            engines["scene-image"] = 1
        report["scene_template"] = str(template)
        svg_scene, aw, ah = compose.asset_image(compose.cutout(png))
        assets["scene"] = (svg_scene, aw, ah)
    else:
        for index, stage_spec in enumerate(spec["stages"]):
            if not use_images:
                # Vector mode: draw a glyph per stage so every panel has an icon.
                import framework as _fw
                glyph = _fw.entity_glyph(
                    stage_spec, 50, 50, 78, palette.get("primary", "#3F5A6B"))
                assets[index] = (('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                                  + glyph + '</svg>').encode("utf-8"), 100.0, 100.0)
                engines["vector-glyph"] = engines.get("vector-glyph", 0) + 1
                continue
            stage("generate", f"实体 {index+1}/{total}：{stage_spec['label']}")
            prompt = stage_spec["prompt"] or f"isolated scientific illustration of {stage_spec['label']}"
            prompt += ("\nIsolated single object, pure white background, no text, no labels, "
                       "no arrows, centered, publication-quality scientific illustration; "
                       "follow the requested visual style.")
            if suffix:
                prompt += chr(10) + str(suffix)
            try:
                png = pipeline.generate_raw(prompt, config)
            except Exception:
                # One retry with a short, cheap prompt: long prompts are the usual
                # reason the image backend stalls past its timeout.
                short = (f"Flat 2D scientific vector icon of {stage_spec['label']}, "
                         "isolated, pure white background, no text, no labels, centered.")
                png = pipeline.generate_raw(short, config)
            cut = compose.cutout(png)
            svg, aw, ah = compose.asset_image(cut)
            assets[index] = (svg, aw, ah)
            engines["image"] = engines.get("image", 0) + 1

    canvas = config.get("canvas") if config.get("canvas_user") else [1536, 1024]
    shape = config.get("viewport_shape") or "rect"
    renderer = RENDERERS[archetype]

    def review_svg(data):
        try:
            import review
            return review.findings(data, None)
        except Exception:
            return []

    import model_review
    def context_fn(current_spec, kind):
        stage_labels = [str(s.get("label") or "") for s in current_spec.get("stages") or []]
        return {
            "kind": archetype,
            "title": current_spec.get("title"),
            "canvas": canvas,
            "layout": current_spec.get("layout"),
            "regions": current_spec.get("regions") or [],
            "stages": stage_labels,
            "scene_plate": bool(assets.get("scene")),
            "ocr_texts": [str(i + 1) for i in range(len(stage_labels))] + stage_labels,
        }
    final_svg, rework = model_review.run_loop(
        spec, lambda: renderer(spec, assets, canvas, shape, palette),
        _shrink_spec, review_svg, context_fn,
        config, archetype, on_stage=stage, max_rounds=10)
    report["rework"] = rework
    pipeline._check_svg(final_svg, allow_image=bool(assets))
    report["stages"]["generate"] = {"entities": total if scene_mode else len(assets),
                                       "engines": engines,
                                       "mode": "scene" if scene_mode else "per-entity"}
    report["stages"]["assemble"] = {"bytes": len(final_svg)}
    report["spec"] = spec
    report["bytes"] = len(final_svg)
    return final_svg, report


def _shrink_spec(spec: dict) -> None:
    """No blind truncation; the model repair patch edits only what it must."""
    return None
