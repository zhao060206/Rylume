"""Versioned, provider-independent scientific scene documents.

Geometry is in millimetres; font and stroke sizes are in points.  Generated
content, direct manipulation, checks and export all consume the same document.
No SVG supplied by a model is accepted by this module.
"""
from __future__ import annotations

import copy
import json
import math
import re
import threading
from pathlib import Path

SCHEMA_VERSION = 2
PT_MM = 25.4 / 72
OBJECT_TYPES = {
    "ligand", "receptor", "receptor_dimer", "gpcr", "kinase", "protein", "tf",
    "dna", "mrna", "lipid", "vesicle", "mvb", "vesicle_fusion", "nucleus",
    "mitochondrion", "golgi", "er", "cell", "tumor_cell", "immune_cell",
    "fibroblast", "endothelial", "collagen", "tissue", "complex", "domain",
    "process", "text", "membrane", "nuclear_pore",
    "junction", "pathogen", "stem_cell", "organelle", "channel", "antibody", "symbol",
}
RELATION_TYPES = {"sequence", "activates", "inhibits", "binds", "converts", "transports", "associates"}
PORTS = {"auto", "n", "e", "s", "w"}
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,95}$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
DEFAULT_STYLE = {
    "font_family": "Arial", "font_size_pt": 8, "min_font_size_pt": 7,
    "stroke_pt": 0.8, "show_title": False, "relation_labels": False, "template": "", "colorway": "lagoon", "glyph_tint": 0.65,
    "palette": {"primary": "#2E6F83", "secondary": "#669A83", "accent": "#D99854"},
}


class SceneError(ValueError):
    """An invalid scene or an operation that cannot be applied."""


class RevisionConflict(SceneError):
    """A stale editor must not overwrite a more recent revision."""


def _number(value, name, low=-4000, high=4000):
    if isinstance(value, bool):
        raise SceneError(f"{name} 必须是数值")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise SceneError(f"{name} 必须是数值") from None
    if not math.isfinite(result) or not low <= result <= high:
        raise SceneError(f"{name} 超出允许范围 ({low}–{high})")
    return round(result, 5)


def _id(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise SceneError("对象 ID 只能包含字母、数字、下划线和连字符")
    return value


def _text(value, limit=240):
    if value is None:
        return ""
    result = str(value)
    if len(result) > limit:
        raise SceneError(f"文字超出 {limit} 字限制")
    return "".join(c for c in result if c >= " " or c in "\n\t")


def _color(value):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise SceneError("颜色必须是 #RRGGBB 格式")
    return value


def empty_scene(title="未命名图版", source_text="", width_mm=180, height_mm=120):
    return {
        "schema_version": SCHEMA_VERSION, "revision": 1, "id": "scene",
        "title": title, "source_text": source_text,
        "layout": "pathway",
        "canvas": {"width_mm": width_mm, "height_mm": height_mm},
        "style": copy.deepcopy(DEFAULT_STYLE), "compartments": [], "objects": [],
        "relations": [], "annotations": [], "unresolved": [],
        "requirements": {"objects": [], "relations": []}, "provenance": {}, "generation_contract": {},
    }


def normalize_scene(value):
    """Validate untrusted model/editor input and return a detached document."""
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise SceneError("需要 schema_version=2 的场景文档")
    scene = empty_scene()
    scene.update({k: copy.deepcopy(v) for k, v in value.items() if k in scene})
    scene["id"] = _id(scene["id"])
    scene["revision"] = int(_number(scene["revision"], "revision", 1, 10**9))
    scene["title"] = _text(scene["title"], 180)
    scene["source_text"] = _text(scene["source_text"], 8000)
    if scene.get("layout") not in ("pathway", "process", "network", "assembly"):
        raise SceneError("不支持的场景布局")
    canvas = scene["canvas"]
    if not isinstance(canvas, dict):
        raise SceneError("画布尺寸无效")
    scene["canvas"] = {k: _number(canvas.get(k, d), k, 40, 1000)
                       for k, d in (("width_mm", 180), ("height_mm", 120))}
    supplied_style = scene.get("style")
    if not isinstance(supplied_style, dict):
        raise SceneError("样式无效")
    style = {**copy.deepcopy(DEFAULT_STYLE), **{k: v for k, v in supplied_style.items()
                                             if k in DEFAULT_STYLE}}
    style["font_family"] = _text(style["font_family"], 80)
    if not re.fullmatch(r"[\w ,\-]+", style["font_family"]):
        raise SceneError("字体名称无效")
    style["min_font_size_pt"] = _number(style["min_font_size_pt"], "最小字号", 7, 24)
    style["font_size_pt"] = _number(style["font_size_pt"], "字号", style["min_font_size_pt"], 48)
    style["stroke_pt"] = _number(style["stroke_pt"], "线宽", 0.2, 6)
    style["show_title"] = bool(style["show_title"])
    style["relation_labels"] = bool(style["relation_labels"])
    style["template"] = _text(style.get("template", ""), 60)
    style["colorway"] = _text(style.get("colorway", "lagoon"), 60)
    # Documents created before the gallery release keep their original fill contrast.
    style['glyph_tint'] = _number(supplied_style.get('glyph_tint', .8), '填充明度', .2, .95)
    palette = style.get("palette") or {}
    if not isinstance(palette, dict):
        raise SceneError("配色无效")
    style["palette"] = {k: _color(palette.get(k, v)) for k, v in DEFAULT_STYLE["palette"].items()}
    scene["style"] = style
    for key, maximum in (("compartments", 40), ("objects", 500), ("relations", 1000),
                         ("annotations", 100), ("unresolved", 100)):
        if not isinstance(scene[key], list) or len(scene[key]) > maximum:
            raise SceneError(f"{key} 数量或格式无效")
    seen = set()
    clean_compartments = []
    for c in scene["compartments"]:
        if not isinstance(c, dict):
            raise SceneError("区室格式无效")
        cid = _id(c.get("id"))
        if cid in seen:
            raise SceneError(f"重复对象 ID: {cid}")
        seen.add(cid)
        out = {"id": cid, "kind": _text(c.get("kind", cid), 60),
               "label": _text(c.get("label", ""), 100)}
        for key in ("x", "y", "w", "h"):
            if key in c:
                out[key] = _number(c[key], key, 0.1 if key in ("w", "h") else -4000)
        clean_compartments.append(out)
    scene["compartments"] = clean_compartments
    compartment_ids = {c["id"] for c in clean_compartments}
    clean_objects = []
    for o in scene["objects"]:
        if not isinstance(o, dict):
            raise SceneError("对象格式无效")
        oid = _id(o.get("id"))
        if oid in seen:
            raise SceneError(f"重复对象 ID: {oid}")
        seen.add(oid)
        kind = o.get("type", "protein")
        if kind not in OBJECT_TYPES:
            raise SceneError(f"不支持的科研图元: {kind}")
        role = o.get('role', 'entity')
        if role not in ('entity', 'context', 'annotation'):
            raise SceneError('对象角色无效')
        compartment = str(o.get("compartment") or "")
        if compartment and compartment not in compartment_ids:
            raise SceneError(f"对象 {oid} 的区室不存在: {compartment}")
        out = {"id": oid, "entity_id": _id(o.get("entity_id") or oid), "type": kind, "role": role,
               "label": _text(o.get("label", "")), "state": _text(o.get("state", ""), 80),
               "compartment": compartment, "group_id": _text(o.get("group_id", ""), 96),
               "locked": bool(o.get("locked", False)), "visible": bool(o.get("visible", True)),
               "rotation": _number(o.get("rotation", 0), "旋转", -36000, 36000) % 360,
               "font_size_pt": _number(o.get("font_size_pt", style["font_size_pt"]), "字号", style["min_font_size_pt"], 48),
               "label_dx": _number(o.get("label_dx", 0), "label_dx"),
               "label_dy": _number(o.get("label_dy", 0), "label_dy"),
               "evidence": _text(o.get("evidence", ""), 1000)}
        if o.get('visual_description'):
            out['visual_description']=_text(o['visual_description'],1000)
        if o.get('reference_object_id'):
            out['reference_object_id']=_id(o['reference_object_id'])
        if o.get('evidence_source') in ('user_text','reference_image','canvas_sketch','knowledge'):
            out['evidence_source'] = o['evidence_source']
            out['evidence_ref'] = _text(o.get('evidence_ref',''),240)
        if o.get('illustration'):
            from figure_assets import validate_illustration
            illustration = o['illustration']
            if not isinstance(illustration, dict):
                raise SceneError('插画对象格式无效')
            data = illustration.get('data')
            out['illustration'] = {'data': data, 'sha256': validate_illustration(data), 'kind': 'generated-raster'}
        if o.get("asset_id"):
            from scientific_library import library
            if not isinstance(o['asset_id'],str) or not IDENTIFIER.fullmatch(o['asset_id']):raise SceneError('未知科研素材，请使用素材库')
            aid=o['asset_id']
            from resource_packs import snapshot
            try:
                if o.get('asset_snapshot'):
                    out['asset_snapshot']=snapshot(o['asset_snapshot'],aid)
                elif aid in library() and library()[aid].get('_file'):
                    meta=library()[aid]
                    out['asset_snapshot']=snapshot({'svg':Path(meta['_file']).read_text(encoding='utf8'),'meta':meta},aid)
                elif aid not in library():raise SceneError('未知科研素材：素材包未安装且图版没有素材快照，请先下载对应学科包')
            except ValueError as exc:raise SceneError(str(exc)) from None
            out["asset_id"] = aid
        for key in ("x", "y", "w", "h"):
            if key in o:
                out[key] = _number(o[key], key, 0.1 if key in ("w", "h") else -4000)
        for key in ("fill", "stroke"):
            if o.get(key):
                out[key] = _color(o[key])
        if "stroke_pt" in o:
            out["stroke_pt"] = _number(o["stroke_pt"], "线宽", 0.2, 6)
        clean_objects.append(out)
    scene["objects"] = clean_objects
    if sum(len(o.get('illustration',{}).get('data','')) for o in clean_objects)>21_600_000:
        raise SceneError('插画总量过大，请减少对象数量或缩小单个插画后再保存')
    object_ids = {o["id"] for o in clean_objects}
    clean_relations = []
    for r in scene["relations"]:
        if not isinstance(r, dict):
            raise SceneError("关系格式无效")
        rid = _id(r.get("id"))
        if rid in seen:
            raise SceneError(f"重复对象 ID: {rid}")
        seen.add(rid)
        if r.get("source") not in object_ids or r.get("target") not in object_ids:
            raise SceneError(f"连接 {rid} 的起点或终点不存在")
        if r.get("type", "associates") not in RELATION_TYPES:
            raise SceneError(f"连接 {rid} 的关系类型无效")
        out = {"id": rid, "source": r["source"], "target": r["target"],
               "type": r.get("type", "associates"), "label": _text(r.get("label", ""), 100),
               "indirect": bool(r.get("indirect", False)), "uncertain": bool(r.get("uncertain", False)),
               "evidence": _text(r.get("evidence", ""), 1000)}
        if r.get('evidence_source') in ('user_text','reference_image','canvas_sketch','knowledge'):
            out['evidence_source'] = r['evidence_source']
            out['evidence_ref'] = _text(r.get('evidence_ref',''),240)
        for key in ("source_port", "target_port"):
            out[key] = r.get(key, "auto")
            if out[key] not in PORTS:
                raise SceneError("连接端口无效")
        for key in ("source_anchor", "target_anchor"):
            if r.get(key) is not None:
                anchor = r[key]
                if not isinstance(anchor, dict) or anchor.get('side') not in PORTS - {'auto'}:
                    raise SceneError("连接边缘位置无效")
                out[key] = {'side': anchor['side'], 't': _number(anchor.get('t'), '边缘位置', 0, 1)}
        if r.get('label_position') is not None:
            position = r['label_position']
            if not isinstance(position, dict):
                raise SceneError("连线文字位置无效")
            out['label_position'] = {k: _number(position.get(k), '文字'+k) for k in ('x', 'y')}
        if r.get("control") is not None:
            control = r["control"]
            if not isinstance(control, dict):
                raise SceneError("曲线控制点无效")
            out["control"] = {k: _number(control.get(k), k) for k in ("x", "y")}
        if r.get("stroke"):
            out["stroke"] = _color(r["stroke"])
        if "stroke_pt" in r:
            out["stroke_pt"] = _number(r["stroke_pt"], "线宽", 0.2, 6)
        clean_relations.append(out)
    scene["relations"] = clean_relations
    # Annotation text is represented by editable text objects.  Older clients
    # can retain this reserved field, but it cannot inject renderable markup.
    scene["annotations"] = [_text(a, 1000) for a in scene["annotations"] if isinstance(a, str)]
    scene["unresolved"] = [_text(x, 1000) for x in scene["unresolved"]]
    req = scene.get("requirements")
    if not isinstance(req, dict):
        raise SceneError("需求清单无效")
    scene["requirements"] = {k: [_id(x) for x in req.get(k, [])] for k in ("objects", "relations")}
    if not isinstance(scene.get("provenance"), dict):
        scene["provenance"] = {}
    # Only descriptive metadata is retained here; endpoints never return keys.
    scene["provenance"] = {k: _text(v, 8000) for k, v in scene["provenance"].items()
                           if k in ("model", "created_at", "method", "example", "reference_summary", "reference_rights",
                                     "pre_annotation_revision", "rollback_from", "rollback_to", "annotation_count",
                                     "original_text", "generation_brief", "knowledge_sources", "scientific_assumptions",
                                     "reference_id", "reference_purpose", "generation_mode", "draft_source_id", "draft_source_revision")}
    contract = scene.get('generation_contract') or {}
    if not isinstance(contract, dict):
        raise SceneError('生成需求基线格式无效')
    # Data only. Never retain provider credentials or executable markup here.
    scene['generation_contract'] = {k: _text(contract[k], 200000 if k in ('expected_objects','expected_relations') else 8000) for k in (
        'original_text', 'generation_brief', 'reference_id', 'reference_summary', 'reference_purpose',
        'layout', 'draft_source_id', 'draft_source_revision', 'source_kind', 'verification',
        'expected_objects', 'expected_relations') if k in contract}
    return scene


def apply_operations(scene, operations, *, allowed_ids=None):
    """Apply one editor gesture transactionally; the caller owns revision CAS."""
    if not isinstance(operations, list) or not operations or len(operations) > 1000:
        raise SceneError("需要 1–1000 个修改操作")
    draft = copy.deepcopy(scene)
    for op in operations:
        if not isinstance(op, dict):
            raise SceneError("修改操作格式无效")
        name = op.get("op")
        oid = op.get("id")
        if allowed_ids is not None and name not in ("update", "update_relation"):
            raise SceneError("局部 AI 修改仅可更新选中对象及其连接")
        if allowed_ids is not None and oid not in allowed_ids:
            raise SceneError("AI 修改超出了选中范围")
        if name == "replace":
            replacement = normalize_scene(op.get("scene"))
            for key in ("id", "revision", "source_text", "requirements", "provenance", "generation_contract"):
                replacement[key] = copy.deepcopy(scene[key])
            draft = replacement
        elif name in ("update", "update_relation"):
            key = "objects" if name == "update" else "relations"
            target = next((o for o in draft[key] if o["id"] == oid), None)
            if target is None:
                raise SceneError(f"对象不存在: {oid}")
            changes = op.get("changes")
            if not isinstance(changes, dict) or "id" in changes:
                raise SceneError("对象 ID 不可修改")
            if key=='objects' and any(k in changes and changes[k]!=target.get(k) for k in ('type','state','asset_id')) and 'illustration' not in changes:
                target.pop('illustration',None)
            target.update(changes)
        elif name in ("add", "add_relation"):
            key, field = ("objects", "object") if name == "add" else ("relations", "relation")
            new = copy.deepcopy(op.get(field))
            if not isinstance(new, dict):
                raise SceneError("新增对象格式无效")
            index = op.get("index", len(draft[key]))
            draft[key].insert(max(0, min(int(index), len(draft[key]))), new)
        elif name in ("remove", "remove_relation"):
            key = "objects" if name == "remove" else "relations"
            if not any(o["id"] == oid for o in draft[key]):
                raise SceneError(f"对象不存在: {oid}")
            draft[key] = [o for o in draft[key] if o["id"] != oid]
            if name == "remove":
                draft["relations"] = [r for r in draft["relations"] if oid not in (r["source"], r["target"])]
        elif name == "canvas":
            old_width = draft["canvas"]["width_mm"]
            old_height = draft['canvas']['height_mm']
            draft["canvas"] = {"width_mm": op.get("width_mm", old_width),
                               "height_mm": op.get("height_mm", draft["canvas"]["height_mm"])}
            if op.get("reflow"):
                from scene_render import layout_scene
                if draft.get('provenance',{}).get('method') in ('original-scientific-storyboard','original-editable-workflow'):
                    sx=_number(draft['canvas']['width_mm'],'width_mm',40,1000)/old_width
                    sy=_number(draft['canvas']['height_mm'],'height_mm',40,1000)/old_height
                    for obj in draft['objects']:
                        for key in ('x','w','label_dx'):obj[key]=obj.get(key,0)*sx
                        for key in ('y','h','label_dy'):obj[key]=obj.get(key,0)*sy
                    for rel in draft['relations']:
                        if rel.get('control'):
                            rel['control']['x']*=sx;rel['control']['y']*=sy
                        if rel.get('label_position'):
                            rel['label_position']['x']*=sx;rel['label_position']['y']*=sy
                    from scene_render import repair_geometry
                    draft=repair_geometry(draft,passes=2)
                else:draft = layout_scene(draft, force=True)
        elif name == "style":
            changes = op.get("changes")
            if not isinstance(changes, dict):
                raise SceneError("样式修改格式无效")
            if "palette" in changes:
                changes = {**changes, "palette": {**draft["style"].get("palette", {}), **changes["palette"]}}
            draft["style"].update(changes)
        elif name == "set_annotations":
            annotations = op.get("annotations")
            if not isinstance(annotations, list):
                raise SceneError("批注列表格式无效")
            draft["annotations"] = copy.deepcopy(annotations)
        elif name == "reorder":
            ids = op.get("ids")
            if not isinstance(ids, list) or len(set(ids)) != len(ids) or set(ids) != {o["id"] for o in draft["objects"]}:
                raise SceneError("图层顺序必须包含全部对象")
            by_id = {o["id"]: o for o in draft["objects"]}
            draft["objects"] = [by_id[x] for x in ids]
        else:
            raise SceneError(f"未知操作: {name}")
    return normalize_scene(draft)


def audit_scene(scene):
    """Evidence-linked structural checks; VLM opinions are a separate channel."""
    scene = normalize_scene(scene)
    findings = []

    def add(code, message, ids=(), severity="warning", **evidence):
        findings.append({"code": code, "severity": severity, "object_ids": list(ids),
                         "message": message, "source": "deterministic", "evidence": evidence})

    width, height = (scene["canvas"][k] for k in ("width_mm", "height_mm"))
    objects = {o["id"]: o for o in scene["objects"]}
    relations = {r["id"]: r for r in scene["relations"]}
    if scene.get('generation_contract'):
        from scientific_intent import intent_contract,canonical_phase,labeled_cell_phase,excluded_object_evidence,contradicted_relation_evidence
        baseline=scene['generation_contract'].get('original_text') or scene['source_text']
        intent=intent_contract(baseline)
        if intent['requires_mitosis'] and intent['depicts_phases']:
            actual={canonical_phase(o.get('state','')) or labeled_cell_phase(o['label'],biological_context=True) for o in objects.values() if o['visible'] and o['type']=='cell'}
            missing=[phase for phase in intent['explicit_phases'] if phase not in actual]
            if missing:
                add('missing-scientific-state','原始描述中的分期未在图中表达：'+'、'.join(missing),severity='error',source_text=baseline)
            for o in objects.values():
                if labeled_cell_phase(o['label'],biological_context=True) and o['type']!='cell':
                    add('phase-morphology','分期标签没有对应的细胞形态',[o['id']],'error')
        if intent['domain']=='biology' and intent['excluded_phases']:
            for o in objects.values():
                phase=canonical_phase(o.get('state','')) or labeled_cell_phase(o['label'],biological_context=True)
                if o['visible'] and o['type']=='cell' and phase in intent['excluded_phases']:
                    add('excluded-scientific-state','出现作者明确排除的细胞分期：'+phase,[o['id']],'error',source_text=baseline)
        for o in objects.values():
            evidence=excluded_object_evidence(baseline,o['label'])
            if o['visible'] and evidence:add('excluded-object','出现作者明确要求不添加的对象',[o['id']],'error',source_text=evidence)
        for r in relations.values():
            evidence=contradicted_relation_evidence(baseline,objects[r['source']]['label'],objects[r['target']]['label'],r['type'])
            if evidence:add('contradicted-relation','关系与原文的否定要求冲突，请核对',[r['id']],'error',source_text=evidence)
        generated_text=' '.join([scene['title']]+[o['label']+' '+o.get('state','') for o in objects.values()]+[r['label'] for r in relations.values()])
        if intent['domain']=='biology':
            foreign=('latent','physical priors','感知阵列','潜变量','action dispatch','具身智能','u_mitosis')
            leaked=[term for term in foreign if term in generated_text.lower() and term not in baseline.lower()]
            if leaked:
                add('unsupported-mechanism','出现原描述没有要求的工程控制概念：'+'、'.join(leaked),severity='error')
    for oid in scene["requirements"]["objects"]:
        if oid not in objects or not objects[oid]["visible"]:
            add("required-object", "原始需求中的对象缺失或被隐藏", [oid], "error")
    for rid in scene["requirements"]["relations"]:
        if rid not in relations:
            add("required-relation", "原始需求中的关系缺失", [rid], "error")
    compartment_map = {c["id"]: c for c in scene["compartments"]}
    for o in objects.values():
        if not o["visible"]:
            continue
        oid = o["id"]
        if not o["label"].strip() and o.get('role') != 'context':
            add("empty-label", "对象没有标签", [oid])
        if not all(k in o for k in ("x", "y", "w", "h")):
            add("unplaced", "对象尚未完成布局", [oid], "error")
            continue
        if o["x"] < 0 or o["y"] < 0 or o["x"] + o["w"] > width + 0.05 or o["y"] + o["h"] > height + 0.05:
            add("outside-canvas", "对象超出画布", [oid], "error", bounds=[o[k] for k in ("x", "y", "w", "h")])
        if o["font_size_pt"] < 7:
            add("font-floor", "最终尺寸下的字号小于 7 pt", [oid], "error")
        c = compartment_map.get(o.get("compartment"))
        if c and all(k in c for k in ("x", "y", "w", "h")):
            cx, cy = o["x"] + o["w"] / 2, o["y"] + o["h"] / 2
            if not (c["x"] <= cx <= c["x"] + c["w"] and c["y"] <= cy <= c["y"] + c["h"]):
                add("compartment", "对象中心已移出其标记区室", [oid], compartment=c["id"])
    for r in relations.values():
        if not objects[r["source"]]["visible"] or not objects[r["target"]]["visible"]:
            add("hidden-endpoint", "连接的一端被隐藏", [r["id"], r["source"], r["target"]])
        if r["uncertain"]:
            add("uncertain-relation", "此关系的科学含义需要作者确认", [r["id"]])
    visible = [o for o in objects.values() if o["visible"] and o.get('role') != 'context' and all(k in o for k in ("x", "y", "w", "h"))]
    for index, a in enumerate(visible):
        for b in visible[index + 1:]:
            if a.get("group_id") and a.get("group_id") == b.get("group_id"):
                continue
            overlap = max(0, min(a["x"]+a["w"], b["x"]+b["w"])-max(a["x"], b["x"])) * max(0, min(a["y"]+a["h"], b["y"]+b["h"])-max(a["y"], b["y"]))
            if overlap > 0.55 * min(a["w"]*a["h"], b["w"]*b["h"]):
                add("overlap", "两个对象大面积重叠，请检查是否为预期的结合状态", [a["id"], b["id"]], overlap_mm2=round(overlap, 2))
    try:
        from scene_render import label_boxes
        boxes = label_boxes(scene)
        # Renderer supplies measured/estimated wrapped label rectangles.
        for box in boxes:
            if box["x"] < 0 or box["y"] < 0 or box["x"]+box["w"] > width+0.1 or box["y"]+box["h"] > height+0.1:
                add("label-outside", "标签超出画布", [box["id"]], "error")
        for i, a in enumerate(boxes):
            for b in boxes[i+1:]:
                if min(a["x"]+a["w"],b["x"]+b["w"])-max(a["x"],b["x"]) > 0.4 and min(a["y"]+a["h"],b["y"]+b["h"])-max(a["y"],b["y"]) > 0.4:
                    add("label-overlap", "两个标签重叠", [a["id"], b["id"]])
            for o in visible:
                if o["id"] == a["id"]:
                    continue
                overlap_w = min(a["x"]+a["w"],o["x"]+o["w"])-max(a["x"],o["x"])
                overlap_h = min(a["y"]+a["h"],o["y"]+o["h"])-max(a["y"],o["y"])
                if overlap_w > 0.6 and overlap_h > 0.6:
                    add("label-object-overlap", "标签与另一个对象重叠", [a["id"],o["id"]])
    except ImportError:
        pass
    for item in scene["unresolved"]:
        add("author-review", item)
    return {"revision": scene["revision"], "status": "needs_attention" if findings else "passed",
            "errors": sum(f["severity"] == "error" for f in findings),
            "warnings": sum(f["severity"] == "warning" for f in findings),
            "findings": findings, "vision": {"status": "not_requested", "findings": []},
            "author_confirmed": False}


class SceneRepository:
    """Revision directories + one atomic HEAD; exports pin immutable revisions."""
    def __init__(self, job_dir):
        self.root = Path(job_dir)
        self.lock = threading.RLock()

    def read(self, revision=None):
        from studio_storage import recover_pending_replacements
        recover_pending_replacements(self.root,recursive=False)
        if revision is None:
            head = json.loads((self.root / "scene-head.json").read_text(encoding="utf-8"))
            revision = head["revision"]
        revision = int(_number(revision, "revision", 1, 10**9))
        return normalize_scene(json.loads((self.root / "revisions" / str(revision) / "scene.json").read_text(encoding="utf-8")))

    def commit(self, scene, base_revision=None):
        import os
        import uuid
        from scene_render import render_scene, layout_scene
        with self.lock:
            head_path = self.root / "scene-head.json"
            current = self.read() if head_path.exists() else None
            if current is not None and base_revision != current["revision"]:
                raise RevisionConflict("图版已被其他操作更新，请保留当前草稿并重新载入")
            if current is None and base_revision not in (None, 0):
                raise RevisionConflict("场景尚未创建")
            scene = layout_scene(normalize_scene(scene))
            scene["revision"] = (current["revision"] + 1) if current else 1
            svg = render_scene(scene)
            audit = audit_scene(scene)
            folder = self.root / "revisions" / str(scene["revision"])
            folder.mkdir(parents=True, exist_ok=True)
            # A process interrupted before HEAD is published leaves an orphan,
            # never a half-readable current scene. Reusing that revision is safe.
            def _safe_replace(s, d):
                from studio_storage import durable_replace
                import time
                for attempt in range(3):
                    try:
                        durable_replace(s, d)
                        return
                    except PermissionError:
                        if attempt==2:raise
                        time.sleep(.03)
            for filename, data in (("scene.json", json.dumps(scene, ensure_ascii=False, indent=2)),
                                   ("result.svg", svg), ("audit.json", json.dumps(audit, ensure_ascii=False, indent=2))):
                temp = folder / (filename + "." + uuid.uuid4().hex + ".tmp")
                temp.write_text(data, encoding="utf-8")
                _safe_replace(temp, folder / filename)
            temp = self.root / ("scene-head." + uuid.uuid4().hex + ".tmp")
            temp.write_text(json.dumps({"revision": scene["revision"]}), encoding="utf-8")
            _safe_replace(temp, head_path)
            return {"scene": scene, "revision": scene["revision"], "svg": svg, "audit": audit}

    def patch(self, base_revision, operations):
        with self.lock:
            current = self.read()
            if current["revision"] != base_revision:
                raise RevisionConflict("图版修订号已变化，当前修改没有覆盖已保存内容")
            return self.commit(apply_operations(current, operations), base_revision)
