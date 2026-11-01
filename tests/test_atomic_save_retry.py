from pathlib import Path
import pytest
import studio_storage


def test_transient_windows_reader_cannot_turn_a_save_into_a_failure(tmp_path,monkeypatch):
    source=tmp_path/'pending.json';target=tmp_path/'saved.json'
    source.write_text('new');target.write_text('old')
    original=studio_storage.os.replace;calls=[]
    def sharing_violation(first,second):
        calls.append(1)
        if len(calls)<3:
            assert target.read_text()=='old' and source.read_text()=='new'
            error=PermissionError('sharing violation');error.winerror=32;raise error
        original(first,second)
    monkeypatch.setattr(studio_storage.os,'replace',sharing_violation)
    monkeypatch.setattr(studio_storage.time,'sleep',lambda _:None)
    studio_storage.durable_replace(source,target)
    assert len(calls)==3 and target.read_text()=='new' and not source.exists()


def test_persistent_windows_denial_preserves_original_and_pending_file(tmp_path,monkeypatch):
    source=tmp_path/'pending.json';target=tmp_path/'saved.json'
    source.write_text('new');target.write_text('old');calls=[]
    def denied(*_):
        calls.append(1);error=PermissionError('denied');error.winerror=5;raise error
    monkeypatch.setattr(studio_storage.os,'replace',denied)
    monkeypatch.setattr(studio_storage.time,'sleep',lambda _:None)
    with pytest.raises(PermissionError):studio_storage.durable_replace(source,target)
    assert len(calls)==6 and target.read_text()=='old' and source.read_text()=='new'
