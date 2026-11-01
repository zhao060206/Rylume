import json
from pathlib import Path

from test_scene_api import studio, example
import app_server


def test_empty_project_membership_rename_and_reload(studio):
    code, created = studio('/api/projects', {'title': '论文图组'})
    assert code == 200
    pid = created['project']['id']
    assert studio('/api/projects')[1]['projects'][0]['id'] == pid
    jid = example(studio)
    _, before = studio('/api/jobs/' + jid + '/scene')
    code, moved = studio('/api/projects/' + pid + '/documents', {'job_ids': [jid]})
    assert code == 200 and moved['documents'][jid] == pid
    _, renamed = studio('/api/projects/' + pid, {'title': '论文终稿', 'base_revision': moved['revision']}, 'PATCH')
    assert renamed['project']['id'] == pid
    assert json.loads((Path(app_server.DATA_DIR)/'projects.json').read_text(encoding='utf8'))['documents'][jid] == pid
    assert studio('/api/jobs/' + jid + '/scene')[1]['scene'] == before['scene']
    assert studio('/api/projects/' + pid, {'title': '过期请求', 'base_revision': moved['revision']}, 'PATCH')[0] == 409
    assert studio('/api/projects')[1]['projects'][0]['title'] == '论文终稿'


def test_move_sort_and_remove_project_preserves_documents(studio):
    first, second = example(studio), example(studio, 'jak_stat')
    pid = studio('/api/projects', {'title': '实验设计'})[1]['project']['id']
    studio('/api/projects/' + pid + '/documents', {'job_ids': [first, second]})
    code, moved = studio('/api/projects/' + pid + '/documents', {'job_ids': [second], 'before_id': first})
    assert code == 200 and moved['order'][pid] == [second, first]
    code, unfiled = studio('/api/projects/unfiled/documents', {'job_ids': [second]})
    assert code == 200 and unfiled['documents'][second] == ''
    code, removed = studio('/api/projects/' + pid, {}, 'DELETE')
    assert code == 200 and removed['projects'] == []
    assert removed['documents'][first] == ''
    assert studio('/api/jobs/' + first + '/scene')[0] == 200
    assert studio('/api/jobs/' + second + '/scene')[0] == 200


def test_legacy_collection_migrates_once_and_validation_is_non_mutating(studio):
    jid = example(studio)
    studio('/api/jobs/' + jid + '/document-info', {'base_revision': 1, 'collection': '旧项目'})
    initial = studio('/api/projects')[1]
    pid = initial['documents'][jid]
    studio('/api/projects/' + pid, {'title': '改名项目'}, 'PATCH')
    assert len(studio('/api/projects')[1]['projects']) == 1
    studio('/api/projects/' + pid, {}, 'DELETE')
    assert studio('/api/projects')[1]['projects'] == []
    before = (Path(app_server.DATA_DIR)/'projects.json').read_bytes()
    assert studio('/api/projects', {'title': ' '})[0] == 400
    assert studio('/api/projects/unfiled/documents', {'job_ids': ['missing']})[0] == 400
    assert (Path(app_server.DATA_DIR)/'projects.json').read_bytes() == before
    assert studio('/api/projects', {'title': '新项目'})[0] == 200
    assert studio('/api/projects', {'title': '新项目'})[0] == 400
