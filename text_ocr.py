"""Lightweight OCR for raster whole-figure outputs.

The vision critic occasionally reports a clearly rendered label as "missing".
When the deliverable is a single generated illustration, OCR gives the review
an independent transcription to check those claims against.
"""

from __future__ import annotations

import re
from functools import lru_cache

_engine = None
_failed = False


def _get_engine():
    global _engine, _failed
    if _engine is not None or _failed:
        return _engine
    try:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    except Exception:
        _failed = True
        _engine = None
    return _engine


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


@lru_cache(maxsize=16)
def _extract_cached(data: bytes) -> tuple[str, ...]:
    engine = _get_engine()
    if engine is None or not data:
        return ()
    try:
        import cv2
        import numpy as np
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return ()
        result, _ = engine(image)
        rows = []
        for line in result or []:
            text = str(line[1] if len(line) > 1 else "").strip()
            try:
                score = float(line[2]) if len(line) > 2 else 1.0
            except (TypeError, ValueError):
                score = 1.0
            # Low-confidence readings are usually DNA/geometry patterns, not
            # labels; including them creates fake "placeholder" findings.
            if text and score >= 0.75:
                rows.append(text)
        return tuple(rows)
    except Exception:
        return ()


def extract_png(data: bytes) -> list[str]:
    return list(_extract_cached(bytes(data or b"")))


def labels_present(required: list[str], texts: list[str]) -> tuple[list[str], list[str]]:
    """Return (present, missing) using whitespace-insensitive comparison."""
    joined = " ".join(_normalize(text) for text in texts)
    present, missing = [], []
    for name in required:
        key = _normalize(name)
        if not key:
            continue
        if key in joined:
            present.append(name)
        else:
            tokens = [word for word in re.findall(r"[a-z0-9\u4e00-\u9fff]+",
                                                   str(name).lower()) if len(word) > 2]
            hits = sum(1 for word in tokens if _normalize(word) in joined)
            (present if tokens and hits / len(tokens) >= 0.75 else missing).append(name)
    return present, missing
