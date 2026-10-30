"""Text detection for the image pipeline.

Two providers:

  vision  a multimodal chat model returns JSON boxes. Works with any
          OpenAI-compatible gateway that accepts image_url content.
  paddle  local PaddleOCR. Heavy, downloads weights on first use.
  none    disable text restoration.

Every provider returns the same shape:
  [{"text": str, "bbox": [x, y, w, h], "font_size": float, "color": "#rrggbb"}]
"""

from __future__ import annotations

import base64
import json
import re
import urllib.request

import numpy as np

PROMPT = (
    "Detect every visible text string in this scientific figure. Return ONLY a "
    "JSON array, no markdown. Each item: {\"text\": exact characters, "
    "\"bbox\": [x, y, width, height] in image pixels, \"font_size\": estimated "
    "pixel height, \"color\": \"#rrggbb\"}. Read left-to-right, top-to-bottom. "
    "Never merge separate labels. Never invent text. Empty array if none."
)


def _post(url: str, key: str, payload: dict, timeout: int = 180) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}" if key else ""},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _endpoint(base_url: str, suffix: str) -> str:
    base = base_url.rstrip("/")
    return base + suffix if base.endswith("/v1") else base + "/v1" + suffix


def _key(section: dict) -> str:
    if section.get("api_key"):
        return str(section["api_key"])
    env = section.get("api_key_env")
    return __import__("os").environ.get(env, "") if env else ""


def _strip_json(raw: str) -> list:
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise RuntimeError("OCR model did not return a JSON array")
    return json.loads(raw[start:end + 1])


def _normalize(items: list, width: int, height: int) -> list[str]:
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        bbox = item.get("bbox")
        if not text or not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        x, y, w, h = (float(v) for v in bbox)
        if w <= 0 or h <= 0:
            continue
        x = max(0.0, min(x, width - 1))
        y = max(0.0, min(y, height - 1))
        w = min(w, width - x)
        h = min(h, height - y)
        color = str(item.get("color") or "#102a33")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            color = "#102a33"
        result.append({
            "text": text,
            "bbox": [round(x, 1), round(y, 1), round(w, 1), round(h, 1)],
            "font_size": float(item.get("font_size") or max(10.0, h * 0.82)),
            "color": color.lower(),
        })
    return result


def detect_vision(png: bytes, config: dict) -> list[dict]:
    section = config.get("ocr") or {}
    source = section if section.get("base_url") else (config.get("text") or {})
    if not source.get("base_url") or not source.get("model"):
        raise RuntimeError("ocr.provider=vision needs base_url and model")
    data_url = "data:image/png;base64," + base64.b64encode(png).decode()
    payload = {
        "model": section.get("model") or source["model"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "temperature": 0,
    }
    response = _post(_endpoint(source["base_url"], "/chat/completions"),
                     _key(section) or _key(source), payload)
    raw = response["choices"][0]["message"]["content"]
    import cv2
    height, width = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR).shape[:2]
    return _normalize(_strip_json(raw), width, height)


def detect_paddle(png: bytes, config: dict) -> list[dict]:
    import tempfile
    from pathlib import Path
    import cv2
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError("PaddleOCR is not installed") from exc

    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    height, width = image.shape[:2]
    with tempfile.TemporaryDirectory(prefix="ocr-") as tmp:
        path = Path(tmp) / "input.png"
        path.write_bytes(png)
        engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        raw = engine.ocr(str(path))
    items = []
    for page in raw or []:
        for entry in page or []:
            box, (text, score) = entry[0], entry[1]
            if float(score) < 0.5:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x, y = min(xs), min(ys)
            w, h = max(xs) - x, max(ys) - y
            items.append({"text": text, "bbox": [x, y, w, h],
                          "font_size": h * 0.82, "color": "#102a33"})
    return _normalize(items, width, height)


def detect(png: bytes, config: dict) -> tuple[list[dict], dict]:
    provider = ((config.get("ocr") or {}).get("provider") or "none").lower()
    if provider == "none":
        return [], {"provider": "none", "count": 0, "restored": False}
    if provider == "vision":
        items = detect_vision(png, config)
    elif provider == "paddle":
        items = detect_paddle(png, config)
    else:
        raise RuntimeError(f"unknown ocr provider: {provider}")
    return items, {"provider": provider, "count": len(items), "restored": bool(items)}
