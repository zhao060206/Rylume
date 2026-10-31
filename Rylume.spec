# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files, copy_metadata

from pathlib import Path
import sys
sys.path.insert(0,str(Path.cwd()))
# Research reference images require individual publication/license verification.
# Only reviewed scientific art is distributed; research downloads stay local.
datas = [(str(file), 'vendor') for file in Path('vendor').glob('*.py')]
for folder in ('ui', 'assets'):
    for file in Path(folder).rglob('*'):
        if file.is_file() and 'references' not in file.parts:
            datas.append((str(file),str(file.parent)))
binaries = []
hiddenimports = ['svgelements', 'svgpathtools', 'framework', 'archetypes', 'archetypes_render', 'ring_render', 'literature', 'fitz', 'review', 'model_review', 'json_repair', 'rework', 'assist_guide', 'webview', 'clr', 'scene_document', 'scene_examples', 'scene_assets', 'scene_render', 'scene_planner', 'scene_service', 'scene_export', 'studio_storage', 'biology_glyphs', 'scientific_library', 'scene_templates', 'scene_storyboards', 'scene_flows', 'relation_visuals', 'annotation_service', 'annotation_planner']
hiddenimports += ['template_library', 'document_workflows']
hiddenimports += ['resource_packs','github_delivery','app_updates','desktop_delivery']
hiddenimports += ['figure_assets', 'figure_generation', 'figure_references', 'scientific_intent']
hiddenimports += ['sketch_layout']
hiddenimports += ['document_conversion', 'document_advisor', 'document_assistant', 'onboarding_state']
hiddenimports += ['annotation_redraw']
# MarkItDown detects local files with Magika's ONNX data. PDFMiner requires CMaps.
# Keep optional online/audio converters inactive; legacy Office uses local LibreOffice.
for package in ('markitdown', 'magika', 'pdfminer', 'mammoth', 'markdownify', 'openpyxl', 'docx', 'pptx'):
    datas += collect_data_files(package)
for distribution in ('markitdown', 'magika', 'pdfminer.six', 'mammoth', 'markdownify', 'openpyxl', 'beautifulsoup4', 'defusedxml', 'cobble', 'python-docx', 'python-pptx'):
    datas += copy_metadata(distribution)
datas += [('packaging/update-helper.ps1','packaging')]
tmp_ret = collect_all('vtracer')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fitz')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pythonnet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('clr_loader')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('rapidocr_onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['app_server.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['paddleocr', 'paddle', 'scipy', 'matplotlib', 'pandas', 'torch', 'PyQt5', 'PySide6', 'onnxruntime.tools', 'onnxruntime.quantization', 'onnxruntime.transformers', 'transformers', 'IPython', 'pytest', 'jedi', 'sphinx', 'docutils', 'sympy', 'notebook', 'tensorboard', 'numba'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Rylume',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\rylume.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Rylume',
)


