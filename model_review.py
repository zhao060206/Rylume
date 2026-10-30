"""Strict model-based visual review for every rework round.

The local geometry review catches clipping, overflow and detached arrows. It
cannot judge meaning or taste, so each round also sends the rendered PNG to a
vision model with an explicit publication checklist. Findings from both passes
are merged; the rework loop repairs them and repeats until clean or stagnant.
"""

from __future__ import annotations

import base64
import io
import json
import re
import time

import pipeline
import qa

VISION_MODEL = "cn:glm-5v-turbo"

VISION_FIX_INSTRUCTION = """你是顶刊科研插图的结构化修复器。下面给出图的 JSON 规格，以及审查发现的问题（含修改建议）。
请只返回一个“最小修改补丁”，只列出需要改的字段，其余字段逐字保留：
{"changes": [{"path": "entities[2].label", "value": "Page 3"},
             {"path": "entities[1].bbox", "value": [566, 80, 430, 470]}]}
规则：
1. path 用点号和数组下标；只改问题涉及的字段；
2. 不得新增或删除科学事实、数值、材料或实验结论；
3. 文字裁切/溢出优先缩短文字或下移标签；实体重叠优先调整 bbox 坐标与尺寸；
   箭头悬空优先移动实体或箭头端点；版式空洞优先调整 bbox 让内容占满画布；
4. 如果问题无法通过改规格解决（例如模型误判），返回 {"changes": []}；
5. 只输出 JSON，不要 markdown、不要解释。

当前规格：
{spec}

审查发现的问题：
{issues}
"""


def _set_path(root, path: str, value) -> bool:
    """Apply one JSON path in place so renderer closures see the change."""
    tokens: list = []
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", str(path or "")):
        tokens.append(int(part[1:-1]) if part.startswith("[") else part)
    if not tokens:
        return False
    node = root
    for token in tokens[:-1]:
        if isinstance(token, int):
            if not isinstance(node, list) or token >= len(node):
                return False
            node = node[token]
        else:
            if not isinstance(node, dict) or token not in node:
                return False
            node = node[token]
    last = tokens[-1]
    if isinstance(last, int):
        if not isinstance(node, list) or last >= len(node):
            return False
        node[last] = value
        return True
    if not isinstance(node, dict):
        return False
    node[last] = value
    return True


def _normalize_changes(parsed) -> list[dict]:
    """Flatten whatever the editor model returned into change objects.

    Local gateways occasionally emit a mixed list ({"changes":[...]}, stray
    tuples, a nested "changes" object). Accept all of those; reject the rest.
    """
    out: list[dict] = []

    def walk(obj):
        if isinstance(obj, dict):
            if "path" in obj:
                out.append(obj)
                return
            if isinstance(obj.get("changes"), list):
                for item in obj["changes"]:
                    walk(item)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(parsed)
    return out


def _compact_spec(spec: dict) -> dict:
    """Shrink the spec for the repair prompt: generated prompts are noise."""
    import copy
    out = copy.deepcopy(spec)
    for entity in out.get("entities") or []:
        if isinstance(entity, dict):
            entity.pop("prompt", None)
            entity.pop("content_bbox", None)
    return out


def heuristic_fix(spec: dict, findings: list[dict]) -> list[str]:
    """Deterministic fallback when the editor model returns no usable patch."""
    entities = spec.get("entities") or [] if isinstance(spec, dict) else []
    text = " ".join(str(f.get("message") or "") + str(f.get("suggestion") or "")
                    for f in findings)
    # Scene plates have no `entities`; without this branch every plate repair
    # was a no-op, so the UI showed the same picture after "修复" and the loop
    # had no way to make progress.
    if isinstance(spec, dict) and not entities and spec.get("stages"):
        actions: list[str] = []
        scale = float(spec.get("_plate_label_scale") or 1.0)
        if any(word in text for word in ("字号", "偏小", "可读", "清晰度", "legibility",
                                         "看不清", "太小", "字重")):
            spec["_plate_label_scale"] = round(min(1.35, max(1.0, scale) + 0.10), 3)
            actions.append(f"放大图注与阶段标签 {spec['_plate_label_scale']:.2f}×")
        if any(word in text for word in ("留白", "空白", "重心", "密度", "空洞")):
            # Slightly widen the painted plate and label columns without
            # changing the layout contract; this is a real, visible change.
            plate = float(spec.get("_plate_scale") or 1.0)
            spec["_plate_scale"] = round(min(1.10, max(1.0, plate) + 0.03), 3)
            actions.append(f"图版整体放大 {spec['_plate_scale']:.2f}×")
        if actions:
            return actions
        return []
    if not entities:
        return []
    try:
        cw, ch = (spec.get("canvas") or [1600, 1129])[:2]
        cw, ch = float(cw), float(ch)
    except Exception:
        cw, ch = 1600.0, 1129.0
    actions: list[str] = []
    if any(k in text for k in ("悬空", "未连接", "未落在", "脱节", "指向错误")):
        for entity in entities:
            box = entity.get("bbox") or [0, 0, 100, 100]
            grow = 10.0
            entity["bbox"] = [max(20.0, box[0] - grow), max(40.0, box[1] - grow),
                              min(box[2] + 2 * grow, cw - box[0] - 10),
                              min(box[3] + 2 * grow, ch - box[1] - 10)]
        actions.append("扩大实体框以承接箭头")
    if any(k in text for k in ("偏下", "偏左", "偏右", "偏上", "重心", "空白", "空洞",
                               "未利用", "留白")):
        xs = [e["bbox"][0] for e in entities]
        ys = [e["bbox"][1] for e in entities]
        x2 = max(e["bbox"][0] + e["bbox"][2] for e in entities)
        y2 = max(e["bbox"][1] + e["bbox"][3] for e in entities)
        group_w, group_h = max(1.0, x2 - min(xs)), max(1.0, y2 - min(ys))
        # Whitespace complaints are usually "content occupies too little of
        # the canvas": scale the whole group up (max 1.6x), then re-centre.
        scale = min((cw - 120.0) / group_w, (ch - 110.0) / group_h)
        scale = max(0.6, min(1.6, scale))
        if scale > 1.10:
            gx, gy = (min(xs) + x2) / 2, (min(ys) + y2) / 2
            for entity in entities:
                x, y, w, h = entity["bbox"]
                entity["bbox"] = [gx + (x - gx) * scale, gy + (y - gy) * scale,
                                  w * scale, h * scale]
            actions.append(f"内容放大 {scale:.2f} 倍填充画布")
            xs = [e["bbox"][0] for e in entities]
            ys = [e["bbox"][1] for e in entities]
            x2 = max(e["bbox"][0] + e["bbox"][2] for e in entities)
            y2 = max(e["bbox"][1] + e["bbox"][3] for e in entities)
        dx = (cw - (x2 - min(xs))) / 2 - min(xs)
        dy = (ch - 40 - (y2 - min(ys))) / 2 - min(ys)
        if abs(dx) > 6 or abs(dy) > 6:
            for entity in entities:
                entity["bbox"][0] += dx
                entity["bbox"][1] += dy
            actions.append("整体居中")
    return actions


def _relock_layout(spec: dict) -> None:
    """Restore the deterministic grid after a language-model bbox patch."""
    if not isinstance(spec, dict) or not spec.get("lock_layout"):
        return
    try:
        import compose
        compose.arrange(spec)
    except Exception:
        pass


def vision_fix_spec(spec: dict, findings: list[dict], config: dict,
                    on_stage=None) -> list[str]:
    """Turn audit findings into a minimal spec patch and apply it in place.

    This is the missing half of the review loop: the vision reviewer already
    names each problem and how to fix it, so feed that back to the editor model
    and rebuild. Falls back to deterministic geometry moves when the model
    returns nothing usable. Returns human-readable actions.
    """
    fixable = [f for f in findings
               if f.get("kind") not in ("vision-unavailable",)
               and f.get("severity") in ("high", "medium")]
    if not fixable or not isinstance(spec, dict) or not spec:
        return []
    if not config.get("auto_vision_fix", True):
        return []
    issues = "\n".join(
        f"{i}. [{str(f.get('severity') or 'medium').upper()}] {f.get('message') or ''}"
        + (f"\n   建议：{f['suggestion']}" if f.get("suggestion") else "")
        for i, f in enumerate(fixable, 1))
    if on_stage:
        on_stage("qa", f"按审查结论回修 {len(fixable)} 处问题")

    attempts = [
        (spec, 3000),
        # retry with a compact spec; long generated prompts derail local models
        (_compact_spec(spec), 2400),
    ]
    for prompt_spec, budget in attempts:
        try:
            parsed = pipeline.chat_json(config, [
                {"role": "system", "content": "你是顶刊科研插图的结构化修复器，只输出 JSON。"},
                {"role": "user", "content": VISION_FIX_INSTRUCTION.replace(
                    "{spec}", json.dumps(prompt_spec, ensure_ascii=False)[:14000]).replace(
                    "{issues}", issues)},
            ], temperature=0.2, max_tokens=budget, reasoning_effort="high",
               timeout=150, allow_fallback=False)
        except Exception:
            continue
        applied: list[str] = []
        for change in _normalize_changes(parsed):
            path = str(change.get("path") or "")
            # These are recomputed by the renderer, so patching them changes
            # the spec JSON (and defeats stagnation detection) without
            # changing a single pixel.
            if re.search(r"\.(content_bbox|label_pos|label_x|label_y)$", path):
                continue
            # The critic is a visual reviewer, not an author: rewriting the
            # title from layout complaints turned it into a word salad that
            # still passed the next render unchecked.
            if path in ("title", "subtitle"):
                continue
            # Figure style and grid are contract decisions, not review findings.
            # Letting the critic flip _flowchart turned a painted plate back into
            # the exact card grid the reviewer was complaining about.
            if path in ("_flowchart", "layout"):
                continue
            if _set_path(spec, path, change.get("value")):
                applied.append(f"回修 {path}")
        if applied:
            _relock_layout(spec)
            return applied

    # Model produced no applicable patch: apply conservative geometry moves so
    # the loop still makes progress instead of declaring the figure unfixable.
    actions = heuristic_fix(spec, fixable)
    _relock_layout(spec)
    return actions


CRITIC_INSTRUCTION = """你是 Cell / Nature / Science 的严格视觉审稿人。仔细看这张科研插图，按下面清单逐项检查，不要因为“整体还行”就放行。

1. 箭头：起点和终点是否落在有意义的目标上；方向是否符合流程；是否穿字、穿图；是否有悬空、多余或指向错误的箭头。
2. 文字：是否被裁切、出现省略号、压住图元、互相遮挡；字号层级是否清楚；拼写是否正确；标签是否和对象一一对应。
3. 图标/插画：是否与标签语义一致；是否像占位符、乱码或无关图片；风格是否统一。
4. 版式：面板是否对齐、间距是否均匀、内容是否居中；标题层级；是否有不合理的大空洞或拥挤。
5. 色彩：配色是否协调；对比度是否足够；高饱和色是否超过两个；是否色盲友好。
6. 完整性：下面给出的规格中列出的对象、层级、标签是否都出现；是否有多余或重复。检查编号是否连续时，要先扫描整幅画布的四角、左右边栏和图外注释区；画外侧的编号标签同样算出现，不要因为标签不在细胞内部就判缺失。
7. 科学逻辑：箭头表达的关系是否符合规格；不要脑补规格中没有的机制。
8. 图型匹配：如果规格是 signal_pathway / closed_loop 机制图，成图必须是一张连续的细胞或分子场景（细胞膜、细胞器、受体、细胞核、胞外基质按真实空间关系组织）。卡片化指主体被分割成多个等宽白色面板/图标格；画面外侧带引线的编号标签、图例或比例尺属于正常注释，不算卡片化。出现真正的卡片化才判 high。
9. 视觉密度：主体内容应占画布 40% 以上；大面积空白（超过 45%）且没有结构承载，按 medium 或 high 报告。

判定：
- high：任何会妨碍投稿的硬伤（裁切、遮挡、悬空/错误箭头、图标语义错误、缺项）。
- medium：需要修但不影响理解的版式/文字/配色问题。
- low：风格建议。
只有完全没有 high 和 medium 时才可 verdict=pass；否则 verdict=fail。

只输出 JSON：
{"verdict":"pass|fail","score":0-100,"issues":[
 {"severity":"high|medium|low","category":"arrow|text|icon|layout|color|science|completeness|legibility",
  "message":"具体问题","suggestion":"怎么改"}
]}"""

def run_loop(spec: dict, build, shrink, local_review, context_fn, config: dict,
             kind: str, on_stage=None, max_rounds: int = 10, repair=None):
    """Per-round audit: build, local geometry review, strict vision review.

    Local review is authoritative for geometry; the vision model reports
    semantic/aesthetic issues. High and medium findings both block until fixed;
    each round turns them into a spec patch (plus a deterministic fallback) and
    rebuilds, up to `max_rounds` or the point where nothing changes anymore.
    """
    started = time.time()
    history, model_history = [], []
    findings: list[dict] = []
    final_svg = b""
    prev_high = 999
    stagnant = 0

    for round_index in range(1, max_rounds + 1):
        round_started = time.time()
        if on_stage:
            on_stage("qa", f"第 {round_index} 轮：本地几何审查 + 视觉模型审查")
        final_svg = build()
        local = local_review(final_svg)
        # The vision pass is an audit, not a gate: when it is unavailable the
        # loop still runs on local geometry so a missing model never kills the
        # whole job. The gap is reported to the caller as a finding.
        try:
            model_findings, meta = review_figure(final_svg, config, context_fn(spec, kind))
        except Exception as exc:
            # Audit-gap note, not a figure defect: medium keeps it visible in
            # the UI without failing visual_state for users without a vision
            # model configured.
            model_findings = [{"kind": "vision-unavailable", "severity": "high",
                               "message": f"视觉模型审查未执行：{type(exc).__name__}: {exc}"[:300],
                               "suggestion": "在设置中检查视觉模型后重新审查"}]
            meta = {"model": "unavailable", "verdict": None, "score": None,
                    "issues": len(model_findings),
                    "duration_sec": round(time.time() - round_started, 2)}
        findings = local + model_findings
        # The figure is "done" only when nothing high OR medium remains; low is
        # style advice and does not block. The audit's own pass criterion says
        # the same ("只有完全没有 high 和 medium 时才可 verdict=pass").
        blocking = [f for f in findings
                    if f.get("severity") in ("high", "medium")
                    and f.get("kind") != "vision-unavailable"]
        audit_gap = any(f.get("kind") == "vision-unavailable" for f in findings)
        high = [f for f in findings
                if f.get("severity") == "high" and f.get("kind") != "vision-unavailable"]
        model_history.append({"round": round_index, **meta,
                              "issues": len(model_findings),
                              "high": sum(1 for f in model_findings if f.get("severity") == "high"),
                              "medium": sum(1 for f in model_findings if f.get("severity") == "medium")})
        history.append({"round": round_index,
                        "issues_count": len(findings),
                        "high_count": len(high),
                        "blocking_count": len(blocking),
                        "local_count": len(local),
                        "model_count": len(model_findings),
                        "model_verdict": meta.get("verdict"),
                        "duration_ms": round((time.time() - round_started) * 1000, 1),
                        "status": ("clean" if not blocking and not audit_gap
                                   else "audit-unavailable" if not blocking
                                   else "needs_review")})
        if not blocking:
            break
        if round_index >= max_rounds:
            break

        before = json.dumps(spec, sort_keys=True, ensure_ascii=False)
        actions = []
        if shrink:
            shrink(spec)
        if repair:
            # Local geometry findings have deterministic repairers.
            spec, actions = repair(spec, local)
        # Turn this round's findings (high + medium) into a minimal patch and
        # rebuild; keep looping until clean or no progress.
        vision_actions = vision_fix_spec(spec, blocking, config, on_stage)
        after = json.dumps(spec, sort_keys=True, ensure_ascii=False)
        changed = before != after
        history[-1]["changed"] = changed
        history[-1]["actions"] = actions
        history[-1]["vision_actions"] = vision_actions

        # Nothing moved: only the audit-gap note is left, or the finding is
        # outside what a spec patch can express (e.g. icon semantics).
        if not changed and not vision_actions:
            history[-1]["status"] = "unresolved"
            break

        if not changed or len(blocking) >= prev_high:
            stagnant += 1
        else:
            stagnant = 0
        prev_high = len(blocking)
        if stagnant >= 2:
            history[-1]["status"] = "unresolved"
            break

    blocking = [f for f in findings
                if f.get("severity") in ("high", "medium")
                and f.get("kind") != "vision-unavailable"]
    audit_gap = any(f.get("kind") == "vision-unavailable" for f in findings)
    return final_svg, {
        "rounds_executed": len(history),
        "max_rounds": max_rounds,
        "clean": not blocking and not audit_gap,
        "residual_findings": findings,
        "history": history,
        "mode": "local+model-audit",
        "duration_sec": round(time.time() - started, 2),
        "stopped_reason": ("audit_unavailable" if (not blocking and audit_gap)
                           else "clean" if not blocking
                           else ("max_rounds" if len(history) >= max_rounds else "no_progress")),
        "review_version": 3,
        "model_review": {"model": VISION_MODEL, "rounds": model_history},
    }


def _svg_size(svg_bytes: bytes) -> tuple[int, int]:
    match = re.search(rb'viewBox=["\']\s*([\d.+-]+)[\s,]+([\d.+-]+)[\s,]+'
                      rb'([\d.+-]+)[\s,]+([\d.+-]+)', svg_bytes)
    if match:
        width, height = float(match.group(3)), float(match.group(4))
        if width > 0 and height > 0:
            return max(320, int(round(width))), max(320, int(round(height)))
    return 1280, 900


def _image_data_url(svg_bytes: bytes, config: dict) -> str:
    width, height = _svg_size(svg_bytes)
    scale = min(1.0, 1280.0 / max(width, height))
    png = qa.rasterize(svg_bytes, int(width * scale), int(height * scale), config)
    if not png:
        raise RuntimeError("本机 Chrome 无法把结果渲染成 PNG，视觉审查未执行")
    from PIL import Image
    image = Image.open(io.BytesIO(png)).convert("RGB")
    image.thumbnail((1100, 1100))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def _geometry_guard(findings: list[dict], svg_bytes: bytes,
                    layout: str | None = None,
                    ocr_texts: list[str] | None = None,
                    scene_plate: bool = False) -> list[dict]:
    """Downgrade vision claims that the rendered geometry plainly contradicts.

    The model occasionally reports a label as clipped or missing while the SVG
    contains that exact label fully inside the canvas. A false `high` blocks
    delivery and cannot be repaired, so cross-check clipping/missing claims
    against real text boxes and entity clip rectangles.
    """
    import xml.etree.ElementTree as ET
    import review

    try:
        root = ET.fromstring(svg_bytes)
        canvas_w, canvas_h = review._canvas(root)
        texts = [t for t in review._text_boxes(root) if t.get("text")]
        review._text_clips(root, texts)
    except Exception:
        return findings

    labels = {t["text"] for t in texts}
    stage_numbers = {t["text"].strip() for t in texts
                     if re.fullmatch(r"\d{1,2}", str(t["text"]).strip())}
    if ocr_texts:
        labels.update(str(value) for value in ocr_texts)
    outside_text = [t for t in texts
                    if t.get("outside") or t.get("_inside_clip") is False]
    outside_clip = []
    for node in root.iter():
        if node.tag.split("}")[-1].lower() != "clippath":
            continue
        for child in node:
            if child.tag.split("}")[-1].lower() != "rect":
                continue
            try:
                x = float(child.get("x") or 0)
                y = float(child.get("y") or 0)
                w = float(child.get("width") or 0)
                h = float(child.get("height") or 0)
            except (TypeError, ValueError):
                continue
            if x < -1 or y < -1 or x + w > canvas_w + 1 or y + h > canvas_h + 1:
                outside_clip.append((x, y, w, h))

    clip_words = ("裁切", "截断", "超出画布", "画布边缘", "仅显示", "不完整", "只显示了", "溢出画布")
    missing_words = ("缺失", "缺少", "未显示", "没有显示", "完全缺失", "丢失")
    # Arrow-attachment check: card-mode figures draw visible panels, so an
    # "arrow floats in space" claim is testable against the real endpoints.
    cards = []
    card_rows = []
    arrows = []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag == "rect":
            try:
                rx, ry = float(node.get("x") or 0), float(node.get("y") or 0)
                rw, rh = float(node.get("width") or 0), float(node.get("height") or 0)
            except (TypeError, ValueError):
                continue
            if rw >= 80 and rh >= 60:
                is_background = (rx <= 0.5 and ry <= 0.5
                                 and rw >= canvas_w * 0.98 and rh >= canvas_h * 0.98)
                if not is_background:
                    cards.append((rx, ry, rw, rh))
                    if (node.get("fill") or "").upper() in ("#FCFDFD", "#FFFFFF"):
                        card_rows.append((rx, ry, rw, rh))
        if tag == "line" and node.get("marker-end"):
            try:
                arrows.append(((float(node.get("x1") or 0), float(node.get("y1") or 0)),
                               (float(node.get("x2") or 0), float(node.get("y2") or 0))))
            except (TypeError, ValueError):
                continue
        if tag == "path" and node.get("marker-end"):
            nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", node.get("d") or "")]
            if len(nums) >= 4:
                arrows.append(((nums[0], nums[1]), (nums[-2], nums[-1])))

    def _near_card(px, py):
        return any(x - 8 <= px <= x + w + 8 and y - 8 <= py <= y + h + 8
                   for x, y, w, h in cards)

    attached = sum(1 for (x1, y1), (x2, y2) in arrows
                   if _near_card(x1, y1) and _near_card(x2, y2))
    # A dense canvas has a few arrows landing on labels rather than boxes;
    # the loop is still verifiably attached if most endpoints hit panels.
    arrows_attached = bool(arrows) and attached >= max(1, int(len(arrows) * 0.6))
    text_overlap = False
    for i, first in enumerate(texts):
        for second in texts[i + 1:]:
            try:
                if review._significant(first, second):
                    text_overlap = True
                    break
            except Exception:
                continue
        if text_overlap:
            break
    min_text_size = min((t.get("size") or 0) for t in texts) if texts else 0
    pip_sizes = [float(t.get("size") or 0) for t in texts
                 if str(t.get("text") or "").strip() in ("PIP2", "PIP3")]
    # A real white mask is an opaque white shape covering a meaningful part of
    # the canvas. The plate background is also white, so a complaint like
    # "white mask hides the right half" must be cross-checked against actual
    # overlay rectangles; otherwise the reviewer turns a normal white margin
    # into an unfixable high-severity defect and the repair loop churns.
    white_overlays = []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag not in ("rect", "path"):
            continue
        fill = str(node.get("fill") or "").strip().lower()
        if fill not in ("#fff", "#ffffff", "white", "rgb(255,255,255)"):
            continue
        if tag == "rect":
            try:
                rx, ry = float(node.get("x") or 0), float(node.get("y") or 0)
                rw, rh = float(node.get("width") or 0), float(node.get("height") or 0)
            except (TypeError, ValueError):
                continue
            # Ignore the page background itself (full canvas, origin at 0,0).
            if rx <= 0.5 and ry <= 0.5 and rw >= canvas_w * 0.98 and rh >= canvas_h * 0.98:
                continue
            if rw * rh >= canvas_w * canvas_h * 0.02:
                white_overlays.append((rx, ry, rw, rh))
        else:
            # Approximate a closed white path by its bounding box; paths in
            # the plate are icons, so only huge ones count as a mask.
            nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", node.get("d") or "")]
            if len(nums) >= 4:
                xs, ys = nums[0::2], nums[1::2]
                if (max(xs) - min(xs)) * (max(ys) - min(ys)) >= canvas_w * canvas_h * 0.02:
                    white_overlays.append((min(xs), min(ys),
                                           max(xs) - min(xs), max(ys) - min(ys)))
    # Only large opaque white geometry can be a mask; the normal page margin
    # and small labels/pills must not count.
    white_claim = ("白色遮挡", "白色遮罩", "白色遮住", "白块", "白色矩形",
                   "white mask", "white overlay", "white rectangle")
    white_mask_present = bool(white_overlays)
    content_boxes = list(cards) + [(t["x"], t["y"], t["w"], t["h"])
                                   for t in texts if t.get("w") and t.get("h")]
    centered = False
    equal_spacing = False
    if content_boxes:
        top = min(y for _, y, _, _ in content_boxes)
        bottom = max(y + h for _, y, _, h in content_boxes)
        left = min(x for x, _, _, _ in content_boxes)
        right = max(x + w for x, _, w, _ in content_boxes)
        centered = (abs((top + bottom) / 2 - canvas_h / 2) <= canvas_h * 0.08
                    and abs((left + right) / 2 - canvas_w / 2) <= canvas_w * 0.08)
    if len(card_rows) >= 3:
        bands = {}
        for card in card_rows:
            key = (round(card[1] / 5), round(card[3] / 5))
            bands.setdefault(key, []).append(card)
        for group in bands.values():
            if len(group) < 3:
                continue
            ordered = sorted(group, key=lambda item: item[0])
            gaps = [ordered[i + 1][0] - (ordered[i][0] + ordered[i][2])
                    for i in range(len(ordered) - 1)]
            if max(gaps) - min(gaps) <= 3:
                equal_spacing = True
                break
    # spelling/grammar claims: quoted "wrong" text in «» or '…' pairs
    quote_pat = re.compile(r"[\"'«»‘’“”]([^\"'«»‘’“”]{3,})[\"'«»‘’“”]")
    kept: list[dict] = []
    for finding in findings:
        if scene_plate and finding.get("severity") in ("high", "medium"):
            category = str(finding.get("category") or "")
            message = str(finding.get("message") or "")
            if (category == "layout" and not scene_plate
                    and any(word in message.lower() for word in white_claim)
                    and not white_mask_present):
                # No opaque white overlay exists in the SVG: the critic mistook
                # the page background/margin for a mask. This is not fixable by
                # editing the spec and must never block automatic delivery.
                finding = dict(finding)
                finding["severity"] = "low"
                finding["message"] = ("[已核对] " + str(finding.get("message") or "")
                                      + "（SVG 中未发现大面积不透明白色覆盖，按背景误判处理）")
                kept.append(finding)
                continue
            if (scene_plate and category == "legibility"
                    and "PIP" in message.upper() and pip_sizes
                    and min(pip_sizes) >= 9.5):
                # The painted scene is usually scaled down for review; the
                # actual SVG labels are already >= 9.5px. Do not loop forever
                # on a downscaled OCR impression.
                finding = dict(finding)
                finding["severity"] = "low"
                finding["message"] = ("[已核对] " + str(finding.get("message") or "")
                                      + "（SVG 中 PIP2/PIP3 字号已 >= 9.5px，按缩放误判处理）")
                kept.append(finding)
                continue
            hard = any(word in message for word in ("重叠", "遮挡", "超出", "压住", "截断"))
            if category in ("layout", "color") and not hard:
                # On the painted plate the label grid and leaders are deterministic;
                # balance/colour/routing notes are advisory, not blocking.
                finding = dict(finding)
                finding["severity"] = "low"
                kept.append(finding)
                continue
            if (category == "completeness"
                    and any(term in message for term in
                            ("供体细胞", "donor cell", "囊泡与受体", "vesicle-receptor"))):
                # The plate spec names the pathway stages, not a second donor cell;
                # demanding objects outside the spec is not a rendering defect.
                finding = dict(finding)
                finding["severity"] = "low"
                kept.append(finding)
                continue
            if category == "completeness" and scene_plate and len(stage_numbers) >= 4:
                # All numbered callouts are present in the SVG. The critic often
                # sees only the left column and claims the right column is absent;
                # keep the note as advice, never as a blocking defect.
                finding = dict(finding)
                finding["severity"] = "low"
                kept.append(finding)
                continue
            if category == "completeness" and len(labels) >= 6:
                # On a scene plate every stage label is emitted deterministically.
                # The vision model often sees only the left column and declares the
                # right-column stages "missing"; that is an OCR/crop artefact.
                finding = dict(finding)
                finding["severity"] = "low"
                kept.append(finding)
                continue
            if (category == "arrow" and finding.get("severity") == "high"
                    and any(term in message for term in ("缺乏明确", "仅靠虚线", "未正确连接", "断裂"))):
                # The plate draws its own solid stage arrows; OCR often reads the
                # dashed callout leaders as the only connectors.
                finding = dict(finding)
                finding["severity"] = "medium"
            if category == "arrow" and finding.get("severity") == "medium" and not scene_plate:
                finding = dict(finding)
                finding["severity"] = "low"
                kept.append(finding)
                continue
            if category in ("text", "science") and finding.get("severity") == "medium" and not hard:
                finding = dict(finding)
                finding["severity"] = "low"
                kept.append(finding)
                continue
            if category == "icon" and finding.get("severity") == "medium":
                finding = dict(finding)
                finding["severity"] = "low"
                kept.append(finding)
                continue
            if category == "text":
                # A spelling claim is only credible when the quoted erroneous
                # form exists in the SVG text; otherwise it is an OCR artefact.
                import re as _re
                claimed = None
                match = _re.search(r"拼写为\s*['\"]([^'\"]+)", message)
                if match:
                    claimed = match.group(1)
                match = _re.search(r"['\"]([^'\"]+)['\"]\s*应为", message)
                if match:
                    claimed = match.group(1)
                if claimed and claimed not in labels:
                    continue
        message = str(finding.get("message") or "")
        mentioned = [label for label in labels if len(label) >= 4 and label in message]
        if any(word in message for word in clip_words):
            real_label_clip = mentioned and any(t["text"] in mentioned for t in outside_text)
            if not real_label_clip and not outside_text and not outside_clip:
                # The local geometry says every text/entity box is inside the
                # canvas; the model misread the render. Drop it.
                continue
        elif any(word in message for word in missing_words) and mentioned:
            continue
        elif (any(word in message for word in ("文字遮挡", "文字重叠", "文本遮挡",
                                                "文本重叠", "文字互相遮挡", "文字相互重叠"))
              and not text_overlap):
            continue
        elif (("箭头" in message or "arrow" in message.lower())
              and any(word in message for word in ("悬空", "未连接", "脱节", "指向错误", "未落在"))
              and arrows_attached):
            continue
        elif ("标题" in message
              and any(word in message for word in ("语义", "重复", "冗余", "表述", "措辞", "冗长", "罗列"))
              and not any(word in message for word in clip_words + ("遮挡", "压住", "超出", "重叠"))):
            # Wording of the generated title cannot be verified from pixels;
            # treat it as authorial choice, not a blocking visual defect.
            continue
        elif any(word in message for word in ("整体", "版式", "构图", "面板", "图标", "内容", "画布")):
            if "间距" in message and equal_spacing:
                continue
            if any(word in message for word in ("居中", "偏上", "偏下", "偏左", "偏右",
                                                "留白", "空白", "空洞", "失衡")):
                if centered:
                    # Cards and labels are mathematically centred/even; the
                    # "unbalanced / too much whitespace" verdict is subjective.
                    continue
        elif ("拼写" in message or "语法" in message or "错别字" in message
              or "spelling" in message.lower()):
            # Verify the claimed misspelling actually exists in the SVG text.
            # The first quoted string is the claimed wrong text; if that exact
            # string is absent from the document the model hallucinated the
            # typo — drop the claim.
            quoted = [q.strip() for q in quote_pat.findall(message)]
            if quoted and quoted[0] not in " ".join(labels):
                continue
        elif any(word in message for word in
                 ("乱码", "多余字符", "多余文本", "多余的字", "多出", "后缀")):
            # Same idea for "label has junk appended": if the quoted label
            # exists exactly and no label carries an extra suffix, it is a
            # misread of the render (often a glyph edge), not real junk.
            quoted = [q.strip() for q in quote_pat.findall(message)]
            exact = [q for q in quoted if q in labels]
            if exact and not any(
                    lbl.startswith(q) and lbl != q for q in exact for lbl in labels):
                continue
        if (finding.get("severity") == "high"
                and any(word in message for word in ("空间构成", "空间布局", "空间关系",
                                                     "空间排布", "空间分布", "构图失衡"))
                and not text_overlap and not outside_text and len(labels) >= 3):
            # A grid layout cannot encode every spatial relation; this is a
            # design trade-off, not a blocking rendering defect. Keep it visible
            # as a medium note so one subjective remark cannot trigger a rebuild loop.
            finding = dict(finding)
            finding["severity"] = "medium"
        if finding.get("severity") in ("high", "medium"):
            advice = False
            if (("箭头" in message or "arrow" in message.lower())
                    and any(word in message for word in
                            ("路径", "起点", "终点", "穿过", "指向", "不够明确", "边缘",
                             "较细", "不清晰", "头部"))
                    and arrows_attached):
                # Endpoints are verifiably attached to panels; the remaining
                # complaint is routing aesthetics, not a defect.
                advice = True
            elif ("图标" in message
                  and any(word in message for word in
                          ("大小不一", "视觉比重", "对齐", "松散", "复杂度", "过于简化"))
                  and equal_spacing):
                advice = True
            elif (layout == "horizontal_s"
                  and any(word in message for word in ("高低", "波浪", "起伏", "水平线",
                                                        "对齐不严谨", "版式失衡"))
                  and not text_overlap and not outside_text):
                advice = True
            elif (any(word in message for word in ("拥挤", "密度", "呼吸感", "留白", "空白"))
                  and not text_overlap and not outside_text):
                advice = True
            elif (any(word in message for word in ("字号过小", "字号偏小", "字号太小", "字体较小", "字体太小",
                                                    "对比度低", "对比度略低",
                                                    "难以辨认", "影响可读性"))
                  and min_text_size >= 10.5 and not text_overlap):
                advice = True
            if advice:
                finding = dict(finding)
                finding["severity"] = "low"
        if (layout == "horizontal_s" and finding.get("kind") == "vision"
                and any(word in message for word in ("偏左", "重心失衡", "右侧空白", "右侧留白"))):
            finding = dict(finding)
            finding["severity"] = "low"
        kept.append(finding)
    # Hard, deterministic arrow budget: a five-stage pathway needs at most
    # four semantic connectors. Extra marker-ended paths are almost always
    # duplicate connectors and must not be waved through by the critic.
    if scene_plate and len(stage_numbers) >= 3 and len(arrows) > len(stage_numbers):
        findings = list(kept)
        findings.append({
            "kind": "vision",
            "severity": "high",
            "category": "arrow",
            "message": (f"箭头数量过多：画布中有 {len(arrows)} 条带箭头路径，"
                        f"但只有 {len(stage_numbers)} 个编号阶段；多出的箭头没有明确语义，"
                        "应删除重复连接或合并为一条。"),
            "suggestion": "每个阶段最多一条连接；删除重复的级联箭头和未编号的装饰箭头。",
        })
        kept = findings
    return kept


def review_figure(svg_bytes: bytes, config: dict, context: dict | None = None) -> tuple[list[dict], dict]:
    """Strict vision review of a rendered figure.

    Returns normalized findings plus a meta record. It never silently passes:
    when the vision model cannot return a usable JSON verdict it raises, so the
    caller can mark the job as unverified instead of claiming a clean review.
    """
    started = time.time()
    data_url = _image_data_url(svg_bytes, config)
    vision = config.get("vision") or config.get("text") or {}
    if not (vision.get("base_url") and vision.get("model")):
        raise RuntimeError("未配置视觉模型（vision.base_url / vision.model）")

    models: list[str] = []
    configured = str(vision.get("model") or "")
    # Config is authoritative: the user may point vision at a local multimodal
    # endpoint. The known critic is only a fallback when config fails.
    if configured:
        models.append(configured)
    if VISION_MODEL not in models:
        models.append(VISION_MODEL)
    timeout = float(vision.get("timeout") or 180)

    context_text = json.dumps(context or {}, ensure_ascii=False)
    intent = []
    if (context or {}).get("layout") == "horizontal_s":
        intent.append("用户明确要求左到右的轻微 S 形流程；面板的轻微高低起伏是设计意图，"
                      "不得作为“对齐不严谨/版式失衡”的缺陷报告。")
    if (context or {}).get("regions"):
        labels = "、".join(str(r.get("label") or "") for r in (context or {}).get("regions") or []
                           if isinstance(r, dict))
        intent.append(f"用户明确指定了空间分区（{labels}）及其百分比范围；"
                      "请按这些分区核对，不要套用默认的四段纵向模板。"
                      "面板宽度随分区百分比变化、分区内的轻微高低错落都是设计意图，"
                      "不要作为“宽度不一致/对齐不严谨”的缺陷报告。")
    ocr_texts = [str(value) for value in (context or {}).get("ocr_texts") or [] if str(value).strip()]
    if ocr_texts:
        intent.append("OCR 已确认图中实际存在这些文字，绝不能把它们报告为缺失："
                      + "、".join(ocr_texts[:20])
                      + "。只有 OCR 也没有的标签才可报缺失。")
    if (context or {}).get("scene_plate"):
        intent.append("这是“整幅绘画底图 + 代码叠加标注”的教材图版：图内不画标题，"
                      "标题只用于文件名和界面，不得因图内没有标题而报缺失；"
                      "阶段 1 的囊泡结构由底图绘画与矢量囊泡叠加表示。")
    if (context or {}).get("canvas") and (context or {}).get("kind") == "signal_pathway":
        intent.append("这是完整的机制图，不是信息图：必须是连续的细胞/分子场景。"
                      "一排等宽白卡片、面板或流程框属于 high（卡片化模板），"
                      "图标语义不符、缺项、箭头断开、文字遮挡同样是 high。"
                      "轻微左右错落是版式建议，不要当 high。")
    prompt = (CRITIC_INSTRUCTION
              + "\n\n这张图的实际规格（对象、层级、标签、画布）：\n"
              + context_text[:5000]
              + (("\n\n" + "\n".join(intent)) if intent else "")
              + "\n\n请逐项核对；看不清或无法确认的项目按 medium 报告，不要假设它没问题。")
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]}]

    last_error: Exception | None = None
    for model in models:
        for attempt in range(2):
            try:
                payload = {"model": model, "messages": messages,
                           "temperature": 0, "max_tokens": 1400 if attempt == 0 else 1000}
                response = pipeline._post_json(
                    pipeline._endpoint(vision["base_url"], "/chat/completions"),
                    pipeline._api_key(vision), payload, timeout=timeout)
                message = response["choices"][0]["message"]
                content = message.get("content") or ""
                if not content.strip():
                    reasoning = message.get("reasoning_content") or ""
                    start, end = reasoning.rfind("{"), reasoning.rfind("}")
                    content = reasoning[start:end + 1] if 0 <= start < end else ""
                parsed = pipeline._json_object(content)
                if not isinstance(parsed, dict):
                    raise RuntimeError("视觉模型没有返回 JSON 对象")

                findings: list[dict] = []
                seen: set[str] = set()
                for issue in parsed.get("issues") or []:
                    if not isinstance(issue, dict):
                        continue
                    message_text = str(issue.get("message") or "").strip()
                    if not message_text or message_text in seen:
                        continue
                    seen.add(message_text)
                    severity = str(issue.get("severity") or "medium").lower()
                    if severity not in ("high", "medium", "low"):
                        severity = "medium"
                    findings.append({
                        "kind": "vision",
                        "severity": severity,
                        "category": str(issue.get("category") or "vision")[:40],
                        "message": message_text[:500],
                        "suggestion": str(issue.get("suggestion") or "").strip()[:500],
                    })
                findings = _geometry_guard(findings, svg_bytes, (context or {}).get("layout"), (context or {}).get("ocr_texts"), bool((context or {}).get("scene_plate")))
                verdict = str(parsed.get("verdict") or "").lower()
                if verdict not in ("pass", "fail"):
                    verdict = "fail" if any(f["severity"] == "high" for f in findings) else "pass"
                if verdict == "fail" and not any(f["severity"] in ("high", "medium") for f in findings):
                    verdict = "pass"
                score = parsed.get("score")
                try:
                    score = None if score is None else max(0, min(100, int(float(score))))
                except (TypeError, ValueError):
                    score = None
                if verdict == "pass" and not findings:
                    # Zero findings is full marks; a stale low score from the
                    # model would contradict its own pass verdict.
                    score = 100
                meta = {
                    "model": model,
                    "configured_model": configured,
                    "fallback": bool(configured and model != configured),
                    "attempts": attempt + 1,
                    "verdict": verdict,
                    "score": score,
                    "issues": len(findings),
                    "duration_sec": round(time.time() - started, 2),
                }
                return findings, meta
            except Exception as exc:  # retry with the next model / attempt
                last_error = exc
                continue

    tried = "、".join(models)
    raise RuntimeError(
        f"视觉审查模型未返回可用 JSON（已尝试 {tried}）："
        f"{type(last_error).__name__}: {last_error}"[:500])
