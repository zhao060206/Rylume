from concurrent.futures import ThreadPoolExecutor
import json
import threading
from types import SimpleNamespace

import pytest

import onboarding_state as guide


def test_first_visit_survives_creation_of_a_practice_job(tmp_path):
    assert guide.load(tmp_path)["status"] == "unseen"
    assert guide.load(tmp_path, has_jobs=True)["status"] == "unseen"
    assert (tmp_path / "onboarding.json").is_file()


def test_existing_users_are_not_interrupted_and_can_replay(tmp_path):
    saved = guide.load(tmp_path, has_jobs=True)
    assert saved["status"] == "skipped" and saved["existing_install"] is True
    assert guide.update(tmp_path, {"status": "in_progress", "step": "select", "practice_job_id": "j_practice"})["status"] == "in_progress"


def test_resume_completed_and_skip_persist_across_reads(tmp_path):
    guide.update(tmp_path, {"status": "in_progress", "step": "asset", "practice_job_id": "j_practice"})
    assert guide.load(tmp_path)["step"] == "asset"
    guide.update(tmp_path, {"status": "completed", "step": "finish"})
    assert guide.load(tmp_path)["status"] == "completed"
    guide.update(tmp_path, {"status": "skipped"})
    assert guide.load(tmp_path)["practice_job_id"] == "j_practice"
    assert guide.load(tmp_path)["status"] == "skipped"


@pytest.mark.parametrize("patch", [None, [], {"path": "elsewhere"}, {"status": "bad"}, {"step": "unknown"}, {"practice_job_id": "../config"}, {"practice_job_id": "a" * 97}, {"status": []}, {"step": True}, {"practice_job_id": 123}])
def test_untrusted_patches_are_rejected_without_changing_saved_state(tmp_path, patch):
    guide.load(tmp_path)
    before = (tmp_path / "onboarding.json").read_bytes()
    with pytest.raises(ValueError):
        guide.update(tmp_path, patch)
    assert (tmp_path / "onboarding.json").read_bytes() == before


def test_parallel_partial_updates_do_not_lose_fields(tmp_path):
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda p: guide.update(tmp_path, p), [{"status": "in_progress"}, {"step": "edit"}, {"practice_job_id": "j_parallel"}]))
    state = guide.load(tmp_path)
    assert (state["status"], state["step"], state["practice_job_id"]) == ("in_progress", "edit", "j_parallel")
    assert not list(tmp_path.glob("*.tmp"))


def test_invalid_record_is_retained_until_user_restarts_guide(tmp_path):
    file = tmp_path / "onboarding.json"
    file.write_text("invalid JSON", encoding="utf8")
    assert guide.load(tmp_path)["status"] == "unseen"
    assert file.read_text(encoding="utf8") == "invalid JSON"
    guide.update(tmp_path, {"status": "skipped"})
    assert json.loads(file.read_text())["status"] == "skipped"


def test_dispatch_is_scoped_to_application_data_and_reports_validation_errors(tmp_path):
    responses = []
    handler = SimpleNamespace(_json=lambda code, body: responses.append((code, body)), _body=lambda: {"practice_job_id": "../../outside"})
    app = SimpleNamespace(DATA_DIR=tmp_path, JOBS={}, JOBS_LOCK=threading.RLock())
    assert guide.dispatch(handler, "GET", "/api/onboarding", app)
    assert responses[-1][0] == 200 and responses[-1][1]["state"]["status"] == "unseen"
    assert guide.dispatch(handler, "POST", "/api/onboarding", app)
    assert responses[-1][0] == 400
    assert not guide.dispatch(handler, "GET", "/api/other", app)
