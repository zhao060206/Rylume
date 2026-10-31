"""Offline release history and a per-install acknowledgement of what's new."""
import re
from pathlib import Path
from product_identity import PRODUCT_VERSION
from resource_packs import _write


def history():
    text = (Path(__file__).parent/'CHANGELOG.md').read_text(encoding='utf8')
    result = []
    for block in re.split(r'(?m)^# ', text)[1:]:
        heading, _, body = block.partition('\n')
        match = re.match(r'(\d+\.\d+\.\d+)\s*[—–-]\s*(\d{4}-\d{2}-\d{2})', heading)
        if match:
            result.append({'version': match[1], 'date': match[2],
                'items': [line[2:].strip() for line in body.splitlines() if line.startswith('- ')]})
    return result


def dispatch(handler, method, path, app):
    if path not in ('/api/release-notes', '/api/release-notes/acknowledge'): return False
    from scene_document import SceneError
    try:
        file = Path(app.DATA_DIR)/'release-notes-seen.json'
        if path.endswith('/acknowledge') and method == 'POST':
            body = handler._body()
            if body.get('version') != PRODUCT_VERSION: raise SceneError('版本已变化，请重新查看更新日志')
            _write(file, {'version': PRODUCT_VERSION})
            handler._json(200, {'ok': True}); return True
        if method != 'GET' or path.endswith('/acknowledge'): raise SceneError('请求无效')
        import json
        try: seen = json.loads(file.read_text(encoding='utf8')).get('version')
        except (OSError, ValueError, AttributeError): seen = None
        releases = history()
        handler._json(200, {'ok': True, 'current_version': PRODUCT_VERSION, 'releases': releases,
            'unread': seen != PRODUCT_VERSION, 'first_use': seen is None})
    except (ValueError, OSError):
        handler._json(400, {'ok': False, 'error': '更新日志暂时不可用，请稍后重试'})
    return True
