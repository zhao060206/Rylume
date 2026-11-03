"""Reproducible large-scene profiling, using isolated revisions and no models.

--serve exposes only the benchmark fixture and UI modules on loopback. Supply
--baseline-ui to compare a previous checkout's editor against the current one.
"""
from __future__ import annotations
import argparse
import cProfile
import json
import pstats
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--svg', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--serve', type=int)
    parser.add_argument('--baseline-ui', type=Path)
    parser.add_argument('--baseline-python', type=Path, help='Profile saved modules from a previous checkout')
    args = parser.parse_args()
    if args.baseline_python:
        sys.path.insert(0, str(args.baseline_python.resolve()))
    from scene_document import SceneRepository
    scene = json.loads(args.scene.read_text(encoding='utf8'))
    args.output.mkdir(parents=True, exist_ok=True)
    if args.serve:
        assert args.svg, '--serve requires --svg'

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                # Only known synthetic/CC-BY fixture snapshots, on loopback.
                name=urlsplit(self.path).path
                if name not in ('/snapshot/grouped','/snapshot/moved','/snapshot/display'):
                    self.send_error(404);return
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<32_000_000:
                    self.send_error(413);return
                value=json.loads(self.rfile.read(length))
                if name=='/snapshot/display':
                    import base64
                    (args.output/'moved-display.png').write_bytes(base64.b64decode(value['png'].split(',',1)[1]))
                else:(args.output/(name.rsplit('/',1)[-1]+'-scene.json')).write_text(json.dumps(value),encoding='utf8')
                self.send_response(204);self.end_headers()

            def do_GET(self):
                path = urlsplit(self.path).path
                file, mime = None, 'text/javascript'
                if path == '/structures':
                    file, mime = ROOT/'tools/benchmark_structures.html', 'text/html'
                elif path == '/elements':
                    file, mime = ROOT/'tools/benchmark_elements.html', 'text/html'
                elif path == '/':
                    file, mime = ROOT/'tools/benchmark_canvas.html', 'text/html'
                elif path == '/scene.json':
                    file, mime = args.scene, 'application/json'
                elif path == '/figure.svg':
                    file, mime = args.svg, 'image/svg+xml'
                elif path.startswith(('/ui/', '/before/')) and path.endswith('.js'):
                    folder = ROOT/'ui' if path.startswith('/ui/') else args.baseline_ui
                    if folder and Path(path).name == path.split('/')[-1]:
                        file = folder/Path(path).name
                if not file or not file.is_file():
                    self.send_error(404)
                    return
                data = file.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', mime+'; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)

        print(f'Benchmark: http://127.0.0.1:{args.serve}/', flush=True)
        ThreadingHTTPServer(('127.0.0.1', args.serve), Handler).serve_forever()
        return
    samples = []
    with tempfile.TemporaryDirectory(prefix='rylume-performance-') as folder:
        repo = SceneRepository(folder)
        repo.commit(scene)
        label = next(o for o in scene['objects'] if o.get('text_appearance'))
        profiler = cProfile.Profile()
        for index in range(4):
            started = time.perf_counter()
            if index == 3:
                profiler.enable()
            options = {} if args.baseline_python else {'delta': True}
            result = repo.patch(index+1, [{'op': 'update', 'id': label['id'],
                               'changes': {'label': label['label']+str(index)}}], **options)
            wire = result if args.baseline_python else {k: v for k, v in result.items() if k not in ('scene', 'svg')}
            raw = json.dumps({'ok': True, **wire}, ensure_ascii=False).encode()
            profiler.disable()
            samples.append({'seconds': round(time.perf_counter()-started, 5), 'response_bytes': len(raw), 'profiled': index == 3})
        profiler.dump_stats(str(args.output/'save.prof'))
        with (args.output/'profile.txt').open('w', encoding='utf8') as stream:
            pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats('cumulative').print_stats(25)
    report = {'scene_bytes': args.scene.stat().st_size, 'objects': len(scene['objects']), 'saves': samples}
    (args.output/'backend.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
