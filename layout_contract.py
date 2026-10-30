"""Extract the user's non-negotiable layout contract from their own brief.

The AI prompt writer is allowed to improve wording, but it must not silently
turn a left-to-right signal pathway into a closed-loop framework template.
This module reads the author's original text (not the rewritten prompt) and
returns the parts the renderer and auditor must honour.
"""

from __future__ import annotations

import re

NEGATION = re.compile(
    r"(?:不要|避免|禁止|不使用|不要用|别用|而非|不是)[^。；;\n]{0,50}?"
    r"(?:闭环|回路|纵向|竖向|自上而下|从上到下|横向|左到右|"
    r"closed[- ]?loop|vertical|top[- ]?to[- ]?bottom|horizontal|left[- ]?to[- ]?right)", re.I)

HORIZONTAL = re.compile(
    r"左到右|从左到右|左至右|由左至右|横向|左右|"
    r"left[- ]?to[- ]?right|horizontal|S\s*形|S[- ]?shaped|serpentine|蜿蜒", re.I)
VERTICAL = re.compile(
    r"自上而下|从上到下|由上至下|纵向|竖向|垂直|"
    r"top[- ]?to[- ]?bottom|vertical|上到下", re.I)
CLOSED = re.compile(r"闭环|闭合回路|反馈回路|closed[- ]?loop|feedback loop", re.I)
RING = re.compile(r"同心圆环|圆环|环形架构|concentric ring|ring architecture", re.I)
ANATOMY = re.compile(r"剖面|分层|截面|结构解剖|解剖图|结构图|结构域|anatomy|layer section|domain architecture", re.I)
NETWORK = re.compile(r"相互调控|互作网络|调控网络|促进.*抑制|network|crosstalk", re.I)
STAGES = re.compile(r"[一二三四五六七八九十\d]+个?阶段|阶段\s*[:：]|阶段，|四步|三步|两步|stepwise|stages?\b", re.I)
PIPELINE = re.compile(r"流程|工序|制备|装配|pipeline|process flow", re.I)
SIGNAL = re.compile(r"信号通路|信号转导|通路|级联|磷酸化|激酶|受体|配体|补体|"
                    r"signaling pathway|signal pathway|cascade|phosphorylat|kinase|"
                    r"receptor|ligand|complement|C1q|MAC", re.I)
# Cards are a deliberate exception, never the default. Only an explicit request
# for a boxed flow chart may switch the pathway renderer back to panels.
FLOWCHART = re.compile(
    r"流程图|流程框图|方框图|框图|方框|卡片式|分栏|panel grid|flow ?chart|block diagram", re.I)


def _clean_stage(label: str) -> str:
    value = re.sub(r"^.*?(?:主路径|路径|顺序|阶段|流程)\s*[:：]\s*", "", str(label or ""))
    value = re.split(r"[。；;\n]", value)[0]
    value = value.strip(" \t\r\n-—–:：0123456789.、)）]")
    value = re.sub(r"^(P\d+|Stage\s*\d+|第[一二三四五六七八九十\d]+[步阶段])\s*[:：、.-]?\s*",
                   "", value, flags=re.I)
    return value.strip(" \t\r\n-—–:：。；;,")


def stage_names(text: str) -> list[str]:
    """Pull the arrow-separated stage chain out of the author's brief."""
    best: list[str] = []
    for line in str(text or "").splitlines():
        if not re.search(r"→|⟶|⇒|->|=>", line):
            continue
        parts = re.split(r"\s*(?:→|⟶|⇒|->|=>)\s*", line)
        names = [_clean_stage(part) for part in parts]
        names = [name for name in names if 2 <= len(name) <= 60]
        if len(names) > len(best):
            best = names
    # A compact Chinese brief often separates stages with semicolons rather
    # than arrows ("配体结合；受体激活；..."). Use it only when it yields a
    # real chain, so ordinary prose is not chopped into fake stages.
    if not best:
        parts = re.split(r"[；;\n]+", str(text or ""))
        names = [_clean_stage(part) for part in parts]
        names = [name for name in names if 3 <= len(name) <= 60]
        if len(names) >= 3:
            best = names
    # "包含5个阶段：1 ... 2 ... 3 ..." is a stage list too. Split on the
    # numbers themselves; the author rarely separates them with arrows.
    parts = re.split(r"(?:^|[\s：:；;。，,])(\d{1,2})\s*[、.．:：]?\s*",
                     str(text or ""))
    numbered = []
    for index in range(1, len(parts) - 1, 2):
        number = int(parts[index])
        value = _clean_stage(parts[index + 1])
        if number == len(numbered) + 1 and 2 <= len(value) <= 80:
            numbered.append(value)
        else:
            break
    if len(numbered) > len(best):
        best = numbered
    return best[:8]


def title_of(text: str) -> str:
    value = str(text or "")
    match = re.search(r"(?:标题|主标题|图题)\s*[:：]?\s*[“\"']([^”\"']{2,120})[”\"']", value)
    if match:
        return match.group(1).strip()
    return ""


def canvas_ratio(text: str):
    match = re.search(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", str(text or ""))
    if not match:
        return None
    value = f"{int(match.group(1))}:{int(match.group(2))}"
    return value if value in ("3:2", "16:9", "1:1", "4:3", "2:1", "3:4") else None


BIO_SUBJECT = re.compile(
    r"细胞|有丝分裂|减数分裂|染色体|染色质|纺锤体|核膜|蛋白|信号通路|受体|配体|囊泡|基因|转录|线粒体|内质网|组织|免疫|肿瘤|凋亡|增殖|分化|\bmitosis\b|\bmeiosis\b|\binterphase\b|\bprophase\b|\bmetaphase\b|\banaphase\b|\btelophase\b|\bcytokinesis\b|\bprotein\b|\breceptor\b|\bligand\b|\bvesicle\b|\bkinase\b|\bsignaling\b",
    re.I
)

def archetype_of(text: str) -> str | None:
    value = NEGATION.sub(" ", str(text or ""))
    from scientific_intent import intent_contract
    is_bio = intent_contract(value)['domain']=='biology'
    # Biological processes, cell divisions and cycles are always process pipelines,
    # never cybernetic/engineering closed loop architectures.
    if is_bio:
        if SIGNAL.search(value):
            return "signal_pathway"
        if PIPELINE.search(value) or STAGES.search(value) or re.search(r"周期|有丝分裂|减数分裂|mitosis|meiosis|cycle|分期|流线|流程|步骤|过程", value, re.I):
            return "process_pipeline"
        if RING.search(value):
            return "ring_architecture"
        if ANATOMY.search(value):
            return "structural_anatomy"
        if CLOSED.search(value) or NETWORK.search(value):
            return "closed_loop"
        return "process_pipeline"

    if CLOSED.search(value) or NETWORK.search(value):
        return "closed_loop"
    if SIGNAL.search(value):
        return "signal_pathway"
    if ANATOMY.search(value) and not STAGES.search(value):
        return "structural_anatomy"
    if RING.search(value):
        return "ring_architecture"
    # Explicit stage chains are temporal/process figures even when the author
    # also says "剖面" (e.g. wound healing across a tissue section). Anatomy
    # requires a structural object, not merely the word "剖面".
    if PIPELINE.search(value) or STAGES.search(value):
        return "process_pipeline"
    if ANATOMY.search(value):
        return "structural_anatomy"
    return None


def _reference_layout(reference) -> dict:
    """Keep the vision model's layout reading, not its colours or prose."""
    if not isinstance(reference, dict):
        return {}
    layout = reference.get("layout_analysis")
    if not isinstance(layout, dict):
        # Callers may pass either the full reference DNA or its layout block.
        layout = reference
    out = {}
    for key in ("composition", "panel_count", "reading_order", "label_position",
                "visual_hierarchy", "background"):
        value = layout.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            out[key] = value
    summary = reference.get("reference_summary") or reference.get("visual_style_summary")
    if summary:
        out["summary"] = str(summary)[:600]
    ratio = reference.get("aspect_ratio_preset") or reference.get("ratio")
    if ratio in ("3:2", "16:9", "1:1", "4:3", "2:1", "3:4"):
        out["ratio"] = ratio
    return out


def _explicit_flowchart(text: str) -> bool:
    """True only for a positive request; "不要卡片/不要分栏" is a negation."""
    for clause in re.split(r"[，。；,.;\n]", str(text or "")):
        hit = FLOWCHART.search(clause)
        if not hit:
            continue
        if re.search(r"(不要|不用|无需|别|禁止|并非|不是|勿|避免).{0,10}"
                     r"(流程|方框|卡片|分栏|框图)", clause):
            continue
        return True
    return False


def build(original_text: str, prompt_text: str = "", reference_layout=None) -> dict:
    value = str(original_text or "").strip() or str(prompt_text or "").strip()
    cleaned = NEGATION.sub(" ", value)
    layout = None
    if HORIZONTAL.search(cleaned):
        layout = "horizontal_s"
    elif VERTICAL.search(cleaned):
        layout = "vertical"
    reference = _reference_layout(reference_layout)
    if not layout and reference.get("reading_order") == "left-to-right":
        layout = "horizontal_s"
    elif not layout and reference.get("reading_order") == "top-to-bottom":
        layout = "vertical"
    ratio = canvas_ratio(value)
    if not ratio and isinstance(reference.get("ratio"), str):
        ratio = reference["ratio"] if reference["ratio"] in (
            "3:2", "16:9", "1:1", "4:3", "2:1", "3:4") else None
    return {
        "source": value[:4000],
        "title": title_of(value),
        "archetype": archetype_of(value),
        "layout": layout,
        "ratio": ratio,
        "stages": stage_names(cleaned),
        "mentions_feedback": bool(CLOSED.search(cleaned)),
        "figure_style": "flowchart" if _explicit_flowchart(cleaned) else "mechanism",
        "reference_layout": reference,
    }


def adherence_findings(contract: dict, report: dict, svg_texts: list[str],
                       finding_factory) -> list[dict]:
    """Return high findings when the delivered figure contradicts the brief."""
    if not isinstance(contract, dict):
        return []
    found = []
    expected = contract.get("archetype")
    report = report or {}
    if expected == "signal_pathway" and (report.get("framework") or report.get("ring")):
        found.append(finding_factory(
            "prompt-drift", "high",
            "提示词要求的是单向信号通路，但实际输出成了框架/闭环模板",
            "按原文重画为信号通路：阶段依序排列，不要套用 A/B/C 闭环框架"))
    if (contract.get("layout") == "horizontal_s"
            and expected == "signal_pathway"
            and (report.get("spec") or {}).get("layout") not in ("horizontal_s",)):
        found.append(finding_factory(
            "prompt-drift", "high",
            "提示词要求左到右/S 形布局，但实际输出不是该布局",
            "按原文的空间描述排版，不要使用自上而下的长条模板"))
    generate_mode = str((report.get("stages") or {}).get("generate", {}).get("mode") or "")
    if (expected == "signal_pathway"
            and contract.get("figure_style") != "flowchart"
            and generate_mode and generate_mode != "scene"):
        found.append(finding_factory(
            "prompt-drift", "high",
            "要求的是生物教材/顶刊机理图，实际输出仍是分栏卡片",
            "改成单幅连续细胞场景 + 外侧编号引线；只有用户明确要求带方框的流程图时才允许卡片"))
    stages = [str(s) for s in (contract.get("stages") or []) if str(s).strip()]
    rendered = [str(s.get("label") or "").strip()
                for s in (report.get("spec") or {}).get("stages") or []
                if isinstance(s, dict) and str(s.get("label") or "").strip()]
    # The brief may demand English labels while its stage chain is Chinese.
    # The planner's labels are then the authoritative spelling of the same
    # stages; check those against the canvas instead of the Chinese names.
    expected_labels = rendered if rendered and len(rendered) >= len(stages) else stages
    if len(expected_labels) >= 2 and svg_texts:
        joined = " ".join(svg_texts or []).lower()
        missing = []
        for name in expected_labels:
            low = name.lower()
            if low in joined:
                continue
            tokens = [word for word in re.findall(r"[a-z0-9]+", low) if len(word) > 2]
            hits = sum(1 for word in tokens if word in joined)
            if not tokens or hits / len(tokens) < 0.75:
                missing.append(name)
        if missing:
            found.append(finding_factory(
                "prompt-drift", "high",
                "提示词列出的阶段在图中缺失：" + "、".join(missing[:5]),
                "逐项补回用户列出的阶段名称，保持原有顺序"))
    if report.get("raster") and svg_texts:
        junk = [text for text in svg_texts
                if re.fullmatch(r"[IVXLCDM]{2,}", str(text).strip())]
        if junk:
            found.append(finding_factory(
                "prompt-drift", "high",
                "图中出现无意义占位文本：" + "、".join(junk[:4]),
                "删除罗马数字/占位符，只保留用户列出的阶段标签"))
    if contract.get("mentions_feedback") is False and svg_texts:
        joined = " ".join(svg_texts or []).lower()
        if any(word in joined for word in ("闭环", "反馈弧", "feedback arc", "feedback loop")):
            found.append(finding_factory(
                "prompt-drift", "high",
                "图中出现了用户原文没有要求的闭环/反馈弧",
                "删除新增的反馈回路，只保留原文的单向阶段"))
    return found
