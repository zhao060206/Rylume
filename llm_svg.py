"""Text-model SVG route: the LLM writes the final SVG from a deterministic grid.

No image generation, no tracing, no quantization. The text model gets:
  - the user's brief
  - a scene plan with exact grid boxes
  - a strict SVG engineering spec and a shape vocabulary

It returns one SVG with native paths and native text. Invalid output is sent
back once with the parser error for repair.
"""

from __future__ import annotations

import json

import compose
import pipeline

SVG_SPEC = """你是资深科研 SVG 工程师，为 Cell/Nature/Science 绘制机制示意图。根据用户需求和给定的场景 JSON，输出一张完整 SVG。

硬性要求：
1. 只输出 SVG 文档，不要 markdown、不要解释。
2. 画布尺寸和 viewBox 必须与 scene.canvas 完全一致，背景纯白。
3. 每个 entity 的 bbox 是它的占位区；图形必须画在 bbox 内，不得越界、不得互相重叠。
4. 每个实体的图形用简化但可辨认的矢量图形：
   - 细胞：圆润闭合 path（可用贝塞尔）+ 细胞核椭圆 + 2-4 个细胞器（线粒体/溶酶体）；
   - 成纤维细胞：梭形闭合 path + 核；
   - ECM/胶原：3-5 条波浪 path；
   - 病毒/细菌/器官/器件：用最简轮廓 + 关键内部结构；
   - 不确定的实体：用带轮廓的圆角矩形 + 简洁符号，不要画成照片。
5. 所有标签必须是原生 <text>，不要转曲、不要 <image>、不要 <foreignObject>。字体用 Times New Roman，字号 20-28，标签放在对应 bbox 下方 28px、水平居中。
6. connectors 用 <line> 或 <path>，箭头用 <defs><marker> 定义后 marker-end 引用；实线表示已证实，虚线 stroke-dasharray="8 6" 表示假说。
7. 线宽统一 2-2.5，配色不超过 6 种语义色，白底、扁平 2D；禁止渐变、阴影、3D、纹理、装饰性元素。
8. 坐标必须是明确数字；先规划再落笔，保证左右/上下对齐，留白均匀。
9. 不添加用户未给出的机制、数据或结论。
"""


def render(text: str, config: dict, on_stage=None) -> tuple[bytes, dict]:
    def stage(name, detail=None):
        if on_stage:
            on_stage(name, detail)

    stage("plan_scene", "model planning the grid")
    scene = compose.arrange(compose.plan_scene(text, config))
    stage("generate", "model writing SVG")
    scene_json = json.dumps(scene, ensure_ascii=False, indent=1)
    messages = [
        {"role": "system", "content": SVG_SPEC},
        {"role": "user", "content": "用户需求：\n" + text + "\n\n场景 JSON：\n" + scene_json},
    ]
    raw = pipeline._chat(config, messages, temperature=0.15)
    svg = pipeline._strip_fences(raw).encode("utf-8")
    try:
        pipeline._check_svg(svg)
    except Exception as exc:
        stage("generate", "repairing invalid SVG")
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content":
                         f"上一版 SVG 未通过校验：{exc}。请返回修正后的完整 SVG，只输出 SVG。"})
        raw = pipeline._chat(config, messages, temperature=0.1)
        svg = pipeline._strip_fences(raw).encode("utf-8")
        pipeline._check_svg(svg)
    report = {
        "llm_svg": True,
        "scene": {"entities": len(scene["entities"]),
                  "connectors": len(scene.get("connectors") or []),
                  "canvas": scene["canvas"]},
        "bytes": len(svg),
    }
    stage("qa", "structural check")
    return svg, report
