"""Text removal, text re-injection and vector cleanup."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import cv2
import numpy as np

SVG_NS = "http://www.w3.org/2000/svg"


def _decode(png: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("cannot decode raster")
    return image


def remove_text(png: bytes, items: list[dict], radius: int = 7) -> tuple[bytes, dict]:
    image = _decode(png)
    if not items:
        return png, {"removed": 0, "bytes": len(png)}
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    for item in items:
        x, y, w, h = (int(round(v)) for v in item["bbox"])
        pad = max(2, int(radius * 0.6))
        cv2.rectangle(mask, (max(0, x - pad), max(0, y - pad)),
                      (min(image.shape[1] - 1, x + w + pad),
                       min(image.shape[0] - 1, y + h + pad)), 255, -1)
    mask = cv2.dilate(mask, np.ones((radius, radius), np.uint8), iterations=1)
    cleaned = cv2.inpaint(image, mask, radius, cv2.INPAINT_TELEA)
    ok, encoded = cv2.imencode(".png", cleaned)
    if not ok:
        raise RuntimeError("cannot encode cleaned raster")
    return encoded.tobytes(), {"removed": len(items), "bytes": int(encoded.size)}


def _text_node(parent: ET.Element, item: dict, scale: float, font: str) -> None:
    x, y, w, h = (_ * scale for _ in item["bbox"])
    size = max(4.0, float(item.get("font_size", h * 0.82)) * scale)
    node = ET.SubElement(parent, f"{{{SVG_NS}}}text", {
        "x": f"{x:.1f}",
        "y": f"{y + h * 0.82:.1f}",
        "font-family": font,
        "font-size": f"{size:.1f}",
        "fill": item.get("color", "#102a33"),
        "{http://www.w3.org/XML/1998/namespace}space": "preserve",
    })
    node.text = item["text"]


def inject_text(svg: bytes, items: list[dict], scale: float = 1.0,
                font: str = "Times New Roman") -> tuple[bytes, dict]:
    if not items:
        return svg, {"injected": 0}
    ET.register_namespace("", SVG_NS)
    root = ET.fromstring(svg)
    group = ET.SubElement(root, f"{{{SVG_NS}}}g", {"id": "restored-text"})
    for item in items:
        _text_node(group, item, scale, font)
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return data, {"injected": len(items), "font": font}


def cleanup(svg: bytes, min_area: float = 6.0) -> tuple[bytes, dict]:
    ET.register_namespace("", SVG_NS)
    root = ET.fromstring(svg)
    removed = 0
    for parent in list(root.iter()):
        for child in list(parent):
            tag = child.tag.split("}")[-1].lower()
            if tag != "path":
                continue
            if _path_area(child) < min_area:
                parent.remove(child)
                removed += 1
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return data, {"removed_paths": removed}


def _path_area(node: ET.Element) -> float:
    d = node.get("d", "")
    numbers = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", d)]
    if len(numbers) < 6:
        return 0.0
    xs = numbers[0::2]
    ys = numbers[1::2]
    if len(xs) < 2 or len(ys) < 2:
        return 0.0
    return max(0.0, (max(xs) - min(xs)) * (max(ys) - min(ys)))


def merge_color_layers(svg: bytes, tolerance: int = 12) -> tuple[bytes, dict]:
    """Merge adjacent paths that share a visually identical fill."""
    ET.register_namespace("", SVG_NS)
    root = ET.fromstring(svg)
    buckets: dict[str, ET.Element] = {}
    merged = 0
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag.split("}")[-1].lower() != "path":
                continue
            fill = (child.get("fill") or "").lower()
            if not re.fullmatch(r"#[0-9a-f]{6}", fill):
                continue
            bucket = buckets.get(fill)
            if bucket is None:
                buckets[fill] = child
                continue
            bucket.set("d", (bucket.get("d", "") + " " + child.get("d", "")).strip())
            parent.remove(child)
            merged += 1
    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return data, {"merged_paths": merged}
