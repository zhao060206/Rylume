"""Exercise the shipped shell and real service with disposable data, using Edge."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.request import urlopen
from zipfile import ZipFile

from PIL import Image
import fitz
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def isolated_server():
    with TemporaryDirectory() as data:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'
        server = subprocess.Popen([sys.executable, str(ROOT / 'app_server.py'), '--no-window',
                                   '--no-migrate', '--port', str(port), '--data-dir', data])
        try:
            for attempt in range(80):
                if server.poll() is not None:
                    raise RuntimeError('Test server exited during startup')
                try:
                    with urlopen(base, timeout=1):
                        break
                except OSError:
                    time.sleep(.25)
            else:
                raise RuntimeError('Test server did not start')
            yield base
        finally:
            server.terminate()
            server.wait(timeout=15)


def exercise(page, base, output):
    page.set_default_timeout(12000)
    find = page.locator
    page.goto(base)
    find('#onboarding-explore').click()
    expect(find('.home-template-example')).to_have_count(3)
    page.screenshot(path=output / 'home.png')
    find('#draw-sketch').click()
    paper=find('#sketch-pad').bounding_box()
    x,y=paper['x']+40,paper['y']+60
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+80,y+40,steps=10);page.mouse.up()
    find('#use-drawn-sketch').click();expect(find('#sketch-pad-dialog')).not_to_be_visible()
    if not find('#clear-generation-reference').is_visible():find('#composer-attach').click()
    expect(find('#generation-reference-preview')).to_be_visible();find('#clear-generation-reference').click()
    if find('#composer-attach').get_attribute('aria-expanded')=='true':find('#composer-attach').click()
    for width in (390, 760, 1024, 1280):
        page.set_viewport_size({'width': width, 'height': 800})
        for selector in ('#generate', '#welcome-blank', '#home-convert-figure', '#welcome-gallery'):
            bounds = find(selector).bounding_box()
            assert bounds and bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1, (width, selector, bounds)
        if width == 390:
            find('.compact-projects summary').click()
            find('.compact-projects [data-command=open-history]').click()
            expect(find('#history-dialog')).to_be_visible()
            find('[data-close=history-dialog]').click()
            page.screenshot(path=output / 'narrow-home.png')
    find('#create-project').click()
    find('#project-name').fill('仪器校准')
    find('#project-dialog .primary').click()
    find('#welcome-blank').click()
    expect(find('#empty-add-text')).to_be_visible()
    page.screenshot(path=output / 'blank.png')
    find('#empty-add-text').click()
    text = 'Calibration check'
    inline = find('.editor-inline-input')
    inline.fill(text)
    inline.press('Enter')
    find('#save-document').click()
    job = page.url.split('#')[-1]
    def scene():
        return page.request.get(f'{base}/api/jobs/{job}/scene').json()['scene']
    assert any(obj['label'] == text for obj in scene()['objects'])
    projects = page.request.get(base + '/api/projects').json()
    assert job in projects['documents']
    page.reload()
    label = find('#canvas-host [data-label-for]').filter(has_text=text).first
    expect(label).to_be_visible()
    before = scene()['objects'][0]
    bounds = label.bounding_box()
    x, y = bounds['x'] + bounds['width']/2, bounds['y'] + bounds['height']/2
    page.mouse.move(x,y); page.mouse.down(); page.mouse.move(x+60,y+30,steps=12); page.mouse.up()
    find('#save-document').click()
    moved = scene()['objects'][0]
    assert (moved['x'], moved['y']) != (before['x'], before['y'])
    find('#undo').click(); find('#save-document').click()
    assert scene()['objects'][0]['x'] == before['x']
    find('#redo').click(); find('#save-document').click()
    assert scene()['objects'][0]['x'] == moved['x']
    print('PASS project, save/reopen, real pointer drag and undo/redo', flush=True)
    find('#open-check-toolbar').click(); expect(find('#inspector-review')).to_be_visible()
    find('#canvas-settings').click(); expect(find('#property-content')).to_be_visible()
    page.set_viewport_size({'width':390,'height':800})
    expect(find('#save-document')).to_be_in_viewport();expect(find('#save-status')).to_be_in_viewport()
    find('#open-annotations').click();expect(page.get_by_role('button',name='整图要求',exact=True)).to_be_in_viewport()
    page.get_by_role('button',name='关闭批注面板').click();page.set_viewport_size({'width':1280,'height':800})
    find('#open-annotations').click(); page.get_by_role('button', name='整图要求',exact=True).click()
    find('.annotation-list textarea').fill('放大标题')
    page.wait_for_function("document.querySelector('.annotation-save').textContent.includes('已保存')")
    assert page.request.get(f'{base}/api/jobs/{job}/annotations').json()['notes'][0]['instruction']=='放大标题'
    find('#open-annotations').click()
    find('#toggle-export').click()
    page.screenshot(path=output / 'export.png')
    for fmt in ('svg','pdf','pptx','png'):
        with page.expect_response(lambda r: r.url.endswith('/save-as') and r.request.method == 'POST') as request:
            find(f'[data-export={fmt}]').click()
        result = request.value.json()
        path = Path(result['path'])
        assert path.is_file() and result['revision'] == scene()['revision']
        if fmt == 'svg': assert text in path.read_text('utf8')
        elif fmt == 'pdf':
            with fitz.open(path) as doc: assert len(doc) == 1 and doc[0].rect.width > 500
        elif fmt == 'pptx':
            with ZipFile(path) as slides: assert text.encode() in slides.read('ppt/slides/slide1.xml')
        else:
            with Image.open(path) as image: assert abs(image.width-180*300/25.4)<2
    find('#close-export').click()
    page.route('**/export-info',lambda route: route.fulfill(status=503,json={'ok':False,'error':'QA 服务暂不可用'}))
    find('#toggle-export').click();expect(find('.export-summary')).to_contain_text('未能读取')
    find('#close-export').click();page.unroute('**/export-info')
    print('PASS review, canvas properties, persisted annotation, four actual export files',flush=True)
    find('#sidebar-assets').click();find('#asset-language-en').click();expect(find('#asset-library-dialog')).to_have_attribute('lang','en')
    find('#asset-library-dialog .floating-minimize').click();find('.window-restore-button').click();find('#asset-language-zh').click()
    object_count=len(scene()['objects']);find('#asset-list .asset-insert').first.click()
    find('[data-close=asset-library-dialog]').click()
    find('#save-document').click();assert len(scene()['objects'])==object_count+1
    find('#toggle-documents').click();find('#document-files').set_input_files({'name':'calibration.txt','mimeType':'text/plain','buffer':b'Calibration record: read the meter, compare the measured value, record the result.'})
    expect(find('#document-list')).to_contain_text('calibration.txt');find('#document-list').get_by_role('button',name='查看 Markdown').click()
    expect(find('#document-markdown')).to_be_visible()
    assert 'Calibration record: read the meter, compare the measured value, record the result.' in find('#document-markdown').input_value()
    find('#document-preview-close').click();find('#close-documents').click()
    find('#toolbar-import-figure').click()
    source=b'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="280" viewBox="0 0 480 280"><rect x="40" y="50" width="140" height="60" fill="#abcabc"/><text x="45" y="88" font-size="20">Meter</text></svg>'
    find('#figure-import-file').set_input_files({'name':'meter.svg','mimeType':'image/svg+xml','buffer':source})
    find('#figure-import-convert').click();find('#figure-import-accept').click(timeout=90000)
    page.wait_for_function('(old)=>location.hash!==old',arg='#'+job)
    job=page.url.split('#')[-1];assert any(o['label']=='Meter' for o in scene()['objects'])
    page.screenshot(path=output / 'imported.png')
    print('PASS bilingual library, minimize/restore, document Markdown, editable SVG import',flush=True)
    find('#open-start').click();find('.home-template-example').first.click();find('#template-detail-size').select_option('single');find('#template-detail-create').click()
    page.wait_for_function('(old)=>location.hash.length>1 && location.hash!==old',arg='#'+job)
    job=page.url.split('#')[-1];template=scene()
    assert template['canvas']['width_mm']==90 and template['relations'] and template['objects']
    find('.workspace-mode-switch [data-workspace-mode=professional]').click()
    expect(find('html')).to_have_attribute('data-workspace-mode','professional')
    find('.workspace-mode-switch [data-workspace-mode=simple]').click();find('#zoom-fit').click()
    expect(find('#canvas-host [data-object-id]').first).to_be_visible();page.screenshot(path=output/'template-editor.png')
    relation=next(r for r in template['relations'] if r['source']=='raf') if any(r['source']=='raf' for r in template['relations']) else template['relations'][0]
    edge=find(f'#canvas-host [data-relation-id="{relation["id"]}"]').first
    original=edge.inner_html()
    glyph=find(f'#canvas-host [data-glyph="{relation["source"]}"]').first.bounding_box()
    x,y=glyph['x']+glyph['width']/2,glyph['y']+glyph['height']/2
    page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+36,y+14,steps=10);page.mouse.up();find('#save-document').click()
    assert original!=edge.inner_html() and any(r['source']==relation['source'] and r['target']==relation['target'] for r in scene()['relations'])
    print('PASS sketch reference, narrow editor, sized template instantiation and mode switch',flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output', type=Path, required=True);args=parser.parse_args()
    args.output.mkdir(exist_ok=True,parents=True)
    with isolated_server() as base,sync_playwright() as driver:
        try:
            browser = driver.chromium.launch(channel='msedge');page=browser.new_page(viewport={'width':1280,'height':800});errors=[]  # _launch_browser
        except Exception:
            browser = driver.chromium.launch();page=browser.new_page(viewport={'width':1280,'height':800});errors=[]
        page.on('pageerror',lambda exc: errors.append(str(exc)))
        try:
            exercise(page,base,args.output);assert not errors,errors
        except Exception:
            page.screenshot(path=args.output/'failure.png');raise
        finally:
            browser.close()
