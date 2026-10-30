"""Atomic physical-size exports pinned to an immutable scene revision."""
from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from scene_document import normalize_scene


def export_scene(scene, format, destination, *, dpi=300, config=None):
    from scene_render import render_scene
    scene = normalize_scene(copy.deepcopy(scene))
    fmt = str(format).lower()
    if fmt not in ("svg", "png", "pdf", "pptx"):
        raise ValueError("不支持的导出格式")
    dpi = int(dpi)
    if dpi < 72 or dpi > 1200:
        raise ValueError("DPI 必须在 72–1200 之间")
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    width_mm, height_mm = (scene["canvas"][key] for key in ("width_mm", "height_mm"))
    svg = render_scene(scene).encode("utf-8")
    result = {"format": fmt, "path": str(destination), "revision": scene["revision"],
              "width_mm": width_mm, "height_mm": height_mm, "raster_objects": [], "warnings": []}
    result['raster_objects'] = [o['label'] or o['id'] for o in scene['objects'] if o.get('illustration') and o['visible']]
    if result['raster_objects']:
        result['warnings'].append('插画对象可整体移动；其内部像素不是独立矢量形状。文字和连线保持可编辑。')
    from scientific_library import credits
    result['artwork_credits'] = credits(scene)
    temp = destination.with_name(destination.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        if fmt == "svg":
            temp.write_bytes(svg)
        elif fmt in ("png", "pdf"):
            import fitz
            doc = fitz.open(stream=svg, filetype="svg")
            pdf = fitz.open(stream=doc.convert_to_pdf(), filetype="pdf")
            expected = fitz.Rect(0,0,width_mm*72/25.4,height_mm*72/25.4)
            if abs(pdf[0].rect.width-expected.width)>0.1 or abs(pdf[0].rect.height-expected.height)>0.1:
                corrected = fitz.open()
                page = corrected.new_page(width=expected.width,height=expected.height)
                page.show_pdf_page(expected,pdf,0)
                pdf.close()
                pdf = corrected
            if fmt == "pdf":
                temp.write_bytes(pdf.tobytes(garbage=3,deflate=True))
            else:
                from PIL import Image
                import io
                pixmap = pdf[0].get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False)
                image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")
                size = (round(width_mm/25.4*dpi),round(height_mm/25.4*dpi))
                if image.size != size:
                    image = image.resize(size,Image.Resampling.LANCZOS)
                image.save(temp,format="PNG",dpi=(dpi,dpi))
                result.update(dpi=dpi,width_px=size[0],height_px=size[1])
            pdf.close()
            doc.close()
        else:
            import ppt_native
            with tempfile.TemporaryDirectory(prefix="cell-scene-ppt-") as folder:
                source = Path(folder)/"figure.svg"
                source.write_bytes(svg)
                native = ppt_native.build(source,Path(folder)/"native",font=scene["style"]["font_family"],preview=False)
                if any("skipped" in x for x in native.get("warnings",[])):
                    raise ValueError("PPTX 包含无法转换的图元："+"；".join(native["warnings"]))
                shutil.copyfile(native["pptx"],temp)
                result["warnings"].extend(native.get("warnings",[]))
                result["objects"] = len(scene["objects"])
                result["text_runs"] = native.get("texts",0)
        shutil.move(str(temp), str(destination))
        if result['artwork_credits']:
            credit_path=destination.with_suffix(destination.suffix+'.credits.txt')
            credit_path.write_text('Scientific artwork attribution (retain in figure legend or acknowledgements):\n\n'+'\n\n'.join(
                f"{c['label']} — {c['author']} ({c['author_url']}), {c['license']} ({c['license_url']}). Source: {c['source_url']}. {c['modifications']}"
                for c in result['artwork_credits']),encoding='utf8')
            result['credits_path']=str(credit_path)
        meta = destination.with_suffix(destination.suffix+".json")
        temp_meta = meta.with_name(meta.name+"."+uuid.uuid4().hex+".tmp")
        temp_meta.write_text(json.dumps(result,ensure_ascii=True,indent=2),encoding="utf-8")
        shutil.move(str(temp_meta), str(meta))
        return result
    finally:
        temp.unlink(missing_ok=True)

