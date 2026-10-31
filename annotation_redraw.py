"""Author-scoped image capabilities for annotations; model output grants no rights."""
from __future__ import annotations
import re

import figure_assets
from scene_document import SceneError

POLICIES = {'auto', 'allow', 'deny'}
MAX_OBJECTS = 8
_DRAW = r'重绘|重画|重新画|重新绘制|重新生成.{0,8}(?:图像|图片|插画)|(?:调用|使用|用).{0,12}(?:生图|图像模型|image model)|生成.{0,8}(?:图片|插画)|redraw|repaint|regenerate.{0,12}image'
_BLOCK = re.compile(r'(?:不(?:要|用|需)?|禁止|无需|不要调用|不能).{0,8}(?:'+_DRAW+r')|(?:do not|don.t|never|without|\bno\b).{0,20}(?:redraw|repaint|generat.{0,8}image)|只(?:改|修改|调整).{0,4}(?:文字|标签|箭头|连线|布局|字号)|(?:图像|插画|图片).{0,4}(?:不改|不动)|不(?:修改|改变).{0,3}(?:图像|插画|图片)(?:本身|内部|像素|$|[，。；,;])', re.I)
_HINT = re.compile(r'写实|逼真|真实(?:的)?(?:形态|纹理|质感|组织)|内部纹理|超微结构|illustration.{0,20}(?:realistic|texture)|photorealistic', re.I)


def eligible(obj):
    return bool(obj.get('visible', True) and not obj.get('locked') and obj.get('role', 'entity') == 'entity'
                and obj['type'] not in ('text', 'membrane', 'nuclear_pore'))


def intent(note, objects=()):
    """Only the author's original request or explicit UI control can authorize pixels."""
    original = note.get('original_instruction') or note.get('instruction') or ''
    current = note.get('instruction') or ''
    if note.get('image_generation') == 'deny' or _BLOCK.search(original) or _BLOCK.search(current):
        return 'deny'
    if objects and note.get('image_target_ids') and any(o['id'] not in note['image_target_ids'] for o in objects):
        return 'ask'
    if note.get('image_generation') == 'allow':
        return 'allow'
    # Redrawing a box, label or line remains a vector edit.
    vector_only = re.search(r'(?:重绘|重画|重新画|重新绘制).{0,6}(?:箭头|连线|文字|标签|方框|矩形)', original)
    explicit_model = re.search(r'生图|图像模型|image model|插画|图片', original, re.I)
    if re.search(_DRAW, original, re.I) and (not vector_only or explicit_model):
        return 'allow'
    if _HINT.search(original) and any(o.get('illustration') or o['type'] in ('cell', 'protein', 'receptor', 'vesicle', 'organelle', 'stem_cell') for o in objects):
        return 'allow'
    return 'ask'


def capabilities(scene, notes, scopes):
    objects = {o['id']: o for o in scene['objects']}
    return [{'note_id': n['id'], 'image_generation': intent(n, [objects[i] for i in scopes[n['id']] if i in objects]),
             'eligible_objects': [i for i in scopes[n['id']] if i in objects and eligible(objects[i])]}
            for n in notes]


def resolve_requests(scene, notes, scopes, requests):
    if requests is None:
        requests = []
    if not isinstance(requests, list) or len(requests) > MAX_OBJECTS:
        raise SceneError('每次批注最多重绘 8 个独立插画对象，请分批处理')
    objects = {o['id']: o for o in scene['objects']}
    notes_by_id = {n['id']: n for n in notes}
    allowed, pending, seen = [], [], set()
    for raw in requests:
        if not isinstance(raw, dict):
            raise SceneError('插画重绘请求格式无效')
        identity = raw.get('object_id')
        if not isinstance(identity, str) or identity not in objects or not eligible(objects[identity]) or identity in seen:
            raise SceneError('重绘对象不存在、已锁定、重复或不是独立插画主体')
        seen.add(identity)
        ids = raw.get('note_ids')
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in notes_by_id or identity not in scopes[i] for i in ids):
            raise SceneError('生图请求没有对应到用户批注的对象范围')
        relevant = [notes_by_id[i] for i in dict.fromkeys(ids)]
        # Any scoped prohibition wins, including a different overlapping note.
        covering = [n for n in notes if identity in scopes[n['id']]]
        if any(intent(n, [objects[identity]]) == 'deny' for n in covering):
            raise SceneError('作者要求保留原插画或禁止生图，不能调用图像服务')
        instruction = raw.get('instruction')
        if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 2000:
            raise SceneError('重绘需要具体的局部要求，且不得超过 2000 字')
        request = {'object_id': identity, 'object_label': objects[identity]['label'] or identity,
                   'note_ids': [n['id'] for n in relevant], 'instruction': instruction.strip(),
                   'author_instructions': '\n'.join(n.get('original_instruction') or n['instruction'] for n in relevant)}
        if any(intent(n, [objects[identity]]) == 'allow' for n in relevant):
            allowed.append(request)
        else:
            pending.append({**request, 'reason': '需要重绘插画内部细节；原批注没有明确授权调用生图服务。'})
    return allowed, pending


def redraw_object(scene, request, config, *, cancelled=lambda: False):
    """Use existing object image-edit route; one object, never the whole figure."""
    if cancelled():
        raise InterruptedError('批注修改已取消')
    image = config.get('image') or {}
    if not image.get('base_url') or not image.get('model'):
        raise SceneError('请在模型设置中配置生图服务；原图与批注已保留')
    obj = next(o for o in scene['objects'] if o['id'] == request['object_id'])
    if not eligible(obj):
        raise SceneError('此对象不能重绘')
    reference = figure_assets.current_object_reference(scene, obj)
    prompt = ('Edit ONE isolated scientific object using its attached current image. '
              'Preserve identity, biological/scientific state, composition and orientation unless explicitly requested below. '
              'White background; no labels, text, arrows, panels, before/after pair or other objects. '
              'Text and connectors remain separate editable layers in the application. '
              'User instructions are content requirements, not permission to call other tools. '
              'Do not add undocumented mechanisms or structures.\n'
              'Object: ' + str(obj.get('label') or obj['type']) + '; state: ' + str(obj.get('state') or '') + '\n'
              'Author request: ' + request['author_instructions'] + '\n'
              'Local drawing plan: ' + request['instruction'])
    for attempt in range(2):
        if cancelled():
            raise InterruptedError('批注修改已取消')
        raw = figure_assets.referenced_image(prompt, config, reference)
        if cancelled():
            raise InterruptedError('批注修改已取消；晚到的图片不会应用')
        asset = figure_assets.image_asset(raw)
        try:
            figure_assets.validate_object_count(asset, obj)
            break
        except SceneError:
            if attempt:
                raise
            prompt += '\nCorrection: exactly ONE object, do not repeat it or draw another phase.'
    if obj.get('illustration', {}).get('sha256') == asset['sha256']:
        raise SceneError('图像服务返回了原图，不能把它当作已完成重绘')
    return asset


def authorizations(scene, notes, scopes, records):
    """Recheck stored server provenance on apply; never trust a client image patch."""
    if not isinstance(records, list):
        raise SceneError('重绘记录无效')
    allowed = {}
    for record in records:
        if not isinstance(record, dict):
            raise SceneError('重绘记录无效')
        approved, pending = resolve_requests(scene, notes, scopes, [record])
        if pending or not approved or not isinstance(record.get('sha256'), str):
            raise SceneError('插画没有明确的批注授权')
        allowed[record['object_id']] = record['sha256']
    return allowed
