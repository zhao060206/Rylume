"""Conversion must preserve visible artwork and refuse active/raster content."""
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('art_import',Path(__file__).resolve().parents[1]/'tools/import_scientific_art.py')
art=importlib.util.module_from_spec(spec);spec.loader.exec_module(art)

def test_flat_conversion_preserves_shapes_opacity_and_rounded_strokes():
    raw=b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><g transform="translate(10 10)"><rect x="5" y="5" width="65" height="60" rx="9" fill="#81b8a4" opacity="0.5"/><path d="M20 30L65 65" fill="none" stroke="#315c4c" stroke-width="5" stroke-linecap="round"/></g></svg>'''
    flat,box=art.flat_vector(raw)
    assert '<path' in flat and '<rect' not in flat and 'round' in flat
    assert art.visual_error(raw,flat)<.035

@pytest.mark.parametrize('body',[
    '<image href="https://example.com/image.png"/>',
    '<script>alert(1)</script>', '<foreignObject/>',
    '<text x="1">do not silently lose my labels</text>',
    '<defs><linearGradient id="g"/></defs>',
    '<use href="https://example.com/file.svg#p"/>',
    '<path onload="alert(1)" d="M0 0L20 20"/>',
])
def test_importer_never_silently_drops_unsupported_or_active_art(body):
    raw=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'+body+'</svg>').encode()
    with pytest.raises(ValueError):art.flat_vector(raw)

def test_clipping_that_changes_the_picture_cannot_pass_visual_comparison():
    raw=b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><clipPath id="half"><rect width="50" height="100"/></clipPath></defs><circle clip-path="url(#half)" cx="50" cy="50" r="40" fill="#277660"/></svg>'''
    flat,_=art.flat_vector(raw)
    assert art.visual_error(raw,flat)>.035
    assert art.silhouette_recall(raw,flat)<.94

def test_millimetres_and_transforms_preserve_outline_thickness():
    raw=b'''<svg xmlns="http://www.w3.org/2000/svg" width="50mm" height="30mm" viewBox="0 0 50 30"><g transform="translate(2 2)"><rect x="1" y="1" width="44" height="24" rx="8" fill="#785ef0" stroke="#000" stroke-width="0.65"/><circle cx="13" cy="12" r="5" fill="#ffb000" stroke="#000" stroke-width="0.65"/></g></svg>'''
    flat,_=art.flat_vector(raw)
    assert art.dark_ink_recall(raw,flat)>=.94
    assert art.visual_error(raw,flat)<.035
    assert art.dark_ink_recall(raw,flat.replace('stroke="#000000"','stroke="none"'))<.5
