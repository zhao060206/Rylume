"""Local projects own document membership, independently of scene revisions."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import threading
import time
import uuid

from resource_packs import _write

_lock = threading.RLock()


class ProjectError(ValueError):
    pass


def _title(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 60:
        raise ProjectError('项目名称需为 1–60 字')
    return value.strip()


def _read(app):
    path = Path(app.DATA_DIR) / 'projects.json'
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf8'))
            if data.get('schema_version') != 1 or not isinstance(data['projects'], list) or not isinstance(data['documents'], dict):
                raise ValueError()
            if any(not isinstance(p,dict) or not re.fullmatch(r'p_[a-f0-9]{16}',str(p.get('id',''))) or not isinstance(p.get('title'),str) for p in data['projects']):raise ValueError()
            if not isinstance(data.get('order',{}),dict) or not isinstance(data.get('revision'),int):raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ProjectError('项目目录无法读取，原文件已保留，请先备份后检查') from None
    else:
        data = {'schema_version': 1, 'revision': 0, 'projects': [], 'documents': {}, 'order': {}}
    dirty = False
    names = {p['title']: p['id'] for p in data['projects']}
    # Record even unfiled documents once: renaming/removing a migrated project
    # must never recreate it from the legacy free-text collection afterwards.
    for job in list(app.JOBS.values()):
        if job['id'] in data['documents']:
            continue
        name = str(job.get('collection') or '').strip()
        pid = names.get(name, '')
        if name and not pid:
            pid = 'p_' + uuid.uuid4().hex[:16]
            data['projects'].append({'id': pid, 'title': name[:60], 'created': time.time()})
            names[name] = pid
        data['documents'][job['id']] = pid
        dirty = True
    if dirty:
        data['revision'] += 1
        _write(path, data)
    return data


def _response(data):
    return {'ok': True, 'revision': data['revision'], 'projects': copy.deepcopy(data['projects']),
            'documents': copy.deepcopy(data['documents']), 'order': copy.deepcopy(data.get('order', {}))}


def dispatch(handler, method, path, app):
    if path != '/api/projects' and not path.startswith('/api/projects/'):
        return False
    try:
        with _lock:
            data = _read(app)
            if path == '/api/projects' and method == 'GET':
                handler._json(200, _response(data))
                return True
            body = handler._body() if method in ('POST', 'PATCH', 'DELETE') else {}
            if 'base_revision' in body and body['base_revision'] != data['revision']:
                handler._json(409, {'ok': False, 'error': '项目列表已变化，请刷新后重试'})
                return True
            if path == '/api/projects' and method == 'POST':
                title = _title(body.get('title'))
                if any(p['title'].casefold() == title.casefold() for p in data['projects']):
                    raise ProjectError('已有同名项目，请使用其他名称')
                project = {'id': 'p_' + uuid.uuid4().hex[:16], 'title': title, 'created': time.time()}
                data['projects'].append(project)
                result = {'project': project}
            else:
                match = re.fullmatch(r'/api/projects/(p_[a-f0-9]{16}|unfiled)(/documents)?', path)
                if not match:
                    raise ProjectError('项目操作无效')
                pid, action = match.groups()
                project = next((p for p in data['projects'] if p['id'] == pid), None)
                if pid != 'unfiled' and not project:
                    handler._json(404, {'ok': False, 'error': '项目已不存在，请刷新列表'})
                    return True
                if action and method == 'POST':
                    ids = body.get('job_ids')
                    if not isinstance(ids, list) or not ids or len(ids) > 1000 or any(not isinstance(j, str) or j not in app.JOBS for j in ids):
                        raise ProjectError('请选择仍然存在的图版')
                    target = '' if pid == 'unfiled' else pid
                    before = body.get('before_id')
                    if before and (before not in app.JOBS or before in ids or data['documents'].get(before, '') != target):
                        raise ProjectError('排序位置已变化，请重试')
                    for jid in ids:
                        data['documents'][jid] = target
                    for key in data.setdefault('order', {}):
                        data['order'][key] = [j for j in data['order'][key] if j not in ids]
                    order = data['order'].setdefault(target, [])
                    if before and before not in order:
                        order.extend(j['id'] for j in sorted(app.JOBS.values(), key=lambda j: j.get('created', 0), reverse=True)
                                     if data['documents'].get(j['id'], '') == target and j['id'] not in order and j['id'] not in ids)
                    index = order.index(before) if before else 0
                    order[index:index] = list(dict.fromkeys(ids))
                    result = {}
                elif not action and project and method == 'PATCH':
                    title = _title(body.get('title'))
                    if any(p['id'] != pid and p['title'].casefold() == title.casefold() for p in data['projects']):
                        raise ProjectError('已有同名项目，请使用其他名称')
                    project['title'] = title
                    result = {'project': project}
                elif not action and project and method == 'DELETE':
                    data['projects'] = [p for p in data['projects'] if p['id'] != pid]
                    data['documents'] = {j: '' if p == pid else p for j, p in data['documents'].items()}
                    data.setdefault('order', {}).pop(pid, None)
                    result = {}
                else:
                    handler._json(405, {'ok': False, 'error': '不支持此项目操作'})
                    return True
            data['revision'] += 1
            _write(Path(app.DATA_DIR) / 'projects.json', data)
            handler._json(200, {**_response(data), **result})
    except (ProjectError, TypeError) as exc:
        handler._json(400, {'ok': False, 'error': str(exc)})
    except OSError:
        handler._json(503, {'ok': False, 'error': '项目暂未写入本机，原项目和图版均已保留，请重试'})
    return True
