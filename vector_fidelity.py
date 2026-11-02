"""Source-resolution checks and bounded vector corrections of tracing residuals.

Corrections are ordinary colored paths, never images. Reject gross failures
instead of replacing the entire figure with a grid of colored pixels.
"""
from __future__ import annotations
import io
from collections import defaultdict
import numpy as np
from PIL import Image


def render_pixels(svg, size):
    import fitz
    with fitz.open(stream=svg.encode() if isinstance(svg,str) else svg,filetype='svg') as doc:
        page=doc[0]
        pix=page.get_pixmap(matrix=fitz.Matrix((size[0]-.0001)/page.rect.width,(size[1]-.0001)/page.rect.height),alpha=False)
    result=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
    if result.size!=size:
        raise ValueError('矢量渲染尺寸与原图不一致，无法完成保真核验')
    return np.asarray(result)


def pixel_quality(source, actual):
    a=np.asarray(source,dtype=np.float32);b=np.asarray(actual,dtype=np.float32)
    mask=np.any(a<245,axis=2)|np.any(b<245,axis=2)
    error=np.abs(a-b)
    difference=float(error[mask].mean()/255) if mask.any() else 0
    return {'available':True,'foreground_similarity':round(100*(1-difference),3),
            'method':'native_resolution_foreground_rgb_mae','size':[a.shape[1],a.shape[0]],
            'large_error_fraction':round(float((error.max(axis=2)[mask]>32).mean()) if mask.any() else 0,5),
            'threshold':99.0,'target_met':difference<=.01,
            'note':'在原始分辨率比较前景 RGB；99% 像素接近度不等于文字、布局和科学含义均已通过。'}


def region_paths(rgb, mask, *, origin=(0,0), precision=4, batch=500):
    """Merge horizontal runs and identical vertical runs into colored regions."""
    rgb=np.asarray(rgb);mask=np.asarray(mask,dtype=bool)
    colors=(rgb.astype(np.uint16)//precision*precision+precision//2).clip(0,255).astype(np.uint8)
    codes=colors[:,:,0].astype(np.int64)*65536+colors[:,:,1].astype(np.int64)*256+colors[:,:,2]
    active={};regions=defaultdict(list)
    for y in range(mask.shape[0]+1):
        runs={}
        if y<mask.shape[0]:
            row=np.where(mask[y],codes[y],-1)
            edges=np.flatnonzero(np.r_[True,row[1:]!=row[:-1],True])
            for x1,x2 in zip(edges[:-1],edges[1:]):
                code=int(row[x1])
                if code<0:continue
                key=(code,int(x1),int(x2));runs[key]=active.pop(key,y)
        for (code,x1,x2),top in active.items():regions[code].append((x1,top,x2,y))
        active=runs
    paths=[];ox,oy=origin
    for code,rects in regions.items():
        for start in range(0,len(rects),batch):
            d=''.join(f'M{x1+ox} {y1+oy}h{x2-x1}v{y2-y1}h{x1-x2}Z' for x1,y1,x2,y2 in rects[start:start+batch])
            paths.append(f'<path fill="#{code:06x}" stroke="none" d="{d}"/>')
    return paths


def correction_paths(png, svg, *, threshold=6):
    source=np.asarray(Image.open(io.BytesIO(png)).convert('RGB'))
    actual=render_pixels(svg,(source.shape[1],source.shape[0]))
    mask=np.abs(source.astype(float)-actual).max(axis=2)>threshold
    fraction=float(mask.mean())
    if fraction>.35:
        raise ValueError('原图与描摹差异过大，不能用局部细节修复掩盖，请换用更清晰的原图')
    return region_paths(source,mask),{'refined_pixel_fraction':round(fraction,5)}
