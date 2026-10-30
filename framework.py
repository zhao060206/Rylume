"""Publication-grade Framework & Closed-Loop System Diagram Engine.

Designed for top-tier scientific papers (Cell / Nature / Science / ACS Nano / Adv Mater).
Renders multi-tier closed-loop perception-inference-actuation-interaction architectures
with live editable text, crisp container cards, data stream ribbons, and bilateral
feedback flows, seamlessly integrating AI-generated high-fidelity vector assets.
"""

from __future__ import annotations

import json
import math
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import compose
import pipeline
from colorsafe import safe_color

FRAMEWORK_INSTRUCTION = """你是顶刊（Cell / Nature / Science / ACS Nano）的高级科学艺术顾问与封面架构师。
用户需要一张系统的“闭环推导图 / 体系架构图 / 科学框架图”（Closed-Loop System Framework）。
请根据用户的研究方向或具体描述，将其提炼为严谨、专业、学术信息密度极高的结构化 JSON 数据。
只输出 JSON，不要任何 markdown 或多余解释。

JSON 结构必须严格如下：
{
  "title": "英文字体大标题（例如 Embodied Physical Intelligence: Closed-Loop Perception, Inference & Actuation）",
  "subtitle": "一句话英文字体副标题阐明核心科学逻辑",
  "sensing_layer_title": "A · 顶层感知/输入层标题（例如 A · DISTRIBUTED MULTIMODAL SENSING ARRAY）",
  "sensing_modalities": [
    {"title": "Mechanical", "color": "#0D9488", "desc": "Strain, Pressure & Shear", "icon_type": "strain"},
    {"title": "Optical", "color": "#0284C7", "desc": "Waveguides & Curvature", "icon_type": "wave"},
    {"title": "Electrical", "color": "#4F46E5", "desc": "Ionotronics & Impedance", "icon_type": "pulse"},
    {"title": "Thermal", "color": "#EA580C", "desc": "Temperature & Heat Flux", "icon_type": "thermo"},
    {"title": "Chemical", "color": "#16A34A", "desc": "Ion Activity & Humidity", "icon_type": "molecule"},
    {"title": "Acoustic", "color": "#9333EA", "desc": "Ultrasound & Resonances", "icon_type": "acoustic"}
  ],
  "data_stream_formula": "HIGH-DIMENSIONAL SENSORY STREAM • S(t) = { s_mech, s_opt, s_elec, s_therm, s_chem, s_acoust }",
  "core_layer_title": "B · 中部核心推理层标题（例如 B · PHYSICS-INFORMED LATENT EMBODIED INFERENCE CORE）",
  "priors_title": "FIRST-PRINCIPLES PHYSICAL PRIORS",
  "priors_items": [
    {"title": "Nonlinear Continuum Mechanics", "desc": "Hyperelastic energy functionals, Cauchy stress tensors"},
    {"title": "Deformable Contact Dynamics", "desc": "Frictional stick-slip, obstacle compliance laws"},
    {"title": "Morphological Computation", "desc": "Passive mechanical reservoir filtering & damping"}
  ],
  "latent_title": "LATENT PHYSICAL STATE INFERENCE (X-NET)",
  "latent_items": [
    {"num": "1", "title": "Real-Time Proprioception", "desc": "Reconstructed 3D continuous strain field & body posture"},
    {"num": "2", "title": "Exteroceptive Contact Awareness", "desc": "Contact point localization, external torque & slip detection"},
    {"num": "3", "title": "Uncertainty & Damage Resilience", "desc": "Degradation tracking, active safety envelope evaluation"}
  ],
  "ai_title": "GENERATIVE & EMBODIED AI",
  "ai_items": [
    {"title": "Spatiotemporal Transformers", "desc": "Multimodal sequence tokenization & attention"},
    {"title": "Physical World Models", "desc": "Latent forward simulation of deformable interactions"},
    {"title": "Continual Reinforcement Learning", "desc": "Policy transfer across unstructured morphologies"}
  ],
  "action_dispatch_formula": "ADAPTIVE CONTROL ACTION DISPATCH • u(t) = π( z_latent(t), S(t) )",
  "embodied_layer_title": "C · 底层具身实现与执行器阵列标题（例如 C · MULTI-SCALE EMBODIED ACTUATION & PHYSICAL REALIZATION）",
  "embodied_entities": [
    {
      "id": "gripper",
      "title": "Compliant Soft Gripper",
      "desc": "Variable-stiffness envelope grasping",
      "prompt": "isolated compliant pneumatic soft robotic gripper with three flexible segmented fingers gently grasping an orange sphere, side view, modern scientific paper illustration, flat 2D vector style, clean dark outline, fills in teal #2E8B7A, warm tan #C89A6B, and light gray accents, pure white background, no text, no labels, no arrows, centered, subject fills about 75% of frame"
    },
    {
      "id": "fish",
      "title": "Biohybrid Fish Swimmer",
      "desc": "Undulatory propulsion & hydrodynamic coupling",
      "prompt": "isolated biomimetic soft robotic fish swimmer with undulating flexible caudal fin, internal compliant chamber skeleton, side view, modern scientific paper illustration, flat 2D vector style, clean dark outline, fills in teal #2E8B7A, lake blue #20639B, and warm tan accents, pure white background, no text, no labels, no arrows, centered, subject fills about 75% of frame"
    },
    {
      "id": "exoskeleton",
      "title": "Wearable Soft Exoskeleton",
      "desc": "Artificial muscle assistive synergy",
      "prompt": "isolated wearable soft assistive robotic exoskeleton suit around elbow joint with pneumatic artificial muscle tendons and sensor bands, modern scientific paper illustration, flat 2D vector style, clean dark outline, fills in warm tan #C89A6B, teal #2E8B7A, and slate gray, pure white background, no text, no labels, no arrows, centered, subject fills about 75% of frame"
    },
    {
      "id": "metamaterial",
      "title": "Metamaterial Locomotor",
      "desc": "Mechanical metamaterial autonomous gait",
      "prompt": "isolated crawling soft robot constructed from mechanical metamaterial lattice cell structure with compliant hinges and bilateral symmetry, modern scientific paper illustration, flat 2D vector style, clean dark outline, fills in warm tan #C89A6B, teal #2E8B7A, and cream, pure white background, no text, no labels, no arrows, centered, subject fills about 75% of frame"
    }
  ],
  "environment_interaction": "PHYSICAL ENVIRONMENT & UNSTRUCTURED TERRAIN CONTACT INTERACTION (DEFORMATION, FRICTION, FLUID RESISTANCE)",
  "left_feedback": "CLOSED-LOOP RECEPTIVE FEEDBACK: CONTACT & DEFORMATION",
  "right_feedback": "ADAPTIVE POLICY UPDATE & CONTINUAL LEARNING LOOP"
}

请确保所有实体 prompt 描述具体物理物体，纯白背景，无任何文字或箭头。
若用户是生物/医学/材料领域（如细胞信号调控闭环、自驱动化学实验室、脑机接口闭环等），相应替换为该领域的顶刊专业词汇与对应实体！
"""

def _esc(val: str) -> str:
    return (str(val).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))

def plan_framework(text: str, config: dict) -> dict:
    brief = str(config.get("design_brief") or "").strip()
    user_text = text
    if brief:
        user_text = (text + chr(10) + chr(10) + "已发表插图风格约束（必须遵守）："
                     + chr(10) + brief)
    messages = [
        {"role": "system", "content": FRAMEWORK_INSTRUCTION},
        {"role": "user", "content": user_text},
    ]
    try:
        return pipeline.chat_json(config, messages, temperature=0.25, max_tokens=4000)
    except Exception:
        raw = pipeline._chat(config, messages, temperature=0.25, max_tokens=4000)
        fixed = pipeline._chat(config, [
            {"role": "system", "content": "You repair invalid JSON. Return ONLY valid JSON object without commentary."},
            {"role": "user", "content": raw[:8000]},
        ], temperature=0)
        return pipeline._json_object(fixed)

def _render_icon(icon_type: str, color: str) -> str:
    icon_type = (icon_type or "").lower()
    color = safe_color(color, "#0D9488")
    if "strain" in icon_type or "mech" in icon_type:
        return (f'<path d="M-15 -6 C-5 -12 5 -12 15 -6 M-15 6 C-5 12 5 12 15 6" stroke="{color}" stroke-width="2.2" fill="none"/>'
                f'<line x1="-15" y1="0" x2="15" y2="0" stroke="{color}" stroke-width="1.8" stroke-dasharray="3 2"/>')
    elif "wave" in icon_type or "opt" in icon_type:
        return (f'<path d="M-14 8 C-6 -8 6 -8 14 8" stroke="{color}" stroke-width="3" fill="none"/>'
                f'<circle cx="0" cy="-6" r="3" fill="{color}"/>')
    elif "pulse" in icon_type or "elec" in icon_type:
        return f'<path d="M-14 0 L-6 10 L6 -10 L14 0" stroke="{color}" stroke-width="2.2" fill="none" stroke-linejoin="round"/>'
    elif "thermo" in icon_type or "heat" in icon_type:
        return f'<path d="M0 -12 L0 6 M-4 6 A4 4 0 1 0 4 6 z" stroke="{color}" stroke-width="2" fill="{color}"/>'
    elif "chem" in icon_type or "molec" in icon_type:
        return (f'<circle cx="-6" cy="0" r="5" fill="{color}"/><circle cx="6" cy="-4" r="4" fill="{color}"/>'
                f'<line x1="-6" y1="0" x2="6" y2="-4" stroke="{color}" stroke-width="2"/>')
    elif "acoust" in icon_type or "sound" in icon_type:
        return (f'<path d="M-12 0 A12 12 0 0 1 -12 -10 M-8 0 A8 8 0 0 1 -8 -6" stroke="{color}" stroke-width="2" fill="none"/>'
                f'<circle cx="-14" cy="4" r="2.5" fill="{color}"/>')
    else:
        return f'<circle cx="0" cy="0" r="8" fill="none" stroke="{color}" stroke-width="2"/><circle cx="0" cy="0" r="3" fill="{color}"/>'

def _measure_text(text: str, size: float, bold: bool = False) -> float:
    try:
        from PIL import ImageFont
        path = r"C:\Windows\Fonts\timesbd.ttf" if bold else r"C:\Windows\Fonts\times.ttf"
        font = ImageFont.truetype(path, max(6, int(round(size))))
        return float(font.getlength(str(text)))
    except Exception:
        return len(str(text)) * size * 0.55


def _measure_vbox(text: str, size: float, bold: bool = False) -> tuple[float, float]:
    """Return (top offset from baseline, glyph height) for vertical centering."""
    try:
        from PIL import ImageFont
        path = r"C:\Windows\Fonts\timesbd.ttf" if bold else r"C:\Windows\Fonts\times.ttf"
        font = ImageFont.truetype(path, max(6, int(round(size))))
        x0, y0, x1, y1 = font.getbbox(str(text))
        return float(y0), float(max(1, y1 - y0))
    except Exception:
        return -size * 0.72, size * 1.02


def _fit_lines(text: str, max_width: float, base: float, floor: float,
               max_lines: int = 2) -> tuple[float, list[str]]:
    """Choose the largest font size whose wrapped lines fit the header width."""
    words = str(text or "").split()
    if not words:
        return base, [""]
    size = base
    while size >= floor:
        lines, current = [], ""
        for word in words:
            candidate = (current + " " + word).strip()
            if not current or _measure_text(candidate, size, True) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) <= max_lines and all(_measure_text(line, size, True) <= max_width for line in lines):
            return size, lines
        size -= 0.5
    # Last resort: hard-wrap characters at the floor size.
    chunk = max(1, int(max_width / (floor * 0.55)))
    return floor, [str(text)[i:i + chunk] for i in range(0, len(str(text)), chunk)][:max_lines]


def _wrap_at(text: str, size: float, max_width: float, bold: bool = False) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if not current or _measure_text(candidate, size, bold) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    out: list[str] = []
    for line in lines:
        while len(line) > 1 and _measure_text(line, size, bold) > max_width:
            cut = len(line)
            while cut > 1 and _measure_text(line[:cut], size, bold) > max_width:
                cut -= 1
            out.append(line[:cut])
            line = line[cut:]
        out.append(line)
    return out


def _ellipsize(text: str, size: float, max_width: float, bold: bool = False) -> str:
    value = str(text or "")
    if _measure_text(value, size, bold) <= max_width:
        return value
    while value and _measure_text(value + "…", size, bold) > max_width:
        value = value[:-1].rstrip(" ,.;:，。；：")
    return (value + "…") if value else "…"


def _fit_text(text: str, max_width: float, base: float, floor: float,
              max_lines: int = 1, bold: bool = False) -> tuple[float, list[str]]:
    """Largest font size whose wrapped lines fit max_width (never overflows)."""
    value = str(text or "").strip()
    if not value:
        return base, [""]
    # Leave a real margin: font metrics under-estimate the rendered width and
    # the card clip would otherwise cut the last word.
    max_width = max(10.0, float(max_width) * 0.94)
    size = base
    while size >= floor:
        lines = _wrap_at(value, size, max_width, bold)
        if len(lines) <= max_lines:
            return size, lines
        size -= 0.5
    lines = _wrap_at(value, floor, max_width, bold)[:max_lines]
    lines[-1] = _ellipsize(lines[-1], floor, max_width, bold)
    return floor, lines


def _tspans(lines: list[str], size: float, x: float, first_y: float, gap: float = 2.0) -> str:
    return "".join(
        f'<tspan x="{x:.1f}" dy="{0 if index == 0 else size + gap:.1f}">{line}</tspan>'
        for index, line in enumerate(lines))


def build_framework_svg(spec: dict, assets: dict[str, tuple[bytes, float, float]],
                        font: str = "Times New Roman", canvas=None,
                        viewport_shape: str = "rect", palette: dict | None = None) -> bytes:
    W, H = 1600, 1150
    body = []
    palette = palette or {}
    primary = safe_color(palette.get("primary"), "#0D9488")
    secondary = safe_color(palette.get("secondary"), "#2563EB")
    accent = safe_color(palette.get("accent"), "#D97706")

    body.append(f'<rect width="{W}" height="{H}" fill="#FAFCFD"/>')
    body.append(f'<rect x="20" y="20" width="{W-40}" height="{H-40}" rx="16" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1.5"/>')

    # Defs
    body.append('''<defs>
  <marker id="arr-gray" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M0 1 L9 5 L0 9 z" fill="#64748B"/>
  </marker>
  <marker id="arr-teal" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M0 1 L9 5 L0 9 z" fill="#0D9488"/>
  </marker>
  <marker id="arr-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M0 1 L9 5 L0 9 z" fill="#2563EB"/>
  </marker>
  <marker id="arr-loop" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0 2 L10 6 L0 10 z" fill="#0D9488"/>
  </marker>
  <marker id="arr-loop-2" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
    <path d="M0 2 L10 6 L0 10 z" fill="#2563EB"/>
  </marker>
  <linearGradient id="grad-core" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%" stop-color="#F0FDF4" stop-opacity="0.9"/>
    <stop offset="50%" stop-color="#EFF6FF" stop-opacity="0.9"/>
    <stop offset="100%" stop-color="#FAF5FF" stop-opacity="0.9"/>
  </linearGradient>
  <linearGradient id="grad-stream" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#0D9488" stop-opacity="0.2"/>
    <stop offset="50%" stop-color="#2563EB" stop-opacity="0.6"/>
    <stop offset="100%" stop-color="#0D9488" stop-opacity="0.2"/>
  </linearGradient>
  <linearGradient id="grad-priors" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#FEF3C7"/>
    <stop offset="100%" stop-color="#FFFBEB"/>
  </linearGradient>
  <linearGradient id="grad-ai" x1="0%" y1="0%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#EEF2FF"/>
    <stop offset="100%" stop-color="#F5F3FF"/>
  </linearGradient>
</defs>''')

    # Header: measure and wrap generated titles so they never run off-canvas
    title_raw = str(spec.get("title") or "Embodied Physical Intelligence: Closed-Loop System Architecture")
    # A model title that lists every subsystem becomes two cramped lines at
    # the top; keep the headline clause and let the panels carry the detail.
    if len(title_raw) > 92 and ":" in title_raw:
        title_raw = title_raw.split(":", 1)[0].strip()
    subtitle_raw = spec.get("subtitle") or "A Unified Framework Connecting Multimodal Physical Sensing, Physics-Informed Latent State Inference, and Adaptive Soft Actuation"
    title_size, title_lines = _fit_lines(title_raw, 1460, 28, 17, max_lines=2)
    # A two-line title needs the subtitle to stay on one line so the header
    # never collides with layer A.
    subtitle_size, subtitle_lines = _fit_lines(subtitle_raw, 1460, 15, 7.5, max_lines=1)
    title = _esc(title_raw)
    subtitle = _esc(subtitle_raw)
    if len(title_lines) == 1:
        title_y = 60
    else:
        title_y = 40
    title_tspans = "".join(
        f'<tspan x="800" dy="{0 if index == 0 else title_size + 2:.1f}">{_esc(line)}</tspan>'
        for index, line in enumerate(title_lines))
    subtitle_y = title_y + (len(title_lines) - 1) * (title_size + 2) + title_size + 8
    subtitle_tspans = "".join(
        f'<tspan x="800" dy="{0 if index == 0 else subtitle_size + 2:.1f}">{_esc(line)}</tspan>'
        for index, line in enumerate(subtitle_lines))
    body.append(f'''
<g id="header">
  <text x="800" y="{title_y}" text-anchor="middle" font-family="{_esc(font)}" font-size="{title_size:.1f}" font-weight="bold" fill="#0F172A">
    {title_tspans}
  </text>
  <text x="800" y="{subtitle_y:.1f}" text-anchor="middle" font-family="{_esc(font)}" font-size="{subtitle_size:.1f}" fill="#475569">
    {subtitle_tspans}
  </text>
  <line x1="120" y1="108" x2="1480" y2="108" stroke="#E2E8F0" stroke-width="1.2"/>
</g>
''')

    # Section A: Multimodal Sensing Layer
    sensing_title_raw = str(spec.get("sensing_layer_title") or "A · DISTRIBUTED MULTIMODAL SENSING ARRAY")
    sensing_title_size, sensing_title_lines = _fit_text(
        sensing_title_raw, 1300, 14, 9.5, max_lines=1, bold=True)
    sensing_title = _esc(sensing_title_raw)
    body.append(f'''
<g id="layer-sensing">
  <rect x="120" y="115" width="1360" height="120" rx="12" fill="#F8FAFC" stroke="#E2E8F0" stroke-width="1"/>
  <text x="140" y="136" font-family="{_esc(font)}" font-size="{sensing_title_size:.1f}" font-weight="bold" fill="#334155" letter-spacing="0.5">
    {sensing_title}
  </text>
</g>
''')

    modalities = spec.get("sensing_modalities") or []
    n_mod = max(1, len(modalities))
    card_w = min(210.0, (1320.0 - (n_mod - 1) * 16.0) / n_mod)
    x_start = 140.0
    for i, mod in enumerate(modalities[:6]):
        x_pos = x_start + i * (card_w + 16.0)
        col = safe_color(mod.get("color"), "#0D9488")
        name_raw = str(mod.get("title") or f"Modality {i+1}")
        desc_raw = str(mod.get("desc") or "")
        text_x = 54.0
        avail = max(40.0, card_w - text_x - 10.0)
        name_size, name_lines = _fit_text(name_raw, avail, 14.5, 9.0, 1, True)
        desc_size, desc_lines = _fit_text(desc_raw, avail, 13.0, 9.5, 2, False)
        t_name = _esc(name_raw)
        desc_y = 52.0
        icon_svg = _render_icon(mod.get("icon_type") or "", col)
        body.append(f'''
        <g transform="translate({x_pos:.1f}, 145)">
          <rect width="{card_w:.1f}" height="84" rx="8" fill="#FFFFFF" stroke="{col}" stroke-width="1.2"/>
          <rect width="{card_w:.1f}" height="6" rx="3" fill="{col}"/>
          <g transform="translate(26, 42)">{icon_svg}</g>
          <text x="{text_x}" y="38" font-family="{_esc(font)}" font-size="{name_size:.1f}" font-weight="bold" fill="{col}" data-box="0,0,{card_w:.1f},84">{t_name}</text>
          <text x="{text_x}" y="{desc_y:.1f}" font-family="{_esc(font)}" font-size="{desc_size:.1f}" fill="#475569" data-box="0,0,{card_w:.1f},84">{_tspans([_esc(line) for line in desc_lines], desc_size, text_x, desc_y, 1.0)}</text>
          <line x1="{card_w/2:.1f}" y1="82" x2="{card_w/2:.1f}" y2="100" stroke="{col}" stroke-width="1.5" marker-end="url(#arr-gray)"/>
        </g>
        ''')

    # Data Stream Ribbon: full width, so every sensing card has a real target
    data_formula_raw = str(spec.get("data_stream_formula") or "HIGH-DIMENSIONAL SENSORY STREAM • S(t)")
    data_size, _ = _fit_text(data_formula_raw, 1280, 12, 8.5, 1, True)
    data_formula = _esc(data_formula_raw)
    body.append(f'''
    <g transform="translate(140, 245)">
      <rect x="0" y="0" width="1320" height="26" rx="13" fill="url(#grad-stream)"/>
      <text x="660" y="17" text-anchor="middle" font-family="{_esc(font)}" font-size="{data_size:.1f}" font-weight="bold" fill="#0F172A">
        {data_formula}
      </text>
      <line x1="660" y1="26" x2="660" y2="60" stroke="#2563EB" stroke-width="2" marker-end="url(#arr-blue)"/>
    </g>
    ''')

    # Section B: Core Layer
    core_title_raw = str(spec.get("core_layer_title") or "B · PHYSICS-INFORMED LATENT EMBODIED INFERENCE CORE")
    priors_title_raw = str(spec.get("priors_title") or "FIRST-PRINCIPLES PHYSICAL PRIORS")
    latent_title_raw = str(spec.get("latent_title") or "LATENT PHYSICAL STATE INFERENCE")
    ai_title_raw = str(spec.get("ai_title") or "GENERATIVE & EMBODIED AI")
    core_title_size, _ = _fit_text(core_title_raw, 1300, 14, 9.5, 1, True)
    priors_title_size, _ = _fit_text(priors_title_raw, 330, 13, 8.5, 1, True)
    latent_title_size, _ = _fit_text(latent_title_raw, 430, 14.5, 9.0, 1, True)
    ai_title_size, _ = _fit_text(ai_title_raw, 330, 13.5, 8.5, 1, True)
    core_title = _esc(core_title_raw)
    priors_title = _esc(priors_title_raw)
    latent_title = _esc(latent_title_raw)
    ai_title = _esc(ai_title_raw)

    body.append(f'''
    <g id="layer-core" transform="translate(120, 305)">
      <rect x="0" y="0" width="1360" height="340" rx="16" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.2"/>
      <text x="24" y="28" font-family="{_esc(font)}" font-size="{core_title_size:.1f}" font-weight="bold" fill="#1E293B">
        {core_title}
      </text>
      
      <!-- Left Wing: Priors -->
      <g transform="translate(30, 48)">
        <rect width="360" height="276" rx="12" fill="url(#grad-priors)" stroke="#F59E0B" stroke-width="1.2"/>
        <rect width="360" height="28" rx="8" fill="#F59E0B"/>
        <text x="180" y="19" text-anchor="middle" font-family="{_esc(font)}" font-size="{priors_title_size:.1f}" font-weight="bold" fill="#FFFFFF">
          {priors_title}
        </text>
    ''')

    priors = spec.get("priors_items") or []
    for idx, item in enumerate(priors[:3]):
        y_it = 48 + idx * 70
        it_t = _esc(item.get("title") or "")
        it_d = _esc(item.get("desc") or "")
        it_t_size, it_t_lines = _fit_text(item.get("title") or "", 292, 13, 10, 1, True)
        it_d_size, it_d_lines = _fit_text(item.get("desc") or "", 292, 13.0, 9, 2, False)
        body.append(f'''
        <g transform="translate(20, {y_it})">
          <rect width="320" height="64" rx="8" fill="#FFFFFF" stroke="#FDE68A" stroke-width="1"/>
          <text x="14" y="24" font-family="{_esc(font)}" font-size="{it_t_size:.1f}" font-weight="bold" fill="#B45309">{_tspans([_esc(line) for line in it_t_lines], it_t_size, 14, 24)}</text>
          <text x="14" y="44" font-family="{_esc(font)}" font-size="{it_d_size:.1f}" fill="#78350F">{_tspans([_esc(line) for line in it_d_lines], it_d_size, 14, 44)}</text>
        </g>
        ''')
    body.append('''
        <path d="M360 132 L420 132" stroke="#F59E0B" stroke-width="2.5" marker-end="url(#arr-gray)"/>
        <text x="390" y="122" text-anchor="middle" font-family="Times New Roman" font-size="11.5" fill="#B45309" font-weight="bold">Physics Loss</text>
      </g>
    ''')

    # Center: Latent Inference
    body.append(f'''
      <g transform="translate(450, 48)">
        <rect width="460" height="276" rx="16" fill="url(#grad-core)" stroke="#0D9488" stroke-width="2"/>
        <rect width="460" height="32" rx="12" fill="#0D9488"/>
        <text x="230" y="22" text-anchor="middle" font-family="{_esc(font)}" font-size="{latent_title_size:.1f}" font-weight="bold" fill="#FFFFFF">
          {latent_title}
        </text>
    ''')
    latent = spec.get("latent_items") or []
    for idx, item in enumerate(latent[:3]):
        y_it = 48 + idx * 72
        it_num = _esc(item.get("num") or str(idx + 1))
        it_t = _esc(item.get("title") or "")
        it_d = _esc(item.get("desc") or "")
        it_t_size, it_t_lines = _fit_text(item.get("title") or "", 344, 13.5, 10, 1, True)
        it_d_size, it_d_lines = _fit_text(item.get("desc") or "", 344, 13.0, 9, 2, False)
        circ_col = "#0D9488" if idx == 0 else ("#0284C7" if idx == 1 else "#9333EA")
        circ_bg = "#CCFBF1" if idx == 0 else ("#E0F2FE" if idx == 1 else "#F3E8FF")
        t_col = "#0F766E" if idx == 0 else ("#0369A1" if idx == 1 else "#7E22CE")
        body.append(f'''
        <g transform="translate(30, {y_it})">
          <rect width="400" height="66" rx="10" fill="#FFFFFF" stroke="#99F6E4" stroke-width="1.2"/>
          <circle cx="28" cy="31" r="14" fill="{circ_bg}"/>
          <text x="28" y="36" text-anchor="middle" font-family="{_esc(font)}" font-size="13" font-weight="bold" fill="{circ_col}">{it_num}</text>
          <text x="56" y="25" font-family="{_esc(font)}" font-size="{it_t_size:.1f}" font-weight="bold" fill="{t_col}">{_tspans([_esc(line) for line in it_t_lines], it_t_size, 56, 25)}</text>
          <text x="56" y="45" font-family="{_esc(font)}" font-size="{it_d_size:.1f}" fill="#475569">{_tspans([_esc(line) for line in it_d_lines], it_d_size, 56, 45)}</text>
        </g>
        ''')
    body.append('</g>')

    # Right: AI Wing
    body.append(f'''
      <g transform="translate(970, 48)">
        <rect width="360" height="276" rx="12" fill="url(#grad-ai)" stroke="#6366F1" stroke-width="1.2"/>
        <rect width="360" height="28" rx="8" fill="#6366F1"/>
        <text x="180" y="19" text-anchor="middle" font-family="{_esc(font)}" font-size="{ai_title_size:.1f}" font-weight="bold" fill="#FFFFFF">
          {ai_title}
        </text>
    ''')
    ai_items = spec.get("ai_items") or []
    for idx, item in enumerate(ai_items[:3]):
        y_it = 48 + idx * 70
        it_t = _esc(item.get("title") or "")
        it_d = _esc(item.get("desc") or "")
        it_t_size, it_t_lines = _fit_text(item.get("title") or "", 292, 13, 10, 1, True)
        it_d_size, it_d_lines = _fit_text(item.get("desc") or "", 292, 13.0, 9, 2, False)
        body.append(f'''
        <g transform="translate(20, {y_it})">
          <rect width="320" height="64" rx="8" fill="#FFFFFF" stroke="#C7D2FE" stroke-width="1"/>
          <text x="14" y="24" font-family="{_esc(font)}" font-size="{it_t_size:.1f}" font-weight="bold" fill="#4338CA">{_tspans([_esc(line) for line in it_t_lines], it_t_size, 14, 24)}</text>
          <text x="14" y="44" font-family="{_esc(font)}" font-size="{it_d_size:.1f}" fill="#312E81">{_tspans([_esc(line) for line in it_d_lines], it_d_size, 14, 44)}</text>
        </g>
        ''')
    body.append('''
        <path d="M0 132 L-60 132" stroke="#6366F1" stroke-width="2.5" marker-end="url(#arr-gray)"/>
        <text x="-30" y="122" text-anchor="middle" font-family="Times New Roman" font-size="11.5" fill="#4338CA" font-weight="bold">Attention</text>
      </g>
    </g>
    ''')

    # Action Dispatch Ribbon: full width, one straight arrow per actuation card
    entities = spec.get("embodied_entities") or []
    n_ent = max(1, len(entities))
    ent_w = min(260.0, (1320.0 - (n_ent - 1) * 20.0) / n_ent)
    x_card_start = 145.0
    action_formula_raw = str(spec.get("action_dispatch_formula") or "ADAPTIVE CONTROL ACTION DISPATCH • u(t) = π( z_latent(t), S(t) )")
    action_size, _ = _fit_text(action_formula_raw, 1280, 13, 9, 1, True)
    action_formula = _esc(action_formula_raw)
    body.append(f'''
    <g transform="translate(140, 665)">
      <rect x="0" y="0" width="1320" height="26" rx="13" fill="url(#grad-stream)"/>
      <text x="660" y="17" text-anchor="middle" font-family="{_esc(font)}" font-size="{action_size:.1f}" font-weight="bold" fill="#0F172A">
        {action_formula}
      </text>
    </g>
    ''')
    for idx in range(min(len(entities), 4)):
        cx = x_card_start + idx * (ent_w + 20.0) + ent_w / 2
        body.append(f'<line x1="{cx:.1f}" y1="691" x2="{cx:.1f}" y2="770" '
                    f'stroke="{primary}" stroke-width="2" marker-end="url(#arr-teal)"/>')

    # Section C: Embodied Actuation Layer
    embodied_title_raw = str(spec.get("embodied_layer_title") or "C · MULTI-SCALE EMBODIED ACTUATION & PHYSICAL REALIZATION")
    embodied_title_size, _ = _fit_text(embodied_title_raw, 1300, 14, 9.5, 1, True)
    embodied_title = _esc(embodied_title_raw)
    body.append(f'''
    <g id="layer-embodiment" transform="translate(120, 770)">
      <rect x="0" y="0" width="1360" height="270" rx="16" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.2"/>
      <text x="24" y="28" font-family="{_esc(font)}" font-size="{embodied_title_size:.1f}" font-weight="bold" fill="#1E293B">
        {embodied_title}
      </text>
    </g>
    ''')

    for idx, ent in enumerate(entities[:4]):
        e_id = ent.get("id") or f"entity{idx}"
        e_title_raw = str(ent.get("title") or "")
        e_desc_raw = str(ent.get("desc") or "")
        e_title_size, _ = _fit_text(e_title_raw, (ent_w - 24) * 0.90, 14, 9.0, 1, True)
        e_desc_size, e_desc_lines = _fit_text(e_desc_raw, (ent_w - 20) * 0.88, 12.5, 9.0, 2, False)
        e_title = _esc(e_title_raw)
        e_desc = _esc(e_desc_raw)
        x_c = x_card_start + idx * (ent_w + 20.0)
        
        asset_tuple = assets.get(e_id)
        if asset_tuple:
            svg_raw, aw, ah = asset_tuple
            inner = compose._clean_asset(svg_raw)
            scale = min((ent_w - 20) / aw, 150 / ah)
            tx = x_c + (ent_w - aw * scale) / 2
            ty = 812 + (150 - ah * scale) / 2
            rendered_inner = f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.4f})">{inner}</g>'
        else:
            rendered_inner = entity_glyph(ent, x_c + ent_w / 2, 812 + 75,
                                          min(96.0, ent_w - 40), secondary)

        body.append(f'''
        <g>
          <rect x="{x_c:.1f}" y="805" width="{ent_w:.1f}" height="215" rx="12" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1.5"/>
          {rendered_inner}
          <text x="{x_c + ent_w/2:.1f}" y="974" text-anchor="middle" font-family="{_esc(font)}" font-size="{e_title_size:.1f}" font-weight="bold" fill="#0F172A" data-box="{x_c:.1f},805,{ent_w:.1f},215">{e_title}</text>
          {f'<text x="{x_c + ent_w/2:.1f}" y="992" text-anchor="middle" font-family="{_esc(font)}" font-size="{e_desc_size:.1f}" fill="#475569" data-box="{x_c:.1f},805,{ent_w:.1f},215">{_tspans([_esc(line) for line in e_desc_lines], e_desc_size, x_c + ent_w/2, 992, 1.0)}</text>' if e_desc else ''}
          <line x1="{x_c + ent_w/2:.1f}" y1="1020" x2="{x_c + ent_w/2:.1f}" y2="1045" stroke="#94A3B8" stroke-width="1.8" marker-end="url(#arr-gray)"/>
        </g>
        ''')

    # Environment Interaction Base
    env_text = _esc(spec.get("environment_interaction") or "PHYSICAL ENVIRONMENT & UNSTRUCTURED TERRAIN CONTACT INTERACTION")
    body.append(f'''
    <g transform="translate(140, 1050)">
      <rect x="0" y="0" width="1320" height="28" rx="8" fill="#F1F5F9" stroke="#94A3B8" stroke-width="1.2" stroke-dasharray="6 4"/>
      <text x="660" y="19" text-anchor="middle" font-family="{_esc(font)}" font-size="12.5" font-weight="bold" fill="#475569" letter-spacing="1">
        {env_text}
      </text>
    </g>
    ''')

    # Global Bilateral Feedback Loops: horizontal, readable labels in the
    # margins (vertical pills were hard to read and failed the model review).
    left_feed_raw = str(spec.get("left_feedback") or "CLOSED-LOOP RECEPTIVE FEEDBACK: CONTACT & DEFORMATION")
    right_feed_raw = str(spec.get("right_feedback") or "ADAPTIVE POLICY UPDATE & CONTINUAL LEARNING LOOP")
    box_w = 92.0
    left_size, left_lines = _fit_text(left_feed_raw, box_w - 16, 8.6, 6.4, max_lines=5, bold=True)
    right_size, right_lines = _fit_text(right_feed_raw, box_w - 16, 8.6, 6.4, max_lines=5, bold=True)
    left_h = len(left_lines) * left_size + (len(left_lines) - 1) * 1.5 + 18
    right_h = len(right_lines) * right_size + (len(right_lines) - 1) * 1.5 + 18
    left_x, left_y = 24.0, 550.0
    right_x, right_y = 1484.0, 550.0

    body.append(f'''
    <g id="feedback-left">
      <circle cx="140" cy="1064" r="3.2" fill="#0D9488"/>
      <path d="M140 1064 C60 1064 60 186 100 186 L121 186" fill="none" stroke="#0D9488" stroke-width="3.5" stroke-dasharray="10 5" marker-end="url(#arr-loop)"/>
      <circle cx="121" cy="186" r="3.2" fill="#0D9488"/>
    </g>
    
    <g id="feedback-right">
      <circle cx="1460" cy="1064" r="3.2" fill="#2563EB"/>
      <path d="M1460 1064 C1540 1064 1540 186 1500 186 L1479 186" fill="none" stroke="#2563EB" stroke-width="3.5" stroke-dasharray="10 5" marker-end="url(#arr-loop-2)"/>
      <circle cx="1479" cy="186" r="3.2" fill="#2563EB"/>
    </g>
    ''')

    content = "".join(body)
    content = (content.replace("#0D9488", primary)
                      .replace("#2563EB", secondary)
                      .replace("#6366F1", secondary)
                      .replace("#F59E0B", accent)
                      .replace("#D97706", accent))

    req_w, req_h = (canvas or [W, H])[:2]
    req_w, req_h = float(req_w), float(req_h)
    scale = min(req_w / W, req_h / H)
    tx = (req_w - W * scale) / 2
    ty = (req_h - H * scale) / 2
    shape = (viewport_shape or "rect").lower()
    if shape in ("circle", "ellipse"):
        # Round viewports cut the corners of a dense framework. Fit the whole
        # figure inside the inscribed rectangle of the actual clip shape.
        if shape == "circle":
            side = (min(req_w, req_h) - 28) / math.sqrt(2)
            scale = min(side / W, side / H)
        else:
            scale = min((req_w - 28) / (W * math.sqrt(2)),
                        (req_h - 28) / (H * math.sqrt(2)))
        tx = (req_w - W * scale) / 2
        ty = (req_h - H * scale) / 2
    inner = f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.5f})">{content}</g>'

    defs = []
    if shape in ("card", "circle", "ellipse"):
        if shape == "card":
            clip = f'<rect x="14" y="14" width="{req_w-28:.1f}" height="{req_h-28:.1f}" rx="24"/>'
        elif shape == "circle":
            r = min(req_w, req_h) / 2 - 14
            clip = f'<circle cx="{req_w/2:.1f}" cy="{req_h/2:.1f}" r="{r:.1f}"/>'
        else:
            clip = (f'<ellipse cx="{req_w/2:.1f}" cy="{req_h/2:.1f}" '
                    f'rx="{req_w/2-14:.1f}" ry="{req_h/2-14:.1f}"/>')
        defs.append(f'<clipPath id="viewport-clip">{clip}</clipPath>')
        inner = f'<g clip-path="url(#viewport-clip)">{inner}</g>'

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<svg xmlns="http://www.w3.org/2000/svg" width="{req_w:.0f}" height="{req_h:.0f}" '
             f'viewBox="0 0 {req_w:.0f} {req_h:.0f}">']
    if defs:
        parts.append(f'<defs>{"".join(defs)}</defs>')
    parts.append(f'<rect width="{req_w:.0f}" height="{req_h:.0f}" fill="#FAFCFD"/>')
    parts.append(inner)
    parts.append("</svg>")
    return (chr(10).join(parts) + chr(10)).encode("utf-8")

def render_framework(text: str, config: dict, on_stage=None) -> tuple[bytes, dict]:
    def stage(name, detail=None):
        if on_stage:
            on_stage(name, detail)

    report = {"framework": True, "stages": {}}
    stage("plan_scene", "planning multi-tier closed-loop framework")
    spec = plan_framework(text, config)
    report["spec"] = spec

    style_dna = config.get("style_dna") or {}
    suffix = style_dna.get("entity_style_prompt_suffix") or ""
    palette = style_dna.get("palette") if isinstance(style_dna.get("palette"), dict) else None
    entities = spec.get("embodied_entities") or []
    assets = {}
    engine_counts = {}
    total = len(entities)
    use_images = config.get("illustration_mode") != "vector"
    for index, entity in enumerate(entities, 1):
        if not use_images:
            # Vector mode still needs an icon per entity; otherwise the cards
            # render as empty text boxes (the critic flags missing icons).
            glyph = entity_glyph(entity, 50, 50, 78,
                                 (palette or {}).get("primary", "#3F5A6B"))
            asset_svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                         + glyph + '</svg>').encode("utf-8")
            assets[entity["id"]] = (asset_svg, 100.0, 100.0)
            engine_counts["vector-glyph"] = engine_counts.get("vector-glyph", 0) + 1
            continue
        stage("generate", f"实体 {index}/{total}：{entity.get('title') or entity['id']}")
        prompt = entity["prompt"]
        if suffix:
            prompt += chr(10) + str(suffix)
        try:
            png = pipeline.generate_raw(prompt, config)
        except Exception:
            # Retry once with a short prompt: long prompts are the usual cause
            # of an image-backend timeout.
            png = pipeline.generate_raw(
                f"Flat 2D scientific vector icon of {entity.get('title') or entity['id']}, "
                "isolated, pure white background, no text, no labels, centered.", config)
        cut = compose.cutout(png)
        svg, aw, ah = compose.asset_image(cut)
        assets[entity["id"]] = (svg, aw, ah)
        engine_counts["image"] = engine_counts.get("image", 0) + 1

    report["stages"]["generate"] = {"entities": len(assets), "engines": engine_counts}
    stage("assemble", "assembling publication-grade framework")
    font = str(config.get("font") or "Times New Roman")
    canvas = config.get("canvas") if config.get("canvas_user") else None
    shape = config.get("viewport_shape") or "rect"

    def build():
        return build_framework_svg(spec, assets, font, canvas=canvas,
                                   viewport_shape=shape, palette=palette)

    def review_svg(data):
        try:
            import review
            return review.findings(data, None)
        except Exception:
            return []

    import model_review
    def context_fn(current_spec, kind):
        return {
            "kind": "closed_loop_framework",
            "title": current_spec.get("title"),
            "canvas": canvas or [W, H],
            "layers": [current_spec.get("sensing_layer_title"),
                       current_spec.get("core_layer_title"),
                       current_spec.get("embodied_layer_title")],
            "modalities": [m.get("title") for m in current_spec.get("sensing_modalities") or []],
            "core_items": [i.get("title") for key in ("priors_items", "latent_items", "ai_items")
                           for i in (current_spec.get(key) or [])],
            "entities": [e.get("title") for e in current_spec.get("embodied_entities") or []],
        }
    final_svg, rework = model_review.run_loop(
        spec, build, _shrink_framework_spec, review_svg, context_fn,
        config, "framework", on_stage=stage, max_rounds=10)
    report["rework"] = rework
    pipeline._check_svg(final_svg, allow_image=bool(assets))
    report["stages"]["assemble"] = {"bytes": len(final_svg)}
    report["bytes"] = len(final_svg)
    return final_svg, report


def _vector_glyph(label: str, cx: float, cy: float, size: float, color: str) -> str:
    """Simple line glyph used by the pure-vector mode (no raster assets)."""
    key = (label or "").lower()
    color = safe_color(color, "#3F5A6B")
    r = size / 2
    parts = []
    if any(word in key for word in ("gear", "transmission", "motor", "gearbox")):
        teeth = 12
        import math as _m
        for i in range(teeth):
            a = 2 * _m.pi * i / teeth
            x1 = cx + _m.cos(a) * r * 0.78
            y1 = cy + _m.sin(a) * r * 0.78
            x2 = cx + _m.cos(a) * r
            y2 = cy + _m.sin(a) * r
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                         f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.66:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.26:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.6"/>')
    elif (any(word in key for word in ("sensor", "sensing", "camera", "proprio"))
          and not any(word in key for word in ("detector", "spectrometer", "analyzer",
                                               "detection", "assay", "reader",
                                               "manipulator", "robotic arm", "robot arm",
                                               "hand", "finger", "tactile"))):
        for k in range(3):
            rad = r * (0.35 + 0.28 * k)
            parts.append(f'<path d="M {cx - rad:.1f} {cy + rad * 0.55:.1f} '
                         f'A {rad:.1f} {rad:.1f} 0 0 1 {cx + rad:.1f} {cy + rad * 0.55:.1f}" '
                         f'fill="none" stroke="{color}" stroke-width="1.8"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy + r * 0.62:.1f}" r="2.6" fill="{color}"/>')
    elif (any(word in key for word in ("soft gripper", "soft robotic gripper",
                                       "compliant gripper", "segmented finger"))
          and not any(word in key for word in ("hand", "anthropomorphic"))):
        # Soft gripper: three compliant fingers on a palm, tendon routing.
        for k, dx in enumerate((-0.38, 0.0, 0.38)):
            x = cx + dx * r
            parts.append(f'<path d="M {x:.1f} {cy + r * 0.58:.1f} '
                         f'C {x - r * 0.18:.1f} {cy + r * 0.2:.1f} '
                         f'{x - r * 0.12:.1f} {cy - r * 0.2:.1f} '
                         f'{x:.1f} {cy - r * 0.58:.1f}" fill="none" '
                         f'stroke="{color}" stroke-width="3.2" stroke-linecap="round"/>')
            parts.append(f'<circle cx="{x:.1f}" cy="{cy - r * 0.58:.1f}" '
                         f'r="{r * 0.055:.1f}" fill="{color}"/>')
        parts.append(f'<rect x="{cx - r * 0.52:.1f}" y="{cy + r * 0.5:.1f}" '
                     f'width="{r * 1.04:.1f}" height="{r * 0.2:.1f}" rx="{r * 0.06:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<line x1="{cx:.1f}" y1="{cy + r * 0.62:.1f}" '
                     f'x2="{cx:.1f}" y2="{cy - r * 0.72:.1f}" '
                     f'stroke="{color}" stroke-width="1.2" stroke-dasharray="3 2"/>')
    elif any(word in key for word in ("gripper", "grasp", "jaw")):
        # Two parallel jaws closing on a part.
        parts.append(f'<path d="M {cx - r * 0.62:.1f} {cy - r * 0.55:.1f} '
                     f'L {cx - r * 0.2:.1f} {cy - r * 0.55:.1f} '
                     f'L {cx - r * 0.2:.1f} {cy + r * 0.35:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')
        parts.append(f'<path d="M {cx + r * 0.62:.1f} {cy - r * 0.55:.1f} '
                     f'L {cx + r * 0.2:.1f} {cy - r * 0.55:.1f} '
                     f'L {cx + r * 0.2:.1f} {cy + r * 0.35:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy + r * 0.12:.1f}" r="{r * 0.2:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.8"/>')
        parts.append(f'<line x1="{cx - r * 0.45:.1f}" y1="{cy + r * 0.7:.1f}" '
                     f'x2="{cx + r * 0.45:.1f}" y2="{cy + r * 0.7:.1f}" '
                     f'stroke="{color}" stroke-width="2"/>')
    elif any(word in key for word in ("mobile base", "mobile manipulator", "wheeled",
                                      "omnidirectional", "terrain adapt")):
        # Wheeled mobile base: chassis, two drive wheels, caster.
        parts.append(f'<rect x="{cx - r * 0.62:.1f}" y="{cy - r * 0.2:.1f}" '
                     f'width="{r * 1.24:.1f}" height="{r * 0.46:.1f}" rx="{r * 0.08:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2.2"/>')
        for wx in (cx - r * 0.38, cx + r * 0.38):
            parts.append(f'<circle cx="{wx:.1f}" cy="{cy + r * 0.5:.1f}" '
                         f'r="{r * 0.2:.1f}" fill="#FFFFFF" stroke="{color}" stroke-width="2"/>')
            parts.append(f'<circle cx="{wx:.1f}" cy="{cy + r * 0.5:.1f}" '
                         f'r="{r * 0.06:.1f}" fill="{color}"/>')
        parts.append(f'<line x1="{cx - r * 0.2:.1f}" y1="{cy + r * 0.2:.1f}" '
                     f'x2="{cx - r * 0.2:.1f}" y2="{cy - r * 0.5:.1f}" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx - r * 0.2:.1f}" cy="{cy - r * 0.5:.1f}" '
                     f'r="{r * 0.1:.1f}" fill="none" stroke="{color}" stroke-width="1.8"/>')
    elif (any(word in key for word in ("manipulator", "robotic arm", "robot arm",
                                       "articulated", "revolute joint", "6-dof",
                                       "six-degree", "serial link"))
          and not any(word in key for word in ("hand", "finger", "gripper", "grasp"))):
        # Serial-link robot arm: base, two links, revolute joints, end flange.
        base_y = cy + r * 0.82
        j1 = (cx - r * 0.38, cy + r * 0.52)
        j2 = (cx + r * 0.02, cy - r * 0.02)
        tip = (cx + r * 0.58, cy - r * 0.55)
        parts.append(f'<line x1="{cx - r * 0.62:.1f}" y1="{base_y:.1f}" '
                     f'x2="{cx + r * 0.3:.1f}" y2="{base_y:.1f}" '
                     f'stroke="{color}" stroke-width="2.4" stroke-linecap="round"/>')
        parts.append(f'<line x1="{cx - r * 0.1:.1f}" y1="{base_y:.1f}" '
                     f'x2="{j1[0]:.1f}" y2="{j1[1]:.1f}" '
                     f'stroke="{color}" stroke-width="2.6" stroke-linecap="round"/>')
        parts.append(f'<line x1="{j1[0]:.1f}" y1="{j1[1]:.1f}" '
                     f'x2="{j2[0]:.1f}" y2="{j2[1]:.1f}" '
                     f'stroke="{color}" stroke-width="2.6" stroke-linecap="round"/>')
        parts.append(f'<line x1="{j2[0]:.1f}" y1="{j2[1]:.1f}" '
                     f'x2="{tip[0]:.1f}" y2="{tip[1]:.1f}" '
                     f'stroke="{color}" stroke-width="2.6" stroke-linecap="round"/>')
        for jx, jy in (j1, j2):
            parts.append(f'<circle cx="{jx:.1f}" cy="{jy:.1f}" r="{r * 0.13:.1f}" '
                         f'fill="#FFFFFF" stroke="{color}" stroke-width="1.8"/>')
        parts.append(f'<rect x="{tip[0] - r * 0.14:.1f}" y="{tip[1] - r * 0.18:.1f}" '
                     f'width="{r * 0.28:.1f}" height="{r * 0.24:.1f}" rx="{r * 0.04:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.6"/>')
    elif any(word in key for word in ("hand", "finger", "tactile", "phalange")):
        # Dexterous hand: palm, four fingers, opposing thumb, tactile dots.
        palm_x, palm_y = cx - r * 0.34, cy - r * 0.05
        palm_w, palm_h = r * 0.62, r * 0.55
        parts.append(f'<rect x="{palm_x:.1f}" y="{palm_y:.1f}" '
                     f'width="{palm_w:.1f}" height="{palm_h:.1f}" rx="{r * 0.1:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        for k in range(4):
            fx = palm_x + r * 0.08 + k * r * 0.15
            top = cy - r * 0.55 - (r * 0.06 if k in (1, 2) else 0)
            parts.append(f'<line x1="{fx:.1f}" y1="{palm_y:.1f}" '
                         f'x2="{fx:.1f}" y2="{top:.1f}" stroke="{color}" '
                         f'stroke-width="2" stroke-linecap="round"/>')
            parts.append(f'<circle cx="{fx:.1f}" cy="{top:.1f}" r="{r * 0.05:.1f}" '
                         f'fill="{color}"/>')
        parts.append(f'<line x1="{palm_x:.1f}" y1="{palm_y + r * 0.18:.1f}" '
                     f'x2="{cx - r * 0.66:.1f}" y2="{palm_y + r * 0.02:.1f}" '
                     f'stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>')
        for k in range(3):
            parts.append(f'<circle cx="{palm_x + r * 0.14 + k * r * 0.16:.1f}" '
                         f'cy="{palm_y + r * 0.34:.1f}" r="{r * 0.035:.1f}" fill="{color}"/>')
    elif any(word in key for word in ("joint module", "variable-stiffness", "pulley",
                                      "compression spring", "series-elastic joint",
                                      "antagonistic")):
        # Rotary joint: two link stubs meeting a bolted bearing race.
        parts.append(f'<line x1="{cx - r * 0.92:.1f}" y1="{cy:.1f}" '
                     f'x2="{cx - r * 0.3:.1f}" y2="{cy:.1f}" '
                     f'stroke="{color}" stroke-width="2.8" stroke-linecap="round"/>')
        parts.append(f'<line x1="{cx + r * 0.3:.1f}" y1="{cy:.1f}" '
                     f'x2="{cx + r * 0.92:.1f}" y2="{cy:.1f}" '
                     f'stroke="{color}" stroke-width="2.8" stroke-linecap="round"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.4:.1f}" '
                     f'fill="#FFFFFF" stroke="{color}" stroke-width="2.4"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.16:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.8"/>')
        import math as _m
        for k in range(6):
            a = _m.pi * k / 3
            bx = cx + _m.cos(a) * r * 0.28
            by = cy + _m.sin(a) * r * 0.28
            parts.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{r * 0.045:.1f}" '
                         f'fill="{color}"/>')
    elif (any(word in key for word in ("前驱体", "配制", "搅拌", "烧杯"))
          and not any(word in key for word in ("交联", "凝胶", "掩模", "封装", "图案"))):
        parts.append(f'<path d="M {cx - r * 0.6:.1f} {cy - r * 0.68:.1f} '
                     f'L {cx - r * 0.48:.1f} {cy + r * 0.72:.1f} '
                     f'Q {cx:.1f} {cy + r * 0.82:.1f} {cx + r * 0.48:.1f} {cy + r * 0.72:.1f} '
                     f'L {cx + r * 0.6:.1f} {cy - r * 0.68:.1f} Z" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<line x1="{cx - r * 0.62:.1f}" y1="{cy - r * 0.62:.1f}" '
                     f'x2="{cx + r * 0.62:.1f}" y2="{cy - r * 0.62:.1f}" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<rect x="{cx - r * 0.5:.1f}" y="{cy + r * 0.08:.1f}" '
                     f'width="{r * 0.92:.1f}" height="{r * 0.5:.1f}" '
                     f'fill="{color}" opacity="0.22"/>')
        for k in range(3):
            gy = cy + r * 0.2 + k * r * 0.15
            parts.append(f'<line x1="{cx + r * 0.34:.1f}" y1="{gy:.1f}" '
                         f'x2="{cx + r * 0.48:.1f}" y2="{gy:.1f}" '
                         f'stroke="{color}" stroke-width="1.4"/>')
        parts.append(f'<line x1="{cx - r * 0.2:.1f}" y1="{cy + r * 0.34:.1f}" '
                     f'x2="{cx - r * 0.05:.1f}" y2="{cy + r * 0.34:.1f}" '
                     f'stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>')
        parts.append(f'<line x1="{cx - r * 0.2:.1f}" y1="{cy + r * 0.34:.1f}" '
                     f'x2="{cx - r * 0.26:.1f}" y2="{cy + r * 0.5:.1f}" '
                     f'stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>')
        parts.append(f'<line x1="{cx - r * 0.05:.1f}" y1="{cy + r * 0.34:.1f}" '
                     f'x2="{cx + r * 0.02:.1f}" y2="{cy + r * 0.5:.1f}" '
                     f'stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>')
        parts.append(f'<path d="M {cx + r * 0.25:.1f} {cy - r * 0.88:.1f} '
                     f'L {cx + r * 0.1:.1f} {cy - r * 0.62:.1f} '
                     f'L {cx + r * 0.2:.1f} {cy - r * 0.38:.1f} '
                     f'L {cx + r * 0.42:.1f} {cy - r * 0.58:.1f} Z" fill="{color}" opacity="0.55"/>')
    elif (any(word in key for word in ("交联", "凝胶"))
          and not any(word in key for word in ("tensile", "testing apparatus",
                                               "readout", "表征"))):
        parts.append(f'<rect x="{cx - r * 0.7:.1f}" y="{cy - r * 0.65:.1f}" '
                     f'width="{r * 1.4:.1f}" height="{r * 1.3:.1f}" rx="{r * 0.14:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        for dx, dy in ((-0.35, -0.28), (0.0, -0.36), (0.34, -0.18), (-0.2, 0.18), (0.28, 0.3), (0.0, 0.0)):
            parts.append(f'<circle cx="{cx + dx * r:.1f}" cy="{cy + dy * r:.1f}" '
                         f'r="{r * 0.08:.1f}" fill="none" stroke="{color}" stroke-width="1.5"/>')
        for a, b in ((-0.35, 0), (0.0, 0), (0.35, 0)):
            parts.append(f'<line x1="{cx + a * r:.1f}" y1="{cy - r * 0.42:.1f}" '
                         f'x2="{cx + a * r:.1f}" y2="{cy + r * 0.38:.1f}" '
                         f'stroke="{color}" stroke-width="1.2"/>')
        parts.append(f'<path d="M {cx - r * 0.52:.1f} {cy:.1f} '
                     f'L {cx + r * 0.52:.1f} {cy:.1f} M {cx:.1f} {cy - r * 0.5:.1f} '
                     f'L {cx:.1f} {cy + r * 0.5:.1f}" stroke="{color}" stroke-width="1.1"/>')
    elif any(word in key for word in ("封装", "表征", "探针")):
        parts.append(f'<rect x="{cx - r * 0.72:.1f}" y="{cy - r * 0.52:.1f}" '
                     f'width="{r * 1.44:.1f}" height="{r * 0.96:.1f}" rx="{r * 0.12:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<rect x="{cx - r * 0.62:.1f}" y="{cy - r * 0.40:.1f}" '
                     f'width="{r * 1.24:.1f}" height="{r * 0.70:.1f}" rx="{r * 0.08:.1f}" '
                     f'fill="{color}" opacity="0.12" stroke="{color}" stroke-width="1.2"/>')
        parts.append(f'<path d="M {cx + r * 0.72:.1f} {cy - r * 0.05:.1f} '
                     f'L {cx + r * 0.95:.1f} {cy - r * 0.05:.1f} '
                     f'L {cx + r * 0.95:.1f} {cy - r * 0.52:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<path d="M {cx - r * 0.9:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx - r * 0.6:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx - r * 0.42:.1f} {cy + r * 0.55:.1f} '
                     f'L {cx - r * 0.22:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx:.1f} {cy + r * 0.46:.1f} '
                     f'L {cx + r * 0.2:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx + r * 0.9:.1f} {cy + r * 0.75:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="1.7"/>')
    elif any(word in key for word in ("microstructure", "micropattern", "micropillar",
                                      "micro mold", "micro-mold", "soft mold", "软模", "微结构")):
        # Soft-mold imprint: micropillar array pressed into a gel slab.
        parts.append(f'<rect x="{cx - r * 0.78:.1f}" y="{cy - r * 0.58:.1f}" '
                     f'width="{r * 1.56:.1f}" height="{r * 0.42:.1f}" rx="{r * 0.05:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        for k in range(6):
            xx = cx - r * 0.62 + k * r * 0.22
            parts.append(f'<rect x="{xx:.1f}" y="{cy - r * 0.52:.1f}" '
                         f'width="{r * 0.13:.1f}" height="{r * 0.28:.1f}" '
                         f'fill="{color}" opacity="0.65"/>')
        parts.append(f'<path d="M {cx - r * 0.92:.1f} {cy - r * 0.3:.1f} '
                     f'L {cx + r * 0.92:.1f} {cy - r * 0.3:.1f}" stroke="{color}" '
                     f'stroke-width="1.5" stroke-dasharray="3 2"/>')
        parts.append(f'<rect x="{cx - r * 0.76:.1f}" y="{cy + r * 0.12:.1f}" '
                     f'width="{r * 1.52:.1f}" height="{r * 0.38:.1f}" rx="{r * 0.05:.1f}" '
                     f'fill="{color}" opacity="0.18" stroke="{color}" stroke-width="1.8"/>')
        for k in range(6):
            xx = cx - r * 0.62 + k * r * 0.22
            parts.append(f'<rect x="{xx:.1f}" y="{cy + r * 0.18:.1f}" '
                         f'width="{r * 0.13:.1f}" height="{r * 0.24:.1f}" '
                         f'fill="none" stroke="{color}" stroke-width="1.3"/>')
    elif any(word in key for word in ("photolith", "lithograph", "掩模", "mask", "图案化", "图案")):
        # Photomask, exposure gap and patterned hydrogel layer.
        parts.append(f'<rect x="{cx - r * 0.7:.1f}" y="{cy - r * 0.72:.1f}" '
                     f'width="{r * 1.4:.1f}" height="{r * 0.34:.1f}" rx="{r * 0.03:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        for k in range(4):
            xx = cx - r * 0.5 + k * r * 0.3
            parts.append(f'<rect x="{xx:.1f}" y="{cy - r * 0.66:.1f}" '
                         f'width="{r * 0.12:.1f}" height="{r * 0.22:.1f}" fill="{color}" opacity="0.7"/>')
        for dx in (-0.4, 0.0, 0.4):
            parts.append(f'<line x1="{cx + dx * r:.1f}" y1="{cy - r * 0.28:.1f}" '
                         f'x2="{cx + dx * r:.1f}" y2="{cy + r * 0.12:.1f}" '
                         f'stroke="{color}" stroke-width="1.6" stroke-dasharray="4 3"/>')
        for yy, op in ((0.24, 0.20), (0.43, 0.55), (0.64, 0.9)):
            parts.append(f'<rect x="{cx - r * 0.78:.1f}" y="{cy + r * yy:.1f}" '
                         f'width="{r * 1.56:.1f}" height="{r * 0.1:.1f}" '
                         f'fill="{color}" opacity="{op}" stroke="{color}" stroke-width="1.1"/>')
        for k in range(4):
            xx = cx - r * 0.52 + k * r * 0.3
            parts.append(f'<line x1="{xx:.1f}" y1="{cy + r * 0.26:.1f}" '
                         f'x2="{xx:.1f}" y2="{cy + r * 0.42:.1f}" '
                         f'stroke="{color}" stroke-width="1.1"/>')
    elif any(word in key for word in ("tensile testing", "tensile tester",
                                      "performance characterization",
                                      "performance testing", "拉伸", "表征测试")):
        # Two clamps gripping a strip with a load arrow and readout.
        parts.append(f'<rect x="{cx - r * 0.58:.1f}" y="{cy - r * 0.82:.1f}" '
                     f'width="{r * 0.32:.1f}" height="{r * 0.34:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<rect x="{cx + r * 0.26:.1f}" y="{cy - r * 0.82:.1f}" '
                     f'width="{r * 0.32:.1f}" height="{r * 0.34:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<line x1="{cx - r * 0.42:.1f}" y1="{cy - r * 0.48:.1f}" '
                     f'x2="{cx - r * 0.42:.1f}" y2="{cy + r * 0.18:.1f}" '
                     f'stroke="{color}" stroke-width="2.4"/>')
        parts.append(f'<line x1="{cx + r * 0.42:.1f}" y1="{cy - r * 0.48:.1f}" '
                     f'x2="{cx + r * 0.42:.1f}" y2="{cy + r * 0.18:.1f}" '
                     f'stroke="{color}" stroke-width="2.4"/>')
        parts.append(f'<rect x="{cx - r * 0.44:.1f}" y="{cy + r * 0.18:.1f}" '
                     f'width="{r * 0.88:.1f}" height="{r * 0.16:.1f}" '
                     f'fill="{color}" opacity="0.28"/>')
        parts.append(f'<path d="M {cx:.1f} {cy - r * 0.96:.1f} '
                     f'L {cx:.1f} {cy - r * 0.68:.1f}" stroke="{color}" '
                     f'stroke-width="2" marker-end=""/>')
        parts.append(f'<path d="M {cx - r * 0.5:.1f} {cy + r * 0.68:.1f} '
                     f'C {cx - r * 0.3:.1f} {cy + r * 0.3:.1f} {cx + r * 0.3:.1f} {cy + r * 0.3:.1f} '
                     f'{cx + r * 0.5:.1f} {cy + r * 0.68:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="1.8"/>')
        parts.append(f'<rect x="{cx - r * 0.5:.1f}" y="{cy + r * 0.76:.1f}" '
                     f'width="{r * 1.0:.1f}" height="{r * 0.2:.1f}" rx="{r * 0.04:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.6"/>')
        parts.append(f'<path d="M {cx - r * 0.4:.1f} {cy + r * 0.9:.1f} '
                     f'L {cx - r * 0.2:.1f} {cy + r * 0.82:.1f} '
                     f'L {cx:.1f} {cy + r * 0.94:.1f} '
                     f'L {cx + r * 0.2:.1f} {cy + r * 0.82:.1f} '
                     f'L {cx + r * 0.4:.1f} {cy + r * 0.9:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="1.4"/>')
    elif any(word in key for word in ("封装", "encapsulat", "sealed chip", "measurement probe",
                                      "readout", "probe", "表征", "探针",
                                      "tensile testing", "performance testing")):
        # Encapsulated microstructured chip, sealing rim and measurement trace.
        parts.append(f'<rect x="{cx - r * 0.72:.1f}" y="{cy - r * 0.52:.1f}" '
                     f'width="{r * 1.44:.1f}" height="{r * 0.96:.1f}" rx="{r * 0.12:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<rect x="{cx - r * 0.62:.1f}" y="{cy - r * 0.40:.1f}" '
                     f'width="{r * 1.24:.1f}" height="{r * 0.70:.1f}" rx="{r * 0.08:.1f}" '
                     f'fill="{color}" opacity="0.12" stroke="{color}" stroke-width="1.2"/>')
        for k in range(4):
            xx = cx - r * 0.45 + k * r * 0.28
            parts.append(f'<line x1="{xx:.1f}" y1="{cy - r * 0.36:.1f}" '
                         f'x2="{xx:.1f}" y2="{cy + r * 0.24:.1f}" '
                         f'stroke="{color}" stroke-width="1.2"/>')
        parts.append(f'<path d="M {cx + r * 0.72:.1f} {cy - r * 0.05:.1f} '
                     f'L {cx + r * 0.95:.1f} {cy - r * 0.05:.1f} '
                     f'L {cx + r * 0.95:.1f} {cy - r * 0.52:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx + r * 0.95:.1f}" cy="{cy - r * 0.55:.1f}" '
                     f'r="{r * 0.09:.1f}" fill="none" stroke="{color}" stroke-width="1.6"/>')
        parts.append(f'<path d="M {cx - r * 0.9:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx - r * 0.6:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx - r * 0.42:.1f} {cy + r * 0.55:.1f} '
                     f'L {cx - r * 0.22:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx:.1f} {cy + r * 0.46:.1f} '
                     f'L {cx + r * 0.2:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx + r * 0.9:.1f} {cy + r * 0.75:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="1.7"/>')
    elif any(word in key for word in ("chip", "electrode", "device", "pattern", "circuit")):
        parts.append(f'<rect x="{cx - r * 0.55:.1f}" y="{cy - r * 0.55:.1f}" '
                     f'width="{r * 1.1:.1f}" height="{r * 1.1:.1f}" rx="{r * 0.12:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        for k in range(4):
            off = -r * 0.33 + k * r * 0.22
            parts.append(f'<line x1="{cx - r * 0.72:.1f}" y1="{cy + off:.1f}" '
                         f'x2="{cx - r * 0.55:.1f}" y2="{cy + off:.1f}" stroke="{color}" stroke-width="1.8"/>')
            parts.append(f'<line x1="{cx + r * 0.55:.1f}" y1="{cy + off:.1f}" '
                         f'x2="{cx + r * 0.72:.1f}" y2="{cy + off:.1f}" stroke="{color}" stroke-width="1.8"/>')
    elif (any(word in key for word in ("交联", "crosslink", "cross-link", "hydrogel",
                                       "凝胶", "sol-gel", "network", "polymer",
                                       "mesh", "gel", "matrix"))
          and not any(word in key for word in ("tensile", "testing apparatus",
                                               "readout", "characterization"))):
        # connected network: nodes joined by short chains
        import math as _m
        nodes = []
        for k in range(5):
            a = -_m.pi / 2 + 2 * _m.pi * k / 5
            nodes.append((cx + _m.cos(a) * r * 0.62, cy + _m.sin(a) * r * 0.62))
        for k in range(5):
            x1, y1 = nodes[k]
            x2, y2 = nodes[(k + 1) % 5]
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                         f'stroke="{color}" stroke-width="1.6"/>')
            parts.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                         f'stroke="{color}" stroke-width="1.2" opacity="0.75"/>')
        for x1, y1 in nodes:
            parts.append(f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="{r * 0.12:.1f}" '
                         f'fill="none" stroke="{color}" stroke-width="1.8"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.16:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.8"/>')
    elif any(word in key for word in ("filter", "porous", "membrane filter", "filtration")):
        # Filter funnel over a membrane with a few passing droplets.
        parts.append(f'<path d="M {cx - r * 0.72:.1f} {cy - r * 0.72:.1f} '
                     f'L {cx + r * 0.72:.1f} {cy - r * 0.72:.1f} '
                     f'L {cx + r * 0.28:.1f} {cy - r * 0.05:.1f} '
                     f'L {cx - r * 0.28:.1f} {cy - r * 0.05:.1f} Z" fill="none" '
                     f'stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        parts.append(f'<rect x="{cx - r * 0.42:.1f}" y="{cy + r * 0.05:.1f}" '
                     f'width="{r * 0.84:.1f}" height="{r * 0.16:.1f}" rx="{r * 0.03:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.8"/>')
        for k in range(3):
            x = cx - r * 0.3 + k * r * 0.3
            parts.append(f'<line x1="{x:.1f}" y1="{cy + r * 0.05:.1f}" '
                         f'x2="{x:.1f}" y2="{cy + r * 0.21:.1f}" stroke="{color}" stroke-width="1.2"/>')
        for k in range(3):
            parts.append(f'<circle cx="{cx - r * 0.25 + k * r * 0.25:.1f}" '
                         f'cy="{cy + r * 0.62:.1f}" r="{r * 0.07:.1f}" fill="{color}"/>')
    elif any(word in key for word in ("test tube", "sample tube", "culture tube",
                                      "centrifuge tube", "pipette", "eppendorf",
                                      "microcentrifuge", "sample prep", "preparation")):
        # Sample tube with a pipette dispensing into it.
        # Straight-sided beaker, stir bar and a rotating solution.
        parts.append(f'<path d="M {cx - r * 0.6:.1f} {cy - r * 0.68:.1f} '
                     f'L {cx - r * 0.48:.1f} {cy + r * 0.72:.1f} '
                     f'Q {cx:.1f} {cy + r * 0.82:.1f} {cx + r * 0.48:.1f} {cy + r * 0.72:.1f} '
                     f'L {cx + r * 0.6:.1f} {cy - r * 0.68:.1f} Z" fill="none" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<line x1="{cx - r * 0.62:.1f}" y1="{cy - r * 0.62:.1f}" '
                     f'x2="{cx + r * 0.62:.1f}" y2="{cy - r * 0.62:.1f}" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<path d="M {cx - r * 0.49:.1f} {cy + r * 0.1:.1f} '
                     f'Q {cx:.1f} {cy + r * 0.25:.1f} {cx + r * 0.49:.1f} {cy + r * 0.1:.1f} '
                     f'L {cx + r * 0.45:.1f} {cy + r * 0.57:.1f} '
                     f'Q {cx:.1f} {cy + r * 0.68:.1f} {cx - r * 0.45:.1f} {cy + r * 0.57:.1f} Z" '
                     f'fill="{color}" opacity="0.25"/>')
        parts.append(f'<path d="M {cx - r * 0.26:.1f} {cy + r * 0.27:.1f} '
                     f'C {cx - r * 0.42:.1f} {cy + r * 0.42:.1f} {cx + r * 0.38:.1f} {cy + r * 0.48:.1f} '
                     f'{cx + r * 0.25:.1f} {cy + r * 0.27:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="1.5"/>')
        parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy + r * 0.55:.1f}" '
                     f'rx="{r * 0.17:.1f}" ry="{r * 0.045:.1f}" fill="{color}"/>')
        parts.append(f'<path d="M {cx + r * 0.25:.1f} {cy - r * 0.88:.1f} '
                     f'L {cx + r * 0.1:.1f} {cy - r * 0.62:.1f} '
                     f'L {cx + r * 0.2:.1f} {cy - r * 0.38:.1f} '
                     f'L {cx + r * 0.42:.1f} {cy - r * 0.58:.1f} Z" fill="{color}" opacity="0.55"/>')
        for dx, dy in ((-0.25, -0.2), (0.0, -0.05), (0.26, -0.18)):
            parts.append(f'<circle cx="{cx + dx * r:.1f}" cy="{cy + dy * r:.1f}" '
                         f'r="{r * 0.045:.1f}" fill="{color}"/>')
    elif any(word in key for word in ("column", "chromatograph", "electrophor",
                                      "separation", "centrifuge", "resin")):
        # Chromatography column with separated bands and collected fractions.
        parts.append(f'<rect x="{cx - r * 0.32:.1f}" y="{cy - r * 0.78:.1f}" '
                     f'width="{r * 0.64:.1f}" height="{r * 1.42:.1f}" rx="{r * 0.08:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<line x1="{cx - r * 0.4:.1f}" y1="{cy - r * 0.78:.1f}" '
                     f'x2="{cx + r * 0.4:.1f}" y2="{cy - r * 0.78:.1f}" '
                     f'stroke="{color}" stroke-width="2.2"/>')
        for k, opacity in enumerate((0.55, 0.35, 0.2)):
            y = cy - r * 0.35 + k * r * 0.3
            parts.append(f'<rect x="{cx - r * 0.26:.1f}" y="{y:.1f}" '
                         f'width="{r * 0.52:.1f}" height="{r * 0.12:.1f}" '
                         f'fill="{color}" opacity="{opacity}"/>')
        parts.append(f'<line x1="{cx:.1f}" y1="{cy + r * 0.64:.1f}" '
                     f'x2="{cx:.1f}" y2="{cy + r * 0.78:.1f}" '
                     f'stroke="{color}" stroke-width="1.8"/>')
        parts.append(f'<rect x="{cx - r * 0.12:.1f}" y="{cy + r * 0.78:.1f}" '
                     f'width="{r * 0.24:.1f}" height="{r * 0.2:.1f}" rx="{r * 0.03:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.6"/>')
    elif any(word in key for word in ("detector", "spectrometer", "spectrum", "analyzer",
                                      "analysis", "detection", "assay", "reader",
                                      "measurement", "meter")):
        # Benchtop detector: flow cell, beam and a peak trace on its screen.
        parts.append(f'<rect x="{cx - r * 0.78:.1f}" y="{cy - r * 0.5:.1f}" '
                     f'width="{r * 0.98:.1f}" height="{r * 0.95:.1f}" rx="{r * 0.08:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<rect x="{cx - r * 0.68:.1f}" y="{cy - r * 0.36:.1f}" '
                     f'width="{r * 0.6:.1f}" height="{r * 0.5:.1f}" rx="{r * 0.03:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.4"/>')
        parts.append(f'<path d="M {cx - r * 0.64:.1f} {cy + r * 0.06:.1f} '
                     f'L {cx - r * 0.5:.1f} {cy + r * 0.06:.1f} '
                     f'L {cx - r * 0.42:.1f} {cy - r * 0.24:.1f} '
                     f'L {cx - r * 0.32:.1f} {cy + r * 0.06:.1f} '
                     f'L {cx - r * 0.18:.1f} {cy + r * 0.06:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="1.6"/>')
        parts.append(f'<circle cx="{cx - r * 0.54:.1f}" cy="{cy - r * 0.22:.1f}" '
                     f'r="{r * 0.07:.1f}" fill="{color}"/>')
        parts.append(f'<line x1="{cx - r * 0.98:.1f}" y1="{cy - r * 0.22:.1f}" '
                     f'x2="{cx - r * 0.78:.1f}" y2="{cy - r * 0.22:.1f}" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<line x1="{cx + r * 0.2:.1f}" y1="{cy - r * 0.3:.1f}" '
                     f'x2="{cx + r * 0.2:.1f}" y2="{cy + r * 0.1:.1f}" '
                     f'stroke="{color}" stroke-width="1.6"/>')
    elif any(word in key for word in ("ligand", "secreted factor", "ev release",
                                      "extracellular vesicle", "vesicle release")):
        # EV / ligand cluster: several vesicles with cargo dots.
        for ox, oy, rad in ((-0.28, -0.12, 0.3), (0.22, -0.26, 0.2), (0.24, 0.24, 0.24)):
            vx, vy, vr = cx + ox * r, cy + oy * r, rad * r
            parts.append(f'<circle cx="{vx:.1f}" cy="{vy:.1f}" r="{vr:.1f}" '
                         f'fill="none" stroke="{color}" stroke-width="2"/>')
            parts.append(f'<circle cx="{vx - vr * 0.18:.1f}" cy="{vy - vr * 0.1:.1f}" '
                         f'r="{vr * 0.22:.1f}" fill="none" stroke="{color}" stroke-width="1.2"/>')
            parts.append(f'<circle cx="{vx + vr * 0.28:.1f}" cy="{vy + vr * 0.2:.1f}" '
                         f'r="{vr * 0.1:.1f}" fill="{color}"/>')
    elif any(word in key for word in ("receptor", "transmembrane", "ligand binding",
                                      "membrane binding")):
        # Membrane receptor: lipid bilayer, receptor body, bound ligand.
        for row_y in (cy - r * 0.14, cy + r * 0.14):
            parts.append(f'<line x1="{cx - r * 0.85:.1f}" y1="{row_y:.1f}" '
                         f'x2="{cx + r * 0.85:.1f}" y2="{row_y:.1f}" '
                         f'stroke="{color}" stroke-width="1.4" stroke-dasharray="4 3"/>')
        parts.append(f'<rect x="{cx - r * 0.15:.1f}" y="{cy - r * 0.5:.1f}" '
                     f'width="{r * 0.3:.1f}" height="{r * 0.95:.1f}" rx="{r * 0.06:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2.2"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy - r * 0.66:.1f}" r="{r * 0.12:.1f}" '
                     f'fill="{color}" opacity="0.45" stroke="{color}" stroke-width="1.4"/>')
        parts.append(f'<path d="M {cx - r * 0.24:.1f} {cy + r * 0.55:.1f} '
                     f'L {cx:.1f} {cy + r * 0.38:.1f} L {cx + r * 0.24:.1f} {cy + r * 0.55:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.8"/>')
    elif any(word in key for word in ("kinase", "cascade", "phosphoryl")):
        # Kinase cascade: three connected nodes with activating arrows.
        nodes = ((cx - r * 0.5, cy + r * 0.34), (cx, cy), (cx + r * 0.5, cy - r * 0.34))
        for nx, ny in nodes:
            parts.append(f'<rect x="{nx - r * 0.22:.1f}" y="{ny - r * 0.22:.1f}" '
                         f'width="{r * 0.44:.1f}" height="{r * 0.44:.1f}" '
                         f'rx="{r * 0.1:.1f}" fill="#FFFFFF" stroke="{color}" stroke-width="2"/>')
            parts.append(f'<circle cx="{nx:.1f}" cy="{ny:.1f}" r="{r * 0.07:.1f}" '
                         f'fill="{color}"/>')
        for index in range(len(nodes) - 1):
            x1, y1 = nodes[index]
            x2, y2 = nodes[index + 1]
            sx, sy = x1 + (x2 - x1) * 0.24, y1 + (y2 - y1) * 0.24
            ex, ey = x1 + (x2 - x1) * 0.76, y1 + (y2 - y1) * 0.76
            parts.append(f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" '
                         f'stroke="{color}" stroke-width="1.8"/>')
            parts.append(f'<path d="M {ex - r * 0.08:.1f} {ey - r * 0.08:.1f} '
                         f'L {ex:.1f} {ey:.1f} L {ex - r * 0.1:.1f} {ey + r * 0.02:.1f}" '
                         f'fill="none" stroke="{color}" stroke-width="1.6"/>')
    elif any(word in key for word in ("nuclear", "nucleus", "transcription",
                                      "gene expression", "tf ")):
        # Nucleus with pores and a transcription factor entering.
        parts.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{r * 0.62:.1f}" '
                     f'ry="{r * 0.5:.1f}" fill="none" stroke="{color}" stroke-width="2.2"/>')
        parts.append(f'<circle cx="{cx + r * 0.1:.1f}" cy="{cy + r * 0.05:.1f}" '
                     f'r="{r * 0.16:.1f}" fill="none" stroke="{color}" stroke-width="1.4"/>')
        import math as _m
        for k in range(6):
            angle = 2 * _m.pi * k / 6
            px = cx + _m.cos(angle) * r * 0.62
            py = cy + _m.sin(angle) * r * 0.5
            parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r * 0.055:.1f}" '
                         f'fill="#FFFFFF" stroke="{color}" stroke-width="1.2"/>')
        parts.append(f'<line x1="{cx - r * 0.95:.1f}" y1="{cy - r * 0.18:.1f}" '
                     f'x2="{cx - r * 0.48:.1f}" y2="{cy - r * 0.18:.1f}" '
                     f'stroke="{color}" stroke-width="2"/>')
        parts.append(f'<path d="M {cx - r * 0.58:.1f} {cy - r * 0.24:.1f} '
                     f'L {cx - r * 0.48:.1f} {cy - r * 0.18:.1f} '
                     f'L {cx - r * 0.58:.1f} {cy - r * 0.12:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="1.8"/>')
    elif any(word in key for word in ("cell", "vesicle", "exosome", "membrane",
                                      "receptor", "nucleus", "protein", "ligand",
                                      "pathway", "antibody", "enzyme")):
        # cell / vesicle: outer membrane, nucleus, surface receptors
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.72:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx - r * 0.08:.1f}" cy="{cy + r * 0.06:.1f}" '
                     f'r="{r * 0.26:.1f}" fill="none" stroke="{color}" stroke-width="1.6"/>')
        for a in (-0.9, 0.2, 1.3):
            import math as _m
            x1 = cx + _m.cos(a) * r * 0.72
            y1 = cy + _m.sin(a) * r * 0.72
            x2 = cx + _m.cos(a) * r * 0.95
            y2 = cy + _m.sin(a) * r * 0.95
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                         f'stroke="{color}" stroke-width="2"/>')
            parts.append(f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="{r * 0.07:.1f}" fill="{color}"/>')
    elif any(word in key for word in ("film", "layer", "coating", "encaps", "laminate",
                                      "sheet", "substrate", "electrode")):
        # stacked layers
        for k in range(3):
            y = cy - r * 0.5 + k * r * 0.42
            parts.append(f'<rect x="{cx - r * 0.8:.1f}" y="{y:.1f}" width="{r * 1.6:.1f}" '
                         f'height="{r * 0.3:.1f}" rx="{r * 0.06:.1f}" fill="none" '
                         f'stroke="{color}" stroke-width="1.8"/>')
    elif any(word in key for word in ("droplet", "particle", "bead", "sphere", "vesicle")):
        parts.append(f'<path d="M {cx - r * 0.7:.1f} {cy + r * 0.75:.1f} '
                     f'L {cx - r * 0.2:.1f} {cy - r * 0.1:.1f} L {cx + r * 0.45:.1f} {cy - r * 0.65:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>')
        parts.append(f'<path d="M {cx + r * 0.2:.1f} {cy - r * 0.45:.1f} '
                     f'L {cx + r * 0.7:.1f} {cy - r * 0.05:.1f}" fill="none" '
                     f'stroke="{color}" stroke-width="2.2" stroke-linecap="round"/>')
        parts.append(f'<circle cx="{cx - r * 0.72:.1f}" cy="{cy + r * 0.76:.1f}" r="3" fill="{color}"/>')
    elif any(word in key for word in ("droplet", "particle", "bead", "sphere")):
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.62:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx - r * 0.18:.1f}" cy="{cy - r * 0.2:.1f}" '
                     f'r="{r * 0.16:.1f}" fill="{color}" opacity="0.35"/>')
    else:
        # neutral entity node: ring + core + ticks (no envelope silhouette)
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.62:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r * 0.24:.1f}" '
                     f'fill="none" stroke="{color}" stroke-width="1.6"/>')
        for a in (0, 90, 180, 270):
            import math as _m
            rad = _m.radians(a)
            parts.append(f'<line x1="{cx + _m.cos(rad) * r * 0.62:.1f}" '
                         f'y1="{cy + _m.sin(rad) * r * 0.62:.1f}" '
                         f'x2="{cx + _m.cos(rad) * r * 0.82:.1f}" '
                         f'y2="{cy + _m.sin(rad) * r * 0.82:.1f}" '
                         f'stroke="{color}" stroke-width="1.6"/>')
    return "".join(parts)


def entity_glyph(entity: dict, cx: float, cy: float, size: float, color: str) -> str:
    """Pick a glyph from every semantic hint the planner produced.

    Short fields are authoritative: model prompts often say "不是烧杯" while
    describing a beaker, so the prompt is only consulted when the shorter
    fields do not resolve.
    """
    label = " ".join(str(entity.get(name) or "")
                     for name in ("glyph", "label", "title"))
    glyph = _vector_glyph(label, cx, cy, size, color)
    if glyph != _vector_glyph("", cx, cy, size, color):
        return glyph
    prompt = str(entity.get("prompt") or "")
    if prompt:
        # The planner writes the icon prompt on purpose ("one isolated
        # laboratory beaker"), while captions may mention neighboring steps
        # ("crosslinker added") that would hijack the keyword match.
        glyph = _vector_glyph(label + " " + re.split(r"[。;；]", prompt)[0],
                              cx, cy, size, color)
        if glyph != _vector_glyph("", cx, cy, size, color):
            return glyph
    for name in ("caption", "desc", "detail"):
        hint = str(entity.get(name) or "")
        if hint:
            glyph = _vector_glyph(hint, cx, cy, size, color)
            if glyph != _vector_glyph("", cx, cy, size, color):
                return glyph
    return _vector_glyph(label + " " + prompt, cx, cy, size, color)


def _shrink_framework_spec(spec: dict) -> None:
    """Text shortening is handled by the model repair patch; blind truncation
    introduced ellipses that the visual critic correctly rejected."""
    return None
