"""Concentric-ring architecture summary renderer.

A true circular architecture figure for mechanical / engineering papers:
a core object in the middle, surrounded by three labelled rings
(functional subsystems -> enabling technologies -> performance outcomes),
with tangential labels, radial guide rings and fully editable vector text.

No image model is used: the figure is pure SVG, so every label and wedge
stays editable in PowerPoint / Illustrator.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import archetypes
import compose
import framework
import pipeline
from colorsafe import safe_color

RING_INSTRUCTION = """你是顶刊（Nature / Science / Cell / ASME / IEEE）科研论文的架构图设计师。
请把用户的研究主题总结成一张“同心圆环架构图”（concentric ring architecture）。先判断用户领域：生物医学、材料、工程或社会科学，全部术语必须来自该领域。

只输出一个 JSON 对象，不要 markdown、不要解释，结构严格如下：
{
  "title": "英文主标题，<= 58 字符",
  "subtitle": "英文副标题，<= 96 字符",
  "core": {"label": "核心对象英文名，<= 20 字符", "caption": "一句话核心定义，<= 28 字符",
           "illustration": "给插画师看的英文物体描述，<= 90 字符：具体是什么设备/结构、什么视角"},
  "rings": [
    {"name": "环名（按内容自拟）", "segments": [
      {"label": "<= 26 chars", "caption": "<= 44 chars",
       "illustration": "英文物体描述，<= 80 字符，写清画什么零件"}
    ]}
  ],
  "label_mode": "arc | radial | horizontal（按参考图的标签习惯选择）",
  "style": "filled | outline（按参考图的环带处理选择）",
  "footnote": "英文图注，<= 110 字符"
}

硬性要求：
1. 环数和每环段数由内容决定，不固定：2–4 个环，每环 3–12 段；不要为了凑数硬拆或硬并。
2. 环的含义按内容自拟，但要形成清晰的层级（如 功能层 / 技术层 / 指标层，或 输入 / 处理 / 输出）。
3. 只使用用户领域的标准英文术语：生物医学用细胞/分子/组织术语，工程才用机械/材料术语；不得把生物主题写成齿轮、轴承、摩擦学。
4. label 用完整标准术语（<= 26 字符），caption <= 44 字符；两者都要写成完整短语，禁止用省略号（…）结尾。caption 必须补充 label 之外的信息，无法补充就留空字符串。
5. label_mode 与 style 必须参考“已发表插图风格约束”选择：参考图以水平/径向标签为主就不要用弧形；参考图以细描边浅色环带为主就不要用深色实心块。
6. 不得添加用户未提及的数值、材料牌号或实验结果。
"""

FALLBACK = {
    "title": "Mechanical System Architecture: A Concentric Summary",
    "subtitle": "Functional subsystems, enabling technologies and performance outcomes of a mechanical system",
    "core": {"label": "Mechanical System", "caption": "Load transfer and motion conversion"},
    "rings": [
        {"name": "Functional subsystems", "segments": [
            {"label": "Power Input", "caption": "Motor and coupling"},
            {"label": "Transmission", "caption": "Gears and shafts"},
            {"label": "Support", "caption": "Bearings and housing"},
            {"label": "Actuation", "caption": "Output and control"},
        ]},
        {"name": "Enabling technologies", "segments": [
            {"label": "Kinematics", "caption": "Gear train synthesis"},
            {"label": "Tribology", "caption": "Lubrication and wear"},
            {"label": "Structural FEA", "caption": "Stress and stiffness"},
            {"label": "Dynamics", "caption": "Modal and vibration"},
            {"label": "Thermal", "caption": "Heat dissipation"},
            {"label": "Condition Monitoring", "caption": "Sensor and diagnosis"},
        ]},
        {"name": "Performance & application", "segments": [
            {"label": "Efficiency", "caption": "Power loss"},
            {"label": "Reliability", "caption": "Fatigue life"},
            {"label": "Noise", "caption": "Acoustic emission"},
            {"label": "Mass", "caption": "Lightweight design"},
            {"label": "Cost", "caption": "Manufacturing"},
            {"label": "Maintainability", "caption": "Service access"},
            {"label": "Thermal Margin", "caption": "Operating window"},
            {"label": "Digital Twin", "caption": "Lifecycle update"},
        ]},
    ],
    "footnote": "Concentric architecture: inner ring functional subsystems, middle ring enabling technologies, outer ring performance and application.",
}


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _esc(value) -> str:
    return (str(value or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _palette(config: dict) -> dict:
    dna = config.get("style_dna") or {}
    palette = dna.get("palette") if isinstance(dna.get("palette"), dict) else {}
    if palette.get("primary"):
        return {
            "primary": safe_color(palette.get("primary"), "#3F5A6B"),
            "secondary": safe_color(palette.get("secondary"), "#7A8B99"),
            "accent": safe_color(palette.get("accent"), "#C04030"),
            "text": safe_color(palette.get("text"), "#0F172A"),
        }
    # No user reference image: use the palette learned from published figures.
    profile = config.get("style_profile") or {}
    colors = [str(c) for c in (profile.get("palette") or [])
              if isinstance(c, str) and c.startswith("#") and len(c) == 7]
    if len(colors) >= 2:
        return {"primary": safe_color(colors[0], "#3F5A6B"),
                "secondary": safe_color(colors[1], "#7A8B99"),
                "accent": safe_color(colors[2] if len(colors) > 2 else "#C04030", "#C04030"),
                "text": "#1E293B"}
    return {"primary": "#3F5A6B", "secondary": "#7A8B99",
            "accent": "#C04030", "text": "#1E293B"}


def _clip_text(value, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[: max(1, limit - 1)].rstrip(" ,.;:，。；：")
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def _norm_text(value: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower())
    words = [w for w in text.split() if w not in
             {"and", "of", "the", "for", "with", "a", "an", "in", "on"}]
    return " ".join(words)


def _same_text(a: str, b: str) -> bool:
    left, right = _norm_text(a), _norm_text(b)
    if not left or not right:
        return False
    if left == right:
        return True
    return right.startswith(left) and len(right) - len(left) <= 6


def _fit_font(text: str, max_width: float, base: float, floor: float,
              bold: bool = False) -> float:
    size = base
    while size > floor and framework._measure_text(text, size, bold) > max_width:
        size -= 0.4
    return max(floor, size)


def _clip_to_width(text: str, max_width: float, size: float) -> str:
    if framework._measure_text(text, size) <= max_width:
        return text
    words = str(text).split()
    while words and framework._measure_text(" ".join(words) + "…", size) > max_width:
        words.pop()
    return (" ".join(words).rstrip(" ,.;:") + "…") if words else text[:1]


def _split_caption(text: str, max_width: float, size: float) -> list[str]:
    if framework._measure_text(text, size) <= max_width:
        return [text]
    words = str(text).split()
    best = None
    for cut in range(1, len(words)):
        left, right = " ".join(words[:cut]), " ".join(words[cut:])
        width = max(framework._measure_text(left, size), framework._measure_text(right, size))
        if best is None or width < best[0]:
            best = (width, [left, right])
    if best and best[0] <= max_width:
        return best[1]
    # Still too long: clip each half to the available arc.
    half = (len(words) + 1) // 2
    return [_clip_to_width(" ".join(words[:half]), max_width, size),
            _clip_to_width(" ".join(words[half:]), max_width, size)]


def _ring_spec(spec: dict) -> dict:
    rings = list(spec.get("rings") or [])
    if not rings:
        raise RuntimeError("ring plan has no rings")
    # 2–4 rings, 3–12 segments each; never force a fixed 4/6/8 layout.
    if len(rings) < 2:
        rings = list(rings) + list(FALLBACK["rings"])[len(rings):2]
    rings = rings[:4]
    clean = []
    for index, ring in enumerate(rings):
        segments = ring.get("segments") or []
        chosen = [
            {"label": _clip_text(s.get("label"), 40),
             "caption": _clip_text(s.get("caption"), 96),
             "illustration": _clip_text(s.get("illustration"), 120)}
            for s in segments[:12]
        ]
        filler_pool = FALLBACK["rings"][min(index, 2)]["segments"]
        while len(chosen) < 3:
            filler = filler_pool[len(chosen) % len(filler_pool)]
            chosen.append(dict(filler))
        clean.append({"name": ring.get("name") or "", "segments": chosen})
    core = spec.get("core") or {}
    label_mode = str(spec.get("label_mode") or "arc").lower()
    if label_mode not in ("arc", "radial", "horizontal"):
        label_mode = "arc"
    ring_style = str(spec.get("style") or "filled").lower()
    if ring_style not in ("filled", "outline"):
        ring_style = "filled"
    return {
        "title": _clip_text(spec.get("title"), 64),
        "subtitle": _clip_text(spec.get("subtitle"), 118),
        "core": {"label": _clip_text(core.get("label"), 20),
                 "caption": _clip_text(core.get("caption"), 42),
                 "illustration": _clip_text(core.get("illustration"), 140)},
        "rings": clean,
        "label_mode": label_mode,
        "style": ring_style,
        "footnote": _clip_text(spec.get("footnote"), 170),
    }


def plan_ring(text: str, config: dict) -> dict:
    best = None
    brief = str(config.get("design_brief") or "").strip()
    user_text = text
    if brief:
        user_text = (text + chr(10) + chr(10) + "已发表插图风格约束（用于配色、字体与细节，不改变同心圆拓扑）："
                     + chr(10) + brief)
    for temperature in (0.35, 0.1):
        try:
            raw = pipeline._chat(config, [
                {"role": "system", "content": RING_INSTRUCTION},
                {"role": "user", "content": user_text},
            ], temperature=temperature, max_tokens=2600)
            data = pipeline._json_object(raw)
            rings = data.get("rings") or []
            counts = [len((r or {}).get("segments") or []) for r in rings]
            spec = _ring_spec(data)
            if len(rings) >= 2 and all(c >= 3 for c in counts):
                return spec
            if best is None or sum(counts) > sum(best[1]):
                best = (spec, counts)
        except Exception:
            continue
    if best is not None:
        return best[0]

    # Last attempt: fill an explicit template (weak models copy structure well).
    template = {
        "title": "English title <= 58 chars",
        "subtitle": "English subtitle <= 96 chars",
        "core": {"label": "core object", "caption": "one-line definition",
                 "illustration": "precise object description for an illustrator"},
        "rings": [
            {"name": "Layer one", "segments": [
                {"label": "", "caption": "", "illustration": ""} for _ in range(5)]},
            {"name": "Layer two", "segments": [
                {"label": "", "caption": "", "illustration": ""} for _ in range(7)]},
            {"name": "Layer three", "segments": [
                {"label": "", "caption": "", "illustration": ""} for _ in range(9)]},
        ],
        "label_mode": "arc",
        "style": "filled",
        "footnote": "English caption <= 110 chars",
    }
    try:
        data = pipeline.chat_json(config, [
            {"role": "system", "content": "Fill the JSON template for the user's topic. "
                                          "2-4 rings, 3-12 segments each; choose counts from the content. Output only JSON."},
            {"role": "user", "content": user_text + chr(10) + json.dumps(template, ensure_ascii=False)},
        ], temperature=0.2, max_tokens=2600)
        spec = _ring_spec(data)
        spec["planner"] = "template"
        return spec
    except Exception:
        pass

    # Topic-aware fallback: keep the user's own topic in the title.
    base = json.loads(json.dumps(FALLBACK))
    clean = re.sub(r"\s+", " ", text).strip()
    base["title"] = _clip_text(clean.split("：")[0] or clean, 40)
    base["subtitle"] = _clip_text(clean, 100)
    base["core"]["label"] = _clip_text(clean.split("：")[0], 20) or base["core"]["label"]
    spec = _ring_spec(base)
    spec["planner"] = "topic-fallback"
    return spec


def _tint(color: str, alpha: float, bg: str = "#FFFFFF") -> str:
    """Blend a colour toward white so PowerPoint (which ignores fill-opacity)
    renders the same pale band as the SVG."""
    try:
        cr, cg, cb = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        br, bgc, bb = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
        return "#%02X%02X%02X" % (
            round(cr * alpha + br * (1 - alpha)),
            round(cg * alpha + bgc * (1 - alpha)),
            round(cb * alpha + bb * (1 - alpha)))
    except Exception:
        return color


def _polar(cx, cy, r, deg):
    rad = math.radians(deg)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _sector(cx, cy, r_in, r_out, a0, a1) -> str:
    x0, y0 = _polar(cx, cy, r_out, a0)
    x1, y1 = _polar(cx, cy, r_out, a1)
    x2, y2 = _polar(cx, cy, r_in, a1)
    x3, y3 = _polar(cx, cy, r_in, a0)
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return (f'M{x0:.2f},{y0:.2f} A{r_out:.2f},{r_out:.2f} 0 {large} 1 {x1:.2f},{y1:.2f} '
            f'L{x2:.2f},{y2:.2f} A{r_in:.2f},{r_in:.2f} 0 {large} 0 {x3:.2f},{y3:.2f} Z')


def _arc_bbox(cx, cy, r, mid, text, size):
    """Approximate the on-screen box of arc text for the pixel reviewer."""
    width = framework._measure_text(text, size)
    dtheta = math.degrees(width / max(1.0, r)) * 1.06
    pts = []
    for k in range(6):
        ang = mid - dtheta / 2 + dtheta * k / 5
        pts.append(_polar(cx, cy, r + size * 0.38, ang))
        pts.append(_polar(cx, cy, r - size * 0.58, ang))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs) - 2, min(ys) - 2, max(xs) - min(xs) + 4, max(ys) - min(ys) + 4


def _tangent(mid_deg: float) -> float:
    deg = mid_deg + 90.0
    while deg > 90:
        deg -= 180
    while deg < -90:
        deg += 180
    return deg


def build_ring_svg(spec: dict, font: str = "Times New Roman",
                   canvas=None, viewport_shape: str = "rect",
                   palette: dict | None = None, assets: dict | None = None) -> bytes:
    assets = assets or {}
    palette = palette or {}
    primary = safe_color(palette.get("primary"), "#1F4E79")
    secondary = safe_color(palette.get("secondary"), "#2F7F8A")
    accent = safe_color(palette.get("accent"), "#D97706")
    ink = safe_color(palette.get("text"), "#0F172A")

    cw, ch = (canvas or [1400, 1400])[:2]
    cw, ch = float(cw), float(ch)
    s = min(cw, ch)
    shape = (viewport_shape or "rect").lower()
    cx, cy = cw / 2, ch / 2
    r_core = 0.105 * s
    rings_spec = (spec.get("rings") or [])[:4]
    n_rings = max(1, len(rings_spec))
    inner0, outer_max = 0.145, 0.440
    band_gap = 0.016 if n_rings <= 3 else 0.013
    thickness = (outer_max - inner0 - band_gap * (n_rings - 1)) / n_rings
    bands = [(inner0 + i * (thickness + band_gap),
              inner0 + i * (thickness + band_gap) + thickness)
             for i in range(n_rings)]

    parts = []
    header = []
    label_mode = spec.get("label_mode") or "arc"
    ring_style = spec.get("style") or "filled"
    # Title block: reserve the full header above the ring; with a circular or
    # elliptical viewport the ring scales down and the title is laid out
    # outside the clip, fitted to the circle's chord at its own baseline.
    tsize, tlines = framework._fit_lines(spec["title"], cw - 200, 30, 17, max_lines=2)
    ty = 54
    if shape in ("circle", "ellipse"):
        ty = 72
        radius = min(cw, ch) / 2 - 14
        cy0 = ch / 2

        def chord_width(lines, size, y, bold=True):
            worst = 0.0
            for index, line in enumerate(lines):
                baseline = y + index * (size + 2)
                y0, height = framework._measure_vbox(line, size, bold)
                dy = max(abs(baseline + y0 - cy0), abs(baseline + y0 + height - cy0))
                if dy >= radius - 6:
                    return 0.0
                worst = max(worst, 2 * math.sqrt(max(1.0, radius * radius - dy * dy)) - 10)
            return worst

        while tsize > 10 and chord_width(tlines, tsize, ty, True) < max(
                framework._measure_text(line, tsize, True) for line in tlines):
            tsize -= 0.6
    title_bottom = ty + (len(tlines) - 1) * (tsize + 2) + tsize
    ssize, slines = framework._fit_lines(spec["subtitle"], cw - 240, 14, 9, max_lines=1)
    sy = title_bottom + 8
    if shape in ("circle", "ellipse"):
        radius = min(cw, ch) / 2 - 14
        cy0 = ch / 2
        while ssize > 8:
            y0, height = framework._measure_vbox(slines[0] if slines else "", ssize, False)
            dy = max(abs(sy + y0 - cy0), abs(sy + y0 + height - cy0))
            allowed = 2 * math.sqrt(max(1.0, radius * radius - dy * dy)) - 10 if dy < radius - 6 else 0
            if allowed >= framework._measure_text(slines[0] if slines else "", ssize):
                break
            ssize -= 0.5
    sub_bottom = sy + (len(slines) - 1) * (ssize + 2) + ssize
    if shape in ("circle", "ellipse"):
        header_bottom = sub_bottom + 46
    else:
        header_bottom = sub_bottom + 18
    for index, line in enumerate(tlines):
        header.append(f'<text x="{cw/2:.1f}" y="{ty + index * (tsize + 2):.1f}" '
                      f'text-anchor="middle" font-family="{_esc(font)}" font-size="{tsize:.1f}" '
                      f'font-weight="bold" fill="{ink}">{_esc(line)}</text>')
    header.append(f'<text x="{cw/2:.1f}" y="{sy:.1f}" text-anchor="middle" '
                  f'font-family="{_esc(font)}" font-size="{ssize:.1f}" fill="#64748B">'
                  f'{_esc(slines[0] if slines else "")}</text>')

    # Scale the ring so header, ring and footnote all fit inside the viewport.
    ring_dia = 2 * bands[-1][1] * s
    footroom = (150.0 if shape in ("circle", "ellipse") else 72.0)
    avail = ch - header_bottom - footroom
    scale_r = min(1.0, avail / ring_dia)
    if scale_r < 1.0:
        r_core *= scale_r
        bands = [(a * scale_r, b * scale_r) for a, b in bands]
        cy = header_bottom + (ch - header_bottom) / 2

    # faint guide circles (skip when the scaled inner band collapses)
    for r in (bands[0][0] - 6, bands[-1][1] + 10):
        if r <= 0:
            continue
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="none" '
                     f'stroke="#E2E8F0" stroke-width="1" stroke-dasharray="3 5"/>')

    counts = [len(r.get("segments") or []) for r in rings_spec]
    # Publication practice: pale bands with thin coloured strokes, not heavy
    # solid fills. One saturated accent is reserved for the outer ring.
    styles = [
        {"fill": _tint(primary, 0.12), "opacity": 1.0, "stroke": primary,
         "label": ink, "caption": "#475569"},
        {"fill": "#FFFFFF", "opacity": 1.0, "stroke": secondary,
         "label": ink, "caption": "#475569"},
        {"fill": _tint(accent, 0.07), "opacity": 1.0, "stroke": accent,
         "label": ink, "caption": "#7C4A03"},
    ]
    gaps = [3.2, 2.6, 2.0, 1.8]
    arc_defs = []
    for ring_index, (ring, count) in enumerate(zip(rings_spec, counts)):
        r_in, r_out = bands[ring_index]
        r_in *= s
        r_out *= s
        step = 360.0 / count
        style = styles[ring_index % len(styles)]
        for seg_index, segment in enumerate(ring["segments"]):
            a0 = -90 + seg_index * step + gaps[ring_index] / 2
            a1 = a0 + step - gaps[ring_index]
            path = _sector(cx, cy, r_in, r_out, a0, a1)
            if ring_style == "outline":
                fill = "#FFFFFF"
                opacity = 1.0
            elif ring_index == 1 and seg_index % 2 == 1:
                fill = "#F7F9FB"
            elif ring_index == 2 and seg_index % 2 == 1:
                fill = _tint(accent, 0.13)
                opacity = 1.0
            else:
                fill = style["fill"]
                opacity = style["opacity"]
            parts.append(f'<path d="{path}" fill="{fill}" fill-opacity="{opacity:.2f}" '
                         f'stroke="{style["stroke"]}" stroke-width="1.1"/>')

            mid = a0 + (a1 - a0) / 2
            r_mid = (r_in + r_out) / 2
            arc = 2 * math.pi * r_mid * (step - gaps[ring_index]) / 360.0
            thickness = r_out - r_in
            avail = thickness * 0.92 if label_mode == "radial" else arc * 0.92
            base_label = 13.5 if ring_index == 0 else (12.5 if ring_index == 1 else 11.5)
            label_size = _fit_font(segment["label"], avail, base_label, 9.2, bold=True)
            label_text = _clip_to_width(segment["label"], avail, label_size)
            caption = segment["caption"]
            if _same_text(segment["label"], caption):
                caption = ""
            cap_base = 9.6 if ring_index == 0 else 9.0
            cap_size = _fit_font(caption, avail, cap_base, 7.4) if caption else cap_base
            cap_text = _clip_to_width(caption, avail, cap_size) if caption else ""

            top = math.sin(math.radians(mid)) < 0
            gap_px = label_size * 0.82 + cap_size + 4
            if cap_text:
                r_label = r_mid + gap_px / 2 if top else r_mid - gap_px / 2
                r_cap = r_mid - gap_px / 2 if top else r_mid + gap_px / 2
            else:
                r_label, r_cap = r_mid, r_mid

            def rotated_bbox(px, py, width, height, deg):
                rad = math.radians(deg)
                ca, sa = math.cos(rad), math.sin(rad)
                pts = []
                for dx, dy in ((-width / 2, -height / 2), (width / 2, -height / 2),
                               (width / 2, height / 2), (-width / 2, height / 2)):
                    pts.append((px + dx * ca - dy * sa, py + dx * sa + dy * ca))
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)

            def emit(text, radius, size, color, weight, key):
                px, py = _polar(cx, cy, radius, mid)
                if label_mode == "radial":
                    # Straight label along the tangent at the segment midpoint;
                    # the tangent is normalized to [-90, 90] so left-side
                    # labels never render upside down.
                    rot = _tangent(mid)
                    bw = framework._measure_text(text, size)
                    bx, by, bw2, bh = rotated_bbox(px, py, bw, size * 1.2, rot)
                    return (f'<text x="{px:.1f}" y="{py + size * 0.35:.1f}" text-anchor="middle" '
                            f'transform="rotate({rot:.2f} {px:.1f} {py:.1f})" '
                            f'font-family="{_esc(font)}" font-size="{size:.1f}" fill="{color}"'
                            + (' font-weight="bold"' if weight else '')
                            + f' data-arc="0" data-bbox="{bx:.1f},{by:.1f},{bw2:.1f},{bh:.1f}" '
                            f'data-ppt-x="{px:.1f}" data-ppt-y="{py:.1f}" '
                            f'data-ppt-rot="{rot:.2f}" data-ppt-anchor="middle">{_esc(text)}</text>')
                if label_mode == "horizontal":
                    bw = framework._measure_text(text, size)
                    bx, by = px - bw / 2, py - size * 0.6
                    return (f'<text x="{px:.1f}" y="{py + size * 0.35:.1f}" text-anchor="middle" '
                            f'font-family="{_esc(font)}" font-size="{size:.1f}" fill="{color}"'
                            + (' font-weight="bold"' if weight else '')
                            + f' data-arc="0" data-bbox="{bx:.1f},{by:.1f},{bw:.1f},{size * 1.2:.1f}" '
                            f'data-ppt-x="{px:.1f}" data-ppt-y="{py:.1f}" '
                            f'data-ppt-rot="0" data-ppt-anchor="middle">{_esc(text)}</text>')
                start, end = (a0, a1) if math.sin(math.radians(mid)) < 0 else (a1, a0)
                sweep = 1 if start < end else 0
                x0, y0 = _polar(cx, cy, radius, start)
                x1, y1 = _polar(cx, cy, radius, end)
                large = 1 if abs(end - start) % 360 > 180 else 0
                path_id = f"rt-{ring_index}-{seg_index}-{key}"
                arc_defs.append(f'<path id="{path_id}" d="M{x0:.2f},{y0:.2f} '
                            f'A{radius:.2f},{radius:.2f} 0 {large} {sweep} {x1:.2f},{y1:.2f}"/>')
                bx, by, bw, bh = _arc_bbox(cx, cy, radius, mid, text, size)
                return (f'<text text-anchor="middle" font-family="{_esc(font)}" '
                        f'font-size="{size:.1f}" fill="{color}"'
                        + (' font-weight="bold"' if weight else '')
                        + f' data-arc="1" data-bbox="{bx:.1f},{by:.1f},{bw:.1f},{bh:.1f}" '
                        f'data-ppt-x="{px:.1f}" data-ppt-y="{py:.1f}" '
                        f'data-ppt-rot="{_tangent(mid):.2f}" data-ppt-anchor="middle">'
                        f'<textPath href="#{path_id}" startOffset="50%" '
                        f'text-anchor="middle">{_esc(text)}</textPath></text>')

            # Inner-ring subsystem images are intentionally not drawn here:
            # at ring scale they shrink into unreadable blobs and collide with
            # the arc labels. The center hero carries the illustration role.
            parts.append(emit(label_text, r_label, label_size, style["label"], True, "l"))
            if cap_text and label_mode != "radial":
                lines = _split_caption(cap_text, avail, cap_size)
                direction = -1.0 if top else 1.0
                for line_index, line in enumerate(lines):
                    radius = r_cap + direction * line_index * (cap_size + 2.5)
                    parts.append(emit(line, radius, cap_size, style["caption"], False,
                                      f"c{line_index}"))

    # core
    core = spec["core"]
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_core:.1f}" fill="#FFFFFF" '
                 f'stroke="{primary}" stroke-width="2.6"/>')
    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_core - 9:.1f}" fill="#F8FAFC" '
                 f'stroke="{secondary}" stroke-width="1" stroke-opacity="0.55"/>')
    hero = assets.get("hero")
    title_shift = 0.0
    if hero:
        hsvg, hw, hh = hero
        target = r_core * 0.82
        scale = min(target / max(1, hw), target / max(1, hh))
        hx = cx - hw * scale / 2
        hy = cy - r_core * 0.82
        parts.append(f'<g transform="translate({hx:.2f},{hy:.2f}) scale({scale:.4f})">'
                     f'{compose._clean_asset(hsvg)}</g>')
        title_shift = r_core * 0.34
    csize, clines = framework._fit_lines(core["label"], r_core * 1.55, 17, 11, max_lines=2)
    offset = (len(clines) - 1) * (csize + 1) / 2
    for index, line in enumerate(clines):
        parts.append(f'<text x="{cx:.1f}" y="{cy - offset + index * (csize + 1) - 2 + title_shift:.1f}" '
                     f'text-anchor="middle" font-family="{_esc(font)}" font-size="{csize}" '
                     f'font-weight="bold" fill="{primary}">{_esc(line)}</text>')
    cap_size, cap_lines = framework._fit_lines(core["caption"], r_core * 1.5, 9.2, 7.5, max_lines=2)
    cap_top = cy + offset * 0.2 + 19 + title_shift
    for index, line in enumerate(cap_lines):
        parts.append(f'<text x="{cx:.1f}" y="{cap_top + index * (cap_size + 2):.1f}" '
                     f'text-anchor="middle" font-family="{_esc(font)}" font-size="{cap_size}" '
                     f'fill="#475569">{_esc(line)}</text>')

    # ring names at the bottom of the figure
    names = [ring["name"] for ring in rings_spec]
    legend = "  ·  ".join(names)
    footnote = str(spec.get("footnote") or "").strip()
    if shape in ("circle", "ellipse"):
        legend_y = ch - 96
        foot_y = ch - 74
    else:
        legend_y = ch - 46
        foot_y = ch - 26
    parts.append(f'<text x="{cw/2:.1f}" y="{legend_y:.1f}" text-anchor="middle" '
                 f'font-family="{_esc(font)}" font-size="10.5" fill="#64748B">{_esc(legend)}</text>')
    if footnote:
        parts.append(f'<text x="{cw/2:.1f}" y="{foot_y:.1f}" text-anchor="middle" '
                     f'font-family="{_esc(font)}" font-size="9.5" fill="#94A3B8">'
                     f'{_esc(footnote)}</text>')

    body = "".join(parts)
    defs = list(arc_defs)
    if shape in ("circle", "ellipse"):
        radius = min(cw, ch) / 2 - 14
        if shape == "circle":
            clip = f'<circle cx="{cw/2:.1f}" cy="{ch/2:.1f}" r="{radius:.1f}"/>'
        else:
            clip = (f'<ellipse cx="{cw/2:.1f}" cy="{ch/2:.1f}" rx="{cw/2-14:.1f}" '
                    f'ry="{ch/2-14:.1f}"/>')
        defs.append(f'<clipPath id="ring-clip">{clip}</clipPath>')
        # Header sits outside the clip: the round window only clips the ring
        # body, so the title can never lose its first or last characters.
        inner = "".join(header) + f'<g clip-path="url(#ring-clip)">{body}</g>'
    elif shape == "card":
        clip = f'<rect x="14" y="14" width="{cw-28:.1f}" height="{ch-28:.1f}" rx="24"/>'
        defs.append(f'<clipPath id="ring-clip">{clip}</clipPath>')
        inner = "".join(header) + f'<g clip-path="url(#ring-clip)">{body}</g>'
    else:
        inner = "".join(header) + body

    svg = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw:.0f}" height="{ch:.0f}" '
           f'viewBox="0 0 {cw:.0f} {ch:.0f}">']
    if defs:
        svg.append(f'<defs>{"".join(defs)}</defs>')
    svg.append(f'<rect width="{cw:.0f}" height="{ch:.0f}" fill="#FFFFFF"/>')
    svg.append(inner)
    svg.append("</svg>")
    return (chr(10).join(svg) + chr(10)).encode("utf-8")


def _shrink(spec: dict) -> None:
    """No blind truncation; the model repair patch edits only what it must."""
    return None


_BASE = (Path(sys.executable).resolve().parent
         if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)


def _asset_ok(png: bytes) -> bool:
    try:
        import cv2
        import numpy as np
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[0] < 300 or image.shape[1] < 300:
            return False
        if float(image.std()) < 8.0:
            return False
        h, w = image.shape[:2]
        corners = np.concatenate([
            image[:12, :12].reshape(-1, 3), image[:12, -12:].reshape(-1, 3),
            image[-12:, :12].reshape(-1, 3), image[-12:, -12:].reshape(-1, 3)])
        return float(corners.mean()) > 232.0
    except Exception:
        return True


def _make_assets(spec: dict, config: dict, palette: dict, stage) -> dict:
    """Generate one hero illustration + four subsystem icons for image mode."""
    cache_root = _BASE / "illustration_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    core = spec["core"]
    # One hero illustration only. Ring segments are labels, not thumbnails.
    items = [("hero", core.get("illustration") or core["label"], True)]
    assets = {}
    # Illustrations are decorative; 640px keeps the SVG small enough that the
    # native PPTX export stays under a minute.
    asset_config = json.loads(json.dumps(config))
    asset_config.setdefault("vectorize", {})["max_side"] = 1024
    for number, (key, label, is_hero) in enumerate(items, 1):
        stage("generate", f"配图 {number}/{len(items)}：{label}")
        prompt = (f"Technical isometric illustration of {label}. "
                  "Single object, pure white background, consistent palette "
                  f"(steel blue {palette.get('primary')}, rust {palette.get('accent')}, "
                  "neutral gray), clean thin dark outlines, flat shading, "
                  "no text, no labels, no arrows, no dimensions, no frame, centered, "
                  "object fills 80% of the frame.")
        if is_hero:
            prompt += " Three-quarter cutaway view showing internal arrangement, high detail."
        else:
            prompt += " Single component or subsystem, no surrounding assembly."
        digest = hashlib.md5(prompt.encode("utf-8")).hexdigest()[:16]
        cached = cache_root / f"{digest}.png"
        try:
            if cached.is_file():
                png = cached.read_bytes()
            else:
                png = pipeline.generate_raw(prompt, config)
                cached.write_bytes(png)
            if not _asset_ok(png):
                simple = (f"Simple flat vector icon of {label}, pure white background, "
                          "single object, centered, no text, no labels.")
                png = pipeline.generate_raw(simple, config)
                cached.write_bytes(png)
            cut = compose.cutout(png)
            assets[key] = compose.asset_image(cut)
        except Exception:
            continue
    return assets


def render_ring(text: str, config: dict, on_stage=None) -> tuple[bytes, dict]:
    def stage(name, detail=None):
        if on_stage:
            on_stage(name, detail)

    report = {"ring": True, "stages": {}}
    stage("plan_scene", "structuring concentric architecture")
    spec = plan_ring(text, config)
    report["spec"] = spec

    canvas = config.get("canvas") if config.get("canvas_user") else [1400, 1400]
    shape = config.get("viewport_shape") or "rect"
    font = str(config.get("font") or "Times New Roman")
    profile = config.get("style_profile") or {}
    if profile.get("font_family") == "sans" and font in ("Times New Roman", "", "None"):
        font = "Arial"
    palette = _palette(config)

    illustration = str(config.get("illustration_mode") or "vector").lower() in ("image", "illustrated")
    assets = _make_assets(spec, config, palette, stage) if illustration else {}
    if illustration:
        report["illustration"] = {"requested": 1, "generated": len(assets),
                                  "fallback": len(assets) == 0}

    def build():
        return build_ring_svg(spec, font, canvas=canvas, viewport_shape=shape,
                              palette=palette, assets=assets)

    def review_svg(data):
        try:
            import review
            return review.findings(data, None)
        except Exception:
            return []

    stage("assemble", "drawing ring bands and labels")
    import model_review
    def context_fn(current_spec, kind):
        return {
            "kind": "concentric_ring",
            "title": current_spec.get("title"),
            "canvas": canvas,
            "core": (current_spec.get("core") or {}).get("label"),
            "label_mode": current_spec.get("label_mode"),
            "rings": [{"name": r.get("name"),
                       "labels": [x.get("label") for x in r.get("segments") or []]}
                      for r in current_spec.get("rings") or []],
        }
    final_svg, rework = model_review.run_loop(
        spec, build, _shrink, review_svg, context_fn,
        config, "ring", on_stage=stage, max_rounds=10)
    report["rework"] = rework
    pipeline._check_svg(final_svg, allow_image=bool(assets))
    report["stages"]["assemble"] = {"bytes": len(final_svg),
                                    "segments": sum(len(r["segments"]) for r in spec["rings"])}
    report["bytes"] = len(final_svg)
    return final_svg, report
