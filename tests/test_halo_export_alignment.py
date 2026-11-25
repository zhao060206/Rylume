"""Regression: an object label's white halo must stay under its own glyphs
in everything MuPDF rasterises (PNG/PDF export, annotation previews).

MuPDF's SVG->PDF writer puts two adjacent text runs that start at the same
position into one BT/ET block and drops the second Tm, so the second run is
drawn after the first run's advance: one word to the right.  Step 7 drew each
label twice at one origin (fill, then halo stroke), so every exported label
got a white copy beside it.  The older pixel test could not see this: a halo
that has moved away no longer covers the glyphs, so the dark-pixel count of
the glyphs is unchanged.

These tests check, glyph by glyph, that every halo (stroke) glyph lies on a
fill glyph of the same character in the PDF that MuPDF writes.  MuPDF may
merge a fill run with following, separately positioned text into one trace
run, so runs are compared per glyph, not as whole strings.
"""
import pytest

import scene_render
from scene_storyboards import make_storyboard

fitz = pytest.importorskip('fitz')


def _scene():
    return make_storyboard('mapk_branch', width_mm=180, height_mm=120)


def _glyphs(page):
    """(kind, char, x, y) for every glyph MuPDF draws on the page."""
    out = []
    for t in page.get_texttrace():
        kind = 'fill' if t.get('type') == 0 else 'stroke'
        for c in t.get('chars') or []:
            out.append((kind, chr(c[0]), c[3][0], c[3][1]))
    return out


def _misaligned(glyphs):
    fills = [g for g in glyphs if g[0] == 'fill']
    return [s for s in glyphs if s[0] == 'stroke' and not s[1].isspace()
            and not any(f[1] == s[1] and abs(f[2] - s[2]) < 0.2 and abs(f[3] - s[3]) < 0.2 for f in fills)]


def _mupdf_glyphs(svg):
    with fitz.open(stream=svg.encode('utf-8'), filetype='svg') as doc:
        with fitz.open(stream=doc.convert_to_pdf(), filetype='pdf') as pdf:
            return _glyphs(pdf[0])


def test_pdf_export_keeps_halo_on_its_label(tmp_path):
    from scene_export import export_scene
    out = tmp_path / 'fig.pdf'
    export_scene(_scene(), 'pdf', out)
    with fitz.open(out) as pdf:
        glyphs = _glyphs(pdf[0])
    assert any(g[0] == 'stroke' for g in glyphs), 'export has no halo glyphs at all'
    assert _misaligned(glyphs) == []


def test_svg_for_mupdf_aligns_halo_for_previews():
    helper = getattr(scene_render, 'svg_for_mupdf', None)
    assert helper is not None, 'scene_render.svg_for_mupdf is missing'
    glyphs = _mupdf_glyphs(helper(scene_render.render_scene(_scene())))
    assert any(g[0] == 'stroke' for g in glyphs)
    assert _misaligned(glyphs) == []


def test_svg_for_mupdf_leaves_svg_without_halo_unchanged(monkeypatch):
    helper = getattr(scene_render, 'svg_for_mupdf', None)
    assert helper is not None, 'scene_render.svg_for_mupdf is missing'
    monkeypatch.setattr(scene_render, 'LABEL_HALO', {})
    svg = scene_render.render_scene(_scene())
    assert helper(svg) == svg
