"""Scene-v2 API adapter. Legacy jobs continue through app_server unchanged."""
from __future__ import annotations

import copy
import json
import re
import threading
import time
import uuid
from pathlib import Path

from scene_document import SceneError, RevisionConflict, SceneRepository, audit_scene

_REPOSITORIES = {}
_REPOSITORIES_LOCK = threading.Lock()
_QUEUES = None
_QUEUES_LOCK = threading.Lock()


def queues():
    global _QUEUES
    with _QUEUES_LOCK:
        if _QUEUES is None:
            from studio_storage import WorkQueues
            _QUEUES = WorkQueues()
    return _QUEUES


def repository(app, job_id):
    folder = app.job_paths(job_id).resolve()
    with _REPOSITORIES_LOCK:
        return _REPOSITORIES.setdefault(str(folder), SceneRepository(folder))


def _is_scene(job):
    return job.get("scene_engine") == "v2"


def _revision(body, key="base_revision"):
    value = body.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise SceneError("请提供有效的场景修订号")
    return value


def _finding_fingerprint(scene, finding):
    import hashlib
    ids=set(finding.get('object_ids',[]))
    fields=('id','x','y','w','h','rotation','visible','label','label_dx','label_dy','font_size_pt','group_id')
    snapshot=[{k:o.get(k) for k in fields} for o in scene['objects'] if o['id'] in ids]
    return hashlib.sha256(json.dumps([finding['code'],finding['object_ids'],snapshot,scene['canvas']],sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def _apply_layout_decisions(scene, audit, job):
    decisions=job.get('layout_decisions',{})
    for f in audit['findings']:
        decision=decisions.get(_finding_fingerprint(scene,f))
        if decision:f.update(status='acknowledged',resolution=decision['reason'])
    return audit


def payload(app, job, revision=None):
    repo = repository(app, job["id"])
    with repo.lock:
        scene = repo.read(revision)
        folder = repo.root / "revisions" / str(scene["revision"])
        result = {"ok": True, "scene": scene, "revision": scene["revision"],
                  "svg": (folder / "result.svg").read_text(encoding="utf-8"),
                  "audit": json.loads((folder / "audit.json").read_text(encoding="utf-8"))}
        result["audit"]["author_confirmed"] = job.get("author_confirmed_revision") == scene["revision"]
        _apply_layout_decisions(scene,result['audit'],job)
        visual = job.get("scene_vision") or {}
        if visual.get("revision") == scene["revision"]:
            result["audit"]["vision"] = visual
        return result


def _publish(app, job, result):
    scene = result["scene"]
    _apply_layout_decisions(scene,result['audit'],job)
    folder = repository(app, job["id"]).root / "revisions" / str(scene["revision"])
    job.update({"scene_revision": scene["revision"], "title": scene["title"],
                "canvas_mm": [scene["canvas"]["width_mm"], scene["canvas"]["height_mm"]],
                "canvas": [round(scene["canvas"]["width_mm"] / 25.4 * 96),
                           round(scene["canvas"]["height_mm"] / 25.4 * 96)],
                "svg_path": str(folder / "result.svg"), "deliverable_svg": str(folder / "result.svg"),
                "scene_path": str(folder / "scene.json"),
                "report": {"mode": "scene-v2", "scene_version": 2, "title": scene["title"],
                           "spec": {"title": scene["title"]}, "scene_audit": result["audit"]},
                "visual_state": "failed" if result["audit"]["errors"] else "unverified",
                "visual_findings": [{"kind": "scene-"+f["code"],
                                     "severity": "high" if f["severity"] == "error" else "low",
                                     "message": f["message"], "object_ids": f["object_ids"],
                                     "evidence": f["evidence"]} for f in result["audit"]["findings"]],
                "review_version": app.REVIEW_VERSION,
                "export_audit": {"svg": {"ok": True, "revision": scene["revision"],
                                          "images": sum(bool(o.get('illustration')) for o in scene['objects'])}},
                "font": scene["style"]["font_family"], "viewport_shape": "rect"})
    # Caches never survive a scene change. Old revision exports remain on disk.
    job.pop("ppt", None)
    job.pop("ppt_export", None)
    job.pop("preview_png", None)
    job.pop("author_confirmed_revision", None)
    app._save_meta(job)


def create_job(app, text, config, *, example=None, revision_of=None, request_id=None):
    config = dict(config)
    config.setdefault('original_text', text)
    config.setdefault('generation_brief', text)
    config.setdefault('canvas_mm', [180,120])
    if example:
        config['illustration_mode'] = 'vector'
    if request_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,96}",str(request_id)):
        raise SceneError("重复提交标识无效")
    job = {"id": "j_" + uuid.uuid4().hex[:12], "title": text[:100] or "未命名图版",
            "text": config.get('generation_brief') or text, "original_text": text, "mode": "scene", "scene_engine": "v2",
           "status": "queued", "progress": 0, "created": time.time(), "message": "等待生成",
            "illustration_mode": config.get('illustration_mode','vector'), "canvas_mm": list(config.get("canvas_mm") or [180,120]),
            "reference_id": config.get('reference_id'), "draft_source_id": config.get('draft_source_id'),
            "generation_brief": config.get('generation_brief') or text,
           "stages": [{"name": n, "label": label, "state": "pending", "detail": None}
                      for n,label in (("start","准备"),("plan_scene","科学内容提取"),
                                       ("assemble","对象布局"),("generate","对象绘制"),("qa","需求核对"))],
           "error": None, "report": None, "svg_path": None, "revision_of": revision_of, "request_id":request_id,
           "literature_enabled": False, "dpi": config.get("dpi", 300)}
    with app.JOBS_LOCK:
        if request_id:
            prior=next((j for j in app.JOBS.values() if j.get('request_id')==request_id),None)
            if prior:
                from figure_generation import fingerprint
                if prior.get('original_text')!=text or (prior.get('generation_fingerprint') and prior['generation_fingerprint']!=fingerprint(config)):
                    raise RevisionConflict("相同提交标识不能用于不同内容")
                return prior
        from figure_generation import fingerprint
        job['generation_fingerprint'] = fingerprint(config)
        app.JOBS[job["id"]] = job
    app._save_meta(job)

    def worker():
        started = time.monotonic()
        try:
            if job.get("cancel_requested"):
                raise InterruptedError("任务已取消")
            job["status"] = "processing"
            app._set_stage(job, "start", "创建可编辑场景")
            if example:
                from scene_examples import make_example
                width, height = config.get("canvas_mm") or [180,120]
                scene = make_example(example, width_mm=width, height_mm=height)
                if config.get('composition_template'):
                    from scene_templates import apply_template, enrich_artwork
                    enrich_artwork(scene,example)
                    scene=apply_template(scene,config['composition_template'],config.get('colorway'))
                job["text"] = job["original_text"] = scene["source_text"]
                meta = {"method": "example"}
            else:
                from figure_generation import plan
                scene, meta = plan(text, config, on_stage=lambda n,d: app._set_stage(job,n,d),
                                         cancelled=lambda: bool(job.get("cancel_requested")))
            scene["id"] = job["id"]
            if job.get("cancel_requested"):
                raise InterruptedError("任务已取消")
            app._set_stage(job, "assemble", "保存可编辑矢量草稿")
            result = repository(app, job["id"]).commit(scene)
            _publish(app, job, result)
            if not example and config.get('illustration_mode') == 'image':
                from figure_assets import illustrate
                def checkpoint(current):
                    saved = repository(app, job['id']).commit(current, base_revision=job['scene_revision'])
                    _publish(app, job, saved)
                scene, job['illustration_result'] = illustrate(scene,config,
                    on_stage=lambda n,d: app._set_stage(job,n,d),
                    cancelled=lambda: bool(job.get('cancel_requested')), checkpoint=checkpoint)
                # Include failures/partial status in the saved draft, too.
                checkpoint(scene)
            app._set_stage(job, "qa", "核对原始需求、对象、连接与物理尺寸")
            if not example and (config.get('vision') or {}).get('base_url') and (config.get('vision') or {}).get('model'):
                from scene_planner import review_scene_visual
                review_snapshot=repository(app,job['id']).read()
                job['scene_vision']={**review_scene_visual(review_snapshot,config),'revision':review_snapshot['revision']}
                if job.get('cancel_requested'):raise InterruptedError('任务已取消；已有草稿保留')
            job["planner"] = meta
            job["status"] = "completed"
            job["message"] = "初稿已生成，可直接编辑；科学内容待作者核对"
            job["duration"] = round(time.monotonic()-started,2)
            for stage in job["stages"]:
                stage["state"] = "done"
            app._save_meta(job)
        except InterruptedError:
            job.update(status="cancelled", message="已取消；已有内容保留", duration=round(time.monotonic()-started,2))
            app._save_meta(job)
        except Exception as exc:
            job.update(status="failed", error=app._friendly_error(exc), message="生成未完成，历史版本保持可用",
                       duration=round(time.monotonic()-started,2))
            app._save_meta(job)
    queues().submit_generation(worker)
    return job


def _export(app, job, body):
    from scene_export import export_scene
    revision = body.get("revision")
    if revision is not None:
        revision = _revision(body, "revision")
    scene = repository(app, job["id"]).read(revision)
    fmt = str(body.get("format", "svg")).lower()
    fmt = "pptx" if fmt == "ppt" else fmt
    if fmt not in ("svg", "png", "pdf", "pptx"):
        raise SceneError("不支持的导出格式")
    dpi = int(body.get("dpi") or 300)
    if dpi not in (120, 150, 300, 600):
        raise SceneError("导出 DPI 请选择 300 或 600")
    default = app.EXPORT_DIR / job["id"] / f"r{scene['revision']}" / app._safe_filename(scene["title"] or "Figure", fmt)
    requested = str(body.get("path") or "").strip()
    destination = Path(requested).resolve() if requested else default
    # Pin before queueing: an edit while export is running cannot change content.
    result = queues().submit_export(export_scene, copy.deepcopy(scene), fmt, destination,
                                    dpi=dpi, config=app.load_config()).result(timeout=300)
    app.SAVED_PATHS.add(str(destination.resolve()))
    record = {"format": fmt, "revision": scene["revision"], "path": str(destination), "created": time.time()}
    job.setdefault("scene_exports", []).append(record)
    if len(job["scene_exports"]) > 100:
        job["scene_exports"] = job["scene_exports"][-100:]
    app._save_meta(job)
    return {"ok": True, **result, "path": str(destination), "folder": str(destination.parent),
            "revision": scene["revision"]}


def _repair(app, job):
    from scene_render import repair_geometry
    repo=repository(app,job["id"])
    with repo.lock:
        original=repo.read()
        scene=repair_geometry(original,passes=2)
        if scene==original:
            return {**payload(app,job),"changed":False,"message":"没有可安全自动修复的几何问题；科学内容请人工确认"}
        result=repo.commit(scene,original["revision"])
        _publish(app,job,result)
        return {"ok":True,**result,"changed":True}


def dispatch(handler, method, path, app):
    """Return True only when the request belongs to the scene-v2 adapter."""
    import desktop_delivery
    if desktop_delivery.dispatch(handler,method,path,app):return True
    import annotation_service
    import document_workflows
    if document_workflows.dispatch(handler,method,path,app):return True
    if annotation_service.dispatch(handler,method,path,app):return True
    try:
        if method == 'POST' and path == '/api/references':
            import figure_references
            body = handler._body()
            result = figure_references.create(app.DATA_DIR, body.get('image'), app.load_config(),
                purpose=str(body.get('purpose') or 'layout'))
            handler._json(200,result)
            return True
        reference_match = re.fullmatch(r'/api/references/(ref_[a-f0-9]{24})/preview.png', path)
        if method == 'GET' and reference_match:
            import figure_references
            handler._send(200, figure_references.preview(app.DATA_DIR,reference_match.group(1)), 'image/png')
            return True
        reference_meta = re.fullmatch(r'/api/references/(ref_[a-f0-9]{24})', path)
        if method == 'GET' and reference_meta:
            import figure_references
            handler._json(200,{'ok':True,**figure_references.read(app.DATA_DIR,reference_meta.group(1)),
                              'preview_url':f'/api/references/{reference_meta.group(1)}/preview.png'})
            return True
        if method == 'POST' and path == '/api/generation/preview':
            import figure_generation
            text,config = figure_generation.prepare(app,handler._body())
            result = queues().submit_generation(figure_generation.preview,app,text,config).result(timeout=260)
            handler._json(200,result)
            return True
        if method == "GET" and path == "/api/scene/catalog":
            from resource_packs import configure,DOMAIN_TITLES
            configure(app.DATA_DIR)
            from scene_assets import asset_catalog, ASSET_DOMAINS
            from scene_examples import EXAMPLES
            assets = []
            for item in asset_catalog():
                if "items" in item:
                    assets.extend({"category":item.get("name",item.get("id","")),**a} for a in item["items"])
                else:
                    assets.append(item)
            from scene_document import OBJECT_TYPES
            assets = [a for a in assets if a.get("type") in OBJECT_TYPES]
            for a in assets:
                a.pop('_file',None)
                a.setdefault('thumbnail','/ui/library/native_'+a['type']+'.svg')
                a.setdefault('license','原创图元')
            from scene_templates import TEMPLATES, COLORWAYS
            ref_path=Path(__file__).resolve().parent/'assets/reference-links.json'
            references=json.loads(ref_path.read_text(encoding='utf8')) if ref_path.exists() else []
            manifest_path=Path(__file__).resolve().parent/'ui/library/manifest.json'
            manifest=json.loads(manifest_path.read_text(encoding='utf8')) if manifest_path.exists() else {}
            from resource_packs import configure,DOMAIN_TITLES
            packs=configure(app.DATA_DIR)
            handler._json(200,{"ok":True,"assets":assets,"examples":EXAMPLES,
                "templates":[{**t,**manifest.get(t['id'],{}),'thumbnail':'/ui/library/'+t['id']+'.svg',
                    'thumbnail_single':'/ui/library/'+t['id']+'-single.svg'} for t in TEMPLATES]+[{k:v for k,v in t.items() if not k.startswith('_')} for t in packs.templates()],
                "colorways":COLORWAYS,"references":references,
                "asset_domains":[{'id':pid,'title':title,'count':sum(a.get('domain')==pid for a in assets),
                    'available':pid=='biology' or any(a.get('domain')==pid for a in assets)} for pid,title in DOMAIN_TITLES.items()]})
            return True
        if method == "POST" and path == "/api/scene/preview-template":
            from scene_templates import apply_template
            from scene_render import render_scene
            body=handler._body()
            job=app.JOBS.get(str(body.get('job_id')))
            if not job or not _is_scene(job):raise SceneError('请先打开可编辑图版')
            scene=repository(app,job['id']).read()
            if _revision(body)!=scene['revision']:raise RevisionConflict('图版已变化，请重新预览')
            candidate=apply_template(scene,str(body.get('template')),body.get('colorway'))
            handler._json(200,{'ok':True,'scene':candidate,'svg':render_scene(candidate),'base_revision':scene['revision'],'audit':audit_scene(candidate)})
            return True
        if method == "POST" and path == "/api/scene/blank":
            from scene_document import empty_scene
            body = handler._body()
            scene = empty_scene(title="未命名图版")
            scene["layout"] = "network"
            scene["id"] = "j_"+uuid.uuid4().hex[:12]
            job = {"id":scene["id"],"title":scene["title"],"text":"","original_text":"",
                   "mode":"scene","scene_engine":"v2","status":"completed","progress":100,
                   "created":time.time(),"illustration_mode":"vector","stages":[],"duration":0}
            result = repository(app,job["id"]).commit(scene)
            _publish(app,job,result)
            with app.JOBS_LOCK:
                app.JOBS[job["id"]] = job
            handler._json(200,{"ok":True,"job_id":job["id"]})
            return True
        if method == "POST" and path == "/api/scene/example":
            from scene_examples import EXAMPLES
            body = handler._body()
            if body.get('template'):
                from resource_packs import manager
                size=body.get('canvas_mm') or [None,None]
                if not isinstance(size,list) or len(size)!=2:raise SceneError('画布尺寸无效')
                packed=manager().template_scene(str(body['template']),*size)
                if packed:
                    from document_workflows import _create
                    handler._json(200,_create(app,packed));return True
            example = str(body.get("example") or "egfr")
            if body.get('template'):
                from scene_templates import template_info
                example=template_info(str(body['template']))['example']
            item = next((x for x in EXAMPLES if x["id"]==example),None)
            if item is None:
                raise SceneError("未知样板")
            config = app.load_config()
            config["canvas_mm"] = body.get("canvas_mm") or (template_info(str(body['template']))['canvas_mm'] if body.get('template') else [180,120])
            config['composition_template']=body.get('template')
            config['colorway']=body.get('colorway')
            job = create_job(app,item["title"],config,example=example)
            handler._json(200,{"ok":True,"job_id":job["id"]})
            return True
        if method == "POST" and path == "/api/generate":
            body = handler._body()
            import figure_generation
            text, config = figure_generation.prepare(app,body)
            job = create_job(app,text,config,request_id=body.get('request_id'))
            handler._json(200,{"ok":True,"job_id":job["id"]})
            return True
        match = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/(scene|editable-copy|redraw|revise|auto-fix|preview-fix|layout-decision|recheck|review-finding|confirm|ppt|ppt-status|save-as|download|pdf|retry|cancel)",path)
        if not match:
            return False
        job_id, action = match.groups()
        job = app.JOBS.get(job_id)
        if not job:
            handler._json(404,{"ok":False,"error":"任务不存在"})
            return True
        if action == "editable-copy" and method == "POST":
            if _is_scene(job):
                source = repository(app,job_id).read()
                clone = copy.deepcopy(source)
                clone["id"] = "j_"+uuid.uuid4().hex[:12]
                clone["revision"] = 1
                copied = copy.deepcopy(job)
                copied.update(id=clone["id"],created=time.time(),revision_of=job_id,scene_exports=[])
                result = repository(app,copied["id"]).commit(clone)
                _publish(app,copied,result)
                with app.JOBS_LOCK:
                    app.JOBS[copied["id"]] = copied
                handler._json(200,{"ok":True,"job_id":copied["id"]})
            else:
                text = job.get("original_text") or job.get("text")
                if not text:
                    raise SceneError("旧任务没有原始描述，无法重建")
                config = app.load_config()
                config["canvas_mm"] = job.get("canvas_mm") or [180,120]
                child = create_job(app,text,config,revision_of=job_id)
                handler._json(200,{"ok":True,"job_id":child["id"],"message":"根据原始描述重建；旧图保持原样"})
            return True
        if not _is_scene(job):
            if action == "scene":
                handler._json(409,{"ok":False,"legacy":True,"error":"旧图没有对象场景，可创建新版可编辑副本"})
                return True
            return False
        body = handler._body() if method in ("POST","PATCH") else {}
        if action == "cancel" and method == "POST":
            if job.get("status") in ("queued","processing"):
                job["cancel_requested"] = True
                job["message"] = "正在取消；当前模型请求结束后停止，结果不会覆盖已有版本"
                app._save_meta(job)
            handler._json(200,{"ok":True,"cancel_requested":True})
            return True
        if action == "retry" and method == "POST":
            config = app.load_config()
            config["canvas_mm"] = job.get("canvas_mm") or [180,120]
            child = create_job(app,job.get("original_text") or job.get("text"),config,revision_of=job_id)
            handler._json(200,{"ok":True,"job_id":child["id"]})
            return True
        if not job.get("scene_revision"):
            handler._json(409,{"ok":False,"error":"场景尚未生成完成"})
            return True
        if action == "scene":
            if method == "GET":
                handler._json(200,payload(app,job))
            elif method == "PATCH":
                repo=repository(app,job_id)
                with repo.lock:
                    result = repo.patch(_revision(body),body.get("operations"))
                    _publish(app,job,result)
                handler._json(200,{"ok":True,**result})
            else:
                handler._json(405,{"ok":False,"error":"method not allowed"})
            return True
        if action == 'layout-decision' and method == 'POST':
            repo=repository(app,job_id)
            with repo.lock:
                scene=repo.read()
                if _revision(body)!=scene['revision']:raise RevisionConflict('图版已变化，请先查看最新建议')
                finding=next((f for f in audit_scene(scene)['findings'] if f['code']==body.get('code') and f['object_ids']==body.get('object_ids')),None)
                if finding is None or finding['severity']!='warning' or finding['code'] not in ('overlap','label-overlap','label-object-overlap','empty-label'):raise SceneError('此项需要实际调整或核对科学内容，不能作为排版选择忽略')
                decisions=job.setdefault('layout_decisions',{});fingerprint=_finding_fingerprint(scene,finding)
                if body.get('restore'):decisions.pop(fingerprint,None)
                else:decisions[fingerprint]={'reason':'作者确认保留当前排版','created':time.time(),'revision':scene['revision']}
                app._save_meta(job)
                handler._json(200,payload(app,job))
            return True
        if action == 'preview-fix' and method == 'POST':
            from scene_render import preview_finding_fix, render_scene
            scene=repository(app,job_id).read()
            if _revision(body)!=scene['revision']:raise RevisionConflict('图版已变化，请重新查看建议')
            finding=next((f for f in audit_scene(scene)['findings'] if f['code']==body.get('code') and f['object_ids']==body.get('object_ids')),None)
            if finding is None:raise SceneError('此建议已经不存在，请刷新检查结果')
            result=preview_finding_fix(scene,finding)
            handler._json(200,{'ok':True,**result,'svg':render_scene(result['scene']),'base_revision':scene['revision']})
            return True
        if action == "revise" and method == "POST":
            from scene_planner import propose_revision
            scene = repository(app,job_id).read()
            revision = _revision(body)
            if revision != scene["revision"]:
                raise RevisionConflict("请保存最新修改后再请求 AI 局部修改")
            instruction = str(body.get("instruction") or "").strip()
            if not instruction:
                raise SceneError("请填写修改要求")
            candidate = queues().submit_generation(propose_revision,copy.deepcopy(scene),instruction,
                                                   body.get("target_ids"),app.load_config()).result(timeout=260)
            if repository(app,job_id).read()["revision"] != revision:
                raise RevisionConflict("AI 生成候选时图版已更新，请基于最新图版重试")
            handler._json(200,{"ok":True,"candidate":candidate})
            return True
        if action=='redraw' and method=='POST':
            from figure_generation import prepare
            current=repository(app,job_id).read()
            if _revision(body)!=current['revision']:raise RevisionConflict('图版已变化，请保存后重绘')
            target_ids=body.get('target_ids') or []
            allowed={o['id'] for o in current['objects'] if not o['locked'] and o['type']!='text'}
            if not isinstance(target_ids,list) or not target_ids or len(target_ids)>24 or any(x not in allowed for x in target_ids):
                raise SceneError('请选取 1–24 个未锁定的图形对象')
            instruction=str(body.get('instruction') or '').strip()
            if not instruction or len(instruction)>2000:raise SceneError('请填写 1–2000 字的重绘要求')
            contract=current.get('generation_contract') or {}
            request={'text':current['source_text'] or current['title'],'canvas_mm':[current['canvas']['width_mm'],current['canvas']['height_mm']],
                     'illustration_mode':'image','generation_brief':contract.get('generation_brief') or current['source_text'] or current['title']}
            if contract.get('reference_id'):
                request.update(reference_id=contract['reference_id'],reference_purpose=contract.get('reference_purpose') or 'layout')
            text,config=prepare(app,request)
            config.update(prepared_scene=copy.deepcopy(current),redraw_ids=list(dict.fromkeys(target_ids)),redraw_instruction=instruction)
            child=create_job(app,text,config,revision_of=job_id,request_id=body.get('request_id'))
            handler._json(200,{'ok':True,'job_id':child['id'],'original_job_id':job_id,'base_revision':current['revision']})
            return True
        if action == "auto-fix" and method == "POST":
            handler._json(200,_repair(app,job))
            return True
        if action == "recheck" and method == "POST":
            result = payload(app,job)
            if body.get("vision"):
                from scene_planner import review_scene_visual
                snapshot = copy.deepcopy(result["scene"])
                job["scene_vision"] = {"status":"running","findings":[],"revision":snapshot["revision"]}
                app._save_meta(job)
                def run_review():
                    result = review_scene_visual(snapshot,app.load_config())
                    job["scene_vision"] = {**result,"revision":snapshot["revision"]}
                    app._save_meta(job)
                queues().submit_generation(run_review)
            handler._json(200,{**result,"findings":result["audit"]["findings"],"vision_started":bool(body.get("vision"))})
            return True
        if action == "confirm" and method == "POST":
            current = repository(app,job_id).read()
            if body.get("revision") is not None and _revision(body,"revision") != current["revision"]:
                raise RevisionConflict("图版已变化，请核对最新修订")
            job["author_confirmed_revision"] = current["revision"]
            app._save_meta(job)
            handler._json(200,{"ok":True,"revision":current["revision"],"author_confirmed":True})
            return True
        if action == "review-finding" and method == "POST":
            current=repository(app,job_id).read()
            visual=job.get('scene_vision') or {}
            if _revision(body)!=current['revision'] or visual.get('revision')!=current['revision']:
                raise RevisionConflict('请核验当前修订的建议')
            index=body.get('index')
            if not isinstance(index,int) or isinstance(index,bool) or not 0<=index<len(visual.get('findings',[])):
                raise SceneError('建议不存在')
            finding=visual['findings'][index]
            finding.update(status='dismissed',resolution=str(body.get('reason') or '作者核验后排除')[:500],resolved_at=time.time())
            app._save_meta(job)
            handler._json(200,payload(app,job))
            return True
        if action == "save-as" and method == "POST":
            handler._json(200,_export(app,job,body))
            return True
        if action == "ppt" and method == "POST":
            revision = body.get("revision") or job["scene_revision"]
            current = job.get("ppt_export") or {}
            if current.get("state")=="running":
                handler._json(200,{"ok":True,"started":True,"status":current})
                return True
            job["ppt_export"] = {"state":"running","pct":0,"stage":"生成原生形状","revision":revision,"started":time.time()}
            app._save_meta(job)
            # Outer control runs outside the export worker to avoid nesting a
            # .result() on that same single-worker queue.
            def run_ppt():
                try:
                    result = _export(app,job,{"format":"pptx","revision":revision})
                    job["ppt"] = {"pptx":result["path"],"revision":revision}
                    job["ppt_export"] = {"state":"completed","pct":100,"stage":"","revision":revision}
                except Exception as exc:
                    job["ppt_export"] = {"state":"failed","pct":0,"stage":"导出失败","error":str(exc)[:300],"revision":revision}
                app._save_meta(job)
            threading.Thread(target=run_ppt,daemon=True).start()
            handler._json(200,{"ok":True,"started":True,"status":job["ppt_export"]})
            return True
        if action == "ppt-status" and method in ("GET","POST"):
            handler._json(200,{"ok":True,**(job.get("ppt_export") or {"state":"not_started","pct":0})})
            return True
        if action in ("download","pdf") and method in ("GET","POST"):
            from urllib.parse import parse_qs
            query = parse_qs(handler.path.split("?",1)[1] if "?" in handler.path else "")
            fmt = "pdf" if action=="pdf" else (query.get("format") or ["svg"])[0]
            result = _export(app,job,{"format":fmt,"dpi":int((query.get("dpi") or [300])[0])})
            file = Path(result["path"])
            mime = {"svg":"image/svg+xml","png":"image/png","pdf":"application/pdf",
                    "pptx":"application/vnd.openxmlformats-officedocument.presentationml.presentation"}[fmt]
            handler._send(200,file.read_bytes(),mime,{"Content-Disposition":f'attachment; filename="{job_id}.{fmt}"'})
            return True
        return False
    except RevisionConflict as exc:
        handler._json(409,{"ok":False,"conflict":True,"error":str(exc)})
    except FileNotFoundError:
        handler._json(404,{"ok":False,"error":"场景修订不存在"})
    except (SceneError,ValueError,TypeError,KeyError,IndexError) as exc:
        handler._json(400,{"ok":False,"error":str(exc)[:500]})
    except TimeoutError:
        handler._json(504,{"ok":False,"error":"请求超时；已有场景和导出版本保持可用"})
    except Exception as exc:
        handler._json(500,{"ok":False,"error":f"{type(exc).__name__}: {exc}"[:500]})
    return True
