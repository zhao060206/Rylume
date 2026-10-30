"""Raster -> real vector paths, using OpenCV only.

No vtracer/potrace dependency. Works well on flat scientific illustrations
(limited palette, clean edges) and degrades on photos.

Method: palette quantization, one binary mask per palette entry, contour
extraction with holes, polygon simplification, one <path> per color with
fill-rule="evenodd" so holes survive.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import cv2
from PIL import Image


def _decode(png: bytes) -> np.ndarray:
    arr = np.frombuffer(png, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError("cannot decode raster for vectorization")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        rgb = img[:, :, :3].astype(np.float32)
        img = (rgb * alpha + 255.0 * (1 - alpha)).astype(np.uint8)
    return img


def _quantize(bgr: np.ndarray, colors: int) -> tuple[np.ndarray, np.ndarray]:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    # Snap anti-aliased near-white pixels to pure white first; otherwise the
    # palette spends most of its slots on 14 indistinguishable whites and the
    # actual figure colors fall off the palette.
    snap = (rgb[:, :, 0] >= 244) & (rgb[:, :, 1] >= 244) & (rgb[:, :, 2] >= 244)
    rgb = rgb.copy()
    rgb[snap] = 255
    pil = Image.fromarray(rgb)
    quantized = pil.quantize(colors=max(2, colors), method=Image.MEDIANCUT,
                             dither=Image.NONE)
    index = np.array(quantized, dtype=np.int16)
    palette = quantized.getpalette() or []
    table = np.array(palette[: 3 * max(2, colors)], dtype=np.uint8).reshape(-1, 3)
    return index, table


def _contour_path(mask: np.ndarray, epsilon: float, speckle: float) -> tuple[str, int]:
    contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    pieces = []
    kept = 0
    for contour in contours:
        if cv2.contourArea(contour) < speckle:
            continue
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) < 3:
            continue
        points = approx.reshape(-1, 2)
        d = [f"M{int(points[0][0])} {int(points[0][1])}"]
        d += [f"L{int(x)} {int(y)}" for x, y in points[1:]]
        d.append("Z")
        pieces.append("".join(d))
        kept += 1
    return "".join(pieces), kept


def vectorize_cv(png: bytes, *, colors: int = 12, speckle: float = 40.0,
                 epsilon: float = 0.8, max_side: int = 1600) -> tuple[bytes, dict]:
    bgr = _decode(png)
    height, width = bgr.shape[:2]
    scale = 1.0
    if max(width, height) > max_side:
        scale = max_side / max(width, height)
        bgr = cv2.resize(bgr, (max(1, int(width * scale)), max(1, int(height * scale))),
                         interpolation=cv2.INTER_AREA)
        height, width = bgr.shape[:2]

    index, table = _quantize(bgr, colors)
    counts = np.bincount(index.ravel(), minlength=len(table))
    order = np.argsort(-counts)

    paths = []
    kept_total = 0
    for palette_index in order:
        count = int(counts[palette_index])
        if count == 0:
            continue
        red, green, blue = (int(v) for v in table[palette_index])
        if red > 248 and green > 248 and blue > 248:
            continue  # background is already the white base rect
        mask = (index == palette_index).astype(np.uint8) * 255
        # close single-pixel gaps without eating detail
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        d, kept = _contour_path(mask, epsilon, speckle)
        if not d:
            continue
        kept_total += kept
        paths.append(
            f'<path d="{d}" fill="#{red:02x}{green:02x}{blue:02x}" '
            f'fill-rule="evenodd" stroke="none"/>'
        )

    svg = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'  <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>\n'
        + "".join(f"  {p}\n" for p in paths)
        + "</svg>\n"
    ).encode("utf-8")

    report = {
        "engine": "opencv",
        "width": width,
        "height": height,
        "scale": round(scale, 4),
        "palette": int(colors),
        "paths": len(paths),
        "contours": kept_total,
        "bytes": len(svg),
    }
    return svg, report


def vectorize_vtracer(png: bytes, *, quality: str = "high",
                      overrides: dict | None = None) -> tuple[bytes, dict]:
    """vtracer: spline paths, true colors, far better than contour tracing."""
    import tempfile
    import vtracer
    high = quality != "standard"
    params = dict(
        colormode="color", hierarchical="stacked", mode="spline",
        filter_speckle=2 if high else 4,
        color_precision=8 if high else 6,
        layer_difference=8 if high else 16,
        corner_threshold=60, length_threshold=4.0,
        max_iterations=10, splice_threshold=45, path_precision=3,
    )
    if overrides:
        params.update(overrides)
    with tempfile.TemporaryDirectory(prefix="vtracer-") as tmp:
        source = Path(tmp) / "source.png"
        target = Path(tmp) / "result.svg"
        source.write_bytes(png)
        vtracer.convert_image_to_svg_py(str(source), str(target), **params)
        svg = target.read_bytes()
    report = {"engine": "vtracer", "bytes": len(svg), "quality": quality}
    if overrides:
        report["params"] = {k: v for k, v in overrides.items()}
    return svg, report


def vectorize(png: bytes, *, engine: str = "vtracer", quality: str = "high",
              colors: int = 32, speckle: float = 40.0, epsilon: float = 0.8,
              max_side: int = 1600) -> tuple[bytes, dict]:
    if (engine or "vtracer").lower() == "vtracer":
        try:
            return vectorize_vtracer(png, quality=quality)
        except Exception as exc:
            svg, report = vectorize_cv(png, colors=colors, speckle=speckle,
                                       epsilon=epsilon, max_side=max_side)
            report["fallback"] = f"vtracer failed: {exc}"[:200]
            return svg, report
    return vectorize_cv(png, colors=colors, speckle=speckle, epsilon=epsilon,
                        max_side=max_side)
