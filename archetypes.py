"""Publication-grade Scientific Figure Archetypes and Deep Style Transfer Engine.

Covers five canonical journal figure archetypes:
1. closed_loop: Embodied AI & cybernetic closed-loop perception-action systems
2. signal_pathway: Intracellular receptor activation & cascade pathway mechanisms
3. process_pipeline: Synthesis, fabrication, and step-by-step experimental methodologies
4. structural_anatomy: Multi-layer cross-sectional devices, metamaterials, and tissue anatomy
5. graphical_abstract: High-level overview, challenge vs. solution, and conceptual abstracts
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pipeline

ARCHETYPE_DESCRIPTIONS = {
    "closed_loop": {
        "name": "闭环推导与系统架构图 (Closed-Loop System Framework)",
        "journals": "Nature / ACS Nano / Science Robotics",
        "description": "多层闭环/互作网络：外部刺激或细胞输入 -> 感知与信号整合 -> 核心调控节点 -> 效应输出 -> 反馈回路；按用户领域选择生物、材料或工程对象",
        "default_ratio": [1600, 1150],
        "default_palette": {"primary": "#0D9488", "secondary": "#2563EB", "accent": "#D97706", "bg": "#FAFCFD", "card": "#FFFFFF", "text": "#0F172A"}
    },
    "signal_pathway": {
        "name": "分子/细胞信号转导机制图 (Cellular Signal Pathway)",
        "journals": "Cell / Nature Cell Bio / Mol Cell",
        "description": "胞外配体 -> 跨膜受体蛋白 -> 磷脂双分子层细胞膜 -> 胞质多级激酶级联活化/抑制 -> 核孔转位 -> 核内转录与靶基因表达",
        "default_ratio": [1536, 1024],
        "default_palette": {"primary": "#A9713F", "secondary": "#2E8B7A", "accent": "#9333EA", "bg": "#FFFFFF", "card": "#FDFCFB", "text": "#1E293B"}
    },
    "process_pipeline": {
        "name": "流程与阶段演变图 (Process / Stage Pipeline)",
        "journals": "Nature Materials / Adv Mater / JACS",
        "description": "按时间或因果顺序展开的阶段链：用户给出的每一步都要保留；生物实验写配体结合、信号激活、转运、效应，材料合成才写前驱体、反应、改性、表征",
        "default_ratio": [1600, 800],
        "default_palette": {"primary": "#0284C7", "secondary": "#4F46E5", "accent": "#EA580C", "bg": "#FAFAFA", "card": "#FFFFFF", "text": "#0F172A"}
    },
    "structural_anatomy": {
        "name": "结构解剖与空间分层图 (Structural Anatomy)",
        "journals": "Nature Electronics / Nature Nanotech",
        "description": "对象的空间层级/剖面：按用户对象拆分组织、细胞、细胞器、结构域或器件层；生物对象不得写成材料层，器件对象才写封装/电极/活性层",
        "default_ratio": [1440, 1080],
        "default_palette": {"primary": "#1E293B", "secondary": "#0D9488", "accent": "#E11D48", "bg": "#F8FAFC", "card": "#FFFFFF", "text": "#0F172A"}
    },
    "graphical_abstract": {
        "name": "论文图形摘要与机制全景 (Graphical Abstract)",
        "journals": "Cell / Science / ACS Central Science",
        "description": "双栏对比或问题-方案-收益全景：左栏常规瓶颈 -> 中部新策略分子机制 -> 右栏显著性能跃升，视觉冲击力强、信息高度浓缩",
        "default_ratio": [1200, 1200],
        "default_palette": {"primary": "#0284C7", "secondary": "#16A34A", "accent": "#DC2626", "bg": "#FFFFFF", "card": "#F8FAFC", "text": "#111827"}
    },
    "ring_architecture": {
        "name": "同心圆环架构总结图 (Concentric Ring Architecture)",
        "journals": "Nature / Science / ASME / IEEE",
        "description": "中心核心对象 + 三层同心环：内环功能子系统、中环使能技术、外环性能指标与应用，沿弧线切向标注，适合机械/工程系统总结",
        "default_ratio": [1400, 1400],
        "default_palette": {"primary": "#1F4E79", "secondary": "#2F7F8A", "accent": "#D97706", "bg": "#FFFFFF", "card": "#F8FAFC", "text": "#0F172A"}
    }
}

STYLE_TRANSFER_INSTRUCTION = """你是顶刊论文艺术总监。用户上传了一张顶级学术期刊（Cell/Nature/Science/ACS Nano）的高水平科研参考图。
请对该参考图进行多维度的视觉风格与结构拓扑反推提取，只输出一个 JSON 对象，不得附带 markdown 或任何解释。

JSON 格式如下：
{
  "archetype": "closed_loop 或 signal_pathway 或 process_pipeline 或 structural_anatomy 或 graphical_abstract",
  "archetype_reason": "判定图型的具体学术视觉依据（例如：包含由配体到细胞核的垂直层级流动和跨膜结构）",
  "reference_summary": "两句中文：先说这是单幅连续场景、多面板还是分栏信息图，再说主体位置、阅读顺序、标签在画内还是画外。",
  "layout_analysis": {
    "composition": "continuous_scene 或 panel_grid 或 multi_panel 或 radial 或 stacked",
    "panel_count": 0,
    "reading_order": "left-to-right 或 top-to-bottom 或 mixed",
    "label_position": "outside 或 inside 或 mixed",
    "visual_hierarchy": "主体占画面比例、主次层级、留白方式",
    "background": "背景与底纹处理"
  },
  "aspect_ratio_preset": "3:2 或 16:9 或 1:1 或 4:3 或 2:1 或 3:4",
  "canvas_size": [1536, 1024],
  "palette": {
    "primary": "#十六进制主色",
    "secondary": "#十六进制副色",
    "accent": "#十六进制点睛强调色",
    "background": "#F8FAFC 或 #FFFFFF",
    "card_background": "#FFFFFF",
    "text": "#0F172A 或 #1E293B"
  },
  "visual_style_summary": "一句话中文总结：画风（如扁平矢量、细描边、微卡片底衬）、配色基调、线宽与留白特征",
  "entity_style_prompt_suffix": "适用于生成独立实体的英语提示词后缀（例如：isolated single biological structure, flat 2D vector style, clean outline, matching palette teal and warm brown, pure white background, no text, no labels）",
  "container_style": "rounded_cards 或 layered_horizontal 或 concentric_circular 或 minimal_flat",
  "connector_style": "smooth_bezier 或 orthogonal 或 straight_arrow"
}
"""

def extract_reference_style(data_url: str, config: dict) -> dict:
    """Analyze uploaded reference image using vision model and extract comprehensive design DNA."""
    vision = config.get("vision") or {}
    text_cfg = config.get("text") or {}
    source = vision if (vision.get("base_url") and vision.get("model")) else text_cfg
    if not (source.get("base_url") and source.get("model")):
        raise RuntimeError("需要先配置视觉模型或文本模型以分析参考图")
    if not data_url.startswith("data:image/"):
        raise RuntimeError("参考图格式无效，需要 data:image/png;base64,... 格式")
    pipeline._validate_data_url(data_url)

    payload = {
        "model": source["model"],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": STYLE_TRANSFER_INSTRUCTION},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "temperature": 0,
        "max_tokens": 3400,
    }
    response = pipeline._post_json(
        pipeline._endpoint(source["base_url"], "/chat/completions"),
        pipeline._api_key(source), payload, timeout=180
    )
    raw = response["choices"][0]["message"]["content"] or ""
    try:
        data = pipeline._json_object(raw)
    except Exception:
        data = _repair_json_by_model(raw, source)
    if not isinstance(data, dict) or not data:
        raise RuntimeError("视觉模型未能提取有效的风格 DNA")
    return data


JSON_REPAIR_INSTRUCTION = (
    "你是 JSON 修复器。把用户给出的内容整理成严格合法的 JSON，只输出 JSON 本体，"
    "不要解释、不要 markdown 代码块。保留原有字段与取值。"
)


def _repair_json_by_model(raw: str, source: dict) -> dict:
    """One cheap model pass to turn a truncated/malformed reply into JSON."""
    if not raw.strip():
        raise RuntimeError("视觉模型返回了空内容")
    payload = {
        "model": source["model"],
        "messages": [
            {"role": "system", "content": JSON_REPAIR_INSTRUCTION},
            {"role": "user", "content": raw[:8000]},
        ],
        "temperature": 0,
        "max_tokens": 3400,
    }
    response = pipeline._post_json(
        pipeline._endpoint(source["base_url"], "/chat/completions"),
        pipeline._api_key(source), payload, timeout=120
    )
    message = response["choices"][0]["message"]
    fixed = message.get("content") or message.get("reasoning_content") or ""
    return pipeline._json_object(fixed)

def apply_style_to_prompt(brief_text: str, style_dna: dict) -> str:
    """Enhance user prompt with extracted reference style DNA without altering scientific intent."""
    arch = style_dna.get("archetype") or "closed_loop"
    arch_info = ARCHETYPE_DESCRIPTIONS.get(arch, ARCHETYPE_DESCRIPTIONS["closed_loop"])
    palette = style_dna.get("palette") or arch_info["default_palette"]
    style_sum = style_dna.get("visual_style_summary") or "顶刊学术插画规范，扁平矢量，细描边，纯白背景"

    p_str = f"主色调 {palette.get('primary', '#0D9488')}，辅助色 {palette.get('secondary', '#2563EB')}，强调色 {palette.get('accent', '#D97706')}"
    enhanced = (
        f"{brief_text.strip()}\n\n"
        f"【学术图型规范】采用 {arch_info['name']} 拓扑布局。\n"
        f"【视觉与色彩DNA】参考期刊图规范：{style_sum}；配色体系：{p_str}；容器规范：{style_dna.get('container_style', 'rounded_cards')}。\n"
        f"【严格约束】所有图中文字均为专业英文标准术语，纯矢量可编辑排版，素材背景纯白无遮挡。"
    )
    return enhanced
