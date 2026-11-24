import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from model_catalog import model_names


def test_saved_service_lists_names_and_never_follows_redirects():
    paths = []

    class Service(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            if self.path == '/redirect/v1/models':
                self.send_response(302)
                self.send_header('Location', '/different-service')
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'data': [{'id':'B'}, {'id':'A'}, {'id':'A'}, {}]}).encode())

    with ThreadingHTTPServer(('127.0.0.1', 0), Service) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            assert model_names({'base_url': base}) == ['A', 'B']
            with pytest.raises(ValueError, match='302'):
                model_names({'base_url': base+'/redirect'})
            assert paths == ['/v1/models', '/redirect/v1/models']
        finally:
            server.shutdown()
            worker.join(timeout=3)
