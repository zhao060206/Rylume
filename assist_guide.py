"""Assist-guided interactive prompt co-pilot.

Follows the patient clarification framework from the assist skill:
1. Steps on the brake: does not guess or bloat prompts blindly.
2. Card-based interactive clarification: asks 2-3 structured choices
   (figure archetype, journal palette, canvas ratio).
3. Plain-language options with clear visual implications.
4. Generates an enhanced, accurate prompt that genuinely elevates the figure
   without inventing unscientific mechanisms or hallucinating details.
"""

from __future__ import annotations

import json
import re

import archetypes
import pipeline

CLARIFY_INSTRUCTION = """你是顶刊论文插画顾问，服务所有学科（机械、材料、能源、电子、化学、生物、医学、计算机、土木……）。
用户给出了一段初步的科研绘图想法。请根据这段文字判断其学科与图版意图，生成 6 个最有信息量的选择题卡片。
不要默认生物学！选项必须贴合用户所在领域：机械/工程用 gearbox、transmission、actuator 等术语；
生物医学才用 receptor、pathway、organelle；材料化学用 synthesis、interface 等。只输出 JSON，不要其他文字。

输出 JSON 格式：
{
  "summary": "用大白话复述你理解的主题，并说明还要确认 6 项关键设计要素。",
  "questions": [
    {"id": "archetype", "title": "选择核心图型架构", "options": [
      {"value": "ring_architecture", "label": "同心圆环架构总结", "desc": "中心对象+三层环：子系统/技术/性能", "recommended": false},
      {"value": "closed_loop", "label": "闭环系统与推导架构", "desc": "感知-推理-执行-反馈闭环"},
      {"value": "process_pipeline", "label": "流程/制备/装配阶段", "desc": "按时间或工序横向展开"},
      {"value": "structural_anatomy", "label": "分层结构剖面", "desc": "多层材料、器件或组织剖面"},
      {"value": "graphical_abstract", "label": "图形摘要/问题-方案-结果", "desc": "三分栏叙事，适合摘要图"},
      {"value": "signal_pathway", "label": "信号/机制通路", "desc": "仅当主题确实是分子或细胞通路时"}
    ]},
    {"id": "palette", "title": "选择配色与投稿期刊风格", "options": [4 个，含期刊名与十六进制色值]},
    {"id": "ratio", "title": "选择画布比例", "options": [
      {"value": "3:2", ...}, {"value": "16:9", ...}, {"value": "1:1", ...},
      {"value": "4:3", ...}, {"value": "2:1", ...}, {"value": "3:4", ...}
    ]},
    {"id": "density", "title": "信息密度", "options": [
      {"value": "minimal", "label": "精简", "desc": "只保留主路径与核心标签"},
      {"value": "standard", "label": "标准", "desc": "主路径+每个节点一行说明", "recommended": true},
      {"value": "dense", "label": "高密度", "desc": "多级分支、参数与注释齐全"}
    ]},
    {"id": "illustration", "title": "出图模式", "options": [
      {"value": "image", "label": "教材式机理图", "desc": "生成式细胞/组织底图 + 可编辑标注，默认用于机制图", "recommended": true},
      {"value": "vector", "label": "纯矢量线框", "desc": "文字+线框/几何图元，全部可编辑；仅明确要求矢量时选"}
    ]},
    {"id": "language", "title": "图中文字", "options": [
      {"value": "en", "label": "英文标准术语", "desc": "投稿国际期刊的默认选择", "recommended": true},
      {"value": "bilingual", "label": "中英对照", "desc": "中文为主，关键术语附英文"},
      {"value": "zh", "label": "全中文", "desc": "组会、答辩或中文期刊"}
    ]}
  ]
}
硬性要求：
1. questions 必须恰好 6 项，id 必须依次是 archetype / palette / ratio / density / illustration / language；不得只输出 3 项或省略任何一项，每项都要有 2-4 个选项。
2. archetype 只能从上面六个 value 中选，但 label/desc 要结合用户领域改写；不要默认推荐 signal_pathway。
3. 每个问题的 options 3-6 个，第一个或标 recommended 的选项必须是最贴合用户原文的。
4. illustration 默认推荐 image（教材式整幅机理图）；只有用户明确说“纯矢量/线框/全部可编辑”时才推荐 vector。用户上传参考图时，先按参考图的排版结构来设计问题，不能套用通用模板。
5. 用语通俗，不堆黑话。
"""

COMPOSE_INSTRUCTION = """你是顶刊论文艺术总监。根据用户的原始科研描述与明确选择项，产出最终绘图提示词。

输出规则（必须严格遵守）：
1. 只输出提示词正文，第一行必须是标记：【绘图提示词】
2. 禁止输出任何思考过程、推演、自我检讨、"用户要的是""我需要""实际上"这类旁白。
3. 全文 500-900 字，分 6 个短段：图表主题 / 画布 / 空间布局 / 配色 / 连接与箭头 / 文字与输出规范。
4. 科学内容只增不改：不得添加用户未提及的生物途径、分子、数值或实验结果；不确定的中介节点不要写。
5. 中文说明 + 英文标准术语，直接可用于绘图；不要代码块、不要markdown标题、不要前后缀问候。
"""

PALETTE_NOTES = {
    "nature": "Nature 冷蓝体系（主色 #0F4D92 / 辅色 #0284C7 / 强调 #D97706）",
    "cell": "Cell 暖棕青绿体系（主色 #A9713F / 辅色 #2E8B7A / 强调 #9333EA）",
    "acsnano": "ACS Nano 高辨识体系（主色 #0D9488 / 辅色 #2563EB / 强调 #EA580C）",
    "minimal": "单色极简体（主色 #334155 / 辅色 #64748B / 强调 #0D9488）",
}

LAYOUT_NOTES = {
    "closed_loop": "环形闭环：传感输入 → 中央推理中枢 → 执行输出 → 反馈回路回到输入端；主环用粗实线，反馈用虚线，箭头正交路由。",
    "signal_pathway": "自上而下或自左向右的单向通路：配体 → 膜受体 → 胞内级联节点 → 核内效应；膜用双层磷脂带切分空间，级联节点按层级垂直排列。",
    "process_pipeline": "等宽阶段卡横向排列，编号 1-N 置于卡片左上角，阶段之间用同向粗箭头连接，每卡含图标 + 阶段名 + 一行说明。",
    "structural_anatomy": "分层剖面：各功能层以斜切梯形层叠，左侧标注层名与厚度，右侧以引线标注材料与功能，层间用细分割线。",
    "graphical_abstract": "三分栏叙事：Problem（现状/瓶颈）→ Strategy（本文方法）→ Outcome（结果/意义），三栏等宽，中央用大箭头串联。",
}


def _template_prompt(original_text: str, arch: str, palette: str, ratio: str,
                     canvas: list[int]) -> str:
    """Deterministic, science-preserving enhancement used when the model
    returns nothing usable. Never invents mechanisms."""
    name = archetypes.ARCHETYPE_DESCRIPTIONS.get(arch, {}).get("name", arch)
    return (
        "【绘图提示词】\n"
        f"图表主题：{name}。基于作者原始描述绘制，科学内容不增不改。\n"
        f"画布：{canvas[0]}×{canvas[1]}（比例 {ratio}），四周留 40px 安全边距，纯白背景。\n"
        f"空间布局：{_layout_note(original_text, arch)}\n"
        f"配色：{PALETTE_NOTES.get(palette, PALETTE_NOTES['nature'])}；同一含义只用一种颜色，关键新组件用强调色。\n"
        "连接与箭头：主通路用 2.5pt 实线箭头，反馈/调控用 1.5pt 虚线箭头；正交路由，箭头不得穿过文字。\n"
        "文字与输出：Arial/Helvetica，标题 14-18pt、正文 9-11pt、英文标准术语；输出纯矢量 SVG，无渐变、无阴影、无位图。\n"
        f"科学内容：{original_text}"
    )


def _layout_note(original_text: str, arch: str) -> str:
    if re.search(r"左到右|从左到右|左至右|横向|S\s*形|left[- ]?to[- ]?right|horizontal", original_text or "", re.I):
        return ("按用户原文的左到右轻微 S 形流程排列：阶段沿水平方向推进，"
                "只做轻微上下错落，不要改成自上而下的长条模板。")
    return LAYOUT_NOTES.get(arch, LAYOUT_NOTES["closed_loop"])


def _clean_enhanced(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    marker = "【绘图提示词】"
    pos = text.find(marker)
    if pos > 0:
        text = text[pos:]
    elif pos < 0:
        return ""
    text = text.strip()
    if len(text) > 1600:
        cut = text.rfind("\n", 0, 1600)
        text = text[:cut if cut > 600 else 1600].rstrip()
    return text


def _domain(text: str) -> str:
    if any(k in text for k in ("细胞", "蛋白", "基因", "受体", "通路", "免疫", "肿瘤", "分子", "代谢", "脑", "神经")):
        return "bio"
    if any(k in text for k in ("机械", "齿轮", "传动", "机器人", "结构", "器件", "材料", "纳米", "能源", "风电",
                                "航空", "车辆", "制造", "装配", "热", "流体", "控制")):
        return "eng"
    if any(k in text for k in ("临床", "疾病", "患者", "治疗", "诊断", "药物")):
        return "med"
    return "other"


def _prefer_archetype(data: dict, text: str) -> None:
    """Correct the pre-selected archetype for wording the model misreads.

    "闭环" contains "环", so models frequently recommend a ring figure for a
    closed-loop system. The user can still pick anything; this only fixes the
    default that a novice would accept.
    """
    import re as _re
    if _re.search(r"闭环|回路|反馈|closed[-_ ]?loop", text, _re.I):
        want = "closed_loop"
    elif _re.search(r"通路|信号|pathway|signal", text, _re.I):
        # "信号通路…S 形流程" also contains 流程; pathway wins.
        want = "signal_pathway"
    elif _re.search(r"流程|制备|工艺|装配|pipeline|process", text, _re.I):
        want = "process_pipeline"
    elif _re.search(r"剖面|分层|截面|anatomy|layer", text, _re.I):
        want = "structural_anatomy"
    else:
        return
    for q in data.get("questions") or []:
        if str(q.get("id")) != "archetype":
            continue
        options = q.get("options") or []
        if not any(str(o.get("value")) == want for o in options):
            info = archetypes.ARCHETYPE_DESCRIPTIONS.get(want) or {}
            options.append({"value": want,
                            "label": str(info.get("name") or want),
                            "desc": str(info.get("desc") or "")[:120],
                            "recommended": True})
        for option in options:
            option["recommended"] = str(option.get("value")) == want


def _recommend_choice(data: dict, qid: str, value: str) -> bool:
    for question in data.get("questions") or []:
        if str(question.get("id")) != qid:
            continue
        options = question.get("options") or []
        if not any(str(o.get("value")) == value for o in options):
            return False
        for option in options:
            option["recommended"] = str(option.get("value")) == value
        return True
    return False


PALETTE_CHOICES = [
    ("nature", "Nature 冷蓝体系", "主色 #0F4D92 / 辅色 #0284C7 / 强调 #D97706"),
    ("cell", "Cell 暖棕青绿体系", "主色 #A9713F / 辅色 #2E8B7A / 强调 #9333EA"),
    ("acsnano", "ACS Nano 高辨识体系", "主色 #0D9488 / 辅色 #2563EB / 强调 #EA580C"),
    ("minimal", "单色极简体", "主色 #334155 / 辅色 #64748B / 强调 #0D9488"),
]


def _canonicalize_palette(data: dict) -> None:
    """The rendering layer only understands the four built-in palette keys."""
    for question in data.get("questions") or []:
        if str(question.get("id")) != "palette":
            continue
        old = question.get("options") or []
        label = ""
        for option in old:
            if option.get("recommended"):
                label = (str(option.get("label") or "") + " " + str(option.get("value") or "")).lower()
                break
        if not label and old:
            label = (str(old[0].get("label") or "") + " " + str(old[0].get("value") or "")).lower()
        if "acs" in label:
            chosen = "acsnano"
        elif "cell" in label or "暖" in label:
            chosen = "cell"
        elif "极简" in label or "单色" in label or "mono" in label:
            chosen = "minimal"
        else:
            chosen = "nature"
        question["options"] = [
            {"value": value, "label": text_label, "desc": desc,
             "recommended": value == chosen}
            for value, text_label, desc in PALETTE_CHOICES
        ]


def _prefer_choices(data: dict, text: str) -> None:
    """Honor explicit ratio/palette/mode choices in the user's own wording."""
    import re as _re
    value = str(text or "")
    ratio = _re.search(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", value)
    if ratio:
        candidate = f"{int(ratio.group(1))}:{int(ratio.group(2))}"
        if candidate in ("3:2", "16:9", "1:1", "4:3", "2:1", "3:4"):
            _recommend_choice(data, "ratio", candidate)
    elif _re.search(r"竖版|纵向|竖向|自上而下|portrait", value, _re.I):
        _recommend_choice(data, "ratio", "3:4")
    elif _re.search(r"横版|横向|左到右|从左到右|landscape", value, _re.I):
        _recommend_choice(data, "ratio", "3:2")
    if _re.search(r"cell|cell 风格|cell系", value, _re.I):
        _recommend_choice(data, "palette", "cell")
    elif _re.search(r"nature|npg", value, _re.I):
        _recommend_choice(data, "palette", "nature")
    elif _re.search(r"acs|acs nano", value, _re.I):
        _recommend_choice(data, "palette", "acsnano")
    elif _re.search(r"极简|单色|minimal", value, _re.I):
        _recommend_choice(data, "palette", "minimal")
    if _re.search(r"生图|插画|生成式|image mode", value, _re.I):
        _recommend_choice(data, "illustration", "image")
    elif _re.search(r"纯矢量|矢量|vector", value, _re.I):
        _recommend_choice(data, "illustration", "vector")
    if _re.search(r"精简|minimal", value, _re.I):
        _recommend_choice(data, "density", "minimal")
    elif _re.search(r"高密度|详细|dense", value, _re.I):
        _recommend_choice(data, "density", "dense")
    elif _re.search(r"标准|standard", value, _re.I):
        _recommend_choice(data, "density", "standard")
    if _re.search(r"中英|bilingual", value, _re.I):
        _recommend_choice(data, "language", "bilingual")
    elif _re.search(r"英文|english|en", value, _re.I):
        _recommend_choice(data, "language", "en")
    elif _re.search(r"全中文|中文", value, _re.I):
        _recommend_choice(data, "language", "zh")
    _ensure_ratio_options(data)


_RATIO_OPTIONS = [
    {"value": "3:2", "label": "3:2 双栏 (1536×1024)", "desc": "论文主图最通用"},
    {"value": "16:9", "label": "16:9 宽屏 (1600×900)", "desc": "横向多阶段或系统流"},
    {"value": "1:1", "label": "1:1 方形 (1200×1200)", "desc": "图形摘要或单栏"},
    {"value": "4:3", "label": "4:3 图版 (1440×1080)", "desc": "常规单栏插图"},
    {"value": "2:1", "label": "2:1 长横图 (1600×800)", "desc": "流程/时间线"},
    {"value": "3:4", "label": "3:4 竖版 (900×1200)", "desc": "单栏纵向机制图"},
]


def _ensure_ratio_options(data: dict) -> None:
    """Model outputs often drop ratios; never let a missing option hide 3:2."""
    for q in data.get("questions") or []:
        if str(q.get("id") or "") != "ratio":
            continue
        opts = q.setdefault("options", [])
        have = {str(o.get("value") or "") for o in opts}
        for opt in _RATIO_OPTIONS:
            if opt["value"] not in have:
                opts.append(dict(opt))
        return


def _fallback_cards(text: str) -> dict:
    domain = _domain(text)
    if domain == "bio":
        arche = [
            {"value": "signal_pathway", "label": "信号/机制通路", "desc": "配体-受体-胞内级联-核内效应", "recommended": "通路" in text or "信号" in text},
            {"value": "closed_loop", "label": "调控闭环", "desc": "输入-调控中枢-效应-反馈回路"},
            {"value": "process_pipeline", "label": "实验/制备流程", "desc": "按时间或处理步骤展开"},
            {"value": "structural_anatomy", "label": "细胞/组织解剖", "desc": "分层剖面与空间关系"},
            {"value": "graphical_abstract", "label": "图形摘要", "desc": "问题-机制-结果三分栏"},
        ]
    else:
        arche = [
            {"value": "ring_architecture", "label": "同心圆环架构", "desc": "中心对象 + 子系统/技术/性能三层环", "recommended": "圆环" in text or "同心" in text or "环形" in text},
            {"value": "closed_loop", "label": "闭环系统架构", "desc": "感知-推理-执行-反馈闭环", "recommended": "闭环" in text or "系统" in text},
            {"value": "process_pipeline", "label": "流程/装配阶段", "desc": "按工序或时间横向展开"},
            {"value": "structural_anatomy", "label": "分层结构剖面", "desc": "多层材料、部件或器件剖面"},
            {"value": "graphical_abstract", "label": "图形摘要", "desc": "问题-方案-结果三分栏"},
        ]
    palette = [
        {"value": "nature", "label": "Nature 冷蓝钢灰", "desc": "主色 #0F4D92 / 辅色 #0284C7 / 强调 #D97706", "recommended": domain in ("eng", "other")},
        {"value": "cell", "label": "Cell 暖棕青绿", "desc": "主色 #A9713F / 辅色 #2E8B7A / 强调 #9333EA", "recommended": domain == "bio"},
        {"value": "acsnano", "label": "ACS Nano 高辨识", "desc": "主色 #0D9488 / 辅色 #2563EB / 强调 #EA580C"},
        {"value": "minimal", "label": "单色极简", "desc": "灰阶 + 单一强调色", "recommended": domain == "med"},
    ]
    ratio = [
        {"value": "3:2", "label": "3:2 双栏 (1536×1024)", "desc": "论文主图最通用", "recommended": True},
        {"value": "16:9", "label": "16:9 宽屏 (1600×900)", "desc": "横向多阶段或系统流"},
        {"value": "1:1", "label": "1:1 方形 (1200×1200)", "desc": "图形摘要或单栏"},
        {"value": "4:3", "label": "4:3 图版 (1440×1080)", "desc": "常规单栏插图"},
        {"value": "2:1", "label": "2:1 长横图 (1600×800)", "desc": "流程/时间线"},
        {"value": "3:4", "label": "3:4 竖版 (900×1200)", "desc": "单栏纵向机制图"},
    ]
    density = [
        {"value": "minimal", "label": "精简", "desc": "只保留主路径与核心标签"},
        {"value": "standard", "label": "标准", "desc": "主路径 + 每个节点一行说明", "recommended": True},
        {"value": "dense", "label": "高密度", "desc": "多级分支、参数与注释齐全"},
    ]
    illustration = [
        {"value": "vector", "label": "纯矢量", "desc": "文字 + 线框/几何图元，全部可编辑", "recommended": True},
        {"value": "image", "label": "素材生图 + 排版", "desc": "逐对象生成细胞/专业素材，再由模型排版；文字与标注可编辑"},
    ]
    language = [
        {"value": "en", "label": "英文标准术语", "desc": "投稿国际期刊", "recommended": True},
        {"value": "bilingual", "label": "中英对照", "desc": "中文为主，关键术语附英文"},
        {"value": "zh", "label": "全中文", "desc": "组会、答辩或中文期刊"},
    ]
    return {
        "summary": "已根据你的原话判断学科与图版意图。为了避免画偏，请确认下面 6 项（已按你的描述预选推荐项）：",
        "questions": [
            {"id": "archetype", "title": "图型架构", "options": arche},
            {"id": "palette", "title": "配色与期刊风格", "options": palette},
            {"id": "ratio", "title": "画布比例", "options": ratio},
            {"id": "density", "title": "信息密度", "options": density},
            {"id": "illustration", "title": "出图模式", "options": illustration},
            {"id": "language", "title": "图中文字", "options": language},
        ],
    }


def _fallback_choices(text: str) -> dict:
    cards = _fallback_cards(text)
    _prefer_choices(cards, text)
    return cards


REFERENCE_LAYOUT_OPTIONS = [
    {"value": "follow", "label": "严格沿用参考图排版",
     "desc": "保持参考图的场景/分栏结构、阅读顺序和标签位置", "recommended": True},
    {"value": "simplify", "label": "保留主结构，适度简化",
     "desc": "沿用参考图的主体布局，删掉与本次内容无关的分栏", "recommended": False},
    {"value": "adapt", "label": "按新内容重排",
     "desc": "保留参考图的配色、层级和标注方式，按新机制重新组织空间", "recommended": False},
]


def _reference_block(dna: dict) -> str:
    layout = dna.get("layout_analysis") or {}
    summary = str(dna.get("reference_summary") or dna.get("visual_style_summary") or "")
    return ("【参考图视觉分析结果（视觉模型已先读取，必须以此为准，不得忽略）】\n"
            "排版摘要：" + summary + "\n"
            "结构化排版：" + json.dumps(layout, ensure_ascii=False, sort_keys=True) + "\n"
            "硬性要求：先复述参考图的排版结构，再根据这个排版提问；"
            "问题选项必须与参考图的阅读顺序、主体位置、标签位置一致，不能套用通用模板。")


def _attach_reference(data: dict, dna: dict) -> dict:
    layout = dna.get("layout_analysis") or {}
    summary = str(dna.get("reference_summary") or dna.get("visual_style_summary") or "")
    data = data if isinstance(data, dict) else {}
    data["questions"] = [q for q in (data.get("questions") or [])
                         if str((q or {}).get("id")) not in
                         ("reference_layout", "reference_content")]
    # Make the learned layout visible in the question itself, not only in the
    # hidden prompt.  The user should see what the vision model actually read.
    comp = {"continuous_scene": "连续场景", "panel_grid": "分栏面板",
            "multi_panel": "多面板", "radial": "环形", "stacked": "上下堆叠"}.get(
                str(layout.get("composition") or ""), str(layout.get("composition") or ""))
    order = {"left-to-right": "左→右", "top-to-bottom": "上→下",
             "mixed": "混合顺序"}.get(str(layout.get("reading_order") or ""),
                                       str(layout.get("reading_order") or ""))
    label = {"outside": "标签在外", "inside": "标签在内",
             "mixed": "标签内外混合"}.get(str(layout.get("label_position") or ""),
                                           str(layout.get("label_position") or ""))
    bits = [x for x in (comp, order, label) if x]
    title = "参考图排版如何使用" + (f"（识别到：{' / '.join(bits)}）" if bits else "")
    data["questions"].insert(0, {
        "id": "reference_layout", "title": title,
        "options": [dict(o) for o in REFERENCE_LAYOUT_OPTIONS],
    })
    data["questions"].insert(1, {
        "id": "reference_content", "title": "参考图的内容元素如何处理",
        "options": [
            {"value": "layout_only", "label": "只借排版，内容全部换成我的描述",
             "desc": "参考图只提供排版语法；细胞类型、对象和机制关系以你的文字为准", "recommended": True},
            {"value": "keep_subjects", "label": "保留参考图的主体对象",
             "desc": "沿用参考图中的细胞/组织/分子类型，机制关系仍以你的描述为准", "recommended": False},
            {"value": "keep_relations", "label": "保留参考图的对象关系",
             "desc": "沿用参考图的对象层级与箭头关系，具体名称以你的描述为准", "recommended": False},
        ],
    })
    data["reference"] = dna
    data["reference_summary"] = summary
    data["reference_layout"] = layout
    lead = "视觉模型已先读取参考图：" + (summary or "已提取排版结构").rstrip("。") + "。"
    count = len(data.get("questions") or [])
    tail = f"请确认下面 {count} 项（第 1 项是参考图排版，已预选推荐项）："
    old = str(data.get("summary") or "")
    # The model may write "下面 6 个问题…" even when a reference adds two
    # questions; cut that stale tail and state the real count.
    old = re.split(r"(?:请确认)?下面\s*\d+\s*(?:个问题|项)", old, maxsplit=1)[0]
    old = re.split(r"要按这个排版落地|还需要(?:你)?确认|需要确认", old, maxsplit=1)[0]
    old = old.rstrip("。 ：:")
    lead = lead[:180]
    old = old[:320]
    data["summary"] = (lead + " " + old + " " + tail).strip()
    return data


def generate_clarification_cards(text: str, config: dict,
                                 reference=None, image=None) -> dict:
    """Analyze the brief (and reference layout first) into choice cards."""
    dna = reference if isinstance(reference, dict) else None
    if image:
        import archetypes
        if not isinstance(image, str) or not image.startswith("data:image/"):
            raise RuntimeError("参考图格式无效")
        dna = archetypes.extract_reference_style(image, config)
    if dna is not None:
        layout = dna.get("layout_analysis")
        if not isinstance(layout, dict) or not layout:
            raise RuntimeError("参考图尚未完成视觉排版分析，请重新上传参考图后再出题")
    prompt_text = text + (chr(10) + chr(10) + _reference_block(dna) if dna else "")
    try:
        data = pipeline.chat_json(config, [
            {"role": "system", "content": CLARIFY_INSTRUCTION},
            {"role": "user", "content": prompt_text},
        ], temperature=0.2, max_tokens=4000)
        questions = data.get("questions") or []
        required = {"archetype", "palette", "ratio", "density", "illustration", "language"}
        if len(questions) >= 6 and required.issubset({str(q.get("id")) for q in questions}):
            by_id = {}
            for question in questions:
                if not isinstance(question, dict):
                    return _fallback_choices(text)
                qid = str(question.get("id"))
                options = question.get("options")
                if qid not in required or not isinstance(options, list) or len(options) < 2:
                    return _fallback_choices(text)
                clean = []
                for option in options:
                    if not isinstance(option, dict):
                        continue
                    value = str(option.get("value") or "").strip()
                    if not value:
                        continue
                    clean.append({
                        "value": value,
                        "label": str(option.get("label") or value)[:80],
                        "desc": str(option.get("desc") or "")[:160],
                        "recommended": bool(option.get("recommended")),
                    })
                if len(clean) < 2:
                    return _fallback_choices(text)
                # Exactly one recommendation, and only if the model marked one.
                if sum(1 for o in clean if o["recommended"]) > 1:
                    first = next(i for i, o in enumerate(clean) if o["recommended"])
                    for index, option in enumerate(clean):
                        option["recommended"] = index == first
                by_id[qid] = {"id": qid, "title": str(question.get("title") or qid)[:60],
                              "options": clean}
            data["questions"] = [by_id[qid] for qid in
                                 ("archetype", "palette", "ratio", "density",
                                  "illustration", "language")]
            # The mechanism plate needs the generated scene by default.  A
            # vector-only request is the exception, never the default.
            if not re.search(r"纯矢量|矢量|线框|vector|全部可编辑", text, re.I):
                for question in data["questions"]:
                    if str(question.get("id")) != "illustration":
                        continue
                    for option in question.get("options") or []:
                        option["recommended"] = str(option.get("value")) == "image"
            data["summary"] = str(data.get("summary") or "")[:400]
            _canonicalize_palette(data)
            _prefer_archetype(data, text)
            _prefer_choices(data, text)
            return _attach_reference(data, dna) if dna else data
    except Exception as exc:
        import sys
        print("clarify fallback:", type(exc).__name__, exc, file=sys.stderr)
    if dna:
        return _attach_reference(_fallback_choices(text), dna)
    return _fallback_choices(text)


def _contradicts_layout(text: str, arch: str, ratio: str) -> bool:
    """Catch the model rewriting a chosen archetype into a different one.

    The compose prompt is generated in free text, so a model can silently turn
    a signal pathway into a closed-loop/ring figure even though the user just
    chose signal_pathway. Falling back to the deterministic template is better
    than handing the renderer a self-contradictory prompt.
    """
    value = str(text or "")
    low = value.lower()
    if arch != "closed_loop" and (
            any(word in value for word in ("闭环", "闭合回路"))
            or "closed-loop" in low or "closed loop" in low or "feedback loop" in low
    ):
        return True
    if arch != "ring_architecture" and ("同心圆环" in value or "concentric ring" in low):
        return True
    if arch == "signal_pathway" and any(word in value for word in ("循环通路", "环形通路")):
        return True
    ratios = {"3:2": ("16:9", "4:3", "1:1", "3:4"), "16:9": ("4:3", "3:2", "1:1", "3:4"),
              "4:3": ("16:9", "3:2", "1:1", "3:4"), "1:1": ("16:9", "3:2", "4:3", "3:4"),
              "3:4": ("16:9", "3:2", "4:3", "1:1"), "2:1": ("16:9", "3:2", "4:3", "1:1")}
    for other in ratios.get(ratio, ()):
        if other in value and ratio not in value:
            return True
    return False


def compose_enhanced_prompt(original_text: str, answers: dict, config: dict,
                            style_dna=None) -> tuple[str, list[int], str]:
    """Synthesize concise, high-impact prompt based on user's exact selections."""
    answers = answers if isinstance(answers, dict) else {}
    arch = str(answers.get("archetype") or "closed_loop")
    palette = str(answers.get("palette") or "nature")
    ratio = str(answers.get("ratio") or "3:2")
    density = str(answers.get("density") or "standard")
    illustration = str(answers.get("illustration") or "vector")
    language = str(answers.get("language") or "en")
    if arch not in archetypes.ARCHETYPE_DESCRIPTIONS:
        arch = "closed_loop"
    if palette not in PALETTE_NOTES:
        palette = "nature"
    if ratio not in ("3:2", "16:9", "1:1", "4:3", "2:1", "3:4"):
        ratio = "3:2"
    if density not in ("minimal", "standard", "dense"):
        density = "standard"
    if illustration not in ("vector", "image"):
        illustration = "vector"
    if language not in ("en", "bilingual", "zh"):
        language = "en"

    ratio_map = {
        "3:2": [1536, 1024],
        "16:9": [1600, 900],
        "1:1": [1200, 1200],
        "4:3": [1440, 1080],
        "2:1": [1600, 800],
        "3:4": [900, 1200],
    }
    canvas = ratio_map.get(ratio, [1536, 1024])

    payload_context = chr(10).join([
        f"用户原始描述：{original_text}",
        f"用户明确指定的图型：{arch}",
        f"用户指定的配色风格：{palette}",
        f"用户指定的画布比例：{ratio} (建议分辨率: {canvas[0]}x{canvas[1]})",
        f"信息密度：{density}（minimal=只留主路径；standard=每节点一行说明；dense=多级分支与参数）",
        f"出图模式：{illustration}（vector=纯矢量线框；image=核心对象与内层模块用生成式插画）",
        f"图中文字：{language}（en=英文标准术语；bilingual=中英对照；zh=全中文）",
    ])
    reference = style_dna if isinstance(style_dna, dict) else {}
    ref_layout = reference.get("layout_analysis") or {}
    ref_summary = str(reference.get("reference_summary")
                      or reference.get("visual_style_summary") or "")
    reference_mode = str(answers.get("reference_layout") or "follow")
    ref_mode_text = {
        "follow": "严格沿用参考图的排版结构、阅读顺序和标签位置",
        "simplify": "保留参考图主结构，减少无关分栏，但不要改回卡片网格",
        "adapt": "保留参考图的配色与信息层级，按新内容重新组织空间",
    }.get(reference_mode, "严格沿用参考图的排版结构")
    content_mode = str(answers.get("reference_content") or "layout_only")
    content_mode_text = {
        "layout_only": "参考图只提供排版语法；图中对象与机制关系以用户原始描述为准，不得照搬参考图内容",
        "keep_subjects": "可沿用参考图的主体对象/细胞类型，但机制关系以用户原始描述为准",
        "keep_relations": "可沿用参考图的对象层级与箭头关系，具体名称以用户原始描述为准",
    }.get(content_mode, "参考图只提供排版语法；内容以用户原始描述为准")
    if ref_layout or ref_summary:
        payload_context += (chr(10) + "参考图排版（最高优先级，必须先满足）："
                            + ref_summary + chr(10)
                            + json.dumps(ref_layout, ensure_ascii=False, sort_keys=True)
                            + chr(10) + "排版使用方式：" + ref_mode_text
                            + chr(10) + "内容使用方式：" + content_mode_text)

    enhanced_text = ""
    for temperature in (0.25, 0.0):
        try:
            raw = pipeline._chat(config, [
                {"role": "system", "content": COMPOSE_INSTRUCTION},
                {"role": "user", "content": payload_context},
            ], temperature=temperature, max_tokens=1800,
               allow_reasoning_fallback=False)
        except Exception:
            continue
        enhanced_text = _clean_enhanced(raw)
        if len(enhanced_text) >= 120 and not _contradicts_layout(enhanced_text, arch, ratio):
            break
        enhanced_text = ""

    if not enhanced_text:
        # Never degrade the author's own words: use the deterministic template.
        enhanced_text = _template_prompt(original_text, arch, palette, ratio, canvas)
        extras = {
            "minimal": "只保留主路径与核心标签，删掉次要注释。",
            "standard": "每个节点保留一行说明，主次分明。",
            "dense": "保留多级分支、关键参数与注释，允许更高信息密度。",
        }[density]
        enhanced_text += (chr(10) + f"信息密度：{extras}")
        enhanced_text += (chr(10) + ("出图模式：纯矢量线框，不使用位图或生成式插画。"
                                     if illustration == "vector" else
                                     "出图模式：核心对象与内层模块使用生成式插画，其余保持矢量线框与文字。"))
        enhanced_text += (chr(10) + {"en": "图中文字：全部使用英文标准术语。",
                                     "bilingual": "图中文字：中文为主，关键术语附英文括注。",
                                     "zh": "图中文字：全中文。"}[language])
    if ref_layout or ref_summary:
        enhanced_text += (chr(10) + "参考图排版（最高优先级）：" + ref_summary
                          + chr(10) + "排版使用方式：" + ref_mode_text
                          + chr(10) + "内容使用方式：" + content_mode_text)
    return enhanced_text, canvas, illustration
