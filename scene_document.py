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

SCHEMA_VERSION = 3
AUDIT_VERSION = 4
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
        "relations": [], "structures": [], "annotations": [], "unresolved": [],
        "requirements": {"objects": [], "relations": []}, "provenance": {}, "generation_contract": {},
    }


def normalize_scene(value):
    """Validate untrusted model/editor input and return a detached document."""
    if not isinstance(value, dict) or value.get("schema_version") not in (2, SCHEMA_VERSION):
        raise SceneError("需要 schema_version=2 或 3 的场景文档")
    scene = empty_scene()
    scene.update({k: copy.deepcopy(v) for k, v in value.items() if k in scene})
    scene['schema_version'] = SCHEMA_VERSION
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
               "font_weight": int(_number(o.get("font_weight", 400), "字重", 100, 900)),
               "evidence": _text(o.get("evidence", ""), 1000)}
        if o.get('label_user_set') is True:out['label_user_set']=True
        if o.get('supplement') is True:out['supplement']=True
        if o.get('visual_description'):
            out['visual_description']=_text(o['visual_description'],1000)
        if o.get('depiction')=='anchor':out['depiction']='anchor'
        if isinstance(o.get('localization'),dict):
            loc=o['localization'];out['localization']={'status':'model_checked','evidence':_text(loc.get('evidence',''),1000),'x':_number(loc.get('x'),'定位 x',0,1),'y':_number(loc.get('y'),'定位 y',0,1)}
        for key in ('display_name', 'source_role'):
            if o.get(key): out[key] = _text(o[key], 240)
        if o.get('edit_status'):
            if o['edit_status'] not in ('verified', 'needs_review', 'outline'):
                raise SceneError('对象核对状态无效')
            out['edit_status'] = o['edit_status']
        if o.get('source_region') is not None:
            region=o['source_region']
            if not isinstance(region,dict):raise SceneError('原图区域格式无效')
            out['source_region']={k:_number(region.get(k), '原图区域 '+k, 0, 1) for k in ('x','y','w','h')}
            if min(out['source_region']['w'],out['source_region']['h'])<=0 or any(out['source_region'][a]+out['source_region'][b]>1.001 for a,b in (('x','w'),('y','h'))):
                raise SceneError('原图区域超出边界')
        if o.get('ocr') is not None:
            record=o['ocr']
            if not isinstance(record,dict):raise SceneError('文字核对信息无效')
            out['ocr']={'original':_text(record.get('original','')), 'confidence':_number(record.get('confidence',0),'文字置信度',0,1), 'confirmed':record.get('confirmed') is True}
            if record.get('suggested'):out['ocr']['suggested']=_text(record['suggested'])
        if o.get('parent_id'):
            out['parent_id']=_id(o['parent_id'])
            if o.get('placement','inside') not in ('inside','boundary','outside'):raise SceneError('包含位置无效')
            if o.get('placement')=='outside' and (out['type']!='text' or out.get('role')!='annotation'):
                raise SceneError('外部从属位置仅用于文字批注')
            out['placement']=o.get('placement','inside')
        if o.get('text_appearance') is not None:
            original=o['text_appearance']
            if kind!='text' or not isinstance(original,dict):raise SceneError('原始字形信息无效')
            out['text_appearance']={'label':_text(original.get('label','')),
                'font_size_pt':_number(original.get('font_size_pt'), '原始字号',7,48),
                'fill':_color(original.get('fill','#000000'))}
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
    by_id={o['id']:o for o in clean_objects}
    for o in clean_objects:
        trail={o['id']};parent=o.get('parent_id')
        while parent:
            if parent not in by_id:raise SceneError('包含关系引用了不存在的对象')
            if parent in trail:raise SceneError('对象包含关系不能循环')
            trail.add(parent);parent=by_id[parent].get('parent_id')
    structures=value.get('structures',[])
    if not isinstance(structures,list) or len(structures)>250:raise SceneError('结构分组格式无效')
    owners={o['id'] for o in clean_objects if o.get('asset_snapshot') and o['type']!='text'}
    memberships=set();group_ids=set();clean_structures=[]
    for group in structures:
        if not isinstance(group,dict):raise SceneError('结构分组格式无效')
        gid=_id(group.get('id'))
        if gid in group_ids:raise SceneError('结构分组 ID 重复')
        group_ids.add(gid);parts=group.get('parts')
        if not isinstance(parts,list) or len(parts)>500:raise SceneError('结构成员格式无效')
        clean=[]
        for part in parts:
            if not isinstance(part,dict) or part.get('owner') not in owners:raise SceneError('结构引用了不存在的图元')
            indices=part.get('indices')
            if not isinstance(indices,list) or not indices or len(indices)>2500:raise SceneError('结构路径数量无效')
            for index in indices:
                if type(index) is not int or not 0<=index<2500 or (part['owner'],index) in memberships:raise SceneError('结构路径重复或无效')
                memberships.add((part['owner'],index))
            clean.append({'owner':part['owner'],'indices':indices[:]})
        if clean:
            structure={'id':gid,'label':_text(group.get('label','独立结构'),100),'parts':clean,'dx':_number(group.get('dx',0),'结构水平偏移',-4000,4000),'dy':_number(group.get('dy',0),'结构垂直偏移',-4000,4000)}
            if 'visible' in group:
                if type(group['visible']) is not bool:raise SceneError('结构可见性格式无效')
                structure['visible']=group['visible']
            background=group.get('background')
            if background is not None:
                if not isinstance(background,dict) or not isinstance(background.get('colors'),list) or len(background['colors'])!=4:raise SceneError('结构背景格式无效')
                structure['background']={key:_number(background.get(key), '结构背景 '+key, .001 if key in ('w','h') else -4000,4000) for key in ('x','y','w','h')}
                structure['background']['colors']=[_color(c) for c in background['colors']]
            if 'foreground' in group:
                if not isinstance(group['foreground'],list) or len(group['foreground'])>500:raise SceneError('结构前景格式无效')
                foreground=[]
                for part in group['foreground']:
                    if not isinstance(part,dict) or part.get('owner') not in owners or not isinstance(part.get('indices'),list) or len(part['indices'])>2500 or any(type(i) is not int or not 0<=i<2500 for i in part['indices']):raise SceneError('结构前景引用无效')
                    foreground.append({'owner':part['owner'],'indices':list(dict.fromkeys(part['indices']))})
                structure['foreground']=foreground
            clean_structures.append(structure)
    scene['structures']=clean_structures
    if sum(len(o.get('illustration',{}).get('data','')) for o in clean_objects)>21_600_000:
        raise SceneError('插画总量过大，请减少对象数量或缩小单个插画后再保存')
    if sum(len(o.get('asset_snapshot',{}).get('svg','').encode('utf8')) for o in clean_objects)>32*1024*1024:
        raise SceneError('矢量结构总量超出当前画布容量，请裁切为单个图版')
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
        if r.get('callout') is True:
            if out['type']!='associates':raise SceneError('指示线不能同时表示科学因果关系')
            out['callout']=True
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
        if r.get('route_through'):
            # Objects the author means this line to cross; deleted ids drop out quietly.
            if not isinstance(r['route_through'], (list, tuple)):
                raise SceneError("连线允许穿过的对象无效")
            through = sorted({t for t in r['route_through'] if t in object_ids})
            if through:
                out['route_through'] = through
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
                                     "reference_id", "reference_purpose", "generation_mode", "draft_source_id", "draft_source_revision",
                                     "ocr_source", "vector_engine", "raster_embedded", "segmentation_method", "layout_method")}
    contract = scene.get('generation_contract') or {}
    if not isinstance(contract, dict):
        raise SceneError('生成需求基线格式无效')
    # Data only. Never retain provider credentials or executable markup here.
    scene['generation_contract'] = {k: _text(contract[k], 200000 if k in ('expected_objects','expected_relations') else 8000) for k in (
        'original_text', 'generation_brief', 'reference_id', 'reference_summary', 'reference_purpose',
        'layout', 'draft_source_id', 'draft_source_revision', 'source_kind', 'verification',
        'layout_policy','layout_summary','editable_layers', 'expected_objects', 'expected_relations') if k in contract}
    return scene


def apply_operations(scene, operations, *, allowed_ids=None):
    """Apply one editor gesture transactionally; the caller owns revision CAS."""
    if not isinstance(operations, list) or not operations or len(operations) > 1000:
        raise SceneError("需要 1–1000 个修改操作")
    draft = copy.deepcopy(scene)
    # Parent moves carry their contents. Explicit child coordinates in the same
    # gesture override inheritance, so a saved drag is never applied twice.
    explicit={op.get('id'):op.get('changes',{}) for op in operations if isinstance(op,dict) and op.get('op')=='update' and isinstance(op.get('changes',{}),dict)}
    by_id={o['id']:o for o in scene['objects']};deltas={}
    def delta(o):
        if o['id'] in deltas:return deltas[o['id']]
        change=explicit.get(o['id'],{});parent=by_id.get(o.get('parent_id'))
        inherited=delta(parent) if parent else {'x':0,'y':0}
        result={k:_number(change[k],k)-o[k] if k in change else inherited[k] for k in ('x','y') if k in o}
        deltas[o['id']]=result;return result
    additions=[]
    for o in scene['objects']:
        if not o.get('parent_id') or o['locked']:continue
        d=delta(o);changes={k:o[k]+v for k,v in d.items() if v and k not in explicit.get(o['id'],{})}
        if changes:additions.append({'op':'update','id':o['id'],'changes':changes})
    operations=operations+additions
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
            if key=='objects' and target['type']=='text' and 'label' in changes and changes['label']!=target['label'] and 'w' not in changes and target.get('state')!='import_text':
                from scene_render import _measure
                size=changes.get('font_size_pt',target['font_size_pt'])*PT_MM
                changes={**changes,'w':max(target['w'],max(_measure(line,size)+2 for line in str(changes['label']).split('\n')))}
                if 'x' not in changes and any(r.get('callout') and r['source']==oid and r.get('source_port')=='e' for r in draft['relations']):
                    changes['x']=target['x']+target['w']-changes['w']
            # A real change to a label offset (drag, nudge, AI or annotation
            # edit) marks the label hand-placed; repair candidates pass False.
            if key=='objects' and 'label_user_set' not in changes and any(k in changes and changes[k]!=target.get(k,0) for k in ('label_dx','label_dy')):
                changes={**changes,'label_user_set':True}
            target.update(changes)
            if key=='objects' and not target.get('label_user_set',True):target.pop('label_user_set',None)
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
                for child in draft['objects']:
                    if child.get('parent_id')==oid:
                        child.pop('parent_id',None);child.pop('placement',None)
                for group in draft.get('structures',[]):
                    group['parts']=[p for p in group['parts'] if p['owner']!=oid]
                    if 'foreground' in group:group['foreground']=[p for p in group['foreground'] if p['owner']!=oid]
                draft['structures']=[g for g in draft.get('structures',[]) if g['parts']]
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
        elif name == 'set_structures':
            draft['structures']=copy.deepcopy(op.get('structures'))
        elif name == "reorder":
            ids = op.get("ids")
            if not isinstance(ids, list) or len(set(ids)) != len(ids) or set(ids) != {o["id"] for o in draft["objects"]}:
                raise SceneError("图层顺序必须包含全部对象")
            by_id = {o["id"]: o for o in draft["objects"]}
            draft["objects"] = [by_id[x] for x in ids]
        else:
            raise SceneError(f"未知操作: {name}")
    return normalize_scene(draft)


def audit_scene(scene, *, _normalized=False):
    """Evidence-linked structural checks; VLM opinions are a separate channel."""
    if not _normalized:
        scene = normalize_scene(scene)
    findings = []

    def add(code, message, ids=(), severity="warning", **evidence):
        findings.append({"code": code, "severity": severity, "object_ids": list(ids),
                         "message": message, "source": "deterministic", "evidence": evidence})

    width, height = (scene["canvas"][k] for k in ("width_mm", "height_mm"))
    objects = {o["id"]: o for o in scene["objects"]}
    relations = {r["id"]: r for r in scene["relations"]}
    source_overlaps=[]
    def original_overlap(a,b,code):
        if scene['provenance'].get('method')!='import-semantic-vector':return False
        if not a.get('source_region') or not b.get('source_region'):return False
        for o in (a,b):
            region=o['source_region']
            if abs(o['w']-region['w']*width)>.03 or abs(o['h']-region['h']*height)>.03 or o.get('rotation',0):return False
            appearance=o.get('text_appearance')
            if o['type']=='text' and (not appearance or any(o[k]!=appearance[k] for k in ('label','font_size_pt','fill')) or o.get('label_dx') or o.get('label_free')):return False
        if any(abs((a[axis]-b[axis])-(a['source_region'][axis]-b['source_region'][axis])*size)>.03 for axis,size in (('x',width),('y',height))):return False
        source_overlaps.append({'code':code,'object_ids':[a['id'],b['id']],'basis':'原图对应区域与相对位置保持一致；透明轮廓的包围框交叠不作为新增遮挡'})
        return True
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
        if not o["label"].strip() and not o.get('display_name') and o.get('role') != 'context':
            add("empty-label", "对象没有标签", [oid])
        if not all(k in o for k in ("x", "y", "w", "h")):
            add("unplaced", "对象尚未完成布局", [oid], "error")
            continue
        if o["x"] < 0 or o["y"] < 0 or o["x"] + o["w"] > width + 0.05 or o["y"] + o["h"] > height + 0.05:
            add("outside-canvas", "对象超出画布", [oid], "error", bounds=[o[k] for k in ("x", "y", "w", "h")])
        if o["font_size_pt"] < 7:
            add("font-floor", "最终尺寸下的字号小于 7 pt", [oid], "error")
        parent=objects.get(o.get('parent_id'))
        if parent and all(k in parent for k in ('x','y','w','h')):
            if o.get('placement')=='outside':valid=True  # Annotation attachment, not scientific containment.
            elif o.get('placement')=='boundary':
                cx,cy=o['x']+o['w']/2,o['y']+o['h']/2
                on_edge=min(abs(cx-parent['x']),abs(cx-parent['x']-parent['w']),abs(cy-parent['y']),abs(cy-parent['y']-parent['h']))<=max(o['w'],o['h'])/2+1
                valid=on_edge and parent['x']-o['w']/2<=cx<=parent['x']+parent['w']+o['w']/2 and parent['y']-o['h']/2<=cy<=parent['y']+parent['h']+o['h']/2
            else:valid=o['x']>=parent['x']-.1 and o['y']>=parent['y']-.1 and o['x']+o['w']<=parent['x']+parent['w']+.1 and o['y']+o['h']<=parent['y']+parent['h']+.1
            if not valid:add('containment','对象的位置与标记的包含关系不一致',[oid,parent['id']],placement=o.get('placement','inside'))
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
    def is_ancestor(parent,child):
        while child.get('parent_id'):
            if child['parent_id']==parent['id']:return True
            child=objects[child['parent_id']]
        return False
    for index, a in enumerate(visible):
        for b in visible[index + 1:]:
            if is_ancestor(a,b) or is_ancestor(b,a):continue
            if a.get("group_id") and a.get("group_id") == b.get("group_id"):
                continue
            overlap = max(0, min(a["x"]+a["w"], b["x"]+b["w"])-max(a["x"], b["x"])) * max(0, min(a["y"]+a["h"], b["y"]+b["h"])-max(a["y"], b["y"]))
            if overlap > 0.55 * min(a["w"]*a["h"], b["w"]*b["h"]):
                if original_overlap(a,b,'overlap'):continue
                add("overlap", "两个对象大面积重叠，请检查是否为预期的结合状态", [a["id"], b["id"]], overlap_mm2=round(overlap, 2))
    try:
        from scene_render import label_boxes, connection_geometry, _label_lines, _measure, line_label_gap, connection_samples, connection_overshoot
        boxes = label_boxes(scene)
        for obj in visible:
            if obj['type']!='text' or obj.get('state')=='import_text' or not obj['label']:continue
            lines,fs=_label_lines(obj)
            if len(lines)>len(obj['label'].split('\n')) and len(obj['label'])<=16 or max(_measure(line,fs) for line in lines)>obj['w']+.5:
                add('text-wrap','短标签被挤成多行或超出文字框，请加宽文字框',[obj['id']],line_count=len(lines),width_mm=obj['w'])
        # Renderer supplies measured/estimated wrapped label rectangles.
        for box in boxes:
            if box["x"] < 0 or box["y"] < 0 or box["x"]+box["w"] > width+0.1 or box["y"]+box["h"] > height+0.1:
                add("label-outside", "标签超出画布", [box["id"]], "error")
            obj=objects.get(box['id'])
            if obj and obj['type']!='text' and not obj.get('label_free') and not obj.get('label_user_set'):
                gap=math.hypot(max(0,obj['x']-box['x']-box['w'],box['x']-obj['x']-obj['w']),max(0,obj['y']-box['y']-box['h'],box['y']-obj['y']-obj['h']))
                if gap>max(4,obj['font_size_pt']*PT_MM*1.5):add('label-detached','标签距离所属对象过远',[obj['id']],distance_mm=round(gap,2))
                home=next((c for c in scene['compartments'] if c['id']==obj.get('compartment')),None)
                cx,cy=box['x']+box['w']/2,box['y']+box['h']/2
                holds=lambda c:all(k in c for k in ('x','y','w','h')) and c['x']<=cx<=c['x']+c['w'] and c['y']<=cy<=c['y']+c['h']
                if home and all(k in home for k in ('x','y','w','h')) and not holds(home):
                    other=next((c for c in scene['compartments'] if c is not home and holds(c)),None)
                    if other:add('label-wrong-compartment','标签落在其它区室，请移回所属区室',[obj['id']],compartment=home['id'],label_compartment=other['id'])
        for r in relations.values():
            if not objects[r['source']]['visible'] or not objects[r['target']]['visible']:continue
            g=connection_geometry(scene,r);c=g['control']
            for box in boxes:
                if box['id']==r['id']:continue
                # Dense samples also detect crossings through narrow glyph rows.
                if any(box['x']-.2 < (1-t)**2*g['x1']+2*(1-t)*t*c['x']+t*t*g['x2'] < box['x']+box['w']+.2 and box['y']-.2 < (1-t)**2*g['y1']+2*(1-t)*t*c['y']+t*t*g['y2'] < box['y']+box['h']+.2 for t in (i/160 for i in range(2,159))):
                    add('line-label-overlap','连线穿过文字，请调整路径或标签',[r['id'],box['id']])
        for r in relations.values():
            # Same rule as an object label: a connector label more than 4 mm from its
            # line reads as loose text. Labels the user placed by hand are left alone.
            if r.get('label_position') or not objects[r['source']]['visible'] or not objects[r['target']]['visible']:continue
            if not any(b['id']==r['id'] for b in boxes):continue
            gap=line_label_gap(scene,r)
            if round(gap,1)>4:add('line-label-detached','连线标签离连线过远',[r['id']],distance_mm=round(gap,2))
        # Two connectors running together read as one line, and an end symbol lying on another
        # connector reads as belonging to it (limits as in tmp/scan_overlap.py).
        import numpy as _np
        from scene_render import connection_symbol_boxes as _sym_boxes,connection_samples as _samples
        curves={}
        for r in relations.values():
            if r.get('callout') or not objects[r['source']]['visible'] or not objects[r['target']]['visible']:continue
            g=connection_geometry(scene,r);curves[r['id']]=(r,g,_np.array(_samples(g,120)))
        def _beside(a,b):
            k=len(a)//10;mid=a[k:len(a)-k]
            d=_np.sqrt(((mid[:,None,:]-b[None,:,:])**2).sum(-1)).min(1)
            step=_np.sqrt((_np.diff(mid,axis=0)**2).sum(-1))
            return float(step[(d[:-1]<.8)&(d[1:]<.8)].sum())
        keys=list(curves)
        for i,a in enumerate(keys):
            for b in keys[i+1:]:
                (ra,ga,pa),(rb,gb,pb)=curves[a],curves[b]
                if pa[:,0].min()>pb[:,0].max()+1 or pb[:,0].min()>pa[:,0].max()+1 or pa[:,1].min()>pb[:,1].max()+1 or pb[:,1].min()>pa[:,1].max()+1:continue
                run=max(_beside(pa,pb),_beside(pb,pa));gap=None
                for (rx,gx,_px),py in (((ra,ga,pa),pb),((rb,gb,pb),pa)):
                    for x0,y0,x1,y1 in _sym_boxes(gx,rx):
                        d=float(_np.sqrt(((py-_np.array([(x0+x1)/2,(y0+y1)/2]))**2).sum(-1)).min())
                        if d<.6:gap=d if gap is None else min(gap,d)
                if run>3 or gap is not None:
                    add('connector-overlap','两条连线贴在一起，读者分不清各自的走向',[a,b],
                        side_by_side_mm=round(run,1),symbol_gap_mm=None if gap is None else round(gap,2))
        from scene_render import connection_symbol_boxes,_object_label_boxes,connection_visible_body
        symbol_labels=_object_label_boxes(scene)
        # Connector geometry: hooks, detours past the ends, binding symbols with no
        # visible line between their discs, and lines run through other objects.
        # Background (context) objects are not obstacles; neither are containers of an
        # end, the membrane an end sits in, or objects listed in route_through.
        for r in relations.values():
            if not objects[r['source']]['visible'] or not objects[r['target']]['visible']:continue
            g=connection_geometry(scene,r);pts=connection_samples(g)
            chord=math.hypot(g['x2']-g['x1'],g['y2']-g['y1'])
            length=sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(pts,pts[1:]))
            if chord>3 and length/chord>1.4:add('connector-hook','连线弯成钩形，请重算弯曲或改走另一侧',[r['id']],ratio=round(length/chord,2))
            over=connection_overshoot(g,pts)
            if over>.5:add('connector-overshoot','连线绕出两端太远',[r['id']],overshoot_mm=round(over,2))
            if r['type']=='binds' and round(length-5,1)<2:add('binds-short','结合的两个对象太近，结合符号之间看不到连线',[r['id']],exposed_mm=round(max(0.0,length-5),2))
            # Any other connector: at least ~2 mm of line has to show behind its end symbol
            # (relation_visuals MIN_BODY; 0.1 mm of sampling slack). Only short ones are measured.
            if r['type']!='binds' and not r.get('callout') and length<14:
                body=connection_visible_body(g,r)
                if body<1.9:add('connector-body-short','两个对象太近，箭头后面几乎看不到连线',[r['id']],exposed_mm=round(body,2))
            ends=[objects[r['source']],objects[r['target']]]
            centres=[(e['x']+e['w']/2,e['y']+e['h']/2) for e in ends if all(k in e for k in ('x','y','w','h'))]
            allowed=set(r.get('route_through') or ())
            for o in visible:
                if o['type']=='text' or o['id'] in (r['source'],r['target']) or o['id'] in allowed:continue
                x0,y0,x1,y1=o['x'],o['y'],o['x']+o['w'],o['y']+o['h']
                if any(x0<=cx<=x1 and y0<=cy<=y1 for cx,cy in centres) or any(is_ancestor(o,e) for e in ends):continue
                if o['type']=='membrane' and any(min(x1,e['x']+e['w'])>max(x0,e['x']) and min(y1,e['y']+e['h'])>max(y0,e['y']) for e in ends if 'x' in e):continue
                if sum(x0+.4<px<x1-.4 and y0+.4<py<y1-.4 for px,py in pts)>=2:add('line-through-object','连线穿过其它对象，请改走旁边',[r['id'],o['id']])
            # A line running through one of its own end objects (it seems to leave from
            # the far side). Containers of the other end, anchors, rotated shapes,
            # membranes, text and callouts are left out.
            if not r.get('callout'):
                for e,far in ((ends[0],ends[1]),(ends[1],ends[0])):
                    if not all(k in q for q in (e,far) for k in ('x','y','w','h')):continue
                    if e.get('depiction')=='anchor' or e.get('rotation',0) or e['type'] in ('text','membrane'):continue
                    fx,fy=far['x']+far['w']/2,far['y']+far['h']/2
                    if (e['x']<=fx<=e['x']+e['w'] and e['y']<=fy<=e['y']+e['h']) or is_ancestor(e,far):continue
                    run=sum(math.hypot(q[0]-p[0],q[1]-p[1]) for p,q in zip(pts,pts[1:])
                            if e['x']+.4<(p[0]+q[0])/2<e['x']+e['w']-.4 and e['y']+.4<(p[1]+q[1])/2<e['y']+e['h']-.4)
                    if run>1.5:add('connector-through-end','连线从自己端点的对象里穿过，请改走另一侧',[r['id'],e['id']],inside_mm=round(run,2))
            cw_,ch_=scene['canvas']['width_mm'],scene['canvas']['height_mm']
            out=max([0.0]+[max(-px,-py,px-cw_,py-ch_) for px,py in pts])
            if out>.2:add('connector-outside-canvas','连线超出画布',[r['id']],outside_mm=round(out,2))
            # Arrow heads, bars and discs drawn over an object's label hide the text.
            covered=[]
            for sx0,sy0,sx1,sy1 in connection_symbol_boxes(g,r):
                for q in symbol_labels:
                    if q['id'] not in covered and min(sx1,q['x']+q['w'])-max(sx0,q['x'])>.1 and min(sy1,q['y']+q['h'])-max(sy0,q['y'])>.1:covered.append(q['id'])
            for qid in covered:add('connector-symbol-on-label','连线末端的箭头或符号压到了标签',[r['id'],qid])
        for i, a in enumerate(boxes):
            for b in boxes[i+1:]:
                if min(a["x"]+a["w"],b["x"]+b["w"])-max(a["x"],b["x"]) > 0.4 and min(a["y"]+a["h"],b["y"]+b["h"])-max(a["y"],b["y"]) > 0.4:
                    if a['id'] in objects and b['id'] in objects and original_overlap(objects[a['id']],objects[b['id']],'label-overlap'):continue
                    add("label-overlap", "两个标签重叠", [a["id"], b["id"]])
            for o in visible:
                if o["id"] == a["id"]:
                    continue
                if objects.get(a['id']) and is_ancestor(o,objects[a['id']]):continue
                overlap_w = min(a["x"]+a["w"],o["x"]+o["w"])-max(a["x"],o["x"])
                overlap_h = min(a["y"]+a["h"],o["y"]+o["h"])-max(a["y"],o["y"])
                if overlap_w > 0.6 and overlap_h > 0.6:
                    if a['id'] in objects and original_overlap(objects[a['id']],o,'label-object-overlap'):continue
                    add("label-object-overlap", "标签与另一个对象重叠", [a["id"],o["id"]])
    except ImportError:
        pass
    for item in scene["unresolved"]:
        add("author-review", item)
    return {"revision": scene["revision"], "audit_version": AUDIT_VERSION, "status": "needs_attention" if findings else "passed",
            "source_overlaps":source_overlaps,
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

    def commit(self, scene, base_revision=None, *, _current=None):
        import os
        import uuid
        from scene_render import render_scene, layout_scene
        with self.lock:
            head_path = self.root / "scene-head.json"
            current = _current if _current is not None else self.read() if head_path.exists() else None
            if current is not None and base_revision != current["revision"]:
                raise RevisionConflict("图版已被其他操作更新，请保留当前草稿并重新载入")
            if current is None and base_revision not in (None, 0):
                raise RevisionConflict("场景尚未创建")
            scene = layout_scene(scene)
            scene["revision"] = (current["revision"] + 1) if current else 1
            svg = render_scene(scene, _laid_out=True)
            audit = audit_scene(scene, _normalized=True)
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

    def patch(self, base_revision, operations, *, delta=False):
        with self.lock:
            current = self.read()
            if current["revision"] != base_revision:
                raise RevisionConflict("图版修订号已变化，当前修改没有覆盖已保存内容")
            result = self.commit(apply_operations(current, operations), base_revision, _current=current)
            if delta:
                changes = scene_delta(current, result['scene'])
                # The editor can render local text/geometry changes directly.
                # New glyph types and compartment/template changes need the
                # canonical SVG to avoid leaving a temporary placeholder visible.
                shell = set(changes['fields']) & {'canvas','style','compartments','layout','title'}
                glyph = any((set(item['changes']) | set(item['unset'])) & {'type','state','asset_id','illustration','text_appearance'}
                            for item in changes['objects']['updated'])
                native_added = any(o['type'] != 'text' and not o.get('asset_snapshot') and not o.get('illustration')
                                   for o in changes['objects']['added'])
                if not (shell or glyph or native_added):
                    result['scene_delta'] = changes
            return result


def scene_delta(before, after):
    """Canonical save acknowledgment; unchanged SVG strings stay on the client."""
    delta = {'fields': {k: v for k, v in after.items()
                        if k not in ('objects', 'relations') and before.get(k) != v}}
    for field in ('objects', 'relations'):
        old = {item['id']: item for item in before[field]}
        new = {item['id']: item for item in after[field]}
        updates = []
        for oid, item in new.items():
            if oid not in old:
                continue
            changes = {k: v for k, v in item.items() if k not in old[oid] or old[oid][k] != v}
            unset = [k for k in old[oid] if k not in item]
            if changes or unset:
                updates.append({'id': oid, 'changes': changes, 'unset': unset})
        delta[field] = {'added': [v for k, v in new.items() if k not in old],
                        'removed': [k for k in old if k not in new], 'updated': updates}
        if list(old) != list(new):
            delta[field]['order'] = list(new)
    return delta
