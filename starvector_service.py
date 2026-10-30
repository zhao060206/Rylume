"""Local StarVector-1B image-to-SVG service.

StarVector is an open-source multimodal model trained specifically for
image-to-SVG. It traces the *actual* artwork (shapes, colors, strokes) instead
of asking a text model to redraw it, so the generated SVG keeps the image
model's style.

Run:
  python starvector_service.py --port 8790

The desktop app calls POST /vectorize with {"image": "<base64 png>"}.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MODEL_DIR = Path(os.environ.get(
    "STARVECTOR_MODEL",
    r"E:\动画\cell-figure-local\models\starvector-1b"))
LOCK = threading.Lock()
MODEL = None


def load_model():
    global MODEL
    if MODEL is not None:
        return MODEL
    import torch
    from transformers import AutoModelForCausalLM
    started = time.time()
    print(f"loading StarVector from {MODEL_DIR} ...", file=sys.stderr, flush=True)
    MODEL = AutoModelForCausalLM.from_pretrained(
        str(MODEL_DIR), torch_dtype=torch.float16, trust_remote_code=True)
    MODEL = MODEL.cuda().eval()
    print(f"loaded in {time.time() - started:.1f}s", file=sys.stderr, flush=True)
    return MODEL


def vectorize(png: bytes, max_length: int = 4000) -> str:
    import torch
    from PIL import Image
    model = load_model()
    with LOCK:
        image = Image.open(io.BytesIO(png)).convert("RGB")
        processor = model.model.processor
        processed = processor(image)
        if isinstance(processed, dict):
            pixels = processed.get("pixel_values", processed)
        else:
            pixels = processed
        pixels = pixels.unsqueeze(0).cuda()
        with torch.inference_mode():
            raw = model.generate_im2svg({"image": pixels}, max_length=max_length)[0]
    if isinstance(raw, (tuple, list)):
        raw = raw[0]
    raw = str(raw)
    start = raw.find("<svg")
    end = raw.rfind("</svg>")
    if start < 0 or end < 0:
        raise RuntimeError("StarVector returned no SVG document")
    return raw[start:end + 6]


class Handler(BaseHTTPRequestHandler):
    server_version = "StarVectorService/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def _json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "model": "starvector-1b",
                             "loaded": MODEL is not None})
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/vectorize":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            png = base64.b64decode(payload["image"])
            started = time.time()
            svg = vectorize(png, int(payload.get("max_length", 4000)))
            self._json(200, {"ok": True, "svg": svg,
                             "seconds": round(time.time() - started, 2)})
        except Exception as exc:
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:800]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--preload", action="store_true")
    args = parser.parse_args()
    if args.preload:
        load_model()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"StarVector service on http://{args.host}:{args.port}", file=sys.stderr, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
