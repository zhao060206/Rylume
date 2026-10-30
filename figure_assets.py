"""Object-level generated illustrations; all placements stay in SceneDocument.

Illustrations are explicitly raster assets. They never replace text, relations,
the scene, or the editable vector draft retained as an earlier revision.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import urllib.error
import urllib.request
import uuid
from functools import lru_cache

from scene_document import SceneError


@lru_cache(maxsize=40)
def validate_illustration(data):
    from PIL import Image
    if not isinstance(data, str) or not data.startswith("data:image/png;base64,") or len(data) > 8_000_000:
        raise SceneError("插画对象必须是小于 6 MB 的内嵌 PNG")
    try:
        raw = base64.b64decode(data.partition(",")[2], validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != "PNG" or image.width * image.height > 5_000_000:
                raise SceneError("插画尺寸过大或格式无效")
            image.verify()
    except SceneError:
        raise
    except Exception as exc:
        raise SceneError("插画数据损坏") from exc
    return hashlib.sha256(raw).hexdigest()


def image_asset(raw):
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(raw)) as image:
        if image.width * image.height > 40_000_000:
            raise SceneError("生成插画像素过大")
        image = ImageOps.exif_transpose(image).convert("RGBA")
        image.thumbnail((1024, 1024))
        # Only remove a white background connected to the outer border.
        # Bright structures enclosed by the object remain opaque.
        import cv2
        import numpy as np
        pixels = np.array(image)
        white = (pixels[:, :, :3].min(axis=2) > 243).astype('uint8')
        count, components = cv2.connectedComponents(white)
        border = set(np.concatenate((components[0], components[-1], components[:,0], components[:,-1])).tolist()) - {0}
        if border:
            pixels[np.isin(components, list(border)), 3] = 0
        image = Image.fromarray(pixels)
        box = image.getbbox()
        if not box:
            raise SceneError("图像模型只返回了空白素材，已保留矢量草稿")
        image = image.crop(box)
        buffer = io.BytesIO()
        image.save(buffer, "PNG", optimize=True)
        # Editor gestures and local recovery include the scene. Keep 24
        # illustrations under the HTTP document limit without a quality hit
        # on the usual 30 mm / 600 DPI printed object.
        while len(buffer.getvalue())>675_000 and min(image.size)>256:
            image.thumbnail((round(image.width*.85),round(image.height*.85)))
            buffer=io.BytesIO();image.save(buffer,'PNG',optimize=True)
        url = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        return {"data": url, "sha256": validate_illustration(url), "width": image.width,
                "height": image.height, "kind": "generated-raster"}


def referenced_image(prompt, config, data_url):
    """Use the standard image-edit endpoint, never pretend a text call saw pixels."""
    import pipeline
    section = config.get("image") or {}
    if section.get("mock_path"):
        return pipeline.generate_raw(prompt, config)
    if not section.get("base_url") or not section.get("model"):
        raise SceneError("请配置图像模型；当前可编辑矢量草稿已保存")
    boundary = "Rylume" + uuid.uuid4().hex
    parts = []
    for key, value in {"model": section["model"], "prompt": prompt, "n": "1",
                       "size": section.get("size") or "1024x1024", "response_format": "b64_json"}.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    pixels = base64.b64decode(data_url.partition(",")[2], validate=True)
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="reference.png"\r\n'
                  'Content-Type: image/png\r\n\r\n').encode() + pixels + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    key = pipeline._api_key(section)
    request = urllib.request.Request(pipeline._endpoint(section["base_url"], "/images/edits"),
        data=b''.join(parts), method="POST", headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": "Bearer " + key if key else "", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=min(180, int(section.get("timeout") or 120))) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 404, 405, 415, 422):
            raise SceneError("当前图像服务不支持参考图重绘；已保留按参考布局生成的可编辑矢量稿") from None
        raise SceneError(f"参考图重绘服务暂不可用（HTTP {exc.code}）；可编辑草稿已保留") from None
    except (OSError, ValueError) as exc:
        raise SceneError("参考图重绘未完成；可编辑草稿已保留") from exc
    item = (result.get("data") or [{}])[0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"], validate=True)
    if item.get("url"):
        with urllib.request.urlopen(item["url"], timeout=90) as response:
            return response.read(12_000_000)
    raise SceneError("图像模型没有返回素材；可编辑草稿已保留")


def object_reference(config,obj):
    """An object-generation request receives its crop, not an entire flowchart."""
    image=config.get('reference_image_data_url')
    if not image:return None
    contract=config.get('reference_contract') or {}
    import re
    label=lambda s:re.sub(r'[\W_]+','',str(s).lower())
    region=next((r for r in contract.get('objects',[]) if r['id']==obj['id'] or (label(r['label']) and label(r['label'])==label(obj['label']))),None)
    if region is None:
        # Layout references still constrain the planner but should not be copied
        # wholesale into every new cell. Style-only references use one subject.
        if config.get('reference_purpose')=='style' and contract.get('objects'):
            region=contract['objects'][0]
        else:return None
    from PIL import Image
    raw=base64.b64decode(image.partition(',')[2],validate=True)
    with Image.open(io.BytesIO(raw)) as source:
        width,height=source.size
        x,y,w,h=(region[k] for k in ('x','y','w','h'))
        border=min(w,h)*.03
        box=(max(0,round((x-border)*width)),max(0,round((y-border)*height)),
             min(width,round((x+w+border)*width)),min(height,round((y+h+border)*height)))
        cropped=source.crop(box)
        out=io.BytesIO();cropped.save(out,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode('ascii')


def validate_object_count(asset,obj):
    """Reject obvious duplicated cells before they can masquerade as one node."""
    if obj['type']!='cell' or any(x in obj.get('state','').lower() for x in ('cytokinesis','daughter','胞质分裂')):
        return
    import cv2
    import numpy as np
    from PIL import Image
    image=Image.open(io.BytesIO(base64.b64decode(asset['data'].partition(',')[2]))).convert('RGBA')
    mask=(np.array(image)[:,:,3]>100).astype('uint8')
    _,labels,stats,centers=cv2.connectedComponentsWithStats(mask)
    areas=stats[1:,cv2.CC_STAT_AREA]
    if len(areas) and sum(area>max(50,float(areas.max())*.25) for area in areas)>1:
        raise SceneError('插画中出现多个独立细胞，已拒绝把它们当作一个对象')


def illustrate(scene, config, *, on_stage=None, cancelled=None, checkpoint=None):
    import pipeline
    objects = [o for o in scene['objects'] if o['type'] not in ('text', 'membrane', 'nuclear_pore')
               and o.get('role') == 'entity' and o.get('visible', True) and not o.get('locked')
               and (not config.get('redraw_ids') or o['id'] in config['redraw_ids'])]
    if len(objects) > 24:
        scene['unresolved'].append('对象超过24个，本次保留矢量稿；可选取对象分批生成插画')
        return scene, {"state": "draft", "generated": 0, "requested": len(objects)}
    generated = 0
    reference_count = 0
    for index, obj in enumerate(objects):
        if cancelled and cancelled():
            raise InterruptedError("任务已取消；已完成的草稿保留")
        if on_stage:
            on_stage('generate', f"绘制对象 {index+1}/{len(objects)}：{obj['label'] or obj['id']}")
        prompt = ("Create ONE isolated scientific illustration of the object below. "
                  "White background, no labels, no text, no arrows, no panels or infographic. "
                  "Preserve the scientific state precisely. Flat clean scientific drawing, "
                  "clear silhouette, restrained colours, consistent line weights. "
                  "The attached reference, if any, provides visual guidance; draw only this object.\n"
                  + json.dumps({k: obj.get(k) for k in ('type','label','state','evidence')}, ensure_ascii=False)
                  + '\nThis request is for this object alone, not the whole figure. Do not show another phase, another cell, a side-by-side comparison, or a before/after pair.'
                  + '\nVisual style: '+str((config.get('style_dna') or {}).get('visual_style_summary') or 'clear scientific illustration')[:700]
                  + '\nPalette: ' + json.dumps(scene['style']['palette']))
        if config.get('redraw_instruction'):
            prompt += '\nRequested change, preserve the object identity and scientific meaning: '+config['redraw_instruction'][:2000]
        try:
            reference = object_reference(config,obj)
            asset=None
            for attempt in range(2):
                local_prompt=prompt if not attempt else prompt+'\nCORRECTION: The previous asset contained multiple separate cells. Draw exactly ONE cell, in only the specified state, with no comparison or second cell.'
                raw = referenced_image(local_prompt, config, reference) if reference else pipeline.generate_raw(local_prompt, config)
                if cancelled and cancelled():
                    raise InterruptedError("任务已取消；已完成的草稿保留")
                asset=image_asset(raw)
                try:
                    validate_object_count(asset,obj)
                    break
                except SceneError:
                    if attempt:raise
            obj['illustration'] = asset
            generated += 1
            reference_count += bool(reference)
            if checkpoint:
                checkpoint(scene)
        except InterruptedError:
            raise
        except Exception as exc:
            message = str(exc) if isinstance(exc, SceneError) else '图像服务未完成素材绘制，已保留可编辑矢量稿'
            scene['unresolved'].append(message[:500])
            # A disconnected endpoint should not be called again for each node.
            break
    return scene, {"state": "ready" if generated == len(objects) else "partial",
                   "generated": generated, "requested": len(objects), "reference_pixels": bool(reference_count),
                   "reference_objects": reference_count}
