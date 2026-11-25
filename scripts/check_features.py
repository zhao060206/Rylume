#!/usr/bin/env python3
"""Rylume 功能检查：连接本机 app_server，逐项调用 API，并把结果写进 docs/功能检查-<日期>.md。

用法：
  python scripts/check_features.py                  # 全部检查（会调用已配置的模型）
  python scripts/check_features.py --offline        # 只跑不调用模型的检查
  python scripts/check_features.py --only edit,export
  python scripts/check_features.py --base http://127.0.0.1:8779

脚本只通过公开 HTTP 接口操作，不读取或修改配置里的密钥。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = "EGFR 信号通路示意图：配体 EGF 结合细胞膜上的 EGFR，激活 RAS、RAF、MEK、ERK，ERK 入核调控基因转录。"


class Fail(Exception):
    pass


class Skip(Exception):
    pass


def _short(res, n=240):
    if isinstance(res, dict):
        res = res.get("error") or res.get("message") or json.dumps(res, ensure_ascii=False)
    elif isinstance(res, (bytes, bytearray)):
        res = res[:n].decode("utf-8", "replace")
    text = str(res).replace("\n", " ")
    return text if len(text) <= n else text[:n] + "…"


class Client:
    def __init__(self, base, timeout=30):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def call(self, path, body=None, method=None, raw=False, timeout=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method or ("POST" if body is not None else "GET"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                payload = r.read()
                if raw or "application/json" not in r.headers.get("Content-Type", ""):
                    return r.status, payload
                return r.status, json.loads(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            try:
                return exc.code, json.loads(payload)
            except ValueError:
                return exc.code, payload

    def ok(self, path, body=None, method=None, **kw):
        code, res = self.call(path, body, method, **kw)
        if code != 200:
            raise Fail(f"{method or ('POST' if body is not None else 'GET')} {path} → {code}：{_short(res)}")
        return res


def request_id():
    return "request_" + uuid.uuid4().hex[:16]


def wait_job(c, job_id, limit):
    end, job = time.time() + limit, {}
    while time.time() < end:
        job = c.ok("/api/jobs/" + job_id)
        if job.get("status") in ("completed", "failed", "cancelled"):
            break
        time.sleep(1.0)
    else:
        raise Fail(f"任务 {job_id} 超过 {limit}s 未完成（{job.get('status')}：{job.get('message')}）")
    if job.get("status") != "completed":
        raise Fail(f"任务 {job_id} 状态为 {job.get('status')}：{job.get('error') or job.get('message')}")
    return job


def read_scene(c, job_id):
    return c.ok(f"/api/jobs/{job_id}/scene")["scene"]


def base_job(c, ctx):
    if not ctx.get("base_job"):
        raise Skip("示例场景未创建（前置检查失败）")
    ctx["scene"] = read_scene(c, ctx["base_job"])
    return ctx["base_job"], ctx["scene"]


def patch(c, job_id, revision, operations):
    return c.ok(f"/api/jobs/{job_id}/scene", {"base_revision": revision, "operations": operations}, "PATCH")


def export(c, ctx, job_id, fmt, name):
    path = f"/api/jobs/{job_id}/pdf" if fmt == "pdf" else f"/api/jobs/{job_id}/download?format={fmt}"
    code, data = c.call(path, raw=True, timeout=300)
    if code != 200:
        raise Fail(f"导出 {fmt} → {code}：{_short(data)}")
    magic = {"svg": b"<svg", "png": b"\x89PNG", "pdf": b"%PDF"}[fmt]
    if magic not in data[:4096]:
        raise Fail(f"导出的 {fmt} 文件头不正确")
    target = ctx["out"] / f"{name}.{fmt}"
    target.write_bytes(data)
    ctx.setdefault("files", []).append(target)
    return target, len(data)


def entity_ids(scene, limit=1):
    ok = [o["id"] for o in scene["objects"] if not o.get("locked") and o.get("visible", True)
          and o.get("role", "entity") == "entity" and o.get("type") not in ("text", "membrane", "nuclear_pore")]
    return ok[:limit]


def type_summary(scene):
    return "、".join(f"{k}×{v}" for k, v in Counter(o.get("type") for o in scene["objects"]).most_common(6))


class Warn(Exception):
    pass


# ---------------------------------------------------------------- 检查项
CHECKS = []
ICON = {'pass': '✅', 'warn': '⚠️', 'fail': '❌', 'skip': '⏭️'}


def check(key, title, model=False):
    def wrap(fn):
        CHECKS.append({'key': key, 'title': title, 'model': model, 'fn': fn})
        return fn
    return wrap


def labelled(scene):
    return next((o for o in scene['objects'] if o.get('label') and not o.get('locked')), None)


def obj_of(scene, oid):
    return next(o for o in scene['objects'] if o['id'] == oid)


@check('state', '服务与配置读取')
def c_state(c, ctx):
    st = c.ok('/api/state')
    cfg = st.get('config') if isinstance(st.get('config'), dict) else {}
    if not cfg:
        return f"服务正常（版本 {st.get('version', '?')}）；没有配置信息"
    parts = []
    for kind in ('text', 'image', 'vision'):
        sec = cfg.get(kind) if isinstance(cfg.get(kind), dict) else {}
        model = sec.get('model') or '未设置模型'
        key = '已填密钥' if sec.get('api_key_set') else '未填密钥'
        tag = '，非官方网关' if sec.get('provider') == 'unofficial' else ''
        parts.append(f'{kind}: {model}（{key}{tag}）')
    ctx['configured'] = {k: bool((cfg.get(k) or {}).get('api_key_set')) for k in ('text', 'image', 'vision')}
    return f"版本 {st.get('version', '?')}；" + '；'.join(parts)


@check('connect', '模型连接测试（文本 / 生图 / 视觉）', model=True)
def c_connect(c, ctx):
    good, bad = [], []
    for target in ('text', 'image', 'vision'):
        code, res = c.call('/api/test', {'target': target}, timeout=180)
        if code == 200 and isinstance(res, dict) and res.get('ok') is not False:
            good.append(target + ' 通过')
        else:
            bad.append(f'{target} 失败（{code}）：{_short(res, 120)}')
    if bad:
        raise Fail('；'.join(bad + good))
    return '；'.join(good)


@check('example', '示例场景（离线基准）')
def c_example(c, ctx):
    res = c.ok('/api/scene/example', {'example': 'egfr'})
    wait_job(c, res['job_id'], 60)
    ctx['base_job'] = res['job_id']
    scene = read_scene(c, res['job_id'])
    export(c, ctx, res['job_id'], 'svg', '01-示例场景')
    return f"r{scene['revision']}，{len(scene['objects'])} 个对象（{type_summary(scene)}）"


@check('edit', '单对象编辑（移动 + 改标签）')
def c_edit(c, ctx):
    job, scene = base_job(c, ctx)
    target = labelled(scene) or scene['objects'][0]
    changes = {'x': round(target['x'] + 2, 2)}
    if target.get('label'):
        changes['label'] = target['label'] + ' ✓'
    patch(c, job, scene['revision'], [{'op': 'update', 'id': target['id'], 'changes': changes}])
    after = read_scene(c, job)
    obj = obj_of(after, target['id'])
    if after['revision'] != scene['revision'] + 1:
        raise Fail(f"修订号没有 +1：r{scene['revision']} → r{after['revision']}")
    if abs(obj['x'] - changes['x']) > 0.01 or obj.get('label') != changes.get('label', obj.get('label')):
        raise Fail(f"修改未生效：x={obj['x']}，label={obj.get('label')!r}")
    export(c, ctx, job, 'svg', '02-单对象编辑后')
    return f"{target['id']}（{target.get('type')}）r{scene['revision']} → r{after['revision']}"


@check('conflict', '过期修订号被拒绝（防止覆盖）')
def c_conflict(c, ctx):
    job, scene = base_job(c, ctx)
    if scene['revision'] < 2:
        raise Skip('需要先通过单对象编辑')
    o = scene['objects'][0]
    code, res = c.call(f'/api/jobs/{job}/scene', {'base_revision': scene['revision'] - 1,
                       'operations': [{'op': 'update', 'id': o['id'], 'changes': {'x': o['x']}}]}, 'PATCH')
    if code != 409:
        raise Fail(f'期望 409，实际 {code}：{_short(res)}')
    return '返回 409：' + _short(res, 80)


@check('asset_error', '锁定对象不能重绘，并给出明确提示')
def c_asset_error(c, ctx):
    job, scene = base_job(c, ctx)
    ids = entity_ids(scene)
    if not ids:
        raise Skip('示例场景里没有插画主体')
    oid = ids[0]
    patch(c, job, scene['revision'], [{'op': 'update', 'id': oid, 'changes': {'locked': True}}])
    locked = read_scene(c, job)
    try:
        code, res = c.call(f'/api/jobs/{job}/redraw', {'base_revision': locked['revision'], 'target_ids': [oid],
                           'instruction': '重绘', 'request_id': request_id()})
    finally:
        patch(c, job, locked['revision'], [{'op': 'update', 'id': oid, 'changes': {'locked': False}}])
    msg = _short(res, 120)
    if code != 400 or not any(k in msg for k in ('锁定', '插画主体')):
        raise Fail(f'期望 400 且说明原因，实际 {code}：{msg}')
    return f'{oid} 锁定后重绘返回 400：{msg}'


@check('export', '导出 SVG / PNG / PDF')
def c_export(c, ctx):
    job, _ = base_job(c, ctx)
    done, bad = [], []
    for fmt in ('svg', 'png', 'pdf'):
        try:
            _, size = export(c, ctx, job, fmt, '03-导出')
            done.append(f'{fmt} {size / 1024:.0f} KB')
        except Fail as exc:
            bad.append(str(exc))
    if bad:
        raise Fail('；'.join(bad + done))
    return '、'.join(done)


@check('copy', '创建可编辑副本')
def c_copy(c, ctx):
    job, scene = base_job(c, ctx)
    res = c.ok(f'/api/jobs/{job}/editable-copy', {})
    child = c.ok('/api/jobs/' + res['job_id'])
    if child.get('revision_of') not in (None, job):
        raise Fail(f"revision_of 应为 {job}，实际 {child['revision_of']}")
    copied = read_scene(c, res['job_id'])
    if len(copied['objects']) != len(scene['objects']):
        raise Fail(f"对象数不一致：{len(scene['objects'])} → {len(copied['objects'])}")
    return f"副本 {res['job_id']}，{len(copied['objects'])} 个对象"


def _generate(c, ctx, mode, name, limit):
    res = c.ok('/api/generate', {'text': PROMPT, 'canvas_mm': [180, 120], 'illustration_mode': mode,
                                 'request_id': request_id()})
    start = time.time()
    wait_job(c, res['job_id'], limit)
    scene = read_scene(c, res['job_id'])
    export(c, ctx, res['job_id'], 'svg', name)
    note = ''
    try:
        export(c, ctx, res['job_id'], 'png', name)
    except Fail as exc:
        note = '；PNG 导出失败：' + str(exc)
    return res['job_id'], scene, time.time() - start, note


@check('generate', '文字描述生成可编辑图', model=True)
def c_generate(c, ctx):
    job, scene, secs, note = _generate(c, ctx, 'vector', '04-可编辑生成', 600)
    ctx['gen_job'] = job
    return f"{secs:.0f}s，{len(scene['objects'])} 个对象（{type_summary(scene)}）{note}"


def has_bitmap(o):
    """插画对象的位图存放在 illustration.data（data:image/...），旧格式用 image / asset_id。"""
    ill = o.get('illustration')
    if isinstance(ill, dict) and str(ill.get('data') or '').startswith('data:image'):
        return True
    return 'image' in str(o.get('type')) or bool(o.get('image')) or bool(o.get('asset_id'))


@check('illustration', '插画模式生图', model=True)
def c_illustration(c, ctx):
    job, scene, secs, note = _generate(c, ctx, 'image', '05-插画模式', 900)
    ctx['illus_job'] = job
    images = sum(1 for o in scene['objects'] if has_bitmap(o))
    if not images:
        raise Warn(f'{secs:.0f}s 完成，但场景里没找到位图对象，生图可能没有生效{note}')
    return f'{secs:.0f}s，{images} 个插画对象{note}'


@check('revise', 'AI 局部修改（生成候选 → 应用）', model=True)
def c_revise(c, ctx):
    job = ctx.get('gen_job') or ctx.get('base_job')
    if not job:
        raise Skip('没有可用的场景')
    scene = read_scene(c, job)
    target = labelled(scene)
    if not target:
        raise Skip('场景里没有带标签的对象')
    label = '检查' + uuid.uuid4().hex[:4]
    res = c.ok(f'/api/jobs/{job}/revise', {'base_revision': scene['revision'], 'target_ids': [target['id']],
               'instruction': f'把选中对象的标签改为「{label}」，其他内容不变'}, timeout=300)
    cand = res.get('candidate') or {}
    ops = cand.get('operations') or []
    summary = '；'.join(map(str, cand.get('summary') or []))
    if not ops:
        raise Fail('模型没有给出修改操作：' + (summary or _short(res)))
    patch(c, job, scene['revision'], ops)
    obj = obj_of(read_scene(c, job), target['id'])
    export(c, ctx, job, 'svg', '06-AI修改后')
    if obj.get('label') != label:
        raise Warn(f"已应用 {len(ops)} 个操作，但标签是 {obj.get('label')!r}，不是 {label!r}；{summary}")
    return f'{len(ops)} 个操作；{summary}'[:200]


@check('redraw', '插画主体局部重绘', model=True)
def c_redraw(c, ctx):
    job = ctx.get('illus_job') or ctx.get('gen_job') or ctx.get('base_job')
    if not job:
        raise Skip('没有可用的场景')
    scene = read_scene(c, job)
    ids = entity_ids(scene)
    if not ids:
        raise Skip('场景里没有可重绘的插画主体')
    res = c.ok(f'/api/jobs/{job}/redraw', {'base_revision': scene['revision'], 'target_ids': ids, 'request_id': request_id(),
               'instruction': '位置和大小不变，画得更细致，内部结构清楚，文字和箭头不改'}, timeout=120)
    start = time.time()
    child = wait_job(c, res['job_id'], 900)
    export(c, ctx, res['job_id'], 'svg', '07-局部重绘后')
    try:
        export(c, ctx, res['job_id'], 'png', '07-局部重绘后')
    except Fail:
        pass
    if child.get('revision_of') not in (None, job):
        raise Fail(f"新任务的 revision_of 应为 {job}，实际 {child.get('revision_of')}")
    return f"重绘 {ids[0]}，{time.time() - start:.0f}s，新任务 {res['job_id']}"


@check('annotation', '批注修改（提交批注 → 候选 → 应用）', model=True)
def c_annotation(c, ctx):
    job, scene = base_job(c, ctx)
    base = f'/api/jobs/{job}'
    t = labelled(scene)
    if not t:
        raise Skip('场景里没有带标签的对象')
    doc = c.ok(base + '/annotations')
    note = {'id': 'n1', 'shape': 'rect', 'x': max(0, t['x'] - 1), 'y': max(0, t['y'] - 1),
            'w': t.get('w', 20) + 2, 'h': t.get('h', 10) + 2, 'instruction': '将标签改为 批注已改'}
    saved = c.ok(base + '/annotations', {'base_annotation_revision': doc.get('annotation_revision', 0), 'notes': [note]}, 'PUT')
    run = c.ok(base + '/annotation-runs', {'base_revision': scene['revision'], 'request_id': request_id(),
               'annotation_revision': saved['annotation_revision']})['run']
    end = time.time() + 600
    while run.get('status') in ('queued', 'running'):
        if time.time() > end:
            raise Fail('批注任务超过 600s 未结束')
        time.sleep(2)
        run = c.ok(base + '/annotation-runs?run_id=' + run['id'])['run']
    cand = run.get('candidate')
    if not cand:
        raise Fail(f"批注任务 {run.get('status')}：{run.get('error') or run.get('message') or '没有候选'}")
    checks = '；'.join(f"{x.get('status')} {x.get('message', '')}" for x in cand.get('checks') or [])
    if not cand.get('can_apply'):
        raise Warn('候选需要人工核对，未自动应用：' + checks)
    applied = c.ok(base + '/annotation-apply', {'run_id': run['id'], 'base_revision': scene['revision']})
    export(c, ctx, job, 'svg', '08-批注修改后')
    return f"已应用到 r{applied.get('revision')}；{checks}"[:200]


@check('vision', '视觉审阅', model=True)
def c_vision(c, ctx):
    job = ctx.get('gen_job') or ctx.get('base_job')
    if not job:
        raise Skip('没有可用的场景')
    c.ok(f'/api/jobs/{job}/recheck', {'vision': True}, timeout=60)
    end = time.time() + 300
    while True:
        page = c.ok(f'/api/jobs/{job}/scene')
        v = (page.get('audit') or {}).get('vision') or page.get('vision') or page.get('scene_vision') or page.get('visual_review')
        if not isinstance(v, dict):
            raise Fail('场景接口里找不到视觉审阅字段，现有字段：' + ', '.join(sorted(page)))
        v = v['current'] if isinstance(v.get('current'), dict) else v
        if v.get('status') != 'running':
            break
        if time.time() > end:
            raise Fail('视觉审阅超过 300s 未结束')
        time.sleep(3)
    if v.get('status') in ('failed', 'error', 'unavailable'):
        raise Fail(f"视觉审阅 {v.get('status')}：{_short(v)}")
    return f"状态 {v.get('status')}，{len(v.get('findings') or [])} 条建议"


@check('reference', '参考图上传与风格分析', model=True)
def c_reference(c, ctx):
    import base64
    png = next((f for f in ctx.get('files', []) if f.suffix == '.png'), None)
    if not png:
        raise Skip('没有可用的 PNG（导出检查未通过）')
    url = 'data:image/png;base64,' + base64.b64encode(png.read_bytes()).decode()
    ref = c.ok('/api/references', {'image': url, 'purpose': 'layout'}, timeout=300)
    rid = ref.get('reference_id')
    if not rid:
        raise Fail('没有返回 reference_id：' + _short(ref))
    code, prev = c.call(f'/api/references/{rid}/preview.png', raw=True)
    if code != 200 or not bytes(prev).startswith(b'\x89PNG'):
        raise Fail(f'参考图预览读取失败（{code}）')
    res = c.ok('/api/analyze-image', {'text': PROMPT, 'image': url}, timeout=300)
    return f"{rid}；风格摘要：{_short(res.get('style_summary') or '', 80)}"


# 每个调用模型的检查需要哪段配置（视觉为空时服务端会回退到文本模型）
NEEDS = {'connect': ('text', 'image', 'vision'), 'generate': ('text',), 'revise': ('text',),
         'annotation': ('text',), 'illustration': ('image',), 'redraw': ('image',),
         'vision': ('vision', 'text'), 'reference': ('vision', 'text')}


# ---------------------------------------------------------------- 报告
def write_report(path, args, ctx, results, stamp):
    rows = [f'# 功能检查 {stamp:%Y-%m-%d %H:%M}', '', f'- 服务地址：{args.base}',
            f"- 模式：{'离线（不调用模型）' if args.offline else '完整'}",
            f"- 产物目录：`{ctx['out']}`（对比页 `gallery.html`）", '',
            '| 检查项 | 结果 | 用时 | 说明 |', '|---|---|---|---|']
    for r in results:
        rows.append(f"| {r['title']} | {ICON[r['status']]} | {r['secs']:.1f}s | {r['note'].replace('|', '/')} |")
    count = Counter(r['status'] for r in results)
    rows += ['', '合计：' + '，'.join(f'{ICON[k]} {count[k]}' for k in ICON if count[k])]
    traced = [r for r in results if r['trace']]
    if traced:
        rows += ['', '## 异常堆栈', '']
        for r in traced:
            rows += [f"### {r['title']}", '', '```', r['trace'].rstrip(), '```', '']
    rows += ['', '## 人工评估', '', '打开对比页逐张查看生图效果、编辑结果和导出质量，结论写在这里。', '']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(rows), encoding='utf-8')


def write_gallery(out, results):
    import html
    parts = ['<!doctype html><meta charset="utf-8"><title>Rylume 功能检查</title>',
             '<style>body{font:14px system-ui;margin:24px;background:#f6f6f4}section{background:#fff;border-radius:8px;'
             'padding:12px 16px;margin:12px 0}.grid{display:flex;flex-wrap:wrap;gap:12px}figure{margin:0;max-width:520px}'
             'img{max-width:100%;border:1px solid #ddd;background:#fff}</style><h1>Rylume 功能检查</h1>']
    for r in results:
        parts.append(f"<section><h2>{ICON[r['status']]} {html.escape(r['title'])}</h2><p>{html.escape(r['note'])}</p><div class=grid>")
        for f in r['files']:
            name = html.escape(f.name)
            if f.suffix in ('.png', '.svg'):
                parts.append(f'<figure><img src="{name}" loading=lazy><figcaption>{name}</figcaption></figure>')
            else:
                parts.append(f'<a href="{name}">{name}</a>')
        parts.append('</div></section>')
    (out / 'gallery.html').write_text('\n'.join(parts), encoding='utf-8')


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description='Rylume 功能检查')
    ap.add_argument('--base', default='http://127.0.0.1:8779')
    ap.add_argument('--offline', action='store_true', help='跳过需要调用模型的检查')
    ap.add_argument('--only', default='', help='逗号分隔：' + ','.join(i['key'] for i in CHECKS))
    ap.add_argument('--out', default='', help='导出文件和对比页目录')
    ap.add_argument('--report', default='', help='报告路径，默认 docs/功能检查-<日期>.md')
    args = ap.parse_args(argv)
    c = Client(args.base)
    try:
        c.ok('/api/state', timeout=5)
    except Exception as exc:
        print(f'连不上 {args.base}：{exc}')
        print('请先启动服务：python app_server.py（默认端口 8779）')
        return 2
    only = {k.strip() for k in args.only.split(',') if k.strip()}
    unknown = only - {i['key'] for i in CHECKS}
    if unknown:
        print('未知检查项：' + ', '.join(sorted(unknown)))
        return 2
    if only:
        only.add('example')  # 其余检查都基于示例场景
    stamp = dt.datetime.now()
    out = Path(args.out) if args.out else ROOT / 'rylume-shots' / f'feature-check-{stamp:%Y%m%d-%H%M%S}'
    out.mkdir(parents=True, exist_ok=True)
    ctx = {'out': out, 'files': []}
    results = []
    for item in CHECKS:
        if only and item['key'] not in only:
            continue
        row = {'key': item['key'], 'title': item['title'], 'files': [], 'trace': '', 'secs': 0.0}
        need = NEEDS.get(item['key'])
        conf = ctx.get('configured') or {}
        if args.offline and item['model']:
            row.update(status='skip', note='离线模式跳过')
        elif need and conf and not any(conf.get(k) for k in need):
            row.update(status='skip', note=f"未填写 {'/'.join(need)} 模型的密钥")
        else:
            start, before = time.time(), len(ctx['files'])
            try:
                row.update(status='pass', note=item['fn'](c, ctx) or '')
            except Skip as exc:
                row.update(status='skip', note=str(exc))
            except Warn as exc:
                row.update(status='warn', note=str(exc))
            except Fail as exc:
                row.update(status='fail', note=str(exc))
            except Exception as exc:
                row.update(status='fail', note=f'{type(exc).__name__}: {exc}', trace=traceback.format_exc())
            row.update(secs=time.time() - start, files=ctx['files'][before:])
        results.append(row)
        print(f"{ICON[row['status']]} {item['title']}  {row['secs']:.1f}s  {row['note']}", flush=True)
    report = Path(args.report) if args.report else ROOT / 'docs' / f'功能检查-{stamp:%Y-%m-%d}.md'
    if not args.report and report.exists():
        # Never overwrite an earlier run's report (e.g. a partial --only rerun).
        report = report.with_name(f'功能检查-{stamp:%Y-%m-%d-%H%M%S}.md')
    write_report(report, args, ctx, results, stamp)
    write_gallery(out, results)
    print(f'报告：{report}')
    print(f"对比页：{out / 'gallery.html'}")
    return 1 if any(r['status'] == 'fail' for r in results) else 0


if __name__ == '__main__':
    sys.exit(main())
