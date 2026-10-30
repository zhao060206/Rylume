"""Persistent reference pixels and explicit, bounded layout observations.

References are user documents, never executable SVG or arbitrary file URLs.
The same pixels remain available to planning, generation and later inspection.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import uuid
from pathlib import Path

from scene_document import OBJECT_TYPES, RELATION_TYPES, SceneError

REFERENCE_ID = re.compile(r"^ref_[a-f0-9]{24}$")
PURPOSES = {"layout", "sketch", "style", "content"}
INSTRUCTION = """分析用户提供的科研参考图或手绘草稿，只返回JSON。
这是观察任务，不能从箭头或匿名形状推断未写明的因果机制。
识别可见对象、标签、位置、连线端点与阅读顺序。草稿中的框/圆也要识别，标签尽量逐字转录；
无法确认的对象使用type=process,label=原有文字或空串，不编造分子名称。
位置为相对于整图的0-1比例，x/y是左上角，w/h是宽高。每个主要对象都有独立稳定id。
只记录实际可见的连线，type=sequence或associates；明确可辨的抑制钝头才使用inhibits。
不要把时间循环改成感知/推理/执行系统。不要为图补充隐形对象。
结构：{"summary":"中文简述", "composition":"serpentine|row|column|cycle|network|free",
"reading_order":"逐项描述顺序", "objects":[{"id":"n1","label":"标签","type":"cell|process|protein|...",
"x":0.1,"y":0.2,"w":0.2,"h":0.25,"state":"可见状态，不确定则空"}],
"relations":[{"source":"n1","target":"n2","type":"sequence","label":"可见文字"}],
"uncertainties":["看不清的文字或端点"],
"style_dna":{"reference_summary":"构图摘要","visual_style_summary":"画风",
"palette":{"primary":"#2E6F83","secondary":"#669A83","accent":"#D99854"},
"layout_analysis":{"composition":"multi_panel","panel_count":5,"reading_order":"mixed","label_position":"outside"}}}
最多60个主体对象；无标签的装饰细节不单独列出。"""


def _root(data_dir):
    return Path(data_dir) / "figure-references"


def _directory(data_dir, reference_id):
    if not isinstance(reference_id, str) or not REFERENCE_ID.fullmatch(reference_id):
        raise SceneError("参考图标识无效，请重新选择参考图")
    return _root(data_dir) / reference_id


def _png(data_url):
    from PIL import Image, ImageOps
    if not isinstance(data_url, str) or not re.match(r"^data:image/(png|jpe?g|webp);base64,", data_url):
        raise SceneError("请上传 PNG、JPEG 或 WebP 图片")
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        if not raw or len(raw) > 10 * 1024 * 1024:
            raise SceneError("参考图请小于 10 MB")
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 36_000_000:
                raise SceneError("参考图像素过大，请缩小到 3600 万像素以内")
            rgba=ImageOps.exif_transpose(image).convert('RGBA')
            paper=Image.new('RGBA',rgba.size,'white')
            paper.alpha_composite(rgba)
            image=paper.convert('RGB')
            image.thumbnail((2400, 2400))
            out = io.BytesIO()
            image.save(out, format="PNG")
            return out.getvalue(), image.size
    except SceneError:
        raise
    except Exception as exc:
        raise SceneError("参考图无法读取，请重新导出为 PNG 或 JPEG") from exc


def normalize_contract(value):
    value = value if isinstance(value, dict) else {}
    objects, ids = [], set()
    source = value.get("objects") or []
    if not isinstance(source, list) or len(source) > 60:
        raise SceneError("参考图对象过多，请选取需要的区域")
    remap = {}
    ambiguous=set()
    notes=[]
    for i, item in enumerate(source):
        if not isinstance(item, dict):
            continue
        raw_id = str(item.get("id") or f"n{i+1}")
        ident = raw_id if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,70}", raw_id) and raw_id not in ids else f"ref_n{i+1}"
        suffix=2
        while ident in ids:
            ident=f'ref_n{i+1}_{suffix}';suffix+=1
        try:
            x, y, w, h = [float(item.get(k, default)) for k, default in (("x", .1), ("y", .1), ("w", .2), ("h", .2))]
            if not all(__import__('math').isfinite(v) for v in (x, y, w, h)):
                continue
            x, y = max(0, min(.98, x)), max(0, min(.98, y))
            w, h = max(.015, min(1-x, w)), max(.015, min(1-y, h))
        except (ValueError, TypeError):
            continue
        ids.add(ident)
        if raw_id in remap or raw_id in ambiguous:
            ambiguous.add(raw_id);remap.pop(raw_id,None)
            notes.append('参考图出现重复对象标识，相关连线未自动认定，请核对对象与端点。')
        else:remap[raw_id]=ident
        kind=item.get('type')
        objects.append({"id": ident, "label": str(item.get("label") or "")[:240],
                        "type": kind if isinstance(kind,str) and kind in OBJECT_TYPES else "process",
                        "state": str(item.get("state") or "")[:80],
                        **{k: round(v, 5) for k, v in zip(("x", "y", "w", "h"), (x,y,w,h))}})
    relations = []
    source_relations=value.get('relations') or []
    if not isinstance(source_relations,list):raise SceneError('参考图连线必须是列表')
    for item in source_relations[:120]:
        if not isinstance(item, dict):
            continue
        a, b = remap.get(str(item.get("source"))), remap.get(str(item.get("target")))
        if a and b and a != b:
            kind=item.get('type')
            relations.append({"source": a, "target": b, "type": kind if isinstance(kind,str) and kind in RELATION_TYPES else "associates",
                              "label": str(item.get("label") or "")[:160]})
    uncertainties=value.get('uncertainties') or []
    if isinstance(uncertainties,str):uncertainties=[uncertainties]
    if not isinstance(uncertainties,list):uncertainties=[]
    return {"coordinates": "normalized", "objects": objects, "relations": relations,
            "summary": str(value.get("summary") or "")[:1800],
            "composition": str(value.get("composition") or "free")[:50],
            "reading_order": str(value.get("reading_order") or "")[:1000],
            "uncertainties": list(dict.fromkeys([str(x)[:400] for x in uncertainties[:20]]+notes))}


def analyze(data_url, config, purpose):
    import pipeline
    section = config.get("vision") or {}
    if not section.get("base_url") or not section.get("model"):
        section = config.get("text") or {}
    if not section.get("base_url") or not section.get("model"):
        raise SceneError("请配置视觉模型后识别参考图；原图已经保存")
    response = pipeline._post_json(pipeline._endpoint(section["base_url"], "/chat/completions"),
                                  pipeline._api_key(section), {
        "model": section["model"], "temperature": 0, "max_tokens": 6000,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": INSTRUCTION + "\n参考用途：" + purpose},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
    }, timeout=120)
    parsed = pipeline._json_object(response["choices"][0]["message"].get("content") or "")
    contract = normalize_contract(parsed)
    dna = parsed.get("style_dna") if isinstance(parsed.get("style_dna"), dict) else {}
    dna["reference_summary"] = contract["summary"]
    return contract, dna


def create(data_dir, data_url, config, *, purpose="layout", analyze_image=True):
    if purpose not in PURPOSES:
        raise SceneError("参考用途无效")
    pixels, size = _png(data_url)
    ident = "ref_" + uuid.uuid4().hex[:24]
    directory = _directory(data_dir, ident)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "source.png").write_bytes(pixels)
    from PIL import Image
    image = Image.open(io.BytesIO(pixels))
    image.thumbnail((800, 800))
    image.save(directory / "preview.png")
    meta = {"reference_id": ident, "purpose": purpose, "sha256": hashlib.sha256(pixels).hexdigest(),
            "width": size[0], "height": size[1], "analysis_status": "not_requested",
            "reference_contract": normalize_contract({}), "style_dna": {}}
    if analyze_image:
        try:
            url = "data:image/png;base64," + base64.b64encode(pixels).decode("ascii")
            meta["reference_contract"], meta["style_dna"] = analyze(url, config, purpose)
            meta["analysis_status"] = "ready"
        except Exception:
            # Do not lose a user's sketch because a remote model is offline.
            meta["analysis_status"] = "unavailable"
            meta["analysis_message"] = "原图已保留，暂时无法识别布局；生成时仍会提供原图"
    (directory / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, **meta, "preview_url": f"/api/references/{ident}/preview.png"}


def read(data_dir, reference_id):
    return json.loads((_directory(data_dir, reference_id) / "meta.json").read_text(encoding="utf-8"))


def image_data_url(data_dir, reference_id):
    data = (_directory(data_dir, reference_id) / "source.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def preview(data_dir, reference_id):
    return (_directory(data_dir, reference_id) / "preview.png").read_bytes()
