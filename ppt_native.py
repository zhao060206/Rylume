"""SVG -> native PowerPoint: real freeform paths + editable text boxes.

This is the no-Cairo fallback for the original `export-ppt` pipeline. It covers
the SVG subset this app produces (rect, ellipse, line, polyline, polygon, path
with M/L/C/Q curves, text). Gradients, clip paths and masks are approximated or
skipped and reported as warnings.

Output: <out_dir>/native.pptx plus an optional PowerPoint-rendered preview.
"""

from __future__ import annotations

import base64
import io
import math
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Emu, Pt
from svgpathtools import parse_path

EMU_PX = 914400.0 / 96.0


def _color(value, default=None):
    if not value or value in ("none", "transparent"):
        return None
    value = value.strip()
    if value.startswith("#"):
        hexa = value[1:]
        if len(hexa) == 3:
            hexa = "".join(ch * 2 for ch in hexa)
        if len(hexa) >= 6:
            try:
                return RGBColor.from_string(hexa[:6].upper())
            except Exception:
                return default
    if value.startswith("rgb("):
        nums = [int(float(v)) for v in re.findall(r"[\d.]+", value)[:3]]
        if len(nums) == 3:
            return RGBColor(*nums)
    if value.startswith("url("):
        return default
    return default


def _num(value, default=0.0):
    try:
        return float(re.match(r"\s*(-?[\d.]+)", str(value)).group(1))
    except Exception:
        return default


def _opacity(node):
    raw = node.get("opacity") or node.get("fill-opacity") or "1"
    return max(0.0, min(1.0, _num(raw, 1.0)))


def _matrix(text):
    """Return (a,b,c,d,e,f) for translate/scale/matrix chains."""
    a, b, c, d, e, f = 1.0, 0.0, 0.0, 1.0, 0.0, 0.0
    if not text:
        return a, b, c, d, e, f
    for name, args in re.findall(r"(translate|scale|matrix|rotate)\s*\(([^)]*)\)", text):
        vals = [float(v) for v in re.findall(r"-?[\d.]+(?:e-?\d+)?", args)]
        if name == "translate" and vals:
            tx = vals[0]
            ty = vals[1] if len(vals) > 1 else 0.0
            e, f = e + a * tx + c * ty, f + b * tx + d * ty
        elif name == "scale" and vals:
            sx = vals[0]
            sy = vals[1] if len(vals) > 1 else sx
            a, b, c, d = a * sx, b * sx, c * sy, d * sy
        elif name == "rotate" and vals:
            deg = vals[0]
            rad = math.radians(deg)
            ca, sa = math.cos(rad), math.sin(rad)
            if len(vals) >= 3:
                cx, cy = vals[1], vals[2]
                e, f = e + a * cx + c * cy, f + b * cx + d * cy
                ra, rb = a * ca + c * sa, b * ca + d * sa
                rc, rd = -a * sa + c * ca, -b * sa + d * ca
                a, b, c, d = ra, rb, rc, rd
                e, f = e - a * cx - c * cy, f - b * cx - d * cy
            else:
                ra, rb = a * ca + c * sa, b * ca + d * sa
                rc, rd = -a * sa + c * ca, -b * sa + d * ca
                a, b, c, d = ra, rb, rc, rd
        elif name == "matrix" and len(vals) == 6:
            na, nb, nc, nd, ne, nf = vals
            a, b, c, d, e, f = (a * na + c * nb, b * na + d * nb,
                                a * nc + c * nd, b * nc + d * nd,
                                a * ne + c * nf + e, b * ne + d * nf + f)
    return a, b, c, d, e, f


def _apply(m, x, y):
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def _m_scale(m) -> float:
    """Uniform scale factor of an SVG matrix (lengths and font sizes)."""
    return max(0.01, math.hypot(m[0], m[1]))


def _first_gradient_stop(root, href):
    ident = (href or "").strip()
    m = re.fullmatch(r"url\(#([^)]+)\)", ident)
    if not m:
        return None
    target = m.group(1)
    for node in root.iter():
        if node.get("id") == target:
            for stop in node.iter():
                if stop.tag.split("}")[-1] == "stop":
                    return _color(stop.get("stop-color") or "#cccccc")
    return None


def _area(points):
    total = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _inside(point, polygon):
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _group_contours(contours):
    """Split contours into outer shapes, attaching contained contours as holes."""
    ordered = sorted(contours, key=lambda c: abs(_area(c)), reverse=True)
    groups = []
    for contour in ordered:
        box = _bbox(contour)
        attached = False
        for group in groups:
            outer_box = _bbox(group["outer"])
            if (box[0] >= outer_box[0] and box[1] >= outer_box[1]
                    and box[2] <= outer_box[2] and box[3] <= outer_box[3]
                    and _inside(contour[0], group["outer"])):
                group["holes"].append(contour)
                attached = True
                break
        if not attached:
            groups.append({"outer": contour, "holes": []})
    return groups


class Builder:
    def __init__(self, root, font, scale_x, scale_y, offset_x, offset_y, on_step=None):
        self.root = root
        self.font = font
        self.sx = scale_x
        self.sy = scale_y
        self.ox = offset_x
        self.oy = offset_y
        self.paths = 0
        self.texts = 0
        self.shapes = 0
        self.warnings = []
        self.on_step = on_step

    def pt(self, x, y, m):
        x, y = _apply(m, x, y)
        return (x - self.ox) * self.sx * EMU_PX, (y - self.oy) * self.sy * EMU_PX

    def fill_of(self, node, default=None):
        value = node.get("fill", default)
        color = _color(value)
        if color is None and value and value.startswith("url("):
            color = _first_gradient_stop(self.root, value)
            if color:
                self.warnings.append("gradient flattened to first stop")
        return color

    def add_path(self, slide, d, node, m, closed=True):
        try:
            path = parse_path(d)
        except Exception as exc:
            self.warnings.append(f"path parse skipped: {exc}")
            return
        contours = []
        for sub in path.continuous_subpaths():
            pts = []
            for seg in sub:
                length = max(1.0, seg.length())
                # Sampling must use final physical scale: a 15 mm biological
                # symbol is much larger than a 15 px legacy shape.
                physical_length = length * _m_scale(m) * max(self.sx, self.sy)
                steps = 1 if seg.__class__.__name__ == "Line" else max(4, min(160, int(physical_length / 1.8) + 1))
                for i in range(steps + 1):
                    p = seg.point(i / steps)
                    pts.append(self.pt(p.real, p.imag, m))
            if len(pts) >= 2:
                contours.append(pts)
        if not contours:
            return
        color = self.fill_of(node)
        stroke = _color(node.get("stroke"))
        width = _num(node.get("stroke-width"), 0.0) * _m_scale(m) * self.sy
        has_marker = bool(node.get("marker-end"))
        groups = _group_contours([c for c in contours if len(c)>=3]) if color is not None else [{"outer":c,"holes":[]} for c in contours]
        for group in groups:
            self._compound(slide, group, color, stroke, width, closed, marker=has_marker)

    def _compound(self, slide, group, color, stroke, width, closed, marker=False):
        outer = group["outer"]
        # If there is no fill (e.g. stroke path/connector), keep it open
        should_close = closed and (color is not None)
        try:
            builder = slide.shapes.build_freeform(outer[0][0], outer[0][1], scale=1.0)
            builder.add_line_segments(outer[1:], close=should_close)
            shape = builder.convert_to_shape()
        except Exception as exc:
            self.warnings.append(f"freeform skipped: {exc}")
            return
        shape.name = f"path {self.paths + 1}"
        _drop_style(shape)
        if color is None:
            shape.fill.background()
        else:
            shape.fill.solid()
            shape.fill.fore_color.rgb = color
        if stroke is None or width <= 0:
            shape.line.fill.background()
        else:
            shape.line.color.rgb = stroke
            shape.line.width = Emu(int(width * EMU_PX))
        if marker and len(outer) >= 2:
            p_last = outer[-1]
            p_prev = outer[-2]
            stroke_col = stroke or RGBColor(0x33, 0x47, 0x5B)
            self._arrow(slide, p_prev[0], p_prev[1], p_last[0], p_last[1], stroke_col, max(1.5, width))
        if group["holes"]:
            from pptx.oxml.ns import qn
            from pptx.oxml.xmlchemy import OxmlElement
            path_list = shape._element.spPr.find(qn('a:custGeom')).find(qn('a:pathLst'))
            base_path = path_list.find(qn('a:path'))
            left, top = int(shape.left), int(shape.top)
            outer_sign = _area(outer) >= 0
            for hole in group["holes"]:
                points = list(hole)
                if (_area(points) >= 0) == outer_sign:
                    points.reverse()
                for index, (x, y) in enumerate(points):
                    tag = 'a:moveTo' if index == 0 else 'a:lnTo'
                    step = OxmlElement(tag)
                    point = OxmlElement('a:pt')
                    point.set('x', str(int(x) - left))
                    point.set('y', str(int(y) - top))
                    step.append(point)
                    base_path.append(step)
                base_path.append(OxmlElement('a:close'))
        self.paths += 1
        self.shapes += 1

    def add_rect(self, slide, node, m):
        x, y = _num(node.get("x")), _num(node.get("y"))
        w, h = _num(node.get("width")), _num(node.get("height"))
        if w <= 0 or h <= 0:
            return
        rot_deg = math.degrees(math.atan2(m[1], m[0]))
        if abs(rot_deg) > 0.1:
            corners = [
                self.pt(x, y, m),
                self.pt(x + w, y, m),
                self.pt(x + w, y + h, m),
                self.pt(x, y + h, m)
            ]
            try:
                builder = slide.shapes.build_freeform(corners[0][0], corners[0][1], scale=1.0)
                builder.add_line_segments(corners[1:], close=True)
                shape = builder.convert_to_shape()
                _drop_style(shape)
                self._paint(shape, node, _m_scale(m))
                self.shapes += 1
                return
            except Exception:
                pass

        x1, y1 = self.pt(x, y, m)
        x2, y2 = self.pt(x + w, y + h, m)
        rounded = _num(node.get("rx"), 0) > 0
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
            Emu(int(min(x1, x2))), Emu(int(min(y1, y2))),
            Emu(int(abs(x2 - x1))), Emu(int(abs(y2 - y1))))
        if rounded:
            try:
                shape.adjustments[0] = min(0.5, _num(node.get("rx")) / min(w, h))
            except Exception:
                pass
        _drop_style(shape)
        self._paint(shape, node, _m_scale(m))
        self.shapes += 1

    def add_ellipse(self, slide, node, m):
        if node.tag.split("}")[-1] == "circle":
            cx, cy, rx, ry = (_num(node.get("cx")), _num(node.get("cy")),
                              _num(node.get("r")), _num(node.get("r")))
        else:
            cx, cy = _num(node.get("cx")), _num(node.get("cy"))
            rx, ry = _num(node.get("rx")), _num(node.get("ry"))
        if rx <= 0 or ry <= 0:
            return
        x1, y1 = self.pt(cx - rx, cy - ry, m)
        x2, y2 = self.pt(cx + rx, cy + ry, m)
        shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, Emu(int(x1)), Emu(int(y1)),
                                       Emu(int(x2 - x1)), Emu(int(y2 - y1)))
        _drop_style(shape)
        self._paint(shape, node, _m_scale(m))
        self.shapes += 1

    def _paint(self, shape, node, scale: float = 1.0):
        color = self.fill_of(node)
        stroke = _color(node.get("stroke"))
        width = _num(node.get("stroke-width"), 0.0) * scale * self.sy
        if color is None:
            shape.fill.background()
        else:
            shape.fill.solid()
            shape.fill.fore_color.rgb = color
        if stroke is None or width <= 0:
            shape.line.fill.background()
        else:
            shape.line.color.rgb = stroke
            shape.line.width = Emu(int(width * EMU_PX))
            if node.get("stroke-dasharray"):
                shape.line.dash_style = MSO_LINE_DASH_STYLE.DASH

    def add_line(self, slide, node, m):
        x1, y1 = self.pt(_num(node.get("x1")), _num(node.get("y1")), m)
        x2, y2 = self.pt(_num(node.get("x2")), _num(node.get("y2")), m)
        color = _color(node.get("stroke")) or RGBColor(0x10, 0x2A, 0x33)
        width = _num(node.get("stroke-width"), 1.0) * _m_scale(m) * self.sy
        shape = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Emu(int(x1)),
                                           Emu(int(y1)), Emu(int(x2)), Emu(int(y2)))
        _drop_style(shape)
        shape.line.color.rgb = color
        shape.line.width = Emu(int(width * EMU_PX))
        if node.get("stroke-dasharray"):
            shape.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        if node.get("marker-end"):
            self._arrow(slide, x1, y1, x2, y2, color, width)
        self.shapes += 1

    def _arrow(self, slide, x1, y1, x2, y2, color, width):
        angle = math.atan2(y2 - y1, x2 - x1)
        size = max(8.0 * EMU_PX, width * 3.0 * EMU_PX)
        wing = angle + math.pi * 0.82
        left = (x2 + size * math.cos(wing), y2 + size * math.sin(wing))
        wing = angle - math.pi * 0.82
        right = (x2 + size * math.cos(wing), y2 + size * math.sin(wing))
        builder = slide.shapes.build_freeform(x2, y2, scale=1.0)
        builder.add_line_segments([left, right], close=True)
        shape = builder.convert_to_shape()
        shape.fill.solid()
        shape.fill.fore_color.rgb = color
        shape.line.fill.background()

    def add_image(self, slide, node, m):
        href = (node.get("href") or node.get("{http://www.w3.org/1999/xlink}href") or "")
        if not href.startswith("data:image/"):
            self.warnings.append("external image skipped")
            return
        try:
            header, payload = href.split(",", 1)
            raw = base64.b64decode(payload)
        except Exception as exc:
            self.warnings.append(f"image decode skipped: {exc}")
            return
        x, y = _num(node.get("x")), _num(node.get("y"))
        w, h = _num(node.get("width"), 0), _num(node.get("height"), 0)
        if w <= 0 or h <= 0:
            return
        x1, y1 = self.pt(x, y, m)
        x2, y2 = self.pt(x + w, y + h, m)
        try:
            slide.shapes.add_picture(io.BytesIO(raw), Emu(int(x1)), Emu(int(y1)),
                                     Emu(int(x2 - x1)), Emu(int(y2 - y1)))
            self.shapes += 1
        except Exception as exc:
            self.warnings.append(f"picture skipped: {exc}")

    def add_text(self, slide, node, m):
        # Multiline <text> carries each visual line in its own <tspan>; joining
        # them into one string collapses the layout in PowerPoint. Keep the
        # per-tspan lines as separate paragraphs in one text box.
        tspans = [child for child in node
                  if child.tag.split("}")[-1] == "tspan" and (child.text or "").strip()]
        lines = [(child.text or "").strip() for child in tspans]
        if not lines:
            # Ring labels live in <textPath> and have no direct text node.
            paths = [child for child in node if child.tag.split("}")[-1] == "textPath"]
            inline = "".join("".join(p.itertext()) for p in paths).strip()
            if not inline:
                inline = (node.text or "").strip()
            if not inline:
                return
            lines = [inline]
        text = " ".join(lines)
        size_px = _num(node.get("font-size"), 16.0)
        m_scale = _m_scale(m)
        arc_x = node.get("data-ppt-x")
        arc_y = node.get("data-ppt-y")
        if arc_x is not None and arc_y is not None:
            # Text drawn on a ring path: place a rotated, editable text box at
            # the arc midpoint (PowerPoint cannot follow an arbitrary path).
            x, y = self.pt(_num(arc_x), _num(arc_y), m)
        else:
            x, y = self.pt(_num(node.get("x")), _num(node.get("y")), m)
        size_emu = size_px * m_scale * self.sy * EMU_PX
        anchor = node.get("data-ppt-anchor") or node.get("text-anchor", "start")
        width = max(size_emu * 1.5, len(text) * size_emu * 0.65 + size_emu * 0.5)
        left = x
        if anchor == "middle":
            left = x - width / 2
        elif anchor == "end":
            left = x - width
        top = y - size_emu * 0.86
        line_gap = _num(node.get("data-line-step"), size_px * 1.28)
        box_h = size_emu * 1.5 + (len(lines) - 1) * line_gap * m_scale * self.sy * EMU_PX
        box = slide.shapes.add_textbox(Emu(int(left)), Emu(int(top)),
                                       Emu(int(width)), Emu(int(box_h)))
        if node.get("data-ppt-rot") is not None:
            rot_deg = _num(node.get("data-ppt-rot"), 0.0)
        else:
            rot_deg = math.degrees(math.atan2(m[1], m[0]))
        if abs(rot_deg) > 0.1:
            try:
                box.rotation = (rot_deg % 360)
            except Exception:
                pass
        frame = box.text_frame
        frame.word_wrap = False
        frame.auto_size = MSO_AUTO_SIZE.NONE
        frame.vertical_anchor = MSO_ANCHOR.TOP
        frame.margin_left = frame.margin_right = 0
        frame.margin_top = frame.margin_bottom = 0
        para = frame.paragraphs[0]
        para.alignment = {"middle": PP_ALIGN.CENTER, "end": PP_ALIGN.RIGHT}.get(anchor, PP_ALIGN.LEFT)
        for index, line in enumerate(lines):
            if index > 0:
                para = frame.add_paragraph()
                para.alignment = {"middle": PP_ALIGN.CENTER, "end": PP_ALIGN.RIGHT}.get(anchor, PP_ALIGN.LEFT)
            run = para.add_run()
            run.text = line
            run.font.size = Pt(size_px * 0.75 * m_scale * self.sy)
            run.font.name = self.font
            fw = (node.get("font-weight") or "").lower()
            if fw in ("bold", "700", "800", "900"):
                run.font.bold = True
            fs = (node.get("font-style") or "").lower()
            if fs in ("italic", "oblique"):
                run.font.italic = True
            color = self.fill_of(node) or RGBColor(0x10, 0x2A, 0x33)
            run.font.color.rgb = color
        self.texts += 1

    def walk(self, slide, container, m):
        for node in container:
            tag = node.tag.split("}")[-1]
            if tag in ("defs", "marker", "metadata", "title", "desc", "style"):
                continue
            local = _matrix(node.get("transform"))
            combined = (
                m[0] * local[0] + m[2] * local[1],
                m[1] * local[0] + m[3] * local[1],
                m[0] * local[2] + m[2] * local[3],
                m[1] * local[2] + m[3] * local[3],
                m[0] * local[4] + m[2] * local[5] + m[4],
                m[1] * local[4] + m[3] * local[5] + m[5],
            )
            if tag == "g" or tag == "svg":
                scientific_id = node.get("data-object-id") or node.get("data-relation-id")
                if scientific_id:
                    # A scientific object is one selectable group in PowerPoint;
                    # its paths and live labels remain individually editable.
                    from types import SimpleNamespace
                    group = slide.shapes.add_group_shape()
                    group.name = scientific_id
                    self.walk(SimpleNamespace(shapes=group.shapes), node, combined)
                else:
                    self.walk(slide, node, combined)
            elif tag == "rect":
                self.add_rect(slide, node, combined)
            elif tag in ("circle", "ellipse"):
                self.add_ellipse(slide, node, combined)
            elif tag == "line":
                self.add_line(slide, node, combined)
            elif tag in ("polyline", "polygon"):
                points = re.findall(r"-?[\d.]+", node.get("points", ""))
                pts = [(self.pt(float(points[i]), float(points[i + 1]), combined))
                       for i in range(0, len(points) - 1, 2)]
                if len(pts) >= 2:
                    builder = slide.shapes.build_freeform(pts[0][0], pts[0][1], scale=1.0)
                    builder.add_line_segments(pts[1:], close=(tag == "polygon"))
                    shape = builder.convert_to_shape()
                    self._paint(shape, node, _m_scale(m))
                    self.paths += 1
            elif tag == "path":
                self.add_path(slide, node.get("d", ""), node, combined,
                              closed=not node.get("fill", "").lower() == "none")
            elif tag == "text":
                self.add_text(slide, node, combined)
            elif tag == "image":
                self.add_image(slide, node, combined)
            if tag in ("rect", "circle", "ellipse", "line", "polyline", "polygon",
                       "path", "text", "image") and self.on_step:
                self.on_step()


def _drop_style(shape):
    """Remove the theme style (fill/line/effect incl. shadow) so only explicit
    SVG fill and stroke are rendered."""
    try:
        from pptx.oxml.ns import qn
        element = shape._element
        style = element.find(qn("p:style"))
        if style is not None:
            element.remove(style)
    except Exception:
        pass


def _canvas(root):
    def length(value, fallback):
        if value is None or str(value).endswith("%"):
            return fallback
        m = re.fullmatch(r"\s*([+\-\d.eE]+)\s*(px|pt|pc|mm|cm|in)?\s*", str(value))
        if not m:
            return fallback
        return float(m.group(1)) * {None: 1.0, "px": 1.0, "pt": 96 / 72, "pc": 16.0,
                                    "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0}[m.group(2)]
    vb = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox", "").strip()) if v]
    if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
        width = length(root.get("width"), vb[2])
        height = length(root.get("height"), vb[3])
        return width, height, vb
    width = length(root.get("width"), 1280.0)
    height = length(root.get("height"), 900.0)
    return width, height, [0.0, 0.0, width, height]


def _preview(pptx_path: Path, png_path: Path) -> str | None:
    """Render slide 1 to PNG, preferring headless LibreOffice.

    PowerPoint COM intermittently raises RPC_E_DISCONNECTED mid-export on
    Windows and takes the caller down with a fatal exception; LibreOffice is
    slower but stable and does not require an interactive session.
    """
    soffice = shutil.which("soffice") or r"C:\Program Files\LibreOffice\program\soffice.exe"
    if Path(soffice).is_file():
        try:
            with tempfile.TemporaryDirectory(prefix="ppt-preview-") as tmp:
                profile = Path(tmp) / "profile"
                subprocess.run([
                    soffice, "--headless", "--norestore",
                    f"-env:UserInstallation={profile.as_uri()}",
                    "--convert-to", "png", "--outdir", tmp, str(pptx_path),
                ], check=False, capture_output=True, timeout=180)
                candidate = Path(tmp) / (pptx_path.stem + ".png")
                if candidate.is_file() and candidate.stat().st_size:
                    shutil.copyfile(candidate, png_path)
                    return str(png_path)
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        import win32com.client
        app = win32com.client.DispatchEx("PowerPoint.Application")
        try:
            presentation = app.Presentations.Open(str(pptx_path), WithWindow=False)
            try:
                presentation.Slides(1).Export(str(png_path), "PNG", 0, 0)
            finally:
                presentation.Close()
        finally:
            app.Quit()
        return str(png_path) if png_path.is_file() else None
    except Exception:
        return None


_DRAWABLE = {"rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text", "image"}


def _drawable_count(root) -> int:
    total = 0
    for node in root.iter():
        tag = node.tag.split("}")[-1]
        if tag in _DRAWABLE:
            total += 1
    return max(1, total)


def build(svg_path, out_dir, *, font="Times New Roman", progress=None, preview=True) -> dict:
    svg_path = Path(svg_path).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    root = ET.fromstring(svg_path.read_bytes())
    width, height, vb = _canvas(root)
    scale_x = width / vb[2]
    scale_y = height / vb[3]

    presentation = Presentation()
    presentation.slide_width = Emu(int(width * EMU_PX))
    presentation.slide_height = Emu(int(height * EMU_PX))
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])

    total = _drawable_count(root)
    state = {"done": 0, "last": 0.0}

    def step():
        state["done"] += 1
        now = time.time()
        if progress and (now - state["last"] > 0.25 or state["done"] == total):
            state["last"] = now
            progress(min(0.84, state["done"] / total * 0.84),
                     f"写入形状 {state['done']}/{total}", total)

    builder = Builder(root, font, scale_x, scale_y, vb[0], vb[1], on_step=step)
    builder.walk(slide, root, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    # Round/cropped viewports clip the figure body in SVG. PowerPoint has no
    # per-shape clip, so mirror the frame: draw the clip shape on top in the
    # paper colour so overflowing content reads as cropped, and note it.
    clip_defs = {}
    for node in root.iter():
        if node.tag.split("}")[-1] != "clipPath":
            continue
        for child in node:
            ctag = child.tag.split("}")[-1]
            if ctag == "rect":
                clip_defs[child.get("id") or node.get("id") or ""] = ("rect", child)
            elif ctag == "circle":
                clip_defs[child.get("id") or node.get("id") or ""] = ("circle", child)
            elif ctag == "ellipse":
                clip_defs[child.get("id") or node.get("id") or ""] = ("ellipse", child)
    used_clips = {m.group(1)
                  for node in root.iter()
                  for m in [re.search(r"url\(#([^)]+)\)", node.get("clip-path") or "")]
                  if m}
    paper = RGBColor(0xFF, 0xFF, 0xFF)
    for key, (ctag, child) in clip_defs.items():
        if key not in used_clips:
            continue
        if ctag == "rect":
            w, h = _num(child.get("width"), 0), _num(child.get("height"), 0)
            if w < width * 0.5 or h < height * 0.5:
                continue  # entity-level clip: too small to fake with frames
            x1, y1 = builder.pt(_num(child.get("x")), _num(child.get("y")), (1, 0, 0, 1, 0, 0))
            x2, y2 = builder.pt(_num(child.get("x")) + w, _num(child.get("y")) + h, (1, 0, 0, 1, 0, 0))
            frame = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(int(x1)), Emu(int(y1)),
                                           Emu(int(x2 - x1)), Emu(int(y2 - y1)))
        elif ctag == "circle":
            r = _num(child.get("r"), 0)
            if r < min(width, height) * 0.3:
                continue
            cx, cy = builder.pt(_num(child.get("cx")), _num(child.get("cy")), (1, 0, 0, 1, 0, 0))
            frame = slide.shapes.add_shape(MSO_SHAPE.OVAL,
                                           Emu(int(cx - r * scale_x)), Emu(int(cy - r * scale_y)),
                                           Emu(int(2 * r * scale_x)), Emu(int(2 * r * scale_y)))
        else:
            rx, ry = _num(child.get("rx"), 0), _num(child.get("ry"), 0)
            if rx < width * 0.3:
                continue
            cx, cy = builder.pt(_num(child.get("cx")), _num(child.get("cy")), (1, 0, 0, 1, 0, 0))
            frame = slide.shapes.add_shape(MSO_SHAPE.OVAL,
                                           Emu(int(cx - rx * scale_x)), Emu(int(cy - ry * scale_y)),
                                           Emu(int(2 * rx * scale_x)), Emu(int(2 * ry * scale_y)))
        try:
            frame.fill.solid()
            frame.fill.fore_color.rgb = paper
            frame.line.fill.background()
            # four paper bands around the clip shape mask everything outside it
            x1f, y1f, x2f, y2f = frame.left, frame.top, frame.left + frame.width, frame.top + frame.height
            bands = [
                (0, 0, int(width * EMU_PX), int(max(0, y1f))),
                (0, int(y2f), int(width * EMU_PX), int(max(0, height * EMU_PX - y2f))),
            ]
            for bx, by, bw, bh in bands:
                if bw > 0 and bh > 0:
                    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(int(bx)), Emu(int(by)),
                                                  Emu(int(bw)), Emu(int(bh)))
                    band.fill.solid()
                    band.fill.fore_color.rgb = paper
                    band.line.fill.background()
            frame.fill.background()  # keep the clip window itself transparent
        except Exception as exc:
            builder.warnings.append(f"viewport clip skipped: {exc}")
        builder.warnings.append(
            "viewport clip approximated with paper-coloured frame; check the crop visually")

    pptx_path = out_dir / "native.pptx"
    presentation.save(str(pptx_path))
    if progress:
        progress(0.86, "保存 PPTX", total)
    preview_path = _preview(pptx_path, out_dir / "preview.png") if preview else None
    report = {
        "mode": "native-paths-lite",
        "pptx": str(pptx_path),
        "preview": preview_path,
        "font": font,
        "paths": builder.paths,
        "texts": builder.texts,
        "shapes": builder.shapes,
        "warnings": sorted(set(builder.warnings)),
        "canvas": [width, height],
    }
    import json
    (out_dir / "native.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    if progress:
        progress(0.96, "生成 PPTX 预览", total)
    return report


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--font", default="Times New Roman")
    args = ap.parse_args()
    print(build(args.svg, args.output, font=args.font))
