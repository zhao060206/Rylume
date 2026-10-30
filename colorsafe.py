"""Colour validation for SVG attributes.

Model-generated scenes occasionally return arbitrary strings in colour fields.
Those values are interpolated into SVG attributes and the SVG is later inserted
into the page as HTML, so an unescaped quote would become an event handler.
Only plain hex colours are accepted; everything else falls back to a safe
default instead of failing the whole render.
"""

from __future__ import annotations

import re

_HEX = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def safe_color(value, default: str = "#33475b") -> str:
    text = str(value or "").strip()
    return text if _HEX.fullmatch(text) else default
