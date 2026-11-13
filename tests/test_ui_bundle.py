"""Desktop resource boundary: the shell must load its compiled offline UI."""
import threading
import urllib.request

import app_server
from scripts.build_ui import ROOT, build


def test_compiled_desktop_style_matches_sources():
    assert (ROOT / 'ui/workbench-ui.css').read_text('utf-8') == build()


def test_desktop_serves_the_real_shell_and_its_local_components():
    server = app_server.StudioHTTPServer(('127.0.0.1', 0), app_server.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_address[1]}'
    try:
        for route, content_type, marker in [
            ('/', 'text/html', '/ui/workbench-ui.css'),
            ('/ui/workbench-ui.css', 'text/css', '@layer features, components, workspace, panels'),
            ('/ui/components/controls.js', 'application/javascript', 'enhanceSegments'),
            ('/ui/components/command-palette.js', 'application/javascript', 'setupCommandPalette'),
            ('/ui/product-shell.js', 'application/javascript', 'setupProductShell'),
        ]:
            with urllib.request.urlopen(base + route, timeout=5) as response:
                assert response.status == 200
                assert content_type in response.headers['Content-Type']
                assert marker in response.read().decode('utf-8')
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
