"""Drawing pipeline with swappable model adapters.

Modes, selected by config["mode"]:

  placeholder  no model; deterministic SVG, for protocol testing.
  svg          chat model writes SVG markup directly.
  plan         chat model returns a layout JSON spec; layout.py renders it to
               fully editable SVG (native text, native shapes).
  image        chat model (optional) rewrites the prompt, an image model makes
               a raster, then: OCR -> text removal -> vectorize -> text
               re-injection -> cleanup -> QA.

Config (see config.example.json). Only `mode` is required.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import textwrap
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


class ImageServiceError(RuntimeError):
    """The image model is unreachable or refused the request.

    This must never degrade into a placeholder figure: a blank page reported
    as a completed job is worse than a visible failure.
    """


import layout
import ocr
import qa
import textfix
import vectorizer

STYLE_SUFFIX = (
    "Scientific journal figure for Cell/Nature/Science. Clean flat 2D vector "
    "illustration style, pure white background, restrained semantic colors, "
    "clear outlines, generous whitespace. No 3D rendering, no photographic "
    "lighting, no drop shadows, no decorative gradients, no watermark, no "
    "signature. Keep every label short and legible. Do not render any text "
    "that was not requested."
)

SVG_INSTRUCTION = (
    "You are a scientific figure generator. Return ONE complete SVG document "
    "and nothing else: no markdown fences, no commentary. Rules: root element "
    "must be <svg> with xmlns and viewBox; use only path, rect, circle, "
    "ellipse, line, polyline, polygon, text, tspan, g, defs, linearGradient, "
    "radialGradient, clipPath, marker. Never use <image>, <script>, <foreignObject>, "
    "external href/src, @import, or url() that points outside the document. "
    "All text must be real <text> elements with font-family set, so it stays "
    "editable. Draw every arrow as a path/marker, not as a character. "
    "Background must be white."
)

OPTIMIZE_INSTRUCTION = """你是 Cell / Nature / Science 期刊的资深科学插画师和图表编辑。把用户的一句话需求改写成可以直接交给绘图模型的精确 brief。

硬性规则：
1. 科学事实只增不改：保留用户给出的全部实体、关系、方向、条件和结论；不得新增机制、通路、数据或统计显著性，不得把假说画成已证实。
2. 只补充视觉与版式信息：画布比例、面板划分、阅读顺序、实体位置与大小、形态、配色、线宽、留白、箭头样式、标签文字。
3. 标签必须逐字给出，短而具体，优先英文（如 Tumor cell、TGF-beta、ECM），不要长句，不要图注段落。
4. 输出固定六段，每段用短标题：图型与画布 / 布局 / 实体 / 关系与箭头 / 标签 / 视觉规范。
5. 视觉规范默认：纯白背景、扁平 2D 矢量插画、不超过 6 种语义色、统一线宽、清晰轮廓、充足留白；禁止 3D、写实光影、投影、装饰性渐变、纹理和图标堆砌。
6. 箭头语义明确：实线箭头表示已证实的促进或流向，虚线箭头表示假说或间接，钝头线表示抑制；每条箭头都要有起点和终点。
7. 用户只给摘要时，给一个合理的单面板或双面板布局；不要编造实验结果。
8. 输出中文，不超过 1200 字；不要解释、不要 markdown 代码块、不要前后缀。"""


PLAN_INSTRUCTION = (
    "You are a scientific figure layout planner. Return ONLY a JSON object, no "
    "markdown, no commentary. Schema:\n"
    '{"canvas":[1280,900],"title":"optional",'
    '"panels":[{"label":"A","bbox":[40,80,520,620]}],'
    '"nodes":[{"id":"tumor","label":"Tumor cell","bbox":[100,300,200,90],'
    '"shape":"rounded|rect|ellipse","fill":"#e8f5f1","stroke":"#0f766e",'
    '"text_color":"#0f2d3a","font_size":20}],'
    '"edges":[{"from":"tumor","to":"caf","label":"TGF-beta",'
    '"style":"solid|dashed","arrow":true,"color":"#0f766e"}],'
    '"notes":[{"text":"Hypothesis","x":60,"y":860,"size":16}]}\n'
    "Rules: 4-10 nodes, boxes must not overlap, keep 40px margins, ids unique, "
    "every edge endpoint must exist, labels short (<=28 chars), arrows for "
    "causal flow, dashed arrows for hypotheses. Preserve the user's scientific "
    "claims exactly; never invent results. Use restrained colors."
)


# ---------------------------------------------------------------- transport


def _api_key(section: dict) -> str:
    if section.get("api_key"):
        return str(section["api_key"])
    env = section.get("api_key_env")
    return os.environ.get(env, "") if env else ""


def _endpoint(base_url: str, suffix: str) -> str:
    base = base_url.rstrip("/")
    return base + suffix if base.endswith("/v1") else base + "/v1" + suffix


def _post_json(url: str, key: str, payload: dict, timeout: int = 300) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}" if key else "",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc


def _fold_system(messages: list[dict]) -> list[dict]:
    """Move system messages into the first user turn.

    The local wb2api gateway (127.0.0.1:7863) silently drops every message
    with role="system", which destroys output contracts such as "return only
    this JSON schema". Folding the text into the user turn keeps the contract
    in-band and behaves the same on a plain OpenAI-compatible endpoint.
    """
    systems = [str(m.get("content") or "") for m in messages if m.get("role") == "system"]
    rest = [dict(m) for m in messages if m.get("role") != "system"]
    head = "\n\n".join(part for part in systems if part.strip())
    if not head:
        return rest
    if rest and rest[0].get("role") == "user":
        first = dict(rest[0])
        content = first.get("content")
        if isinstance(content, list):
            first["content"] = [{"type": "text", "text": f"【系统指令】\n{head}"}] + list(content)
        else:
            first["content"] = f"【系统指令】\n{head}\n\n【用户请求】\n{content or ''}"
        rest[0] = first
    else:
        rest.insert(0, {"role": "user", "content": f"【系统指令】\n{head}"})
    return rest


def _chat(config: dict, messages: list[dict], *, temperature: float = 0.3,
          max_tokens: int = 1500, allow_reasoning_fallback: bool = True,
          reasoning_effort: str | None = None, timeout: int = 300) -> str:
    section = config.get("text") or {}
    if not section.get("base_url") or not section.get("model"):
        raise RuntimeError("this mode needs config.text.base_url and config.text.model")
    payload = {"model": section["model"], "messages": _fold_system(messages),
               "temperature": temperature, "max_tokens": max_tokens}
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    response = _post_json(
        _endpoint(section["base_url"], "/chat/completions"),
        _api_key(section),
        payload,
        timeout=timeout,
    )
    msg = response["choices"][0]["message"]
    content = msg.get("content")
    if not content and msg.get("reasoning_content"):
        if not allow_reasoning_fallback:
            raise RuntimeError("model returned reasoning only")
        content = msg["reasoning_content"]
    return content or ""


# ---------------------------------------------------------------- helpers


def _wrap(text: str, width: int = 62, max_lines: int = 12) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    lines = textwrap.wrap(text, width=width, break_long_words=True,
                          break_on_hyphens=False)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: max(0, width - 1)] + "…"
    return lines


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:svg|xml)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("<svg")
    end = raw.rfind("</svg>")
    if start == -1 or end == -1:
        raise RuntimeError("model did not return an <svg> document")
    return raw[start:end + 6]


def _repair_json_text(text: str) -> str:
    text = (text.replace(chr(8220), '"').replace(chr(8221), '"')
                .replace(chr(8216), "'").replace(chr(8217), "'"))
    text = re.sub(r',\s*([}\]])', r'\1', text)
    out, in_string, escaped = [], False, False
    for char in text:
        if in_string:
            if escaped:
                out.append(char); escaped = False
            elif char == chr(92):
                out.append(char); escaped = True
            elif char == chr(34):
                out.append(char); in_string = False
            elif char == chr(10):
                out.append(chr(92) + 'n')
            elif char == chr(9):
                out.append(chr(92) + 't')
            else:
                out.append(char)
        else:
            if char == chr(34):
                in_string = True
            out.append(char)
    return ''.join(out)


def chat_json(config: dict, messages: list[dict], *, temperature: float = 0.2,
              max_tokens: int = 2400, reasoning_effort: str | None = None,
              timeout: int = 300, allow_fallback: bool = True) -> dict:
    """JSON-expecting planner call with optional model fallback.

    The local gateway's deepseek models sometimes emit free-form reasoning in
    `content` instead of JSON; retry the same prompt on models that follow the
    schema reliably. Repair loops disable the fallback: three 240s timeouts
    per round turn a single bad patch into a multi-minute stall.
    """
    section = config.get("text") or {}
    models = [None]
    if allow_fallback and any(host in str(section.get("base_url") or "")
                              for host in ("127.0.0.1", "localhost")):
        models += ["cn:mimo-v2.6-pro", "cn:glm-5.3"]
    last = None
    for model in models:
        active = config
        if model:
            active = dict(config)
            active["text"] = dict(section, model=model)
        try:
            raw = _chat(active, messages, temperature=temperature, max_tokens=max_tokens,
                        reasoning_effort=reasoning_effort, timeout=timeout)
            return _json_object(raw)
        except Exception as exc:
            last = exc
            continue
    raise RuntimeError(f"planner returned no JSON: {last}")


def _json_object(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("model did not return a JSON object")
    body = raw[start:end + 1]
    try:
        return json.loads(body)
    except json.JSONDecodeError as first:
        try:
            return json.loads(_repair_json_text(body))
        except json.JSONDecodeError:
            try:
                import json_repair
                return json_repair.loads(body)
            except Exception:
                raise RuntimeError(f"model JSON invalid: {first}") from None


def _xml_escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _check_svg(data: bytes, allow_image: bool = False) -> None:
    if not data or len(data) > 32 * 1024 * 1024:
        raise RuntimeError("SVG empty or too large")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise RuntimeError(f"SVG parse error: {exc}") from None
    if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
        raise RuntimeError("SVG root missing")
    vector = 0
    for node in root.iter():
        tag = node.tag.split("}")[-1].lower()
        if tag in ("script", "image", "foreignobject", "iframe", "audio", "video"):
            if not (allow_image and tag == "image"):
                raise RuntimeError(f"SVG contains forbidden element <{tag}>")
        for name, value in node.attrib.items():
            attr = name.split("}")[-1].lower()
            text = str(value).strip().lower()
            if attr.startswith("on"):
                raise RuntimeError(f"SVG contains event handler {attr}")
            if "javascript:" in text:
                raise RuntimeError("SVG contains a javascript: URL")
            if attr in ("href", "xlink:href") and text.startswith(("data:text/html",
                                                                  "data:image/svg")):
                raise RuntimeError("SVG contains an unsafe data URL")
        vector += tag in ("path", "rect", "circle", "ellipse", "line",
                          "polyline", "polygon", "text", "use")
    if not vector:
        raise RuntimeError("SVG contains no editable vector objects")


# ---------------------------------------------------------------- placeholder


def placeholder_svg(text: str, image: bytes | None = None) -> bytes:
    lines = _wrap(text) or ["(no text supplied)"]
    body = []
    y = 300
    for line in lines:
        body.append(
            f'<text x="120" y="{y}" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="26" fill="#1b2733">{_xml_escape(line)}</text>'
        )
        y += 40
    note = "local placeholder · replace pipeline mode to use a real model"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="900" viewBox="0 0 1280 900">
  <rect x="0" y="0" width="1280" height="900" fill="#ffffff"/>
  <rect x="48" y="48" width="1184" height="804" rx="24" fill="none" stroke="#d6dee8" stroke-width="2"/>
  <rect x="120" y="120" width="140" height="8" rx="4" fill="#0f766e"/>
  <text x="120" y="200" font-family="Arial, Helvetica, sans-serif" font-size="46"
        font-weight="700" fill="#0f2d3a">Cell Figure (local)</text>
  <text x="120" y="250" font-family="Arial, Helvetica, sans-serif" font-size="22"
        fill="#5b6b7a">{_xml_escape(note)}</text>
  {"".join(body)}
  <path d="M120 720 L420 720" stroke="#0f766e" stroke-width="4"/>
  <path d="M420 720 L405 712 L405 728 Z" fill="#0f766e"/>
  <text x="440" y="729" font-family="Arial, Helvetica, sans-serif" font-size="20"
        fill="#5b6b7a">generated by cell-figure-local</text>
</svg>
'''.encode("utf-8")


# ---------------------------------------------------------------- mode: svg


def text_to_svg(text: str, config: dict) -> bytes:
    raw = _chat(config, [
        {"role": "system", "content": SVG_INSTRUCTION},
        {"role": "user", "content": f"Draw this scientific figure:\n\n{text}\n\nStyle: {STYLE_SUFFIX}"},
    ], temperature=0.4)
    svg = _strip_fences(raw).encode("utf-8")
    _check_svg(svg)
    return svg


# ---------------------------------------------------------------- mode: plan


def plan_to_svg(text: str, config: dict, on_stage=None) -> tuple[bytes, dict]:
    if on_stage:
        on_stage("plan")
    raw = _chat(config, [
        {"role": "system", "content": PLAN_INSTRUCTION},
        {"role": "user", "content": text},
    ], temperature=0.2)
    try:
        spec = _json_object(raw)
        spec = layout.repair_spec(spec)
        spec = layout.center_spec(spec)
        if on_stage:
            on_stage("render", "布局完成")
        svg = layout.render(spec, font=(config.get("font") or "Times New Roman"))
        _check_svg(svg)
        return svg, {"source": "model", "nodes": len(spec.get("nodes") or []),
                     "edges": len(spec.get("edges") or []),
                     "bytes": len(svg)}
    except Exception as exc:
        # deterministic fallback keeps the job deliverable instead of failing hard
        spec = layout.repair_spec({
            "canvas": config.get("canvas") or [1280, 900],
            "title": "Figure",
            "notes": [{"text": f"plan fallback: {type(exc).__name__}", "x": 48,
                       "y": 860, "size": 14}],
            "nodes": [{"id": "body", "label": text[:600], "bbox": [120, 140, 1040, 620],
                       "shape": "rounded", "fill": "#ffffff", "stroke": "#c7d3de",
                       "text_color": "#1b2733", "font_size": 22}],
        })
        svg = layout.render(spec, font=(config.get("font") or "Times New Roman"))
        _check_svg(svg)
        return svg, {"source": "fallback", "error": str(exc)[:400], "bytes": len(svg)}


# ---------------------------------------------------------------- mode: image


def rewrite_prompt(text: str, config: dict) -> str:
    section = config.get("text") or {}
    if not (section.get("base_url") and section.get("model") and section.get("rewrite", True)):
        return f"{text.strip()}\n\n{STYLE_SUFFIX}"
    prompt = _chat(config, [
        {"role": "system", "content":
         "Rewrite a scientific figure request into one visual prompt for an image "
         "generation model. Describe layout, entities, arrows, and colors. Keep all "
         "scientific claims exactly as given; never invent results. Return the prompt "
         "only, no preamble."},
        {"role": "user", "content": text},
    ], temperature=0.3).strip()
    return f"{prompt}\n\n{STYLE_SUFFIX}"


def generate_raw(prompt: str, config: dict) -> bytes:
    section = config.get("image") or {}
    mock = section.get("mock_path")
    if mock:
        from pathlib import Path
        delay = float(section.get("mock_delay") or 0)
        if delay > 0:
            time.sleep(delay)
        return Path(mock).expanduser().read_bytes()
    if not section.get("base_url") or not section.get("model"):
        raise RuntimeError("mode=image needs config.image.base_url and config.image.model")
    payload = {
        "model": section["model"],
        "prompt": prompt,
        "n": 1,
        "size": section.get("size", "1024x1024"),
        "response_format": "b64_json",
    }
    try:
        response = _post_json(_endpoint(section["base_url"], "/images/generations"),
                              _api_key(section), payload,
                              timeout=int(section.get("timeout") or 300))
    except RuntimeError as exc:
        text = str(exc)
        if re.search(r"HTTP (?:5\d\d|429)\b", text):
            raise ImageServiceError(f"生图服务不可用：{text}") from exc
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise ImageServiceError(f"生图服务不可用：{exc}") from exc
    item = response["data"][0]
    if item.get("b64_json"):
        return base64.b64decode(item["b64_json"])
    if item.get("url"):
        try:
            with urllib.request.urlopen(item["url"], timeout=120) as handle:
                return handle.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            raise ImageServiceError(f"生图结果下载失败：{exc}") from exc
    raise RuntimeError("image model returned neither b64_json nor url")


def _whole_figure_prompt(text: str, config: dict) -> str:
    contract = config.get("layout_contract") or {}
    stages = [str(s) for s in (contract.get("stages") or []) if str(s).strip()]
    title = str(contract.get("title") or "").strip()
    layout = contract.get("layout")
    if layout == "horizontal_s":
        composition = ("Horizontal left-to-right flow with a very slight S-shaped vertical offset. "
                       "Do not stack the stages as full-width horizontal bars.")
    else:
        composition = ("Vertical top-to-bottom cascade on a strict two-column grid: all stage "
                       "labels in one left column, right-aligned; all scientific illustrations in "
                       "one right column, left-aligned; each stage shares a row and a common "
                       "baseline. Use one clean vertical arrow spine between the columns. Fill "
                       "about 85% of the canvas width. Do not alternate sides, do not use "
                       "full-width empty cards or long empty strips.")
    lines = [
        "Create one publication-quality scientific mechanism diagram for a Cell/Nature paper.",
        "Flat 2D vector scientific illustration, pure white background, thin dark outlines, "
        "muted journal palette, generous but purposeful white space, clear arrows, no 3D, "
        "no shadows, no gradients, no decorative AI gloss.",
        composition,
        "Fill about 85% of the canvas width and height with meaningful scientific content; "
        "large empty margins are a failure.",
    ]
    if title:
        lines.append(f'Exact main title: "{title}".')
    if stages:
        lines.append("Exact stage labels, spelled exactly and in this order: "
                     + " -> ".join(stages) + ".")
    else:
        lines.append("Use the exact stage labels from the brief; do not invent new labels.")
    lines.append("Every stage must have a distinct scientific illustration: extracellular vesicle, "
                 "membrane receptor, kinase cascade, nucleus/nuclear pore, cartilage matrix. "
                 "Do not reuse the same generic circle or icon for different stages.")
    lines.append("Show extracellular vesicles explicitly as lipid-bilayer spheres with visible "
                 "membrane and cargo releasing ligands; do not replace them with free dots.")
    lines.append("Keep every stage fully inside the frame and balance the top/bottom margins; "
                 "the final cartilage-matrix panel must be complete and not cut off.")
    lines.append("Place each stage label on a consistent vertical grid beside its illustration; "
                 "use clean straight arrows with even spacing.")
    lines.append("Aim for refined high-end Cell/Nature flat-vector illustration: consistent line "
                 "weight, layered detail and subtle flat shading, not generic clip-art.")
    lines.append("Use only the labels above; no extra headings, no sub-labels such as "
                 "'Kinase 1', no roman numerals, no page numbers, no gibberish, no numbers, "
                 "no legend, no watermark.")
    style = config.get("design_brief") or ""
    if style:
        lines.append("Style constraints: " + str(style)[:800])
    return chr(10).join(lines)


def whole_figure_svg(text: str, config: dict) -> tuple[bytes, dict]:
    """One coherent generated illustration instead of strip/card templates."""
    canvas = [int(v) for v in (config.get("canvas") or [1600, 1067])[:2]]
    cw, ch = max(320, canvas[0]), max(320, canvas[1])
    prompt = _whole_figure_prompt(text, config)
    image_config = dict(config)
    image_section = dict(config.get("image") or {})
    ratio = cw / max(1, ch)
    image_section["size"] = ("1536x1024" if ratio >= 1.25 else
                             "1024x1536" if ratio <= 0.8 else "1024x1024")
    image_config["image"] = image_section
    try:
        png = generate_raw(prompt, image_config)
    except Exception as first_error:
        # Size negotiation is the only reason to retry immediately; keep the
        # original service error rather than hiding it behind a second 400.
        image_section["size"] = "1024x1024"
        image_config["image"] = image_section
        try:
            png = generate_raw(prompt, image_config)
        except Exception as second_error:
            raise RuntimeError(f"{type(first_error).__name__}: {first_error}；"
                               f"备用尺寸重试失败：{type(second_error).__name__}: {second_error}") from first_error
    data = base64.b64encode(png).decode("ascii")
    svg = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<svg xmlns="http://www.w3.org/2000/svg" width="{cw}" height="{ch}" '
           f'viewBox="0 0 {cw} {ch}">'
           f'<rect width="{cw}" height="{ch}" fill="#FFFFFF"/>'
           f'<image href="data:image/png;base64,{data}" x="0" y="0" width="{cw}" height="{ch}" '
           f'preserveAspectRatio="xMidYMid meet"/></svg>').encode("utf-8")
    import text_ocr
    ocr_texts = text_ocr.extract_png(png)
    contract = config.get("layout_contract") or {}
    report = {
        "mode": "illustration",
        "ocr_texts": ocr_texts,
        "whole_figure": True,
        "raster": True,
        "spec": {
            "title": contract.get("title") or "",
            "subtitle": "",
            "layout": contract.get("layout") or "vertical",
            "regions": contract.get("regions") or [],
            "stages": [{"label": name, "caption": "", "prompt": "", "color": ""}
                       for name in (contract.get("stages") or [])],
        },
        "layout_contract": contract,
        "bytes": len(svg),
    }
    return svg, report


def generate_image(text: str, config: dict) -> bytes:
    return generate_raw(rewrite_prompt(text, config), config)


def image_to_svg(text: str, config: dict, on_stage=None) -> tuple[bytes, dict]:
    def stage(name, detail=None):
        if on_stage:
            on_stage(name, detail)

    report: dict = {"stages": {}}
    stage("generate")
    base_png = generate_image(text, config)
    report["stages"]["generate"] = {"bytes": len(base_png)}

    stage("ocr")
    items, ocr_report = ocr.detect(base_png, config)
    report["stages"]["ocr"] = ocr_report

    stage("remove_text", f"{len(items)} 处文字")
    cleaned_png, inpaint_report = textfix.remove_text(
        base_png, items, int(((config.get("inpaint") or {}).get("radius", 7))))
    report["stages"]["remove_text"] = inpaint_report

    vcfg = config.get("vectorize") or {}
    stage("vectorize", "轮廓提取")
    svg, vec_report = vectorizer.vectorize(
        cleaned_png,
        engine=str(vcfg.get("engine", "vtracer")),
        quality="high" if _quality(config) == "high" else "standard",
        colors=int(vcfg.get("colors", 32)),
        speckle=float(vcfg.get("speckle", 40)),
        epsilon=float(vcfg.get("epsilon", 0.8)),
        max_side=int(vcfg.get("max_side", 1600)),
    )
    report["stages"]["vectorize"] = vec_report

    stage("inject_text", f"{len(items)} 处标签")
    svg, inject_report = textfix.inject_text(
        svg, items, scale=float(vec_report.get("scale", 1.0)),
        font=(config.get("font") or "Times New Roman"))
    report["stages"]["inject_text"] = inject_report

    stage("cleanup")
    svg, clean_report = textfix.cleanup(svg, float(((config.get("qa") or {}).get("min_path_area", 6))))
    report["stages"]["cleanup"] = clean_report

    stage("merge")
    svg, merge_report = textfix.merge_color_layers(svg)
    report["stages"]["merge"] = merge_report

    _check_svg(svg)
    stage("qa")
    report["qa"] = qa.run(svg, base_png, vec_report["width"], vec_report["height"], config)
    report["bytes"] = len(svg)
    return svg, report


STAGE_LABELS = {
    "start": "准备任务",
    "generate": "正在生成图像",
    "ocr": "正在识别图中文字",
    "remove_text": "正在清理原文字",
    "vectorize": "正在转换为矢量路径",
    "inject_text": "正在回填可编辑文字",
    "cleanup": "正在清理碎片路径",
    "merge": "正在合并同色图层",
    "qa": "正在做质量检查",
    "plan": "正在规划版面",
    "research": "正在检索并学习顶刊配图",
    "plan_scene": "正在拆分图版素材",
    "assemble": "正在拼装素材与标注",
    "render": "正在绘制图形",
    "svg": "正在生成 SVG",
    "validate": "正在校验结果",
}


def _quality(config: dict) -> str:
    value = str(config.get("quality") or "hd").lower()
    return "high" if value in ("high", "hd", "高清") else "standard"


def _retry_budget(config: dict) -> int:
    return 2 if _quality(config) == "high" else 1


def auto_render(text: str, config: dict, on_stage=None) -> tuple[bytes, dict]:
    """No mode selection for the user: image pipeline when a model exists,
    otherwise plan, otherwise placeholder. Auto-retries on QA failure."""
    image = config.get("image") or {}
    text_model = config.get("text") or {}
    has_image = bool(image.get("mock_path") or (image.get("base_url") and image.get("model")))
    has_text = bool(text_model.get("base_url") and text_model.get("model"))

    render_mode = (config.get("render_mode") or "compose").lower()
    if has_image and render_mode == "compose" and has_text:
        try:
            import compose
            return compose.compose_render(text, config, on_stage=on_stage)
        except ImageServiceError:
            # Never mask an unreachable image model: a white placeholder
            # reported as "completed" looks like a valid 1280x900 result.
            raise
        except Exception as exc:
            # Do not trace a whole generated figure: this mode is supposed
            # to build the layout from per-object assets. Fall back to the
            # text planner so labels stay editable and the failure is visible.
            svg, report = plan_to_svg(text, config, on_stage=on_stage)
            report["compose_fallback"] = str(exc)[:400]
            return svg, report

    if has_image:
        attempts = _retry_budget(config) + 1
        last = None
        last_error = None
        for attempt in range(attempts):
            attempt_config = dict(config)
            attempt_config["_attempt"] = attempt
            try:
                svg, report = image_to_svg(text, attempt_config, on_stage=on_stage)
                report["attempt"] = attempt + 1
                last = (svg, report)
                if (report.get("qa") or {}).get("passed"):
                    return last
            except ImageServiceError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt == attempts - 1 and not has_text:
                    raise
        if last is not None:
            return last
        if not has_text and last_error is not None:
            raise last_error

    if has_text:
        svg, report = plan_to_svg(text, config, on_stage=on_stage)
        report["fallback"] = "plan"
        return svg, report

    svg = placeholder_svg(text)
    return svg, {"mode": "placeholder", "bytes": len(svg)}


def optimize_brief(text: str, config: dict, style: str = "",
                   canvas: list | None = None) -> str:
    text = (text or "").strip()
    if not text:
        raise RuntimeError("请先写一句描述")
    section = config.get("text") or {}
    if not (section.get("base_url") and section.get("model")):
        raise RuntimeError("需要先在设置里配置文本模型")
    user_content = text
    if style:
        user_content = (text + chr(10) + chr(10) + "参考图的视觉风格（必须沿用这些视觉特征，"
                        "但不得照抄图中的具体科学内容）：" + style)
    if canvas and len(canvas) >= 2:
        user_content += (chr(10) * 2 + f"当前画板为 {int(canvas[0])}×{int(canvas[1])} px。"
                         "如果原文没有明确指定其他比例，画布比例必须保持当前画板，"
                         "不要擅自改成 16:9。")
    raw = ""
    last_error: Exception | None = None
    for attempt in range(2):
        prompt = user_content
        if attempt:
            # A long style DNA can make the model spend the whole budget on
            # reasoning and return no answer; retry with a shorter brief.
            prompt = text + chr(10) * 2 + "参考图风格摘要：" + style[:600]
        try:
            raw = _chat(config, [
                {"role": "system", "content": OPTIMIZE_INSTRUCTION},
                {"role": "user", "content": prompt},
            ], temperature=0.35 if attempt == 0 else 0.2,
                max_tokens=3000,
                allow_reasoning_fallback=False)
        except Exception as exc:
            last_error = exc
            continue
        if raw.strip():
            break
    if not raw.strip():
        raise RuntimeError(f"模型没有返回有效内容：{last_error}")
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    lines = [line for line in raw.splitlines() if line.strip()]
    if lines and lines[0].strip().startswith(("好的", "以下是", "优化后", "这是")):
        lines = lines[1:]
    out = chr(10).join(lines).strip()
    if len(out) > 1800:
        out = out[:1800].rsplit("。", 1)[0] + "。"
    if not out:
        raise RuntimeError("模型没有返回有效内容")
    return out


VISION_INSTRUCTION = """你是 Cell / Nature / Science 期刊的视觉编辑与科研图像分析专家。分析用户上传的科研图，只输出一个 JSON 对象，不要解释、不要 markdown。

JSON 字段：
figure_type: 图型（mechanism diagram / flowchart / graphical abstract / multi-panel data figure / illustration / photo / other）
domain: 学科领域
style: 视觉风格（flat vector / semi-realistic / 3D render / hand-drawn / painterly / photo）
layout: 布局（面板数、阅读顺序、主体位置、留白）
palette: 主色数组，最多 6 个 #rrggbb
linework: 线条特征（粗细、描边、圆角、虚线）
typography: 文字层级、字体气质、标签位置
background: 背景（纯白 / 浅灰 / 渐变 / 纹理）
texture: 纹理与光影（无 / 轻度 / 写实）
labels: 图中可见的标签文字数组
style_brief: 120 字以内的中文风格描述，可直接作为绘图提示词

判断依据只看可见的视觉特征：图形语言、配色数量与饱和度、线条粗细、文字层级、面板数量、留白、箭头与标注方式。不要臆造图中不存在的科学结论。"""


def style_summary(style: dict) -> str:
    keys = ("figure_type", "domain", "style", "layout", "palette", "linework",
            "typography", "background", "texture", "style_brief")
    parts = []
    for key in keys:
        value = style.get(key)
        if isinstance(value, list):
            value = "、".join(str(v) for v in value)
        if value:
            parts.append(str(value))
    return "；".join(parts)[:1400]


def _validate_data_url(data_url: str, minimum: int = 128) -> None:
    """Reject empty or truncated uploads before they reach a vision model."""
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        raise RuntimeError("参考图格式无效")
    _, _, payload = data_url.partition(",")
    if len(payload) < minimum:
        raise RuntimeError("参考图内容为空，请重新上传")
    try:
        base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise RuntimeError(f"参考图数据损坏，请重新上传：{exc}")


def analyze_image(data_url: str, config: dict) -> tuple[dict, str]:
    vision = config.get("vision") or {}
    text_cfg = config.get("text") or {}
    source = vision if (vision.get("base_url") and vision.get("model")) else text_cfg
    if not (source.get("base_url") and source.get("model")):
        raise RuntimeError("需要先配置文本模型或视觉模型")
    _validate_data_url(data_url)
    payload = {
        "model": source["model"],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": VISION_INSTRUCTION},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "temperature": 0,
        "max_tokens": 1500,
    }
    response = _post_json(_endpoint(source["base_url"], "/chat/completions"),
                          _api_key(source), payload, timeout=180)
    raw = response["choices"][0]["message"]["content"]
    style = _json_object(raw)
    return style, style_summary(style)


# ---------------------------------------------------------------- entry point


def render(text: str, image: bytes | None, config: dict, on_stage=None) -> tuple[bytes, dict]:
    mode = (config.get("mode") or "placeholder").lower()
    if on_stage:
        on_stage("start", mode)
    if mode == "placeholder":
        svg = placeholder_svg(text, image)
        return svg, {"mode": mode, "bytes": len(svg)}
    if mode == "svg":
        if on_stage:
            on_stage("svg")
        svg = text_to_svg(text, config)
        return svg, {"mode": mode, "bytes": len(svg)}
    if mode == "plan":
        svg, report = plan_to_svg(text, config, on_stage)
        report["mode"] = mode
        return svg, report
    if mode == "image":
        svg, report = image_to_svg(text, config, on_stage)
        report["mode"] = mode
        return svg, report
    if mode == "compose":
        import compose
        svg, report = compose.compose_render(text, config, on_stage)
        report["mode"] = mode
        return svg, report
    if mode == "auto":
        svg, report = auto_render(text, config, on_stage)
        report["mode"] = mode
        return svg, report
    raise RuntimeError(f"unknown pipeline mode: {mode}")


if __name__ == "__main__":
    brief = sys.argv[1] if len(sys.argv) > 1 else "Tumor cell and fibroblast interaction"
    cfg_path = __import__("pathlib").Path(sys.argv[2]) if len(sys.argv) > 2 else \
        __import__("pathlib").Path(__file__).with_name("config.json")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig")) if cfg_path.is_file() else {"mode": "placeholder"}
    out, rep = render(brief, None, cfg)
    target = __import__("pathlib").Path(__file__).with_name("smoke-test.svg")
    target.write_bytes(out)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"wrote {target} ({len(out)} bytes)")
