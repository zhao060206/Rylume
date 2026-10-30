"""Document management and recovery; every restore creates a new revision."""
from __future__ import annotations
import copy
import json
import re
import time
import uuid
from urllib.parse import parse_qs, urlsplit
from scene_document import SceneError, RevisionConflict, normalize_scene, audit_scene


def _create(app, scene, *, origin=None):
    from scene_service import repository, _publish
    scene = normalize_scene(scene)
    scene['id'] = 'j_' + uuid.uuid4().hex[:12]
    scene['revision'] = 1
    job = dict(id=scene['id'], title=scene['title'], text=scene['source_text'],
               original_text=scene['source_text'], mode='scene', scene_engine='v2',
               status='completed', progress=100, created=time.time(), stages=[],
               illustration_mode='vector', duration=0, revision_of=origin)
    result = repository(app, job['id']).commit(scene)
    _publish(app, job, result)
    with app.JOBS_LOCK:
        app.JOBS[job['id']] = job
    return {'ok': True, 'job_id': job['id']}


def export_info(scene, dpi=300):
    from scientific_library import credits
    from scene_render import render_scene
    width, height = scene['canvas']['width_mm'], scene['canvas']['height_mm']
    sources = credits(scene)
    attribution = '\n\n'.join(
        c['label']+' — '+c['author']+', '+c['license']+'. '+c['source_url']
        + (' '+c['modifications'] if c.get('modifications') else '') for c in sources)
    return dict(ok=True, revision=scene['revision'], width_mm=width, height_mm=height,
                width_px=round(width*dpi/25.4), height_px=round(height*dpi/25.4), dpi=dpi,
                min_font_pt=min([scene['style']['font_size_pt']]+[o['font_size_pt'] for o in scene['objects'] if o['visible']]),
                vector='<image' not in render_scene(scene), object_count=sum(o['visible'] for o in scene['objects']),
                relation_count=len(scene['relations']), artwork_credits=sources, attribution=attribution,
                audit=audit_scene(scene))


def dispatch(handler, method, path, app):
    from scene_service import repository, payload, _publish, _revision
    try:
        if path in ('/api/scene/import', '/api/scene/preview') and method == 'POST':
            scene = normalize_scene(handler._body().get('scene'))
            if path.endswith('/preview'):
                from scene_render import render_scene
                handler._json(200, dict(ok=True, scene=scene, svg=render_scene(scene), audit=audit_scene(scene)))
            else:
                handler._json(200, _create(app, scene))
            return True
        match = re.fullmatch(r'/api/jobs/([A-Za-z0-9_-]+)/(document-info|revisions|restore-revision|export-info)', path)
        if not match:
            return False
        job_id, action = match.groups()
        job = app.JOBS.get(job_id)
        if not job:
            raise FileNotFoundError('图版不存在')
        body = handler._body() if method in ('POST', 'PATCH') else {}
        if action == 'document-info' and method in ('POST', 'PATCH'):
            title = str(body.get('title', job.get('title', ''))).strip()
            collection = str(body.get('collection', job.get('collection', ''))).strip()
            if not title or len(title)>120 or len(collection)>60:
                raise SceneError('图版名称需为 1–120 字，分类最多 60 字')
            if 'archived' in body and not isinstance(body['archived'], bool):
                raise SceneError('归档状态格式无效')
            if job.get('scene_engine') == 'v2':
                repo = repository(app, job_id)
                with repo.lock:
                    scene = repo.read()
                    if _revision(body) != scene['revision']:
                        raise RevisionConflict('图版已更新，请重新打开图版信息')
                    if title != scene['title']:
                        scene['title'] = title
                        _publish(app, job, repo.commit(scene, scene['revision']))
            job.update(title=title, collection=collection, archived=body.get('archived', job.get('archived', False)))
            app._save_meta(job)
            handler._json(200, {'ok': True, 'job_id': job_id})
            return True
        if job.get('scene_engine') != 'v2':
            raise SceneError('此功能适用于可编辑图版；历史插画可先创建可编辑副本')
        repo = repository(app, job_id)
        if action == 'revisions' and method == 'GET':
            query = parse_qs(urlsplit(handler.path).query)
            if query.get('revision'):
                revision = int(query['revision'][0])
                handler._json(200, payload(app, job, revision))
            else:
                labels = job.get('revision_labels', {})
                rows = []
                head=repo.read()['revision']
                for folder in sorted((repo.root/'revisions').iterdir(), key=lambda p: int(p.name) if p.name.isdigit() else -1, reverse=True):
                    if folder.name.isdigit() and int(folder.name)<=head and (folder/'scene.json').is_file():
                        document = json.loads((folder/'scene.json').read_text(encoding='utf8'))
                        rows.append(dict(revision=int(folder.name), title=document['title'],
                                         created_at=(folder/'scene.json').stat().st_mtime,
                                         label=labels.get(folder.name, '创建图版' if folder.name=='1' else '保存编辑')))
                handler._json(200, dict(ok=True, current_revision=repo.read()['revision'], revisions=rows))
            return True
        if action == 'restore-revision' and method == 'POST':
            with repo.lock:
                base = _revision(body)
                source = repo.read(_revision(body, 'revision'))
                result = repo.commit(source, base)
                job.setdefault('revision_labels', {})[str(result['revision'])] = '恢复自 r'+str(body['revision'])
                _publish(app, job, result)
            handler._json(200, payload(app, job))
            return True
        if action == 'export-info' and method == 'GET':
            handler._json(200, export_info(repo.read()))
            return True
        handler._json(405, dict(ok=False, error='此操作不支持该请求方式'))
        return True
    except RevisionConflict as exc:
        handler._json(409, dict(ok=False, error=str(exc)))
    except FileNotFoundError as exc:
        handler._json(404, dict(ok=False, error=str(exc)))
    except (ValueError, TypeError, KeyError) as exc:
        handler._json(400, dict(ok=False, error=str(exc)))
    return True
