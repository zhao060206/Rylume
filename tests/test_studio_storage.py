import json
from pathlib import Path
import pytest
from studio_storage import get_data_dir,prepare_data_dir,acquire_instance_lock,WorkQueues


def test_cross_device_replacement_keeps_complete_content_and_cleans_journal(tmp_path,monkeypatch):
    import os,errno
    from studio_storage import durable_replace
    source=tmp_path/'new.json';target=tmp_path/'existing.json'
    source.write_text('{"new":2}');target.write_text('{"old":1}')
    def refused(*args):raise OSError(errno.EXDEV,'rename unavailable')
    monkeypatch.setattr(os,'replace',refused)
    durable_replace(source,target)
    assert json.loads(target.read_text())=={'new':2} and not source.exists()
    assert not list(tmp_path.glob('.cfs-replace-*.journal'))


def test_complete_journal_recovers_interrupted_target_write(tmp_path):
    import hashlib,base64
    from studio_storage import recover_pending_replacements
    data=b'{"revision":3}';target=tmp_path/'scene-head.json';target.write_bytes(b'{"rev')
    journal=tmp_path/'.cfs-replace-123.journal'
    journal.write_text(json.dumps({'name':target.name,'data':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest()}))
    recover_pending_replacements(tmp_path)
    assert target.read_bytes()==data and not journal.exists()


def test_incomplete_or_traversing_journals_do_not_modify_existing_files(tmp_path):
    from studio_storage import recover_pending_replacements
    target=tmp_path/'meta.json';target.write_text('original')
    (tmp_path/'.cfs-replace-broken.journal').write_text('{"name":')
    (tmp_path/'.cfs-replace-invalid.journal').write_text(json.dumps({'name':'../meta.json','data':'','sha256':''}))
    recover_pending_replacements(tmp_path)
    assert target.read_text()=='original'


def test_permission_denial_preserves_original_and_does_not_use_compatibility_path(tmp_path,monkeypatch):
    import os
    from studio_storage import durable_replace
    source=tmp_path/'new';source.write_text('new');target=tmp_path/'old';target.write_text('old')
    def denied(*args):raise PermissionError('denied')
    monkeypatch.setattr(os,'replace',denied)
    with pytest.raises(PermissionError):durable_replace(source,target)
    assert target.read_text()=='old' and source.exists()


def test_directory_override_and_both_environment_names(tmp_path,monkeypatch):
    monkeypatch.setenv('CELLFIGURE_DATA_DIR',str(tmp_path/'env'))
    assert get_data_dir()==tmp_path/'env'
    assert get_data_dir(tmp_path/'explicit')==tmp_path/'explicit'
    monkeypatch.delenv('CELLFIGURE_DATA_DIR')
    monkeypatch.setenv('CELL_FIGURE_STUDIO_DATA_DIR',str(tmp_path/'alias'))
    assert get_data_dir()==tmp_path/'alias'


def test_instance_lock_rejects_second_owner_and_releases(tmp_path):
    with acquire_instance_lock(tmp_path):
        with pytest.raises(RuntimeError):acquire_instance_lock(tmp_path)
    with acquire_instance_lock(tmp_path):pass


def legacy(root,title,status='completed'):
    folder=root/'studio-jobs'/'j_same';folder.mkdir(parents=True)
    (root/'exports'/'j_same').mkdir(parents=True)
    (root/'exports'/'j_same'/'figure.svg').write_text(title,encoding='utf-8')
    meta={'id':'j_same','title':title,'status':status,'next_job':'j_same','svg_path':str(folder/'result.svg'),
          'ppt':{'path':str(root/'exports'/'j_same'/'figure.svg')}}
    (folder/'meta.json').write_text(json.dumps(meta),encoding='utf-8')
    (folder/'result.svg').write_text(title,encoding='utf-8')
    (root/'config.json').write_text('{"text":{"model":"test"}}',encoding='utf-8')
    return folder


def test_namespaced_import_rewrites_paths_preserves_originals_and_restarts_idempotently(tmp_path):
    source_a=tmp_path/'a'/'app';source_b=tmp_path/'b'/'app'
    a=legacy(source_a,'first');b=legacy(source_b,'second')
    original=(a/'meta.json').read_bytes();target=tmp_path/'new'
    result=prepare_data_dir(target,[source_a,source_b])
    ids=[s['jobs']['j_same']['new_id'] for s in result['sources'].values()]
    assert len(set(ids))==2
    for source,title in ((source_a,'first'),(source_b,'second')):
        entry=result['sources'][str(source)]
        item=entry['jobs']['j_same'];new=target/'studio-jobs'/item['new_id']
        meta=json.loads((new/'meta.json').read_text(encoding='utf-8'))
        assert meta['id']==new.name and meta['title']==title and meta['next_job']==new.name
        assert Path(meta['svg_path'])==new/'result.svg'
        assert Path(meta['ppt']['path']).read_text(encoding='utf-8')==title
        assert (Path(item['backup'])/'meta.json').is_file()
    assert (a/'meta.json').read_bytes()==original
    before={p.name for p in (target/'studio-jobs').iterdir()}
    again=prepare_data_dir(target,[source_a,source_b])
    assert {p.name for p in (target/'studio-jobs').iterdir()}==before
    assert again['sources']==result['sources']


def test_active_and_invalid_tasks_are_retried_without_overwriting_usable_results(tmp_path):
    source=tmp_path/'old';folder=legacy(source,'active','processing');target=tmp_path/'new'
    first=prepare_data_dir(target,[source]);record=first['sources'][str(source)]['jobs']['j_same']
    assert record['status']=='pending_active'
    (folder/'meta.json').write_text('{broken',encoding='utf-8')
    failed=prepare_data_dir(target,[source])
    assert failed['sources'][str(source)]['jobs']['j_same']['status']=='failed'
    (folder/'meta.json').write_text(json.dumps({'id':'j_same','title':'finished','status':'completed'}),encoding='utf-8')
    final=prepare_data_dir(target,[source])
    item=final['sources'][str(source)]['jobs']['j_same']
    assert item['status']=='complete'
    imported=target/'studio-jobs'/item['new_id']/'meta.json'
    original=imported.read_bytes()
    (folder/'meta.json').write_text('{}',encoding='utf-8')
    prepare_data_dir(target,[source])
    assert imported.read_bytes()==original


def test_work_queues_are_serial_and_generation_is_independent_of_export():
    import threading
    event=threading.Event()
    with WorkQueues() as queues:
        running=queues.submit_generation(event.wait,2)
        assert queues.submit_export(lambda:42).result(timeout=1)==42
        second=queues.submit_generation(lambda:99)
        assert not second.done()
        event.set()
        assert running.result(timeout=1) and second.result(timeout=1)==99


def test_imported_identifier_obeys_existing_job_path_limit(tmp_path):
    source=tmp_path/'very_long_source_directory_name';folder=legacy(source,'long id')
    renamed=folder.with_name('j_'+'x'*62);folder.rename(renamed)
    result=prepare_data_dir(tmp_path/'target',[source])
    item=result['sources'][str(source)]['jobs'][renamed.name]
    assert item['status']=='complete' and len(item['new_id'])<=64
