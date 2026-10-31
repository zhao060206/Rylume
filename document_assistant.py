"""Local document library and cancellable model-planning queue."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import threading
import time
import uuid
import queue
from concurrent.futures import Future
from pathlib import Path
from urllib.parse import quote

from document_conversion import MAX_UPLOAD, SUPPORTED, ConversionError, DocumentCancelled, convert_document, office_path
from document_advisor import PROMPT_VERSION, SOURCES, analyze_documents, prepare_batches
from studio_storage import durable_replace

_SERVICES, _LOCK = {}, threading.RLock()
ID = re.compile(r'[da]_[0-9a-f]{16}\Z')
PREFIX = '/api/document-assistant'


class _Worker:
    """An interrupted desktop exit preserves drafts instead of waiting on a model."""
    def __init__(self, name):
        self.tasks = queue.Queue()
        self.closed = False
        self.thread = threading.Thread(target=self._run, name=name, daemon=True)
        self.thread.start()

    def _run(self):
        while (task := self.tasks.get()) is not None:
            future, function, args = task
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(function(*args))
                except BaseException as error:
                    future.set_exception(error)

    def submit(self, function, *args):
        if self.closed:
            raise RuntimeError('队列已关闭')
        future = Future()
        self.tasks.put((future, function, args))
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        self.closed = True
        if cancel_futures:
            while True:
                try:
                    task = self.tasks.get_nowait()
                except queue.Empty:
                    break
                if task:
                    task[0].cancel()
        self.tasks.put(None)
        if wait:
            self.thread.join()


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name('.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')
        durable_replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class DocumentLibrary:
    def __init__(self, root):
        self.root = Path(root) / 'document-assistant'
        self.lock = threading.RLock()
        self.documents, self.analyses, self.cancellations = {}, {}, {}
        self.conversions = _Worker('document-convert')
        self.planning = _Worker('document-advice')
        for category, target in (('documents', self.documents), ('analyses', self.analyses)):
            for path in (self.root / category).glob('*/meta.json'):
                if not ID.fullmatch(path.parent.name):
                    continue
                try:
                    value = json.loads(path.read_text(encoding='utf8'))
                    if value['id'] != path.parent.name:
                        continue
                    if value.get('status') in ('queued', 'running', 'converting'):
                        value.update(status='failed', message='上次处理因软件退出而中断，原文件和已有结果已保留，可以重试。')
                        atomic(path, value)
                    target[value['id']] = value
                except (OSError, ValueError, KeyError):
                    continue

    def folder(self, identity):
        if not isinstance(identity, str) or not ID.fullmatch(identity):
            raise ValueError('文档或建议 ID 无效')
        return self.root / ('documents' if identity.startswith('d_') else 'analyses') / identity

    def _save(self, identity, **changes):
        with self.lock:
            collection = self.documents if identity.startswith('d_') else self.analyses
            item = collection[identity]
            item.update(changes, updated=time.time())
            atomic(self.folder(identity) / 'meta.json', item)

    def _conversion_save(self, identity, event, **changes):
        with self.lock:
            if self.cancellations.get(identity) is event:
                self._save(identity, **changes)

    def list(self):
        with self.lock:
            return dict(documents=sorted(copy.deepcopy(list(self.documents.values())), key=lambda d: d['created'], reverse=True), analyses=sorted(copy.deepcopy(list(self.analyses.values())), key=lambda a: a['created'], reverse=True)[:30], capabilities={'formats': sorted(SUPPORTED), 'max_upload_bytes': MAX_UPLOAD, 'legacy_office_available': bool(office_path()), 'converter': 'Microsoft MarkItDown 0.1.9', 'prompt_version': PROMPT_VERSION, 'prompt_sources': SOURCES})

    def upload(self, name, encoded):
        if not isinstance(name, str) or not name.strip() or len(name) > 240 or any(c in name for c in ('\r', '\n', '\x00')):
            raise ValueError('文件名无效')
        name = name.replace('\\', '/').split('/')[-1].strip()
        ext = Path(name).suffix.lower()
        if ext not in SUPPORTED:
            raise ValueError('暂不支持此文件格式。请选择 PDF、PPT/PPTX、DOC/DOCX、文本或表格。')
        if not isinstance(encoded, str) or len(encoded) > (MAX_UPLOAD * 4 // 3 + 8):
            raise ValueError('单个文件请小于 16 MB')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as error:
            raise ValueError('文件编码无效，请重新选择文件') from error
        if not raw or len(raw) > MAX_UPLOAD:
            raise ValueError('文件为空或超过 16 MB')
        digest = hashlib.sha256(raw).hexdigest()
        with self.lock:
            for old in self.documents.values():
                if old['sha256'] == digest and old['extension'] == ext:
                    if old.get('archived'):
                        self._save(old['id'], archived=False)
                    return dict(ok=True, document=copy.deepcopy(old), duplicate=True)
            if len(self.documents) >= 100:
                raise ValueError('本机文档库已达到 100 份，请在新的数据目录建立文档库。')
            identity = 'd_' + uuid.uuid4().hex[:16]
            folder = self.folder(identity)
            folder.mkdir(parents=True)
            (folder / ('source' + ext)).write_bytes(raw)
            record = dict(id=identity, name=name, extension=ext, bytes=len(raw), sha256=digest, status='queued', progress=0, created=time.time(), updated=time.time(), archived=False, revision=0, message='等待本机转换为 Markdown', warnings=[])
            self.documents[identity] = record
            self._save(identity)
            self._queue_conversion(identity)
            return dict(ok=True, document=copy.deepcopy(record), duplicate=False)

    def _queue_conversion(self, identity, ocr=False):
        event = threading.Event()
        self.cancellations[identity] = event
        self._save(identity, status='queued', progress=0, message='等待本机转换', ocr=bool(ocr))
        self.conversions.submit(self._convert, identity, event, ocr)

    def _convert(self, identity, event, ocr):
        try:
            if event.is_set():
                raise DocumentCancelled()
            self._conversion_save(identity, event, status='converting', message='正在本机转换为 Markdown')
            record = self.documents[identity]
            result = convert_document(self.folder(identity) / ('source' + record['extension']), cancelled=event.is_set, progress=lambda n, text: self._conversion_save(identity, event, progress=n, message=text) if not event.is_set() else None, ocr=ocr)
            with self.lock:
                if event.is_set() or self.cancellations.get(identity) is not event:
                    raise DocumentCancelled()
                atomic(self.folder(identity) / 'content.json', result)
                # The downloadable Markdown is precisely what the planner reads.
                (self.folder(identity) / 'content.md').write_text(result['markdown'], encoding='utf8')
                self._save(identity, status='ready', progress=100, message='Markdown 已就绪', revision=record.get('revision', 0) + 1, characters=len(result['markdown']), pages=result['pages'], warnings=result['warnings'], converter=result['converter'], scanned_pages=result['scanned_pages'], markdown_sha256=hashlib.sha256(result['markdown'].encode()).hexdigest())
        except DocumentCancelled:
            self._conversion_save(identity, event, status='cancelled', message='已取消转换；原文件仍保留，可重试')
        except Exception as error:
            self._conversion_save(identity, event, status='failed', message=('转换没有完成：' + str(error))[:1600])

    def content(self, identity):
        with self.lock:
            record = self.documents.get(identity)
            if not record:
                raise FileNotFoundError('文档不存在')
            path = self.folder(identity) / 'content.json'
            if not path.is_file():
                raise ValueError('Markdown 尚未生成，请等待转换完成或重试。')
            return dict(document=copy.deepcopy(record), **json.loads(path.read_text(encoding='utf8')))

    def document_action(self, identity, action, body):
        with self.lock:
            if identity not in self.documents:
                raise FileNotFoundError('文档不存在')
            if action == 'cancel':
                if self.documents[identity]['status'] in ('queued', 'converting'):
                    self.cancellations.get(identity, threading.Event()).set()
                    self._save(identity, status='cancelled', message='已取消；原文件和已有 Markdown 保留')
            elif action == 'retry':
                if self.documents[identity]['status'] in ('queued', 'converting'):
                    raise ValueError('此文档正在转换，请等待或先取消。')
                self._queue_conversion(identity, ocr=body.get('ocr') is True)
            elif action == 'archive':
                if not isinstance(body.get('archived'), bool):
                    raise ValueError('请提供有效的移出状态')
                self._save(identity, archived=body['archived'])
            return dict(ok=True, document=copy.deepcopy(self.documents[identity]))

    def analyze(self, identities, focus, config):
        if not isinstance(identities, list) or not 1 <= len(identities) <= 8 or not all(isinstance(i, str) for i in identities) or len(set(identities)) != len(identities):
            raise ValueError('请选择 1–8 份不同的文档。')
        if not isinstance(focus, str) or len(focus) > 1500:
            raise ValueError('分析重点请控制在 1500 字以内。')
        model = config.get('text') or {}
        if not model.get('base_url') or not model.get('model'):
            raise ValueError('请先在「设置 → 模型设置」配置文本模型。文件转换已在本机完成。')
        with self.lock:
            documents = []
            for identity in identities:
                doc = self.documents.get(identity)
                if not doc or doc['status'] != 'ready' or doc.get('archived'):
                    raise ValueError('请等待所选文档转换完成，或取消选择未就绪的文件。')
                content = self.content(identity)
                documents.append({k: content['document'][k] for k in ('id', 'name', 'revision', 'markdown_sha256')} | {k: content[k] for k in ('sections', 'markdown', 'warnings')})
            prepare_batches(documents)
            fingerprint = hashlib.sha256(json.dumps({'documents': [(d['id'], d['markdown_sha256']) for d in documents], 'focus': focus, 'model': model['model']}, sort_keys=True).encode()).hexdigest()
            for old in self.analyses.values():
                if old.get('fingerprint') == fingerprint and old['status'] in ('queued', 'running'):
                    return dict(ok=True, analysis=copy.deepcopy(old), duplicate=True)
            if len(self.analyses) >= 100:
                raise ValueError('分析历史已达到 100 次；请使用新的数据目录继续。')
            identity = 'a_' + uuid.uuid4().hex[:16]
            record = dict(id=identity, document_ids=identities, document_names=[d['name'] for d in documents], focus=focus, model=model['model'], fingerprint=fingerprint, status='queued', progress=0, message='等待模型分析', created=time.time(), updated=time.time(), prompt_version=PROMPT_VERSION)
            self.analyses[identity] = record
            self._save(identity)
            atomic(self.folder(identity) / 'inputs.json', documents)
            event = threading.Event()
            self.cancellations[identity] = event
            self.planning.submit(self._analyze, identity, documents, copy.deepcopy(config), event)
            return dict(ok=True, analysis=copy.deepcopy(record), duplicate=False)

    def _analyze(self, identity, documents, config, event):
        try:
            if event.is_set():
                raise DocumentCancelled()
            self._save(identity, status='running', message='正在阅读 Markdown')
            result = analyze_documents(documents, config, focus=self.analyses[identity]['focus'], cancelled=event.is_set, progress=lambda n, text: self._save(identity, progress=n, message=text) if not event.is_set() else None)
            with self.lock:
                if event.is_set():
                    raise DocumentCancelled()
                atomic(self.folder(identity) / 'result.json', result)
                self._save(identity, status='completed', progress=100, message=f"已生成 {len(result['suggestions'])} 条绘图建议", suggestion_count=len(result['suggestions']))
        except DocumentCancelled:
            self._save(identity, status='cancelled', message='已取消；转换文件及历史建议均保留')
        except Exception as error:
            self._save(identity, status='failed', message=('分析没有完成：' + str(error))[:1600])

    def analysis(self, identity):
        with self.lock:
            record = self.analyses.get(identity)
            if not record:
                raise FileNotFoundError('分析记录不存在')
            path = self.folder(identity) / 'result.json'
            return dict(ok=True, analysis=copy.deepcopy(record), result=json.loads(path.read_text(encoding='utf8')) if path.is_file() else None)

    def cancel_analysis(self, identity):
        with self.lock:
            if identity not in self.analyses:
                raise FileNotFoundError('分析记录不存在')
            if self.analyses[identity]['status'] in ('queued', 'running'):
                self.cancellations.get(identity, threading.Event()).set()
                self._save(identity, status='cancelled', message='已取消；晚到的模型结果不会应用')
            return self.analysis(identity)


def library(app):
    key = str(Path(app.DATA_DIR).resolve())
    with _LOCK:
        return _SERVICES.setdefault(key, None) or _create_library(key)


def _create_library(key):
    value = DocumentLibrary(key)
    _SERVICES[key] = value
    return value


def dispatch(handler, method, path, app):
    if not (path == PREFIX or path.startswith(PREFIX + '/')):
        return False
    try:
        store = library(app)
        body = handler._body() if method == 'POST' else {}
        if path == PREFIX and method == 'GET':
            result = store.list()
            model = (app.load_config().get('text') or {})
            result['text_model'] = {'configured': bool(model.get('base_url') and model.get('model')), 'model': model.get('model') or ''}
            handler._json(200, dict(ok=True, **result))
        elif path == PREFIX + '/upload' and method == 'POST':
            handler._json(202, store.upload(body.get('name'), body.get('data')))
        elif path == PREFIX + '/analyze' and method == 'POST':
            handler._json(202, store.analyze(body.get('document_ids'), body.get('focus', ''), app.load_config()))
        elif match := re.fullmatch(PREFIX + r'/documents/(d_[0-9a-f]{16})(?:/(markdown|retry|cancel|archive))?', path):
            identity, action = match.groups()
            if method == 'GET' and action in (None, 'markdown'):
                content = store.content(identity)
                if action == 'markdown':
                    name = Path(content['document']['name']).stem + '.md'
                    handler._send(200, content['markdown'].encode('utf8'), 'text/markdown; charset=utf-8', {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(name)})
                else:
                    handler._json(200, dict(ok=True, **content))
            elif method == 'POST' and action in ('retry', 'cancel', 'archive'):
                handler._json(200, store.document_action(identity, action, body))
            else:
                raise FileNotFoundError('此文档操作不存在')
        elif match := re.fullmatch(PREFIX + r'/analyses/(a_[0-9a-f]{16})(/cancel)?', path):
            identity, action = match.groups()
            if method == 'GET' and not action:
                handler._json(200, store.analysis(identity))
            elif method == 'POST' and action:
                handler._json(200, store.cancel_analysis(identity))
            else:
                raise FileNotFoundError('此分析操作不存在')
        else:
            raise FileNotFoundError('文档助手接口不存在')
    except FileNotFoundError as error:
        handler._json(404, dict(ok=False, error=str(error)))
    except (ValueError, TypeError, KeyError) as error:
        handler._json(400, dict(ok=False, error=str(error)))
    except OSError:
        handler._json(503, dict(ok=False, error='文档暂时无法保存或读取，请稍后重试。'))
    return True
