"""Component-based scientific figure pipeline.

Instead of asking the image model for one crowded figure and tracing it, this
pipeline:

  1. plans a scene: canvas, shared style, 3-8 isolated entities, connectors, labels
  2. generates each entity separately on a pure-white background
  3. cuts the white background away and crops to the object
  4. vectorizes each isolated asset with vtracer
  5. composes the assets + native arrows + native text into one SVG

That keeps every biological structure clean and lets the layout stay editable.
"""

from __future__ import annotations

import base64
import io
import math
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

import layout
import ocr
import vectorizer
from colorsafe import safe_color

SCENE_INSTRUCTION = """你是 Cell / Nature / Science 期刊科研图版的艺术指导。把用户的需求拆成可独立生成的素材和一份布局，只输出一个 JSON 对象，不要解释。

JSON 结构：
{
 "canvas": [1536, 1024],
 "title": "概括性英文图题（不超过 10 个词，不要用冒号罗列阶段名）",
 "subtitle": "可选的一行英文副标题（不要重复阶段名，不要用箭头）",
 "style": "共享视觉规范：扁平 2D 矢量、线宽、配色、描边、留白",
 "entities": [
   {"id": "archaeopteryx", "label": "Archaeopteryx", "bbox": [60, 140, 460, 560],
    "prompt": "one isolated side-view Archaeopteryx with spread wings, toothed beak, long bony tail, flat vector, no text, no labels, no arrows, pure white background, centered", "z": 1}
 ],
 "connectors": [
   {"from": "archaeopteryx", "to": "early_birds", "style": "solid", "arrow": true, "label": ""}
 ],
 "labels": [
   {"text": "Time", "x": 40, "y": 50, "size": 26}
 ]
}

硬性规则：
1. 3-8 个实体；每个实体是一个独立的生物结构、细胞、器官、器件或物体。
2. 若涉及系统闭环推导（如感知-推导-驱动-环境回路，闭环调控体系，生命周期环，自驱动实验室），设置 "layout": "closed_loop"，entities 按顺时针流转环节排列（可选一个核心 core 实体），connectors 形成首尾相连的闭环回路，回连箭头标明闭环反馈（如 "Closed-Loop Feedback"）。
3. entity.prompt 只描述一个物体，绝不写文字、标签、箭头、时间轴或背景；统一要求纯白背景、主体居中、占画面 70%、扁平 2D 矢量。
4. 所有文字放进 labels，所有关系放进 connectors；素材图里不生成任何文字。title 是图顶部的总标题，不属于 labels。
5. bbox 互不重叠，留 40px 边距，阅读顺序从左到右或顺时针闭环。
6. style 里写同一套配色和线宽，确保多次生成看起来像同一套图。
7. 不编造科学结论；只把用户给出的实体和关系拆开。
8. connectors 只连接空间上相邻的实体（同一行左右相邻，或上下相邻）。不要用一条长斜线跨越整张画布去连接两个相隔很远的实体；如果关系确实跨行，改为在 labels 里用短语说明，或让路径经过中间实体。
"""


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _esc(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def plan_scene(text: str, config: dict) -> dict:
    import pipeline
    messages = [
        {"role": "system", "content": SCENE_INSTRUCTION},
        {"role": "user", "content": text + "\n\n只输出符合上述结构的 JSON 对象本体："
         "第一个字符必须是 {，最后一个字符必须是 }；不要 Mermaid、SVG、HTML 或任何解释。"},
    ]
    scene = None
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            candidate = pipeline.chat_json(
                config, messages,
                temperature=0.25 if attempt == 0 else 0.1,
                max_tokens=6000,
                allow_fallback=False,
            )
        except Exception as exc:
            last_error = exc
            continue
        if (isinstance(candidate, dict) and isinstance(candidate.get("entities"), list)
                and candidate["entities"]):
            scene = candidate
            break
        last_error = RuntimeError("planner returned JSON without entities")
    if scene is None:
        raise RuntimeError(f"scene planning failed: {last_error}")
    scene = repair_scene(scene, config)
    subtitle_text = str(scene.get("subtitle") or "")
    if re.search(r"→|←|↔|->|=>", subtitle_text):
        scene["subtitle"] = ""
    if (3 <= len(scene["entities"]) <= 5
            and re.search(r"从左到右|从左至右|依次|序列|流程|阶段|"
                          r"left[- ]to[- ]right|linear (?:process|workflow|pipeline)|"
                          r"(?:three|four|five) stages?|step[- ]by[- ]step|pipeline",
                          text, re.I)):
        scene["layout"] = "row"
    elif re.search(r"闭环|回路|循环|推导图|调控体系|闭环系统|系统图|cycle|closed[-_ ]?loop|feedback", text, re.I):
        scene["layout"] = "closed_loop"
    # Layout is deterministic for generated figures; the audit loop must not
    # let a language model drag boxes into empty corners.
    scene["lock_layout"] = True
    return scene


def repair_scene(scene: dict, config: dict) -> dict:
    if config.get("canvas_user") and config.get("canvas"):
        canvas = config["canvas"]
    else:
        canvas = scene.get("canvas") or config.get("canvas") or [1536, 1024]
    cw, ch = _num(canvas[0], 1536), _num(canvas[1], 1024)
    entities = []
    seen = set()
    for index, item in enumerate(scene.get("entities") or []):
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or f"entity{index + 1}")
        if ident in seen:
            ident = f"{ident}{index}"
        seen.add(ident)
        box = item.get("bbox") or [80, 120, 300, 300]
        x, y, w, h = (_num(box[0], 80), _num(box[1], 120),
                      _num(box[2], 300), _num(box[3], 300))
        x = max(20.0, min(x, cw - 40))
        y = max(60.0, min(y, ch - 40))
        w = max(80.0, min(w, cw - x - 20))
        h = max(80.0, min(h, ch - y - 20))
        entities.append({
            "id": ident,
            "label": str(item.get("label") or ""),
            "bbox": [x, y, w, h],
            "prompt": str(item.get("prompt") or ""),
            "glyph": str(item.get("glyph") or ""),
            "label_dx": _num(item.get("label_dx"), 0),
            "label_dy": _num(item.get("label_dy"), 0),
            "z": int(_num(item.get("z"), index)),
        })
    scene = dict(scene)
    scene["canvas"] = [cw, ch]
    if config.get("viewport_shape"):
        scene["viewport_shape"] = config["viewport_shape"]
    style_dna = config.get("style_dna") or {}
    if isinstance(style_dna.get("palette"), dict):
        scene["palette"] = style_dna["palette"]
    defaults = {"primary": "#3F5A6B", "secondary": "#7A8B99",
                "accent": "#C04030", "text": "#102a33"}
    if isinstance(scene.get("palette"), dict):
        scene["palette"] = {key: safe_color(value, defaults.get(key, "#33475b"))
                            for key, value in scene["palette"].items()}
    scene["entities"] = entities
    scene["connectors"] = [c for c in (scene.get("connectors") or [])
                           if c.get("from") in seen and c.get("to") in seen]
    return scene


def arrange(scene: dict) -> dict:
    """Ignore model-chosen pixel boxes; place entities on a deterministic grid or loop."""
    entities = scene.get("entities") or []
    if not entities:
        return scene
    cw, ch = scene["canvas"]
    count = len(entities)
    # Only reserve header space when a title/subtitle will actually be drawn.
    title_h = 80.0 if (scene.get("title") or scene.get("subtitle")) else 28.0
    margin, gap = 60.0, 40.0
    label_h = 44.0

    # 1. Closed-loop layout: arrange entities along a smooth clockwise cycle
    if scene.get("layout") == "closed_loop" and 3 <= count <= 8:
        core_idx = None
        for i, ent in enumerate(entities):
            if ent.get("core") or re.search(r"core|brain|center|hub", ent["id"], re.I):
                core_idx = i
                break
        cx, cy = cw / 2, (ch + title_h) / 2
        bw, bh = 260.0, 200.0
        if core_idx is not None and count > 3:
            core_ent = entities[core_idx]
            core_ent["bbox"] = [cx - bw / 2, cy - bh / 2, bw, bh]
            core_ent["label_pos"] = [cx, cy + bh / 2 + 28]
            ring_ents = [e for i, e in enumerate(entities) if i != core_idx]
        else:
            ring_ents = entities
        n_ring = len(ring_ents)
        rx = min(cw * 0.36, (cw - 2 * margin - bw) / 2)
        ry = min(ch * 0.33, (ch - title_h - margin - bh) / 2)
        for i, ent in enumerate(ring_ents):
            angle = -math.pi / 2 + (2 * math.pi / n_ring) * i
            ex = cx + rx * math.cos(angle)
            ey = cy + ry * math.sin(angle)
            ent["bbox"] = [ex - bw / 2, ey - bh / 2, bw, bh]
            ent["label_pos"] = [ex, ey + bh / 2 + 28]
        scene["center"] = [cx, cy]
        # Auto-complete cycle connectors if missing
        existing = {(c.get("from"), c.get("to")) for c in (scene.get("connectors") or [])}
        conns = list(scene.get("connectors") or [])
        for i in range(n_ring):
            src_id = ring_ents[i]["id"]
            dst_id = ring_ents[(i + 1) % n_ring]["id"]
            if (src_id, dst_id) not in existing:
                lbl = "Feedback" if (i + 1) == n_ring else ""
                conns.append({"from": src_id, "to": dst_id, "style": "solid",
                              "arrow": True, "curved": True, "label": lbl})
        scene["connectors"] = conns
        return scene

    # 2. Row layout: linear process / timeline
    row_layout = scene.get("layout") == "row" and count <= 5
    if row_layout:
        cols = count
    else:
        if count == 3 and cw / max(ch, 1) > 1.15:
            cols = 3
        else:
            cols = 1 if count == 1 else 2 if count <= 4 else 3
    rows = math.ceil(count / cols)
    cell_w = (cw - 2 * margin - (cols - 1) * gap) / cols
    row_gap = 18.0
    available = ch - title_h - margin
    if row_layout:
        # Keep the user's canvas ratio; only shrink the cell to fit.
        cell_h = min(cell_w * 1.05, available - label_h)
        block_h = cell_h + label_h
    else:
        # Every row owns a caption band, so labels never spill into the next row.
        raw_h = (available - rows * label_h - (rows - 1) * row_gap) / rows
        cell_h = min(raw_h, cell_w * 1.15)
        block_h = rows * (cell_h + label_h) + (rows - 1) * row_gap
    y0 = title_h + max(0.0, (available - block_h) / 2)
    pitch = cell_h + label_h + row_gap
    for index, entity in enumerate(entities):
        row, col = divmod(index, cols)
        in_row = min(cols, count - row * cols)
        row_w = in_row * cell_w + (in_row - 1) * gap
        x = (cw - row_w) / 2 + col * (cell_w + gap)
        y = y0 + row * pitch
        entity["bbox"] = [x, y, cell_w, cell_h]
        entity["label_pos"] = [x + cell_w / 2, y + cell_h + 30]
    return scene


def _white_alpha(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    white = ((image[:, :, 0] >= 244) & (image[:, :, 1] >= 244)
             & (image[:, :, 2] >= 244)).astype(np.uint8)
    count, labels = cv2.connectedComponents(white, connectivity=8)
    border = set(labels[0, :].tolist()) | set(labels[-1, :].tolist())
    border |= set(labels[:, 0].tolist()) | set(labels[:, -1].tolist())
    alpha = np.full((height, width), 255, np.uint8)
    for label in border:
        if label == 0:
            continue
        alpha[labels == label] = 0
    return alpha


def cutout(png: bytes) -> bytes:
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("asset image decode failed")
    alpha = _white_alpha(image)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha > 0).astype(np.uint8), 8)
    if count > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        largest = int(areas.max()) if len(areas) else 0
        keep = [index + 1 for index, area in enumerate(areas)
                if area >= max(60, largest * 0.08)]
        mask = np.isin(labels, keep)
        alpha[~mask] = 0
    ys, xs = np.where(alpha > 0)
    if len(xs) == 0:
        raise RuntimeError("asset is empty after background removal")
    x1, x2 = int(xs.min()), int(xs.max()) + 1
    y1, y2 = int(ys.min()), int(ys.max()) + 1
    rgba = np.dstack([image[y1:y2, x1:x2], alpha[y1:y2, x1:x2]])
    ok, encoded = cv2.imencode(".png", rgba)
    if not ok:
        raise RuntimeError("asset crop encode failed")
    return encoded.tobytes()


def _spindle_vertical(png: bytes) -> bool:
    """Detect a vertical teal spindle axis in a division-stage asset.

    Text prompts alone do not reliably control orientation; rotating when the
    microtubule mass runs top-to-bottom makes metaphase/anaphase/telophase
    consistent with the left-to-right reading order.
    """
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        return False
    if image.shape[2] == 4:
        alpha = image[:, :, 3:4].astype(np.float32) / 255.0
        bgr = (image[:, :, :3] * alpha + 255.0 * (1 - alpha)).astype(np.uint8)
    else:
        bgr = image
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 0] >= 70) & (hsv[:, :, 0] <= 100)
            & (hsv[:, :, 1] >= 55) & (hsv[:, :, 2] >= 50))
    ys, xs = np.where(mask)
    if len(xs) < 300:
        return False
    values, vectors = np.linalg.eigh(np.cov(np.column_stack([xs, ys]).T))
    axis = vectors[:, int(np.argmax(values))]
    return abs(axis[1]) > abs(axis[0]) * 1.15


def _rotate_cw(png: bytes) -> bytes:
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        return png
    rotated = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    ok, encoded = cv2.imencode(".png", rotated)
    return encoded.tobytes() if ok else png


def asset_svg(png: bytes, config: dict) -> tuple[bytes, float, float, str]:
    import svg_convert
    svg, engine = svg_convert.convert(png, config)
    svg, width, height = normalize_asset(svg)
    return svg, width, height, engine


def _geometry_bbox(root):
    # svgelements applies nested transforms, which vtracer relies on; a raw
    # path bbox would report pre-transform coordinates and misplace assets.
    try:
        from svgelements import SVG
        import io as _io
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        parsed = SVG.parse(_io.StringIO(ET.tostring(root, encoding="unicode")))
        box = parsed.bbox()
        if box and all(v is not None for v in box):
            return float(box[0]), float(box[1]), float(box[2]), float(box[3])
    except Exception:
        pass
    from svgpathtools import parse_path
    xs, ys = [], []
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        try:
            if tag == "path" and node.get("d"):
                b = parse_path(node.get("d")).bbox()
                xs += [b[0], b[1]]; ys += [b[2], b[3]]
            elif tag == "rect":
                x, y = _num(node.get("x")), _num(node.get("y"))
                w, h = _num(node.get("width")), _num(node.get("height"))
                xs += [x, x + w]; ys += [y, y + h]
            elif tag in ("circle", "ellipse"):
                cx, cy = _num(node.get("cx")), _num(node.get("cy"))
                rx = _num(node.get("r")) if tag == "circle" else _num(node.get("rx"))
                ry = _num(node.get("r")) if tag == "circle" else _num(node.get("ry"))
                xs += [cx - rx, cx + rx]; ys += [cy - ry, cy + ry]
            elif tag in ("line", "polyline", "polygon"):
                vals = [_num(v) for v in re.findall(r"-?[\d.]+", node.get("points", ""))]
                if tag == "line":
                    vals = [_num(node.get("x1")), _num(node.get("y1")),
                            _num(node.get("x2")), _num(node.get("y2"))]
                xs += vals[0::2]; ys += vals[1::2]
        except Exception:
            continue
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def normalize_asset(svg: bytes) -> tuple[bytes, float, float]:
    """Set viewBox to the real geometry and shift content to 0,0."""
    root = ET.fromstring(svg)
    box = _geometry_bbox(root)
    if not box:
        parts = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox", "")) if v]
        w, h = (parts[2], parts[3]) if len(parts) == 4 else (512.0, 512.0)
        return svg, w, h
    minx, miny, maxx, maxy = box
    w, h = max(1.0, maxx - minx), max(1.0, maxy - miny)
    root.set("viewBox", f"0 0 {w:.2f} {h:.2f}")
    root.set("width", f"{w:.2f}")
    root.set("height", f"{h:.2f}")
    group = ET.Element("{http://www.w3.org/2000/svg}g",
                       {"transform": f"translate({-minx:.2f},{-miny:.2f})"})
    for child in list(root):
        tag = child.tag.split("}")[-1].lower()
        if tag == "defs":
            continue
        root.remove(child)
        group.append(child)
    root.append(group)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), w, h


def asset_image(cut_png: bytes) -> tuple[bytes, float, float]:
    """Wrap a cut-out PNG as an SVG <image> asset at its native resolution."""
    from base64 import b64encode
    from PIL import Image
    import io as _io
    image = Image.open(_io.BytesIO(cut_png))
    width, height = image.size
    payload = b64encode(cut_png).decode("ascii")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
           f'<image href="data:image/png;base64,{payload}" x="0" y="0" '
           f'width="{width}" height="{height}"/></svg>').encode("utf-8")
    return svg, float(width), float(height)


def _clean_asset(svg: bytes) -> str:
    """Return the asset's inner SVG markup, dropping near-white background paths."""
    try:
        ET.register_namespace("", "http://www.w3.org/2000/svg")
    except Exception:
        pass
    root = ET.fromstring(svg)
    pieces = []
    for child in root:
        tag = child.tag.split("}")[-1]
        if tag in ("defs", "metadata", "title", "desc", "style"):
            continue
        fill = (child.get("fill") or "").lower()
        if re.fullmatch(r"#[fF]{6}", fill):
            continue
        if tag == "path" and not child.get("d"):
            continue
        pieces.append(ET.tostring(child, encoding="unicode"))
    return "".join(pieces)


def _anchor(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    acx, acy = ax + aw / 2, ay + ah / 2
    bcx, bcy = bx + bw / 2, by + bh / 2
    dx, dy = bcx - acx, bcy - acy
    if dx == 0 and dy == 0:
        return acx, acy
    sx = (aw / 2) / abs(dx) if dx else math.inf
    sy = (ah / 2) / abs(dy) if dy else math.inf
    scale = min(sx, sy)
    return acx + dx * scale, acy + dy * scale


def _text_width(text: str, size: float) -> float:
    """Conservative width estimate; CJK glyphs are ~1em, Latin ~0.56em."""
    width = 0.0
    for ch in str(text):
        width += size * (1.0 if ord(ch) > 0x2E7F else 0.56)
    return width


def _label_box(text: str, x: float, y: float, size: float) -> list[float]:
    width = _text_width(text, size)
    return [x - width / 2, y - size * 0.92, width, size * 1.16]


def _overlap(a, b, pad: float = 0.0) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]) + pad
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]) + pad
    return max(0.0, w) * max(0.0, h)


def _point_in_box(x, y, box, pad=0.0):
    return (box[0] - pad <= x <= box[0] + box[2] + pad
            and box[1] - pad <= y <= box[1] + box[3] + pad)


def _path_clear(points, obstacles, pad=6.0) -> bool:
    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        steps = max(4, int(math.hypot(x2 - x1, y2 - y1) / 16))
        for step in range(steps + 1):
            t = step / steps
            x, y = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            if any(_point_in_box(x, y, box, pad) for box in obstacles):
                return False
    return True


def _polyline_length(points):
    return sum(math.hypot(points[i + 1][0] - points[i][0],
                          points[i + 1][1] - points[i][1])
               for i in range(len(points) - 1))


def _point_at(points, fraction):
    total = _polyline_length(points) or 1.0
    target = total * fraction
    walked = 0.0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        seg = math.hypot(x2 - x1, y2 - y1)
        if walked + seg >= target:
            t = (target - walked) / seg if seg else 0
            return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, (x2 - x1) / (seg or 1), (y2 - y1) / (seg or 1)
        walked += seg
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    seg = math.hypot(x2 - x1, y2 - y1) or 1
    return x2, y2, (x2 - x1) / seg, (y2 - y1) / seg


def _route(x1, y1, x2, y2, obstacles, cw, ch):
    """Choose a clear line, an orthogonal detour, or a quadratic arc."""
    straight = [(x1, y1), (x2, y2)]
    if not obstacles or _path_clear(straight, obstacles):
        return "line", straight
    xs = [box[0] for box in obstacles] + [box[0] + box[2] for box in obstacles]
    ys = [box[1] for box in obstacles] + [box[1] + box[3] for box in obstacles]
    top, bottom = min(ys) - 30, max(ys) + 30
    left, right = min(xs) - 30, max(xs) + 30
    candidates = []
    for ym in (top, bottom):
        if 18 <= ym <= ch - 18:
            candidates.append([(x1, y1), (x1, ym), (x2, ym), (x2, y2)])
    for xm in (left, right):
        if 18 <= xm <= cw - 18:
            candidates.append([(x1, y1), (xm, y1), (xm, y2), (x2, y2)])
    candidates.sort(key=_polyline_length)
    for points in candidates:
        if _path_clear(points, obstacles):
            return "polyline", points
    # Quadratic arc on either side of the straight line.
    dx, dy = x2 - x1, y2 - y1
    dist = math.hypot(dx, dy) or 1
    nx, ny = -dy / dist, dx / dist
    for bulge in (40, -40, 70, -70):
        qx, qy = (x1 + x2) / 2 + nx * bulge, (y1 + y2) / 2 + ny * bulge
        curve = []
        for step in range(17):
            t = step / 16
            curve.append(((1 - t) ** 2 * x1 + 2 * (1 - t) * t * qx + t ** 2 * x2,
                          (1 - t) ** 2 * y1 + 2 * (1 - t) * t * qy + t ** 2 * y2))
        if _path_clear(curve, obstacles):
            return "curve", [(x1, y1), (qx, qy), (x2, y2)]
    return "line", straight


def _connector(c, boxes, center=None, obstacles=None, placed=None, canvas=None, label_obstacles=None):
    src, dst = boxes.get(c.get("from")), boxes.get(c.get("to"))
    if not src or not dst:
        return "", None
    obstacles = obstacles or []
    label_obstacles = label_obstacles if label_obstacles is not None else obstacles
    placed = placed if placed is not None else []
    cw, ch = canvas or (1280, 900)
    x1, y1 = _anchor(src, dst)
    x2, y2 = _anchor(dst, src)
    # Vertical edges would otherwise run straight through the caption band.
    # Leave from / arrive at a side edge when the caption sits in the way.
    if y2 > y1 + 24:
        x1 = src[0] + src[2] if x2 >= x1 else src[0]
        y1 = src[1] + src[3] * 0.62
    elif y2 < y1 - 24:
        x2 = dst[0] + dst[2] if x1 >= x2 else dst[0]
        y2 = dst[1] + dst[3] * 0.38
    color = safe_color(c.get("color"), "#33475b")
    width = _num(c.get("width"), 3)
    dash = ' stroke-dasharray="8 6"' if c.get("style") == "dashed" else ""
    marker = ' marker-end="url(#arrow)"' if c.get("arrow", True) else ""
    kind, points = _route(x1, y1, x2, y2, obstacles, cw, ch)
    if kind == "curve" and center is not None:
        # Closed loops bow away from the hub for a readable cycle.
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        vx, vy = mx - center[0], my - center[1]
        length = math.hypot(vx, vy)
        if length > 1:
            qx, qy = mx + vx / length * 55, my + vy / length * 55
            curve = []
            for step in range(17):
                t = step / 16
                curve.append(((1 - t) ** 2 * x1 + 2 * (1 - t) * t * qx + t ** 2 * x2,
                              (1 - t) ** 2 * y1 + 2 * (1 - t) * t * qy + t ** 2 * y2))
            if _path_clear(curve, obstacles):
                points = [(x1, y1), (qx, qy), (x2, y2)]
                kind = "curve"
    if kind == "curve":
        path = (f'<path d="M {x1:.1f} {y1:.1f} Q {points[1][0]:.1f} {points[1][1]:.1f} '
                f'{x2:.1f} {y2:.1f}" fill="none" stroke="{color}" stroke-width="{width}"'
                f'{dash}{marker}/>')
        route_points = points
    elif kind == "polyline":
        # The first pair follows M; every later pair is a line segment.
        coords = [f'{px:.1f} {py:.1f}' for px, py in points]
        path = (f'<path d="M {coords[0]} ' + " ".join("L " + c for c in coords[1:])
                + f'" fill="none" stroke="{color}" stroke-width="{width}" '
                  f'stroke-linejoin="round"{dash}{marker}/>')
        route_points = points
    else:
        path = (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{color}" stroke-width="{width}"{dash}{marker}/>')
        route_points = points
    label = None
    text = str(c.get("label") or "").strip()
    if text:
        best = None
        # Keep the caption near the source entity. A label parked at the
        # geometric midpoint of a long diagonal reads as belonging to whatever
        # happens to sit beside the midpoint.
        for fraction in (0.10, 0.16, 0.24, 0.34, 0.46, 0.60):
            px, py, ux, uy = _point_at(route_points, fraction)
            nx, ny = -uy, ux
            for offset in (-14, 14, -24, 24, -36, 36, -50, 50, -64, 64):
                lx, ly = px + nx * offset, py + ny * offset + 5
                box = _label_box(text, lx, ly, 17)
                collision = 0.0
                for obstacle in label_obstacles:
                    collision += _overlap(box, obstacle, 8)
                for other in placed:
                    collision += _overlap(box, other, 8)
                score = collision * 4
                if box[0] < 6 or box[1] < 6 or box[0] + box[2] > cw - 6 or box[1] + box[3] > ch - 6:
                    score += 10000
                candidate = (collision > 0.5, collision, score, lx, ly, box)
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
        if best is not None:
            label = {"text": text, "x": best[3], "y": best[4],
                     "box": best[5], "color": color, "size": 17}
    return path, label


def _place_entity_label(entity, content, obstacles, placed, cw, ch):
    text = str(entity.get("label") or "").strip()
    if not text:
        return None
    size = 22
    x, y, w, h = content
    candidates = [
        (x + w / 2, y + h + 30),
        (x + w / 2, y - 14),
        (x + w + 12 + _text_width(text, size) / 2, y + h / 2 + size * 0.3),
        (x - 12 - _text_width(text, size) / 2, y + h / 2 + size * 0.3),
    ]
    best = None
    for lx, ly in candidates:
        box = _label_box(text, lx, ly, size)
        collision = 0.0
        for obstacle in obstacles:
            collision += _overlap(box, obstacle, 8)
        for other in placed:
            collision += _overlap(box, other, 8)
        score = collision * 4
        if box[0] < 8 or box[1] < 6 or box[0] + box[2] > cw - 8 or box[1] + box[3] > ch - 6:
            score += 10000
        if entity.get("label_dy"):
            score += abs(ly - (y + h + 30 + _num(entity.get("label_dy"), 0))) * 0.2
        candidate = (collision > 0.5, collision, score, lx, ly, box)
        if best is None or candidate[:3] < best[:3]:
            best = candidate
    return {"text": text, "x": best[3], "y": best[4], "box": best[5],
            "color": None, "size": size}


def compose_svg(scene: dict, assets: dict, font: str) -> bytes:
    cw, ch = scene["canvas"]
    palette = scene.get("palette") or {}
    label_color = safe_color(palette.get("text"), "#102a33")
    card_stroke = safe_color(palette.get("primary"), "#3F5A6B")
    v_shape = (scene.get("viewport_shape") or "rect").lower()

    defs = ['<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M0 0 L10 5 L0 10 z" fill="#33475b"/></marker>']

    vector_cards = bool(scene.get("vector_glyphs"))
    fit = {}
    for entity in scene["entities"]:
        asset = assets.get(entity["id"])
        if not asset:
            continue
        _, aw, ah = asset
        _, _, w, h = entity["bbox"]
        # Vector glyphs get a visible card frame, so they need breathing room.
        fit[entity["id"]] = min(w / aw, h / ah) * (0.72 if vector_cards else 0.94)
    row_scale = min(fit.values()) if (scene.get("layout") == "row" and fit) else None

    # Anchor arrows to the visible glyph, not the (often invisible) layout
    # cell: a full-cell anchor leaves short arrows floating in the gaps.
    boxes = {}
    for entity in scene["entities"]:
        asset = assets.get(entity["id"])
        x, y, w, h = entity["bbox"]
        if not asset or vector_cards:
            boxes[entity["id"]] = (x, y, w, h)
            continue
        _, aw, ah = asset
        scale = row_scale or fit[entity["id"]]
        boxes[entity["id"]] = (x + (w - aw * scale) / 2,
                               y + (h - ah * scale) / 2, aw * scale, ah * scale)

    content = []
    # Journal artwork carries no title inside the image; the caption belongs
    # in the manuscript. Keep metadata on the scene for filenames/UI only.
    title = ""
    subtitle = ""
    content_boxes = {}
    for entity in scene["entities"]:
        asset = assets.get(entity["id"])
        if not asset:
            continue
        _, aw, ah = asset
        x, y, w, h = entity["bbox"]
        if vector_cards:
            content_boxes[entity["id"]] = [x, y, w, h]
        else:
            scale = row_scale or min(w / aw, h / ah) * 0.94
            content_boxes[entity["id"]] = [x + (w - aw * scale) / 2,
                                           y + (h - ah * scale) / 2, aw * scale, ah * scale]
        entity["content_bbox"] = list(content_boxes[entity["id"]])

    title_obstacle = [0, 0, cw, 88] if (title or subtitle) else [0, 0, 0, 0]
    label_obstacles = list(content_boxes.values()) + ([title_obstacle] if title else [])
    entity_labels = []
    for entity in scene["entities"]:
        content_box = content_boxes.get(entity["id"])
        if not content_box:
            continue
        label = _place_entity_label(entity, content_box, label_obstacles,
                                    [item["box"] for item in entity_labels], cw, ch)
        if label:
            label["id"] = entity["id"]
            entity_labels.append(label)
    entity_label_boxes = {label["id"]: label["box"] for label in entity_labels}

    center_pt = scene.get("center")
    connector_lines = []
    connector_labels = []
    for connector in scene.get("connectors") or []:
        if not connector.get("label") and not connector.get("arrow"):
            continue
        endpoints = (connector.get("from"), connector.get("to"))
        obstacles = [box for key, box in content_boxes.items() if key not in endpoints]
        obstacles += [box for key, box in entity_label_boxes.items() if key not in endpoints]
        path, label = _connector(connector, boxes, center=center_pt,
                                 obstacles=obstacles,
                                 label_obstacles=list(content_boxes.values()) + [
                                     item["box"] for item in entity_labels],
                                 placed=[item["box"] for item in connector_labels],
                                 canvas=(cw, ch))
        if path:
            connector_lines.append(path)
        if label:
            connector_labels.append(label)
    content.extend(connector_lines)

    for entity in sorted(scene["entities"], key=lambda e: e.get("z", 0)):
        asset = assets.get(entity["id"])
        if not asset:
            continue
        svg, aw, ah = asset
        x, y, w, h = entity["bbox"]
        scale = row_scale or min(w / aw, h / ah) * (0.72 if vector_cards else 0.94)
        tx = x + (w - aw * scale) / 2
        ty = y + (h - ah * scale) / 2
        inner = _clean_asset(svg)
        clip_id = f"clip-{entity['id']}"
        defs.append(f'<clipPath id="{clip_id}"><rect x="{x - 0.5:.1f}" y="{y - 0.5:.1f}" '
                    f'width="{w + 1:.1f}" height="{h + 1:.1f}"/></clipPath>')
        if vector_cards:
            content.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                           f'rx="{min(20.0, h * 0.06):.1f}" fill="#FCFDFD" '
                           f'stroke="{_esc(card_stroke)}" stroke-opacity="0.36" stroke-width="1.4"/>')
        content.append(f'<g clip-path="url(#{clip_id})">'
                       f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.5f})">{inner}</g></g>')
        if not vector_cards:
            content.append(f'<rect x="{tx:.2f}" y="{ty:.2f}" width="{aw * scale:.2f}" '
                           f'height="{ah * scale:.2f}" fill="none" stroke="#ffffff" stroke-width="4"/>')

    for label in entity_labels:
        box = label["box"]
        content.append(f'<text x="{label["x"]:.1f}" y="{label["y"]:.1f}" '
                       f'text-anchor="middle" font-family="{_esc(font)}" font-size="{label["size"]}" '
                       f'data-bbox="{box[0]:.1f},{box[1]:.1f},{box[2]:.1f},{box[3]:.1f}" '
                       f'fill="{_esc(label_color)}" '
                       f'style="paint-order:stroke;stroke:#ffffff;stroke-width:6;stroke-linejoin:round">'
                       f'{_esc(label["text"])}</text>')
    for label in connector_labels:
        box = label["box"]
        content.append(f'<text x="{label["x"]:.1f}" y="{label["y"]:.1f}" '
                       f'text-anchor="middle" font-family="{_esc(font)}" font-size="{label["size"]}" '
                       f'data-bbox="{box[0]:.1f},{box[1]:.1f},{box[2]:.1f},{box[3]:.1f}" '
                       f'fill="{_esc(label["color"] or label_color)}" '
                       f'style="paint-order:stroke;stroke:#ffffff;stroke-width:5;stroke-linejoin:round">'
                       f'{_esc(label["text"])}</text>')

    bg = [f'<rect x="0" y="0" width="{cw:.0f}" height="{ch:.0f}" fill="#ffffff"/>']
    if v_shape in ("card", "circle", "ellipse"):
        if v_shape == "card":
            clip = (f'<rect x="14" y="14" width="{cw-28:.1f}" height="{ch-28:.1f}" rx="24"/>')
            bg.append(f'<rect x="14" y="14" width="{cw-28:.1f}" height="{ch-28:.1f}" rx="24" '
                      f'fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1.6"/>')
        elif v_shape == "circle":
            r = min(cw, ch) / 2 - 14
            clip = f'<circle cx="{cw/2:.1f}" cy="{ch/2:.1f}" r="{r:.1f}"/>'
        else:
            rx, ry = cw / 2 - 14, ch / 2 - 14
            clip = f'<ellipse cx="{cw/2:.1f}" cy="{ch/2:.1f}" rx="{rx:.1f}" ry="{ry:.1f}"/>'
        defs.append(f'<clipPath id="viewport-clip">{clip}</clipPath>')
        body_content = "".join(content)
        if v_shape in ("circle", "ellipse"):
            if v_shape == "circle":
                side = (min(cw, ch) - 28) / 1.41421356
                k = min(side / cw, side / ch)
            else:
                k = min((cw - 28) / (cw * 1.41421356),
                        (ch - 28) / (ch * 1.41421356))
            body_content = (f'<g transform="translate({cw*(1-k)/2:.2f},{ch*(1-k)/2:.2f}) '
                            f'scale({k:.4f})">{body_content}</g>')
            # Keep the review's entity boxes in the same coordinate system as
            # the scaled labels, otherwise label/entity checks false-positive.
            ox, oy = cw * (1 - k) / 2, ch * (1 - k) / 2
            for ent in scene.get("entities") or []:
                box = ent.get("content_bbox")
                if box:
                    ent["content_bbox"] = [box[0] * k + ox, box[1] * k + oy,
                                           box[2] * k, box[3] * k]
        inner = f'<g clip-path="url(#viewport-clip)">' + body_content + '</g>'
        # Restore a crisp viewport edge above the clipped content.
        if v_shape == "card":
            bg.append(f'<rect x="14" y="14" width="{cw-28:.1f}" height="{ch-28:.1f}" rx="24" '
                      f'fill="none" stroke="#CBD5E1" stroke-width="1.6"/>')
        elif v_shape == "circle":
            bg.append(f'<circle cx="{cw/2:.1f}" cy="{ch/2:.1f}" r="{r:.1f}" fill="none" '
                      f'stroke="#CBD5E1" stroke-width="1.6"/>')
        else:
            bg.append(f'<ellipse cx="{cw/2:.1f}" cy="{ch/2:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
                      f'fill="none" stroke="#CBD5E1" stroke-width="1.6"/>')
    else:
        inner = "".join(content)

    nl = chr(10)
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw:.0f}" height="{ch:.0f}" '
             f'viewBox="0 0 {cw:.0f} {ch:.0f}">',
             f'  <defs>{"".join(defs)}</defs>']
    parts += ["  " + line for line in bg]
    parts.append("  " + inner)
    parts.append("</svg>")
    svg = (nl.join(parts) + nl).replace("__FONT__", _esc(font))
    return svg.encode("utf-8")


def compose_render(text: str, config: dict, on_stage=None) -> tuple[bytes, dict]:
    import pipeline

    # Explicit archetype choice from the AI guide always wins.
    style_dna = config.get("style_dna") or {}
    requested = str(config.get("archetype") or style_dna.get("archetype") or "").strip().lower()

    # Concentric ring architecture summary (mechanical / engineering systems).
    if requested == "ring_architecture" or re.search(
            r"圆环|环形架构|环形图|同心圆|环状|radial|ring[-_ ]?architecture", text, re.I):
        try:
            import ring_render
            return ring_render.render_ring(text, config, on_stage=on_stage)
        except Exception as exc:
            svg, report = pipeline.plan_to_svg(text, config, on_stage=on_stage)
            report["ring_error"] = f"{type(exc).__name__}: {exc}"[:400]
            report["fallback"] = "plan_after_ring_failure"
            return svg, report

    if requested in ("signal_pathway", "process_pipeline", "structural_anatomy", "graphical_abstract"):
        try:
            import archetypes_render
            return archetypes_render.render_archetype(text, config, requested, on_stage=on_stage)
        except Exception as exc:
            # Do not silently re-run the whole image pipeline (it doubles the
            # wait); fall back to the fast text-only layout and say why.
            svg, report = pipeline.plan_to_svg(text, config, on_stage=on_stage)
            report["archetype_error"] = f"{type(exc).__name__}: {exc}"[:400]
            report["fallback"] = "plan_after_archetype_failure"
            return svg, report

    # When the user asks for a closed-loop system derivation, framework, or regulation architecture,
    # route to the dedicated publication-grade multi-tier framework engine.
    framework_error = None
    if requested == "closed_loop" or re.search(r"闭环|回路|系统图|架构图|推导图|调控体系|闭环系统|framework|closed[-_ ]?loop|perception-action|system.*architecture", text, re.I):
        try:
            import framework
            return framework.render_framework(text, config, on_stage=on_stage)
        except Exception as exc:
            framework_error = f"{type(exc).__name__}: {exc}"[:400]

    def stage(name, detail=None):
        if on_stage:
            on_stage(name, detail)

    # Vector mode still goes through the entity planner + assembly loop: each
    # entity gets a drawn glyph (not a blank card), and the result is audited
    # by the same per-round geometry + vision review as image mode.
    report = {"compose": True, "stages": {}}
    if framework_error:
        report["framework_error"] = framework_error
    stage("plan_scene", "model splitting the figure")
    scene = arrange(plan_scene(text, config))
    report["scene"] = {"entities": len(scene["entities"]),
                       "connectors": len(scene.get("connectors") or []),
                       "canvas": scene["canvas"]}
    report["scene_data"] = {
        "canvas": scene["canvas"],
        "entities": scene["entities"],
        "connectors": scene.get("connectors") or [],
        "labels": scene.get("labels") or [],
        "layout": scene.get("layout"),
        "lock_layout": True,
        "title": scene.get("title"),
        "subtitle": scene.get("subtitle"),
        "vector_glyphs": bool(scene.get("vector_glyphs")),
    }
    style = str(scene.get("style") or "")
    palette = scene.get("palette") or {"primary": "#3F5A6B", "secondary": "#7A8B99",
                                       "accent": "#C04030"}
    assets = {}
    engine_counts = {}
    total = len(scene["entities"])
    vector_mode = str(config.get("illustration_mode") or "") == "vector"
    scene["vector_glyphs"] = vector_mode
    for index, entity in enumerate(scene["entities"], 1):
        stage("generate", f"实体 {index}/{total}：{entity.get('label') or entity['id']}")
        if vector_mode:
            import framework
            glyph = framework.entity_glyph(
                entity, 50, 50, 78, palette.get("primary", "#3F5A6B"))
            glyph_svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                         + glyph + '</svg>').encode("utf-8")
            assets[entity["id"]] = (glyph_svg, 100.0, 100.0)
            engine_counts["vector-glyph"] = engine_counts.get("vector-glyph", 0) + 1
            continue
        prompt = entity["prompt"]
        if style:
            prompt = (prompt + chr(10) + chr(10) + "Shared visual style: " + style +
                      chr(10) + "Isolated single object, pure white background, no text, "
                      "no labels, no arrows, no frame, centered, publication-quality "
                      "scientific illustration; follow the requested visual style.")
        png = pipeline.generate_raw(prompt, config)
        cut = cutout(png)
        if re.search(r"mitos|anaphase|telophase|spindle|chromatid", prompt, re.I)                 and _spindle_vertical(cut):
            cut = _rotate_cw(cut)
        svg, aw, ah = asset_image(cut)
        assets[entity["id"]] = (svg, aw, ah)
        engine_counts["image"] = engine_counts.get("image", 0) + 1
    report["stages"]["generate"] = {"entities": len(assets), "engines": engine_counts}
    stage("assemble", "placing assets and connectors")
    font = str(config.get("font") or "Times New Roman")
    
    # Run pixel-level rework loop (up to 10 rounds) to auto-heal text/entity collisions
    import rework

    def refresh_assets(current_scene, current_assets):
        """Vector glyphs are derived from label/prompt, so a spec patch that
        rewrites an icon prompt must rebuild its glyph in the next round."""
        if not vector_mode:
            return current_assets
        import framework
        palette_now = current_scene.get("palette") or {}
        color = palette_now.get("primary", "#3F5A6B")
        rebuilt = {}
        for entity in current_scene.get("entities") or []:
            glyph = framework.entity_glyph(entity, 50, 50, 78, color)
            rebuilt[entity["id"]] = (
                ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                 + glyph + '</svg>').encode("utf-8"), 100.0, 100.0)
        return rebuilt

    svg, scene, rework_report = rework.run_rework_loop(
        scene, assets, font, compose_svg, max_rounds=10, config=config,
        context={"kind": "compose", "canvas": scene.get("canvas"),
                 "entities": [e.get("label") for e in scene.get("entities") or []],
                 "connectors": [c.get("label") for c in scene.get("connectors") or []]},
        on_stage=stage, assets_fn=refresh_assets if vector_mode else None)
    report["rework"] = rework_report
    # The audit loop may have moved boxes to heal overlaps; publish the scene
    # that was actually rendered, not the pre-rework layout.
    report["scene_data"] = {
        "canvas": scene["canvas"],
        "entities": scene.get("entities") or [],
        "connectors": scene.get("connectors") or [],
        "labels": scene.get("labels") or [],
        "layout": scene.get("layout"),
        "lock_layout": scene.get("lock_layout", True),
        "title": scene.get("title"),
        "subtitle": scene.get("subtitle"),
        "vector_glyphs": bool(scene.get("vector_glyphs")),
    }
    # Compose assets are embedded <image> rasters in image mode; allow them
    # here or _check_svg fails the whole render and silently re-runs the full
    # image pipeline (double cost, different layout).
    pipeline._check_svg(svg, allow_image=bool(assets))
    report["stages"]["assemble"] = {"bytes": len(svg), "rework_rounds": rework_report.get("rounds_executed")}
    report["bytes"] = len(svg)
    return svg, report
