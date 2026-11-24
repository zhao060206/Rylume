"""Missing optional components: modules still import, exports fail in plain words."""
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import app_server
import scene_export

ROOT = Path(__file__).resolve().parents[1]
RAW = ("ModuleNotFoundError", "ImportError", "No module named")


def _python(code, cwd):
    prelude = f"import sys\nsys.path.insert(0, {str(ROOT)!r})\n"
    return subprocess.run([sys.executable, "-c", prelude + code], cwd=cwd,
                          capture_output=True, text=True, timeout=120)


def test_importing_rebuild_reads_and_writes_nothing(tmp_path):
    result = _python("import rebuild\nassert callable(rebuild.main)", tmp_path)
    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


def test_annotation_planner_imports_without_pymupdf(tmp_path):
    code = ("sys.modules['fitz'] = None\nsys.modules['pymupdf'] = None\n"
            "import annotation_planner\nassert 'fitz' not in vars(annotation_planner)")
    result = _python(code, tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("module,fmt,use", [
    ("fitz", "png", "PNG"), ("fitz", "pdf", "PDF"),
    ("svgpathtools", "pptx", "PowerPoint"), ("fitz", "", "PNG/PDF"),
])
def test_missing_component_message_is_plain(module, fmt, use):
    message = app_server._missing_component_error(
        ModuleNotFoundError(f"No module named '{module}'", name=module), fmt)
    assert use in message and module in message and "重新安装" in message
    assert not any(word in message for word in RAW)


@pytest.fixture
def studio(tmp_path, monkeypatch):
    monkeypatch.setattr(app_server, "JOBS", {})
    monkeypatch.setattr(app_server, "DATA_DIR", tmp_path)
    monkeypatch.setattr(app_server, "JOBS_DIR", tmp_path / "studio-jobs")
    monkeypatch.setattr(app_server, "EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(app_server, "CONFIG_PATH", tmp_path / "config.json")
    app_server.save_config({"mode": "auto", "default_illustration_mode": "vector"})
    server = app_server.StudioHTTPServer(("127.0.0.1", 0), app_server.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    root = f"http://127.0.0.1:{server.server_address[1]}"

    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(root + path, data=data, headers={"Content-Type": "application/json"},
                                     method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())
    yield request
    server.shutdown()
    server.server_close()
    worker.join(timeout=3)


def _example(studio):
    status, result = studio("/api/scene/example", {"example": "egfr"})
    assert status == 200, result
    job_id = result["job_id"]
    for _ in range(100):
        _, job = studio("/api/jobs/" + job_id)
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.02)
    assert job["status"] == "completed", job
    return job_id


def _missing(name):
    def export_scene(*args, **kwargs):
        raise ModuleNotFoundError(f"No module named '{name}'", name=name)
    return export_scene


@pytest.mark.parametrize("fmt,module,use", [
    ("png", "fitz", "PNG"), ("pdf", "fitz", "PDF"), ("pptx", "svgpathtools", "PowerPoint"),
])
def test_save_as_reports_missing_component_in_plain_words(studio, monkeypatch, fmt, module, use):
    job_id = _example(studio)
    monkeypatch.setattr(scene_export, "export_scene", _missing(module))
    status, result = studio(f"/api/jobs/{job_id}/save-as", {"format": fmt, "revision": 1})
    assert status == 500 and not result["ok"], result
    assert use in result["error"] and "重新安装" in result["error"]
    assert not any(word in result["error"] for word in RAW)


def test_background_ppt_failure_is_plain(studio, monkeypatch):
    job_id = _example(studio)
    monkeypatch.setattr(scene_export, "export_scene", _missing("svgpathtools"))
    status, started = studio(f"/api/jobs/{job_id}/ppt", {"revision": 1})
    assert status == 200, started
    for _ in range(250):
        _, state = studio(f"/api/jobs/{job_id}/ppt-status")
        if state.get("state") != "running":
            break
        time.sleep(0.02)
    assert state["state"] == "failed", state
    assert "PowerPoint" in state["error"] and not any(word in state["error"] for word in RAW)
