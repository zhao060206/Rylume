"""Small per-workspace onboarding record, independent of model credentials."""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path

from studio_storage import durable_replace

LOCK = threading.RLock()
STATUSES = {"unseen", "in_progress", "skipped", "completed"}
STEPS = {"welcome", "select", "edit", "asset", "export", "finish"}
FIELDS = {"status", "step", "practice_job_id"}
JOB_ID = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")


def _default(has_jobs=False):
    return dict(version=1, status="skipped" if has_jobs else "unseen",
                step="welcome", practice_job_id=None, existing_install=bool(has_jobs))


def _validate(value):
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError("引导进度包含不支持的字段")
    if "status" in value and (not isinstance(value["status"], str) or value["status"] not in STATUSES):
        raise ValueError("引导状态无效")
    if "step" in value and (not isinstance(value["step"], str) or value["step"] not in STEPS):
        raise ValueError("引导步骤无效")
    job = value.get("practice_job_id")
    if job is not None and (not isinstance(job, str) or not JOB_ID.fullmatch(job)):
        raise ValueError("练习图版 ID 无效")


def _write(root, state):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / "onboarding.json"
    temporary = target.with_name(".onboarding-" + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf8") as stream:
            json.dump(state, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        durable_replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def load(root, *, has_jobs=False):
    with LOCK:
        file = Path(root) / "onboarding.json"
        try:
            raw = json.loads(file.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict) or raw.get("version") != 1:
                raise ValueError("unsupported guide version")
            values = {k: raw[k] for k in FIELDS if k in raw}
            _validate(values)
            return {**_default(has_jobs), **values, "existing_install": raw.get("existing_install") is True}
        except FileNotFoundError:
            state = _default(has_jobs)
            _write(root, state)  # Remember the first visit before a practice job exists.
            return state
        except (ValueError, TypeError):
            # Keep an unreadable record in place until the user explicitly acts.
            return _default(has_jobs)


def update(root, patch, *, has_jobs=False):
    _validate(patch)
    with LOCK:
        state = {**load(root, has_jobs=has_jobs), **patch}
        _write(root, state)
        return state


def dispatch(handler, method, path, app):
    if path != "/api/onboarding" or method not in ("GET", "POST"):
        return False
    try:
        with app.JOBS_LOCK:
            has_jobs = bool(app.JOBS)
        state = (load(app.DATA_DIR, has_jobs=has_jobs) if method == "GET"
                 else update(app.DATA_DIR, handler._body(), has_jobs=has_jobs))
        handler._json(200, dict(ok=True, state=state))
    except ValueError as error:
        handler._json(400, dict(ok=False, error=str(error)))
    except OSError:
        handler._json(503, dict(ok=False, error="新手引导进度暂时无法保存，已有图版不受影响"))
    return True
