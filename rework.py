"""Pixel-level Automated Rework & Collision Repair Engine.

Implements an iterative self-healing layout loop (up to 10 rounds) that audits
rendered SVG geometry for text-text occlusion, text-entity collision, entity overlap,
and canvas boundary overflows, mathematically repairing bounding boxes and label
anchors until flawless or max rounds reached with explicit diagnostic reporting.
"""

from __future__ import annotations

import copy
import math
import review

MAX_REWORK_ROUNDS = 10


def repair_scene_step(scene: dict, findings: list[dict]) -> tuple[dict, list[str]]:
    """Apply one step of geometric repulsion and clamping based on audit findings."""
    scene = copy.deepcopy(scene)
    cw, ch = scene.get("canvas") or [1536, 1024]
    actions = []

    entity_map = {e["id"]: e for e in scene.get("entities") or []}
    label_to_entity = {e.get("label"): e for e in scene.get("entities") or [] if e.get("label")}

    for f in findings:
        kind = f.get("kind")
        msg = f.get("message") or ""
        box = f.get("box") or [0, 0, 0, 0]

        # 1. Label out of canvas bounds
        if "超出画布" in msg:
            for text_lbl, ent in label_to_entity.items():
                # review truncates the label to 30 chars in its message; match
                # on the prefix so long labels still find their entity.
                if text_lbl and (text_lbl in msg or msg.find(text_lbl[:30]) >= 0):
                    dx = float(ent.get("label_dx") or 0)
                    dy = float(ent.get("label_dy") or 0)
                    bx, by, bw, bh = box
                    if bx < 6:
                        dx += (6 - bx)
                    if by < 6:
                        dy += (6 - by)
                    if bx + bw > cw - 6:
                        dx -= (bx + bw - (cw - 6))
                    if by + bh > ch - 6:
                        dy -= (by + bh - (ch - 6))
                    ent["label_dx"], ent["label_dy"] = dx, dy
                    actions.append(f"Clamped label {text_lbl} into canvas")

        # 2. Label overlaps entity or too close
        elif "与实体距离过近" in msg or "压住实体" in msg or ("遮挡实体" in msg and "标签" in msg):
            for text_lbl, ent in label_to_entity.items():
                if text_lbl and (text_lbl in msg or msg.find(text_lbl[:30]) >= 0):
                    ent["label_dy"] = float(ent.get("label_dy") or 0) + 24.0
                    actions.append(f"Shifted label {text_lbl} downward by 24px to prevent entity overlap")

        # 3. Two labels overlapping each other
        elif "标签互相遮挡" in msg:
            parts = msg.replace("标签互相遮挡：", "").split(" / ")
            if len(parts) == 2:
                lbl_a, lbl_b = parts[0].strip(), parts[1].strip()
                ent_b = label_to_entity.get(lbl_b)
                if ent_b:
                    ent_b["label_dy"] = float(ent_b.get("label_dy") or 0) + 26.0
                    actions.append(f"Separated overlapping label {lbl_b} downward by 26px")

        # 4. Entity-Entity overlap
        elif "实体框重叠" in msg:
            parts = msg.replace("实体框重叠：", "").split(" / ")
            if len(parts) == 2:
                ea, eb = entity_map.get(parts[0].strip()), entity_map.get(parts[1].strip())
                if ea and eb:
                    box_a, box_b = ea["bbox"], eb["bbox"]
                    ca_x, ca_y = box_a[0] + box_a[2] / 2, box_a[1] + box_a[3] / 2
                    cb_x, cb_y = box_b[0] + box_b[2] / 2, box_b[1] + box_b[3] / 2
                    dx, dy = cb_x - ca_x, cb_y - ca_y
                    dist = math.hypot(dx, dy)
                    if dist < 1.0:
                        dx, dy, dist = 10.0, 0.0, 10.0
                    push = 25.0
                    shift_x = (dx / dist) * push
                    shift_y = (dy / dist) * push
                    eb["bbox"][0] = max(40.0, min(cw - eb["bbox"][2] - 40.0, eb["bbox"][0] + shift_x))
                    eb["bbox"][1] = max(60.0, min(ch - eb["bbox"][3] - 40.0, eb["bbox"][1] + shift_y))
                    if eb.get("label_pos"):
                        eb["label_pos"][0] += shift_x
                        eb["label_pos"][1] += shift_y
                    actions.append(f"Repelled overlapping entities {ea['id']} and {eb['id']}")

        # 5. Text overflowing its container or clipped by the viewport: shrink
        # the owning entity's label; shorten the text only when still needed.
        elif ("文字溢出容器" in msg or "文字被视窗裁切" in msg
              or "标题超出视窗卡片" in msg or "文本疑似乱码" in msg):
            target = None
            for text_lbl, ent in label_to_entity.items():
                if text_lbl and (text_lbl in msg or msg.find(text_lbl[:30]) >= 0):
                    target = (text_lbl, ent)
                    break
            if target:
                text_lbl, ent = target
                if len(text_lbl) > 14:
                    ent["label"] = text_lbl[:max(10, len(text_lbl) - 3)].rstrip()
                    label_to_entity.pop(text_lbl, None)
                    label_to_entity[ent["label"]] = ent
                    actions.append(f"Shortened overflowing label {text_lbl} → {ent['label']}")
                else:
                    ent["label_dy"] = float(ent.get("label_dy") or 0) + 18.0
                    actions.append(f"Shifted short overflowing label {text_lbl} downward")
            else:
                # Container overflow without a matching entity label: give the
                # biggest boxes a little less content pressure.
                for ent in scene.get("entities") or []:
                    if ent["bbox"][2] > cw * 0.45 or ent["bbox"][3] > ch * 0.45:
                        ent["bbox"][2] *= 0.95
                        ent["bbox"][3] *= 0.95
                        actions.append(f"Shrunk oversized entity {ent['id']}")

        # 6. Arrow endpoints detached: widen every box slightly so connectors
        # land inside an entity instead of floating in the margin.
        elif "箭头" in msg and ("悬空" in msg or "未连接" in msg or "终点" in msg):
            for ent in scene.get("entities") or []:
                x, y, w, h = ent["bbox"]
                grow = 8.0
                ent["bbox"] = [max(20.0, x - grow), max(40.0, y - grow),
                               w + 2 * grow, h + 2 * grow]
            actions.append("Expanded entity boxes to catch detached arrows")

    return scene, actions


def run_rework_loop(initial_scene: dict, assets: dict, font: str,
                     compose_func, max_rounds: int = MAX_REWORK_ROUNDS,
                     config: dict | None = None,
                     context: dict | None = None,
                     on_stage=None, assets_fn=None) -> tuple[bytes, dict, dict]:
    """Compose adapter for the shared local+model audit loop.

    assets_fn(scene, assets) may rebuild glyph assets when a repair patch
    changes an entity's icon prompt; otherwise the first-round assets are
    reused and prompt edits would have no visible effect.
    """
    import model_review
    state = {"scene": copy.deepcopy(initial_scene)}

    def build():
        nonlocal assets
        if assets_fn is not None:
            rebuilt = assets_fn(state["scene"], assets)
            if rebuilt is not None:
                assets = rebuilt
        return compose_func(state["scene"], assets, font)

    def local_review(svg):
        return review.findings(svg, state["scene"])

    def repair(scene, local_findings):
        repaired, actions = repair_scene_step(scene, local_findings)
        state["scene"] = repaired
        return repaired, actions

    def context_fn(scene, kind):
        return context or {
            "kind": "compose", "canvas": scene.get("canvas"),
            "entities": [e.get("label") for e in scene.get("entities") or []],
            "connectors": [c.get("label") for c in scene.get("connectors") or []],
        }

    svg, rework_report = model_review.run_loop(
        state["scene"], build, None, local_review, context_fn,
        config or {}, "compose", max_rounds=max_rounds, repair=repair,
        on_stage=on_stage)
    return svg, state["scene"], rework_report
