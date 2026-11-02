"""Raster scientific figures to editable vector scenes without embedded bitmaps.

The tracer keeps the original painter order. Consecutive paths are grouped only
to keep the editor responsive; no path is reordered or rasterized again.
"""
from __future__ import annotations

import html
import io
import re
from pathlib import Path

from scene_document import SceneError, empty_scene, normalize_scene


def _configured_reader(config: dict) -> bool:
    section = config.get("vision") or {}
    if not section.get("model") or not section.get("base_url"):
        section = config.get("text") or {}
    return bool(section.get("model") and section.get("base_url"))


def _text_color(image, box) -> str:
    import numpy as np
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    crop = np.asarray(image.crop((max(0, x1), max(0, y1), min(image.width, x2), min(image.height, y2))).convert("RGB"))
    if crop.size == 0:
        return "#253844"
    pixels = crop.reshape(-1, 3).astype(float)
    luminance = pixels.mean(axis=1)
    dark = float(np.median(luminance)) < 128
    threshold = np.percentile(luminance, 75 if dark else 25)
    chosen = pixels[luminance >= threshold] if dark else pixels[luminance <= threshold]
    rgb = np.median(chosen if len(chosen) else pixels, axis=0).astype(int)
    return "#" + "".join(f"{max(0, min(255, int(v))):02X}" for v in rgb)


def _font_weight(image, box, font_size: float) -> int:
    """Estimate boldness from foreground coverage, not from label semantics."""
    import numpy as np
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    crop = np.asarray(image.crop((max(0,x1),max(0,y1),min(image.width,x2),min(image.height,y2))).convert("RGB")).astype(float)
    if crop.size == 0 or min(crop.shape[:2]) < 2:
        return 400
    border = np.concatenate([crop[0],crop[-1],crop[:,0],crop[:,-1]],axis=0)
    background = np.median(border,axis=0)
    density = float((np.linalg.norm(crop-background,axis=2)>65).mean())
    return 700 if density >= .39 or (font_size >= 13.8 and density >= .28) or (font_size >= 11.5 and density >= .34) else 400


def local_text_observation(png: bytes) -> tuple[dict, list[str]]:
    """Local OCR fallback. No image or credentials leave the machine."""
    import cv2
    import numpy as np
    from PIL import Image
    from text_ocr import _get_engine
    engine = _get_engine()
    if engine is None:
        return {"objects": []}, ["本机 OCR 不可用；插画已转为路径，文字需要手动添加。"]
    image = Image.open(io.BytesIO(png)).convert("RGB")
    array = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    result, _ = engine(array)
    objects, low_confidence = [], 0
    for index, row in enumerate(result or []):
        try:
            points, label, confidence = row[:3]
            label = str(label).strip()
            confidence = float(confidence)
            if not label:
                continue
            if confidence < .55:
                low_confidence += 1
                continue
            xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
            x1, x2, y1, y2 = max(0, min(xs)), min(image.width, max(xs)), max(0, min(ys)), min(image.height, max(ys))
            if x2-x1 < 2 or y2-y1 < 2:
                continue
            objects.append({"id": f"ocr_text_{index}", "kind": "text", "label": label,
                            "x": x1/image.width, "y": y1/image.height,
                            "w": (x2-x1)/image.width, "h": (y2-y1)/image.height,
                            "fill": _text_color(image, (x1, y1, x2, y2))})
        except (TypeError, ValueError, IndexError):
            continue
    warnings = [f"本机 OCR 跳过了 {low_confidence} 个低置信度文字区域，请对照原图补充。"] if low_confidence else []
    return {"objects": objects}, warnings


def _observation(png: bytes, config: dict) -> tuple[dict, str, list[str]]:
    # OCR geometry is more faithful to the original pixels than a model's
    # approximate box. Use it first; the vision model remains a fallback for
    # installations or figures where local OCR finds no usable text.
    local, local_warnings = local_text_observation(png)
    if local.get("objects"):
        return local, "local_ocr", local_warnings
    if _configured_reader(config):
        try:
            from figure_imports import observe
            value = observe(png, config)
            if isinstance(value, dict) and any(o.get("kind") == "text" for o in value.get("objects", [])):
                return value, "vision", []
        except Exception:
            # A model failure is reported truthfully; local OCR still provides a useful candidate.
            pass
        return {"objects": []}, "unavailable", ["文字识别未完成；插画已转为路径，请手动添加文字。"] + local_warnings
    return local, "local_ocr", local_warnings


def _path_groups(svg: bytes, text_items: list[dict], image_size: tuple[int, int], chunk_size: int = 24):
    from svgelements import SVG, Shape, Path as SvgPath
    root_text = re.sub(r"<\?xml[^>]*\?>", "", svg.decode("utf-8")).strip()
    root_text = re.sub(r"\s+version=\"[^\"]*\"", "", root_text)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(root_text)
    if not root.get("viewBox"):
        root.set("viewBox", f"0 0 {root.get('width')} {root.get('height')}")
    parsed = SVG.parse(io.StringIO(ET.tostring(root, encoding="unicode")))
    width, height = image_size
    boxes = [(o["x"]*width-4, o["y"]*height-4, (o["x"]+o["w"])*width+4, (o["y"]+o["h"])*height+4)
             for o in text_items]
    paths, removed = [], 0
    for element in parsed.elements():
        if not isinstance(element, Shape):
            continue
        bounds = element.bbox()
        if not bounds:
            continue
        x1, y1, x2, y2 = bounds
        if x2-x1 <= 0 or y2-y1 <= 0:
            continue
        # Only remove paths wholly contained in a text box. Large background or
        # border paths are never deleted merely because they touch text.
        def text_outline(box):
            a, b, c, d = box
            if x1 >= a and y1 >= b and x2 <= c and y2 <= d:
                return True
            center_inside = a <= (x1+x2)/2 <= c and b <= (y1+y2)/2 <= d
            comparable_size = (x2-x1) <= (c-a)*1.6 and (y2-y1) <= (d-b)*1.8
            return center_inside and comparable_size and (x2-x1)*(y2-y1) <= (c-a)*(d-b)*1.8
        if any(text_outline(box) for box in boxes):
            removed += 1
            continue
        values = element.values
        fill = str(element.fill)
        stroke = str(element.stroke)
        attrs = " ".join(f'{k}="{html.escape(str(values[k]), quote=True)}"' for k in
                         ("stroke-linecap", "stroke-linejoin", "fill-rule", "opacity", "fill-opacity", "stroke-opacity")
                         if k in values)
        # svgelements expands transforms into binary floating point decimals;
        # subpixel rounding avoids huge snapshots without changing visible geometry.
        data = re.sub(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?',
            lambda m:format(float(m[0]),'.3f').rstrip('0').rstrip('.'), SvgPath(element).d())
        paths.append({"bbox": bounds, "index": len(paths), "markup":
            f'<path d="{html.escape(data, quote=True)}" fill="{fill if fill != "None" else "none"}" '
            f'stroke="{stroke if stroke != "None" else "none"}" stroke-width="{element.stroke_width}" {attrs}/>'})
    if not paths:
        raise SceneError("矢量化没有生成有效路径，请提高原图分辨率后重试")
    chunk_size=max(chunk_size, (len(paths)+349)//350)
    groups = []
    chunks, current, current_bytes = [], [], 0
    for path in paths:
        size = len(path["markup"].encode("utf-8"))
        if size > 240*1024:
            raise SceneError("单个矢量路径过于复杂，请裁切为单个图版或提高原图清晰度后重试")
        if current and (len(current) >= chunk_size or current_bytes+size > 180*1024):
            chunks.append(current); current, current_bytes = [], 0
        current.append(path); current_bytes += size
    if current:
        chunks.append(current)
    for items in chunks:
        x1 = min(p["bbox"][0] for p in items); y1 = min(p["bbox"][1] for p in items)
        x2 = max(p["bbox"][2] for p in items); y2 = max(p["bbox"][3] for p in items)
        markup = f'<svg viewBox="{x1} {y1} {x2-x1} {y2-y1}">' + "".join(p["markup"] for p in items) + "</svg>"
        groups.append({"bbox": (x1, y1, x2, y2), "markup": markup, "paths": len(items),
                       "first": items[0]["index"], "last": items[-1]["index"]})
    return groups, {"vector_paths": len(paths), "removed_text_paths": removed,
                    "source_paths": len(paths)+removed, "vector_groups": len(groups)}


def remove_text_ink(png: bytes, items: list[dict], *, include_masks=False) -> tuple[bytes, dict]:
    """Inpaint text ink only, preserving colored artwork inside OCR bounds."""
    import cv2
    import numpy as np
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    mask = np.zeros(image.shape[:2], np.uint8)
    height, width = mask.shape
    regions=[]
    for item in items:
        x = max(0, int(item['x']*width)-1); y = max(0, int(item['y']*height)-1)
        right = min(width, int((item['x']+item['w'])*width)+2)
        bottom = min(height, int((item['y']+item['h'])*height)+2)
        crop = image[y:bottom, x:right].astype(float)
        if not crop.size:
            continue
        light = crop.mean(axis=2)
        background = float(np.percentile(light, 75))
        chroma = crop.max(axis=2)-crop.min(axis=2)
        # Colored labels are identified by distance from their observed ink.
        color = item.get('fill', '#000000').lstrip('#')
        ink = np.array([int(color[i:i+2], 16) for i in (4,2,0)])
        if max(ink)-min(ink) > 55:
            pixels = np.linalg.norm(crop-ink, axis=2) < 85
        elif background > 128:
            pixels = (light < background-28) & (chroma < 65)
        else:
            pixels = (light > background+30) & (chroma < 65)
        local = cv2.dilate(pixels.astype(np.uint8)*255, np.ones((3,3),np.uint8))
        mask[y:bottom,x:right] = np.maximum(mask[y:bottom,x:right], local)
        if include_masks:regions.append((x,y,right,bottom,local))
    cleaned = cv2.inpaint(image, mask, 3, cv2.INPAINT_TELEA) if mask.any() else image
    ok, data = cv2.imencode('.png', cleaned)
    if not ok:
        raise SceneError('无法处理原图文字区域，原文件已保留')
    return data.tobytes(), {'removed': len(items), **({'masks':regions} if include_masks else {})}


def reconstruct(png: bytes, name: str, config: dict, *, checkpoint=None) -> tuple[dict, dict]:
    from PIL import Image
    from figure_imports import _dimensions, _number, _snapshot
    from vectorizer import vectorize_vtracer
    tick = checkpoint or (lambda message: None)
    tick('正在识别原图文字与位置')
    observation, ocr_source, warnings = _observation(png, config)
    image = Image.open(io.BytesIO(png)).convert("RGB")
    width_mm, height_mm = _dimensions(*image.size)
    scene = empty_scene(Path(name).stem, width_mm=width_mm, height_mm=height_mm)
    scene["layout"] = "network"; scene["style"]["show_title"] = False
    text_items = []
    for item in observation.get("objects", []):
        if item.get("kind") != "text":
            continue
        ident = str(item.get("id") or f"text_{len(text_items)}")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,70}", ident):
            ident = f"text_{len(text_items)}"
        x, y, w, h = [_number(item.get(k), 0, 1) for k in ("x", "y", "w", "h")]
        if x+w > 1.001 or y+h > 1.001 or min(w, h) <= 0:
            continue
        label = str(item.get("label") or "").strip()[:240]
        if not label:
            continue
        font_size = max(7, min(48, _number(item.get("font_size_pt") or h*height_mm*72/25.4*.8, .1, 500)))
        pixel_box = (x*image.width, y*image.height, (x+w)*image.width, (y+h)*image.height)
        fill = item.get("fill") if isinstance(item.get("fill"), str) and re.fullmatch(r"#[0-9a-fA-F]{6}", item["fill"]) else _text_color(image, pixel_box)
        text_items.append({"id": ident, "kind": "text", "label": label, "x": x, "y": y, "w": w, "h": h,
                           "font_size_pt": font_size, "fill": fill, "font_weight": _font_weight(image, pixel_box, font_size)})
    # Remove the original text before tracing. This avoids leaving antialiased
    # glyph fragments or deleting a large background path merely because it
    # touches a letter. Only the small OCR rectangles are inpainted.
    tick('正在修复文字底色并保留周围插画')
    cleaned, removal = remove_text_ink(png, text_items,include_masks=True)
    tick('正在描摹贝塞尔曲线与颜色')
    for precision, layers in ((8,4),(8,8),(7,12)):
        traced, engine = vectorize_vtracer(cleaned, quality="high", overrides={
            "color_precision": precision, "filter_speckle": 2, "path_precision": 3,
            "length_threshold": 2.0, "layer_difference": layers})
        from vector_fidelity import correction_paths
        corrections,refinement=correction_paths(cleaned,traced)
        # Repair only measured local residuals with ordinary vector regions.
        # A gross mismatch is rejected by correction_paths, never concealed.
        traced=traced.replace(b'</svg>',(''.join(corrections)+'</svg>').encode())
        tick('正在建立可编辑的矢量图层')
        try:
            groups, report = _path_groups(traced, [], image.size, chunk_size=40)
            if len(groups)+len(text_items)<=480:break
        except SceneError:
            if precision==7:raise
    if len(groups)+len(text_items)>480:
        raise SceneError('原图细节超出当前画布容量，请裁切为单个图版后重试。原图已保留。')
    report["removed_text_regions"] = removal["removed"]
    report.update(refinement)
    scale = width_mm / image.width
    for index, group in enumerate(groups):
        x1, y1, x2, y2 = group["bbox"]
        ident = f"vector_layer_{index:03d}"
        scene["objects"].append({"id": ident, "type": "process", "role": "context", "label": "",
            "x": x1*scale, "y": y1*scale, "w": max(.1, (x2-x1)*scale), "h": max(.1, (y2-y1)*scale),
            "evidence_source": "reference_image", "evidence": "原图像素的矢量描摹；未嵌入位图",
            **_snapshot("import_"+ident, group["markup"])})
        scene["objects"][-1]["asset_snapshot"]["meta"].update({
            "label": f"矢量路径组 {index+1} · {group['paths']} 条",
            "modifications": "Traced from the imported raster; consecutive original paths grouped without reordering."})
    from vector_fidelity import region_paths
    import numpy as np
    pixels=np.asarray(image)
    cleared=np.asarray(Image.open(io.BytesIO(cleaned)).convert('RGB'))
    outlined=0
    for index,item in enumerate(text_items):
        x, y, w, h = item["x"]*width_mm, item["y"]*height_mm, item["w"]*width_mm, item["h"]*height_mm
        scene["objects"].append({"id": item["id"], "type": "text", "label": item["label"],
            "state": "import_text",
            "font_weight": item["font_weight"],
            "x": x, "y": y, "w": w, "h": h, "font_size_pt": item["font_size_pt"], "fill": item["fill"],
            "label_dx": 0, "label_dy": -h/2-item["font_size_pt"]*25.4/72*.75,
            "evidence_source": "reference_image", "evidence": "原图文字；请作者核对 OCR 与字体"})
        if index<len(removal['masks']):
            left,top,right,bottom,mask=removal['masks'][index]
            crop=pixels[top:bottom,left:right]
            ink=(mask>0)&np.any(crop!=cleared[top:bottom,left:right],axis=2)
            paths=region_paths(crop,ink)
            if paths:
                svg=f'<svg viewBox="0 0 {right-left} {bottom-top}">'+''.join(paths)+'</svg>'
                scene['objects'][-1].update(_snapshot('import_text_'+str(index),svg))
                scene['objects'][-1].update(x=left*scale,y=top*scale,w=(right-left)*scale,h=(bottom-top)*scale,
                    text_appearance={k:item[k] for k in ('label','font_size_pt','fill')})
                outlined+=1
    scene["provenance"].update({"method": "import-raster-high-fidelity-vector", "raster_embedded": False,
                                "ocr_source": ocr_source, "vector_engine": engine["engine"]})
    scene["unresolved"] = warnings + [
        "输出不包含位图。插画为可编辑贝塞尔路径；为保持画布响应，连续路径按原始绘制顺序分组。",
        "点击“矢量细节”可逐路径选择、改色、移动和删除。原图箭头保持轮廓路径，未自动绑定科研对象。",
        "保留原字形的标签使用独立矢量轮廓，避免字体替换造成乱码和错位；在软件中改字或字号后切换为文字。PPTX 中未替换的原字形仍是轮廓，无法直接作为文本键入。",
        "未识别的小字可能保留为文字轮廓路径；OCR 文本、字体和科学含义仍需对照原图核验。"]
    report.update({"ocr_source": ocr_source, "texts": len(text_items), "raster_embedded": False,
                   "outline_labels":outlined,
                   "trace_parameters":engine.get('params',{})})
    return normalize_scene(scene), report


def fidelity_report(png: bytes, svg: str) -> dict:
    from PIL import Image
    from vector_fidelity import render_pixels,pixel_quality
    source=Image.open(io.BytesIO(png)).convert('RGB')
    return pixel_quality(source,render_pixels(svg,source.size))
