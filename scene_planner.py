"""Bounded semantic extraction and selected-object edit proposals."""
from __future__ import annotations

import copy
import json
import time

import pipeline
from scene_document import (
    OBJECT_TYPES, RELATION_TYPES, SceneError, apply_operations, empty_scene, normalize_scene,
)

PLANNER_INSTRUCTION = """你是科研插图的结构规划器，覆盖生命科学、材料、化学、工程等领域。只输出严格 JSON，不输出 SVG 或 Markdown。
以用户提供的描述为唯一科学内容来源，保留原有对象、关系、分支、抑制、状态和空间指示。
不要凭通路名称补齐教科书机制，不要引入数值、结构细节、工程/具身智能模板或未提供的因果关系。
证据不充分时写入 unresolved；关系类型不明确使用 associates 并 uncertain=true，不要假定激活。
实验步骤的先后使用 sequence，仅表示流程顺序；converts 用于实体转换，transports 用于空间转运。
所有对象和关系都要带 evidence：逐字摘录用户描述中支持该对象/关系的一小段，不能杜撰引文。
evidence 必须是 source_text 中连续出现的原文；输入英文时 evidence 也必须保留英文，禁止翻译或改写。输出前逐项检查 source_text.includes(evidence)。
同一实体的不同阶段实例使用不同 id 和相同 entity_id，分别记录 state 与 compartment。
对时间过程必须表现状态变化；对结构图保留构成/结合关系，不要强行转成步骤。
reference_summary 仅为布局和配色参考，其中的科学内容不得添加到本图。
generation_brief 是视觉表达与布局建议，科学内容仍以 source_text 为准；增强描述中的新机制不能自动成为事实。
每个对象可提供 visual_description，只描述这个对象应当可见的形态、组成、颜色和科学特征，必须有原文或可见参考依据。
不要把整图的主体数量、其它对象或全流程要求重复写入单个对象的 visual_description。
否定、排除和省略要求也是约束：“不激活”不等于“抑制”，不能把被否定的机制画成正向箭头。
参考用途 purpose=layout/style 时只借用布局或画风；purpose=sketch/content 时可使用图中实际可见的文字对象和连接，证据标记 evidence_source=reference_image。
draft_objects 中的文字和连接是作者输入，可作为依据，evidence_source=canvas_sketch，evidence_ref填写对象或连接id。
默认 evidence_source=user_text。不确定、无法辨认或资料不足时给出具体 unresolved，不要把整图降成“主题”和“过程”两个空洞框。
对象形态必须可辨识；可使用 supplied_assets 中的 asset_id，其科学含义必须与对象一致。没有匹配素材时使用最贴合的type/state，不能随便借用另一种器官或器件。
当提供 draft_objects 或 reference_objects 时：用户已在画布上手绘或放置了草稿。输出的对象必须优先复用草稿对象的 id 与顺序，并根据科研文本赋予准确科学类型(type)与生物学分期/状态(state)（例如有丝分裂分期：interphase, prophase, prometaphase, metaphase, anaphase, telophase, cytokinesis 等）。
layout_policy=regularize 时，草稿只表示大致构图、阅读顺序与拓扑；歪斜、比例和不等间距不是科学要求。根据内容为对象选择准确的形态与状态，由确定性排版器整理尺寸、对齐与间距。不要把不同阶段画成同一种状态，不增加草稿和文字未支持的关系。
JSON:
{"title":"简短图题","layout":"pathway|process|network|assembly",
 "compartments":[{"id":"extracellular","label":"Extracellular space","kind":"extracellular"},
 {"id":"membrane","label":"Plasma membrane","kind":"membrane"},
 {"id":"cytoplasm","label":"Cytoplasm","kind":"cytoplasm"},
 {"id":"nucleus","label":"Nucleus","kind":"nucleus"}],
 "objects":[{"id":"protein_a","entity_id":"protein_a","type":"protein","label":"A",
 "compartment":"cytoplasm","state":"","visual_description":"仅该对象有依据的可见形态与配色要求","evidence":"用户原文摘录"}],
 "relations":[{"id":"r1","source":"protein_a","target":"protein_b","type":"activates",
 "label":"","indirect":false,"uncertain":false,"evidence":"用户原文摘录"}],
 "unresolved":["需作者补充的信息"]}
只保留有用的区室；无细胞区室的网络、组织过程、结构域图和实验流程可以 compartments=[]。
不要输出坐标，布局由本地引擎决定。默认短英文标签；用户指定中文时保留中文。
可用对象类型：%s
可用关系类型：%s
""" % (", ".join(sorted(OBJECT_TYPES)), ", ".join(sorted(RELATION_TYPES)))


def _request(config, messages, *, max_tokens=6500):
    source = config.get("text") or {}
    if not source.get("base_url") or not source.get("model"):
        raise SceneError("请先配置文本模型，或打开一张内置可编辑样板")
    started = time.monotonic()
    request = {"model": source["model"], "messages": pipeline._fold_system(messages), "temperature": 0,
               "max_tokens": max_tokens}
    if "deepseek" in source["model"].lower():
        request["thinking"] = {"type": "disabled"}
    response = pipeline._post_json(
        pipeline._endpoint(source["base_url"], "/chat/completions"), pipeline._api_key(source),
        request, timeout=120,
    )
    message = response["choices"][0]["message"]
    content = message.get("content") or ""
    if not content:
        raise SceneError("文本模型没有返回完整场景；请重试或在设置中选择支持 JSON 的文本模型")
    return pipeline._json_object(content), round(time.monotonic() - started, 2)


def plan_scene(text, config, *, on_stage=None, cancelled=None):
    text = str(text).strip()
    if not text:
        raise SceneError("请先填写科研内容")
    width, height = config.get("canvas_mm") or (180, 120)
    from scientific_intent import mitosis_candidate,canonical_phase,intent_contract,phase_sketch,labeled_cell_phase,classical_mitosis_compatible,apply_division_context
    intent=intent_contract(text)
    candidate=phase_sketch(text,config)
    if candidate is not None:
        if on_stage:on_stage('plan_scene','按草稿标明的分期匹配科学形态，保留对象与连接')
        return candidate,{'method':'author-phase-sketch','model_duration_sec':0,'attempts':0}
    if not config.get('reference_id') and not config.get('sketch_scene'):
        candidate = mitosis_candidate(text,width,height)
        if candidate is not None:
            if on_stage:on_stage('plan_scene','创建经典分期候选，并标明补充依据与待确认内容')
            return candidate, {'method':'scientific-knowledge-candidate','model_duration_sec':0,'attempts':0}
    base = empty_scene(source_text=text, width_mm=width, height_mm=height)
    reference = config.get("style_dna") or {}
    summary = str(reference.get("reference_summary") or reference.get("visual_style_summary") or "")[:1000]
    context = {"source_text": text, "reference_summary": summary,
               "reference_layout": reference.get("layout_analysis") or {},
               "final_dimensions_mm": [width, height],
               "generation_brief":str(config.get('generation_brief') or text)[:8000],
               "reference_purpose":config.get('reference_purpose','layout'),
               "layout_policy":config.get('layout_policy','preserve')}
    try:
        from scientific_library import library
        import re
        tokens={word.lower() for word in re.findall(r'[A-Za-z][A-Za-z0-9-]{2,}|[\u4e00-\u9fff]{2,}',text)}
        candidates=[]
        for asset in library().values():
            description=' '.join(str(asset.get(k,'')) for k in ('asset_id','label','name','category','tags')).lower()
            rank=sum(len(token) for token in tokens if token in description)
            if rank:candidates.append((rank,asset))
        context['supplied_assets']=[{k:a.get(k,'') for k in ('asset_id','label','category','domain')}
                                   for rank,a in sorted(candidates,key=lambda pair:pair[0],reverse=True)[:30]]
    except (ImportError,FileNotFoundError):
        context['supplied_assets']=[]
    sketch = config.get("sketch_scene")
    ref_contract = config.get("reference_contract") or {}
    if sketch and sketch.get("objects"):
        context["draft_objects"] = [{"id": o["id"], "label": o.get("label", ""), "type": o.get("type", "process")}
                                     for o in sketch["objects"]]
        context["draft_relations"] = [{"source": r["source"], "target": r["target"], "type": r.get("type", "sequence")}
                                       for r in sketch.get("relations", [])]
        context["draft_instruction"] = "用户在画布上手绘/摆放了草稿结构（draft_objects与draft_relations）。输出的对象必须优先对应复用草稿中的id，并根据科研文本赋予准确科学type与state！"
    elif ref_contract and ref_contract.get("objects"):
        use_content=config.get('reference_purpose') in ('sketch','content')
        context["reference_objects"] = [{"id": o["id"], "label": o.get("label", "") if use_content else "", "type": o.get("type", "process") if use_content else 'process',
                                         **{k:o[k] for k in ('x','y','w','h') if k in o}}
                                         for o in ref_contract["objects"]]
        context["reference_reading_order"] = ref_contract.get("reading_order", "")
        if use_content:context['reference_relations']=ref_contract.get('relations') or []
    content=json.dumps(context, ensure_ascii=False)
    if config.get('reference_image_data_url'):
        content=[{'type':'text','text':content},{'type':'image_url','image_url':{'url':config['reference_image_data_url']}}]
    messages = [{"role": "system", "content": PLANNER_INSTRUCTION},
                {"role": "user", "content": content}]
    request_config=config
    if config.get('reference_image_data_url') and (config.get('vision') or {}).get('base_url') and (config.get('vision') or {}).get('model'):
        request_config={**config,'text':config['vision']}
    error = None
    for attempt in range(2):
        if cancelled and cancelled():
            raise InterruptedError("任务已取消")
        if on_stage:
            on_stage("plan_scene", "提取对象、关系和区室" if not attempt else "校正场景格式")
        try:
            spec, duration = _request(request_config, messages)
            base=empty_scene(source_text=text,width_mm=width,height_mm=height)
            for key in ("title", "layout", "compartments", "objects", "relations", "unresolved"):
                if key in spec:
                    base[key] = spec[key]
            if not base["objects"]:
                raise SceneError("描述中未提取到可绘制对象，请补充需要展示的分子、细胞或步骤")
            # A model cannot assign its own geometry or lower the font floor.
            missing_evidence=[]
            for obj in base["objects"]:
                for key in ("x", "y", "w", "h", "rotation", "font_size_pt", "fill", "stroke"):
                    obj.pop(key, None)
                evidence = str(obj.get("evidence") or "").strip()
                external_evidence=(obj.get('evidence_source')=='canvas_sketch' and bool(sketch)) or (obj.get('evidence_source')=='reference_image' and bool(config.get('reference_id')) and config.get('reference_purpose') in ('sketch','content'))
                if not evidence or (evidence not in text and not external_evidence):
                    missing_evidence.append(obj.get('id'))
                    base["unresolved"].append(f"对象 {obj.get('label') or obj.get('id')} 缺少可定位的原文依据，请确认")
                if classical_mitosis_compatible(text) and (obj.get('type')=='cell' or (obj.get('type')=='process' and intent['domain']=='biology')):
                    phase=canonical_phase(obj.get('state','')) or labeled_cell_phase(obj.get('label',''),biological_context=True)
                    if phase:
                        obj.update(type='cell',state=phase)
                        obj.pop('asset_id',None)
            for relation in base["relations"]:
                evidence = str(relation.get("evidence") or "").strip()
                external_evidence=(relation.get('evidence_source')=='canvas_sketch' and bool(sketch)) or (relation.get('evidence_source')=='reference_image' and bool(config.get('reference_id')) and config.get('reference_purpose') in ('sketch','content'))
                if not evidence or (evidence not in text and not external_evidence):
                    missing_evidence.append(relation.get('id'))
                    relation["uncertain"] = True
                    base["unresolved"].append(f"关系 {relation.get('id')} 缺少原文依据，请确认")
            if not attempt and len(missing_evidence)>max(1,(len(base['objects'])+len(base['relations']))/3):
                raise SceneError('多数 evidence 不是 source_text 中逐字摘录的连续原文。英文描述请引用英文片段，不要翻译成中文。请重新提取。')
            from scientific_intent import excluded_object_evidence,contradicted_relation_evidence
            names={o.get('id'):o.get('label','') for o in base['objects']}
            for obj in base['objects']:
                denied=excluded_object_evidence(text,obj.get('label',''))
                if denied:raise SceneError('规划包含被原文明确排除的对象：'+denied)
            for relation in base['relations']:
                denied=contradicted_relation_evidence(text,names.get(relation.get('source'),''),names.get(relation.get('target'),''),relation.get('type'))
                if denied:raise SceneError('规划关系违反原文否定要求：'+denied)
            if not base["relations"] and len(base["objects"]) > 1:
                base["unresolved"].append("尚未说明对象间关系；当前保留对象，请补充连接及方向")
            base["requirements"] = {"objects": [o["id"] for o in base["objects"]],
                                    "relations": [r["id"] for r in base["relations"]]}
            base["provenance"] = {"method": "model-semantic-extraction", "model": request_config["text"]["model"],
                                  "reference_summary": summary}
            if reference.get("palette"):
                for key in base["style"]["palette"]:
                    if key in reference["palette"]:
                        base["style"]["palette"][key] = reference["palette"][key]
            apply_division_context(base,text)
            base = normalize_scene(base)
            if cancelled and cancelled():
                raise InterruptedError("任务已取消")
            from scene_render import layout_scene, repair_geometry
            if on_stage:
                on_stage("assemble", "按区室和关系装配矢量对象")
            return repair_geometry(layout_scene(base),passes=2), {"model_duration_sec": duration, "attempts": attempt + 1}
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            error = exc
            if not attempt:
                messages.append({"role": "user", "content": "上一份结构无法使用，请重新提取，严格遵守 JSON 格式。错误：" + str(exc)[:500]})
                continue
            raise SceneError(f"模型返回的场景格式无效：{exc}") from exc
    raise SceneError(str(error))


def scene_for_model(scene):
    """Binary artwork is an image resource, never megabytes of text tokens."""
    result=copy.deepcopy(scene)
    for obj in result['objects']:
        illustration=obj.pop('illustration',None)
        snapshot=obj.pop('asset_snapshot',None)
        if illustration:obj['artwork']={'kind':'raster','sha256':illustration['sha256'],'editing':'整体重绘使用专门重绘功能，内部像素不能由对象补丁修改'}
        elif snapshot:obj['artwork']={'kind':'vector-asset','asset_id':obj.get('asset_id','')}
    return result


def propose_revision(scene, instruction, target_ids, config):
    scene = normalize_scene(scene)
    objects = {o["id"]: o for o in scene["objects"]}
    relations = {r["id"]: r for r in scene["relations"]}
    if not isinstance(instruction,str) or not instruction.strip() or len(instruction)>2000:
        raise SceneError('请填写 1–2000 字的修改要求')
    if not isinstance(target_ids,list) or len(target_ids)>1000 or any(not isinstance(x,str) for x in target_ids):
        raise SceneError('请选择有效的对象列表')
    target_ids = list(dict.fromkeys(target_ids or []))
    if not target_ids:
        raise SceneError("请先选择要修改的对象；全图修改请先全选")
    if any(oid not in objects and oid not in relations for oid in target_ids):
        raise SceneError("选中对象已不存在，请重新选择")
    if any(objects[oid]['locked'] or not objects[oid]['visible'] for oid in target_ids if oid in objects):
        raise SceneError('选中对象已锁定或隐藏，请解锁或显示后再修改')
    allowed = set(target_ids)
    # Connected edges may be rerouted, but adjacent unselected objects remain fixed.
    allowed.update(r["id"] for r in relations.values() if (r['source'] in target_ids or r['target'] in target_ids)
                   and not objects[r['source']]['locked'] and not objects[r['target']]['locked'])
    if any(oid in relations and (objects[relations[oid]['source']]['locked'] or objects[relations[oid]['target']]['locked']) for oid in target_ids):
        raise SceneError('不能修改连接到锁定对象的连线')
    system = (
        "你是科研矢量图的局部编辑器，只输出 JSON。只修改用户选中的对象或与其直接连接的线，保留其他对象。"
        "不要删除对象、改变ID、增加未经要求的机制或重排整图。文字不小于7pt。"
        "返回 {\"operations\":[{\"op\":\"update\",\"id\":\"对象ID\",\"changes\":{...}}],\"summary\":[\"修改说明\"]}。"
        "连接使用op=update_relation。坐标单位mm，字号pt。无法理解的要求返回operations=[]并在summary解释。"
    )
    data, _ = _request(config, [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(
        {"instruction": instruction, "target_ids": target_ids, "allowed_ids": sorted(allowed), "scene": scene_for_model(scene)}, ensure_ascii=False)}], max_tokens=4200)
    operations = data.get("operations")
    if not isinstance(operations, list):
        raise SceneError("模型没有返回有效的局部修改")
    if operations:
        # Reject out-of-selection mutations before ever presenting a candidate.
        preview_scene = apply_operations(scene, operations, allowed_ids=allowed)
    else:
        preview_scene = scene
    summary = data.get("summary") or ["模型未提供修改说明"]
    if isinstance(summary, str):
        summary = [summary]
    from scene_render import render_scene
    return {"base_revision": scene["revision"], "operations": operations,
            "preview_svg": render_scene(preview_scene),
            "target_ids": target_ids, "summary": [str(x)[:500] for x in summary[:30]]}


def review_scene_visual(scene, config):
    """Optional VLM advice, preserved verbatim and never used as a save gate."""
    from scene_render import render_scene
    from scene_export import export_scene
    import base64
    import tempfile
    from pathlib import Path
    source = config.get("vision") or {}
    if not source.get("base_url") or not source.get("model"):
        return {"status": "unavailable", "findings": [], "error": "未配置视觉模型"}
    try:
        with tempfile.TemporaryDirectory(prefix="cell-scene-review-") as folder:
            path = Path(folder) / "preview.png"
            export_scene(scene, "png", path, dpi=120, config=config)
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        payload = {"model": source["model"], "temperature": 0, "max_tokens": 2800,
                   "messages": [{"role": "user", "content": [
                       {"type": "text", "text": "审阅此科研示意图。原始描述：" + scene["source_text"] +
                        "\n只提供有图像依据的语义和美观建议，不给总分、不宣布通过。引用相关对象ID。"
                        "首先核对原始需求是否被满足；不能只对照生成器自己的规格。不同科学状态必须有对应形态。"
                        "禁止把时间循环当作控制系统；指出无来源的新增机制或遗漏的阶段。\n独立需求基线：" +
                        json.dumps(scene.get('generation_contract') or {},ensure_ascii=False) +
                        "返回JSON {findings:[{message,object_ids:[],category,evidence}]}。对象清单：" +
                        json.dumps([{k:o.get(k) for k in ("id","label","type","state","evidence_source")} for o in scene["objects"]], ensure_ascii=False)},
                       {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}}]}]}
        if config.get('reference_image_data_url'):
            payload['messages'][0]['content'].extend([
                {'type':'text','text':'下面是作者的原始参考图/草稿。按其用途核对布局或形态，不将参考图中的额外机制添加到作者要求。用途：'+str(config.get('reference_purpose','layout'))},
                {'type':'image_url','image_url':{'url':config['reference_image_data_url']}}])
        response = pipeline._post_json(pipeline._endpoint(source["base_url"], "/chat/completions"),
                                       pipeline._api_key(source), payload, timeout=60)
        raw = response["choices"][0]["message"]["content"]
        result = pipeline._json_object(raw)
        ids = {o["id"] for o in scene["objects"]} | {r["id"] for r in scene["relations"]}
        findings = []
        for item in (result.get("findings") or [])[:30]:
            if not isinstance(item, dict):
                continue
            findings.append({"message": str(item.get("message", ""))[:1000],
                             "object_ids": [x for x in item.get("object_ids", []) if x in ids],
                             "category": str(item.get("category", "advice"))[:50],
                             "evidence": str(item.get("evidence", ""))[:1000],
                             "source": "vision", "status": "unverified", "revision": scene["revision"]})
        return {"status": "completed", "findings": findings, "model": source["model"], "raw": str(raw)[:15000]}
    except Exception as exc:
        return {"status": "unavailable", "findings": [], "error": str(exc)[:500]}
