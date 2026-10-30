"""Local replacement backend for the xiaomiao cell-figure skill.

Implements the exact four endpoints the client expects, for both services:

  /api/cell-figure-plus  (fig1, 20 credits, job id cfp_<24 hex>)
  /api/figure_pro        (fig2, 45 credits, job id fgp_<24 hex>)

Protocol surface required by client.py:
  GET  /me                  -> id, role, credits_available, credits_per_task
  POST /jobs                -> job_id, charged_credits, status
  GET  /jobs/{id}           -> job_id, charged_credits, status, sha256 (when done)
  GET  /jobs/{id}/result    -> raw SVG bytes whose sha256 matches the status

Nothing here talks to xiaomiao. Drawing is delegated to pipeline.py.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pipeline

SERVICES = {
    "/api/cell-figure-plus": {"price": 20, "prefix": "cfp"},
    "/api/figure_pro": {"price": 45, "prefix": "fgp"},
}

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
CONFIG: dict = {}
CONFIG_PATH: Path | None = None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def current_config() -> dict:
    """Reload config.json per job so modes can be switched without a restart."""
    global CONFIG
    if CONFIG_PATH and CONFIG_PATH.is_file():
        try:
            CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            print(f"[warn] cannot reload config: {exc}", file=sys.stderr)
    return CONFIG


def run_job(job_id: str, text: str, image: bytes | None, price: int) -> None:
    with JOBS_LOCK:
        JOBS[job_id]["status"] = "processing"
    try:
        svg, report = pipeline.render(text=text, image=image, config=current_config())
        digest = sha256(svg)
        with JOBS_LOCK:
            JOBS[job_id].update(
                status="completed",
                svg=svg,
                sha256=digest,
                report=report,
                completed_at=time.time(),
            )
        print(f"[job] {job_id} completed ({len(svg)} bytes, {digest[:12]})", file=sys.stderr)
    except Exception as exc:  # keep the job queryable instead of dying silently
        with JOBS_LOCK:
            JOBS[job_id].update(
                status="failed",
                error=f"{type(exc).__name__}: {exc}"[:2000],
                completed_at=time.time(),
            )
        print(f"[job] {job_id} failed: {exc}", file=sys.stderr)


class Handler(BaseHTTPRequestHandler):
    server_version = "CellFigureLocal/1.0"
    protocol_version = "HTTP/1.1"

    # ---------- helpers ----------

    def log_message(self, fmt, *args):  # quieter default logging
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _auth_ok(self) -> bool:
        header = self.headers.get("Authorization", "")
        return header.startswith("Bearer ") and len(header) > 7

    def _route(self) -> tuple[dict, str, list[str]] | None:
        path = self.path.split("?", 1)[0]
        for prefix, service in SERVICES.items():
            if path == prefix or path.startswith(prefix + "/"):
                rest = path[len(prefix):].strip("/")
                return service, prefix, [p for p in rest.split("/") if p]
        return None

    def _job(self, job_id: str) -> dict | None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            return dict(job) if job else None

    # ---------- verbs ----------

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "cell-figure-local", "mode": CONFIG.get("mode")})
            return
        routed = self._route()
        if not routed:
            self._json(404, {"ok": False, "error": "not found"})
            return
        service, _prefix, parts = routed
        if not self._auth_ok():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return

        if parts == ["me"]:
            self._json(200, {
                "ok": True,
                "id": 1,
                "role": "customer",
                "credits_available": 999999,
                "credits_per_task": service["price"],
                "invite_required": False,
            })
            return

        if len(parts) == 2 and parts[0] == "jobs":
            job = self._job(parts[1])
            if not job:
                self._json(404, {"ok": False, "error": "job not found"})
                return
            body = {
                "ok": True,
                "job_id": job["job_id"],
                "charged_credits": job["charged_credits"],
                "status": job["status"],
            }
            if job["status"] == "completed":
                body["sha256"] = job["sha256"]
                body["bytes"] = len(job["svg"])
                body["pipeline_report"] = job.get("report")
            if job.get("error"):
                body["error"] = job["error"]
            self._json(200, body)
            return

        if len(parts) == 3 and parts[0] == "jobs" and parts[2] == "result":
            job = self._job(parts[1])
            if not job:
                self._json(404, {"ok": False, "error": "job not found"})
                return
            if job["status"] != "completed":
                self._json(409, {"ok": False, "error": "job not completed", "status": job["status"]})
                return
            self._send(200, job["svg"], "image/svg+xml")
            return

        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):  # noqa: N802
        routed = self._route()
        if not routed:
            self._json(404, {"ok": False, "error": "not found"})
            return
        service, _prefix, parts = routed
        if not self._auth_ok():
            self._json(401, {"ok": False, "error": "unauthorized"})
            return
        if parts != ["jobs"]:
            self._json(404, {"ok": False, "error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 64 * 1024 * 1024:
                raise ValueError("bad content length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            self._json(400, {"ok": False, "error": f"bad body: {exc}"})
            return

        text = payload.get("text") or ""
        if not isinstance(text, str):
            self._json(400, {"ok": False, "error": "text must be a string"})
            return

        image = None
        image_meta = payload.get("image")
        if image_meta:
            try:
                image = base64.b64decode(image_meta["base64"], validate=True)
            except Exception:
                self._json(400, {"ok": False, "error": "image.base64 invalid"})
                return

        if not text.strip() and not image:
            self._json(400, {"ok": False, "error": "text or image required"})
            return

        approved = payload.get("credits_approved")
        if approved is not None and approved != service["price"]:
            self._json(400, {"ok": False, "error": "credits_approved mismatch"})
            return

        job_id = f"{service['prefix']}_{uuid.uuid4().hex[:24]}"
        with JOBS_LOCK:
            JOBS[job_id] = {
                "job_id": job_id,
                "charged_credits": service["price"],
                "status": "queued",
                "created_at": time.time(),
                "svg": None,
                "sha256": None,
                "error": None,
                "request_id": payload.get("request_id"),
            }

        threading.Thread(target=run_job, args=(job_id, text, image, service["price"]),
                         daemon=True).start()

        self._json(201, {
            "ok": True,
            "job_id": job_id,
            "charged_credits": service["price"],
            "status": "queued",
        })


def main() -> int:
    global CONFIG, CONFIG_PATH
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    args = parser.parse_args()

    CONFIG_PATH = args.config
    if args.config.is_file():
        CONFIG = json.loads(args.config.read_text(encoding="utf-8-sig"))
    else:
        CONFIG = {"mode": "placeholder"}
        print(f"[warn] {args.config} not found; using placeholder pipeline", file=sys.stderr)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"cell-figure-local listening on http://{args.host}:{args.port}", file=sys.stderr)
    print(f"mode={CONFIG.get('mode', 'placeholder')} config={args.config}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
