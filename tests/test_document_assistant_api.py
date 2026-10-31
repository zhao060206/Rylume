"""Real HTTP document workflows; synthetic input and local fake model only."""
import base64
import json
import threading
import time

import pytest

import app_server
import document_assistant as service
from test_scene_api import studio

API = service.PREFIX
TEXT = 'The samples are collected, washed with buffer, measured and then analyzed. No causal mechanism was tested.'
CONFIG = {'text': {'base_url': 'http://127.0.0.1:1/v1', 'model': 'test-document-model', 'api_key': 'test-key'}}


@pytest.fixture(autouse=True)
def close_queues():
    before = set(service._SERVICES)
    yield
    for key in set(service._SERVICES) - before:
        library = service._SERVICES.pop(key)
        for event in library.cancellations.values():
            event.set()
        library.conversions.shutdown(wait=True, cancel_futures=True)
        library.planning.shutdown(wait=True, cancel_futures=True)


def upload(studio, text=TEXT, name='实验方案.txt'):
    code, value = studio(API+'/upload', {'name':name, 'data':base64.b64encode(text.encode()).decode()})
    assert code == 202, value
    return value['document']['id']


def wait(studio, identity, category='documents', status=('ready','failed','cancelled','completed')):
    for _ in range(300):
        _, listing = studio(API)
        row = next(r for r in listing[category] if r['id'] == identity)
        if row['status'] in status:
            return row
        time.sleep(.02)
    raise AssertionError('Document worker timed out')


def test_upload_markdown_download_dedup_archive_and_reopen(studio):
    identity = upload(studio)
    row = wait(studio, identity)
    assert row['status'] == 'ready', row
    code, content = studio(API+'/documents/'+identity)
    assert code == 200 and TEXT in content['markdown'] and content['sections']
    code, download = studio(API+'/documents/'+identity+'/markdown')
    assert code == 200 and download.decode() == content['markdown']
    assert upload(studio) == identity
    code, value = studio(API+'/documents/'+identity+'/archive', {'archived':True})
    assert code == 200 and value['document']['archived']
    assert upload(studio) == identity
    store = service.library(app_server)
    store.conversions.shutdown();store.planning.shutdown()
    reopened = service.DocumentLibrary(app_server.DATA_DIR)
    try:
        assert reopened.content(identity)['markdown'] == content['markdown']
        assert not reopened.documents[identity]['archived']
    finally:
        reopened.conversions.shutdown();reopened.planning.shutdown()


def test_evidence_analysis_uses_configured_text_model_and_keeps_secrets_out(studio, monkeypatch):
    identity = upload(studio);assert wait(studio,identity)['status']=='ready'
    app_server.save_config(CONFIG)
    calls=[]
    def model(config,messages,**kwargs):
        calls.append((config,messages,kwargs))
        body=json.loads(messages[-1]['content']);section=body['sections'][0]
        return json.dumps({'summary':'A measured experiment, with no causal claim.', 'suggestions':[{
            'title':'Sample preparation workflow','kind':'workflow','reason':'Show experimental order',
            'elements':['samples','measurement'],'relations':[{'source':'samples','target':'measurement','type':'sequence'}],
            'visual_plan':'Left to right, preparation followed by measurement',
            'evidence':[{'section_id':section['section_id'],'quote':TEXT}]}]})
    monkeypatch.setattr(service.analyze_documents.__globals__['pipeline'],'_chat',model)
    code,value=studio(API+'/analyze',{'document_ids':[identity],'focus':'experiment'})
    assert code==202,value
    aid=value['analysis']['id'];assert wait(studio,aid,'analyses')['status']=='completed'
    _,result=studio(API+'/analyses/'+aid)
    suggestion=result['result']['suggestions'][0]
    assert suggestion['evidence'][0]['document_id']==identity
    assert TEXT in suggestion['prompt'] and 'samples → measurement' in suggestion['prompt']
    assert result['result']['coverage']['all_selected_sections_read']
    assert calls[0][0]['text']['model']=='test-document-model'
    assert calls[0][2]['timeout']==120
    for path in service.library(app_server).root.rglob('*.json'):
        assert 'test-key' not in path.read_text(encoding='utf8')


def test_duplicate_analysis_and_cancel_discard_late_result(studio,monkeypatch):
    identity=upload(studio);assert wait(studio,identity)['status']=='ready';app_server.save_config(CONFIG)
    entered,release=threading.Event(),threading.Event()
    def slow(*args,**kwargs):
        entered.set();release.wait(4)
        return {'suggestions':[{'title':'late'}]}
    monkeypatch.setattr(service,'analyze_documents',slow)
    _,value=studio(API+'/analyze',{'document_ids':[identity]});aid=value['analysis']['id']
    try:
        assert entered.wait(3)
        _,duplicate=studio(API+'/analyze',{'document_ids':[identity]})
        assert duplicate['duplicate'] and duplicate['analysis']['id']==aid
        code,cancelled=studio(API+'/analyses/'+aid+'/cancel',{})
        assert code==200 and cancelled['analysis']['status']=='cancelled'
    finally:
        release.set()
    service.library(app_server).planning.submit(lambda:None).result(timeout=4)
    _,final=studio(API+'/analyses/'+aid)
    assert final['analysis']['status']=='cancelled' and final['result'] is None
    assert service.library(app_server).content(identity)['markdown']


def test_offline_model_failure_keeps_markdown(studio,monkeypatch):
    identity=upload(studio);assert wait(studio,identity)['status']=='ready';app_server.save_config(CONFIG)
    def offline(*a,**k):raise RuntimeError('local fake model is offline')
    monkeypatch.setattr(service,'analyze_documents',offline)
    _,value=studio(API+'/analyze',{'document_ids':[identity]});aid=value['analysis']['id']
    assert wait(studio,aid,'analyses')['status']=='failed'
    assert TEXT in service.library(app_server).content(identity)['markdown']


def test_invalid_upload_selection_and_request_origin(studio):
    for name,data in [('x.exe','YQ=='),('x.pdf','broken'),('x.txt','')]:
        assert studio(API+'/upload',{'name':name,'data':data})[0]==400
    assert studio(API+'/upload',{'name':'x.txt','data':'YQ=='},headers={'Origin':'https://example.invalid'})[0]==403
    assert studio(API+'/upload',{'name':'x.txt','data':'YQ=='},headers={'Content-Type':'text/plain'})[0]==415
    assert studio(API+'/analyze',{'document_ids':[]})[0]==400
    assert studio(API+'/documents/d_0000000000000000')[0]==404
    identity=upload(studio);assert wait(studio,identity)['status']=='ready'
    code,result=studio(API+'/analyze',{'document_ids':[identity]})
    assert code==400 and '文本模型' in result['error']


def test_interrupted_queue_on_restart_preserves_original(tmp_path):
    folder=tmp_path/'document-assistant'/'documents'/'d_0123456789abcdef';folder.mkdir(parents=True)
    (folder/'source.txt').write_text(TEXT)
    service.atomic(folder/'meta.json',{'id':folder.name,'created':1,'status':'converting'})
    store=service.DocumentLibrary(tmp_path)
    try:
        assert store.documents[folder.name]['status']=='failed'
        assert (folder/'source.txt').read_text()==TEXT
    finally:
        store.conversions.shutdown();store.planning.shutdown()
