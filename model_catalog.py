"""Read model identifiers from an already configured service."""
import json
from urllib import error, request
from urllib.parse import urlsplit

from pipeline import _api_key, _endpoint


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def model_names(section):
    base = str(section.get('base_url') or '').strip()
    if urlsplit(base).scheme not in ('http', 'https') or not urlsplit(base).hostname:
        raise ValueError('请先保存服务地址，再读取模型名称。')
    key = _api_key(section)
    headers = {'Accept': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    req = request.Request(_endpoint(base, '/models'), headers=headers)
    try:
        with request.build_opener(_NoRedirect()).open(req, timeout=12) as response:
            raw = response.read(1024 * 1024 + 1)
    except error.HTTPError as exc:
        raise ValueError(f'服务未提供模型列表（HTTP {exc.code}）。仍可手动填写模型名称。') from None
    except (OSError, TimeoutError):
        raise ValueError('连接模型列表失败，请核对已保存的服务地址。') from None
    if len(raw) > 1024 * 1024:
        raise ValueError('模型列表过大，请手动填写名称。')
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError):
        payload = None
    items = payload.get('data') if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError('服务未返回兼容的模型列表。仍可手动填写名称。')
    names = {item['id'].strip() for item in items if isinstance(item, dict)
             and isinstance(item.get('id'), str) and 0 < len(item['id'].strip()) <= 256}
    if not names:
        raise ValueError('服务未列出可用模型，请核对账号权限或手动填写。')
    return sorted(names)
