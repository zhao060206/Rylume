"""Evidence and long-document contracts for document recommendations."""
import copy
import json
import pytest
import document_advisor as advisor
from document_conversion import DocumentCancelled

QUOTE='Samples are collected, washed with buffer, measured and then analyzed.'
def section(key='d_test:s0001',text=QUOTE):
    return {'section_id':key,'document_id':'d_test','document_name':'protocol.txt','locator':'Section 1','text':text}
def suggestion(key='d_test:s0001',quote=QUOTE,title='Experimental workflow'):
    return {'title':title,'kind':'workflow','priority':'high','reason':'Show experimental order','elements':['Samples','analysis'],
            'relations':[{'source':'Samples','target':'analysis','type':'sequence'}],'visual_plan':'Left to right',
            'evidence':[{'section_id':key,'quote':quote}]}

@pytest.mark.parametrize('changes',[{'kind':[]},{'kind':{}},{'evidence':37},{'evidence':'text'},{'evidence':None},
    {'evidence':[{'section_id':[],'quote':QUOTE}]},{'evidence':[{'section_id':'unknown','quote':QUOTE}]},
    {'evidence':[{'section_id':'d_test:s0001','quote':'A fabricated sentence unrelated to the uploaded document.'}]}])
def test_malformed_or_unlocatable_evidence_never_yields_reusable_prompt(changes):
    item=suggestion();item.update(changes)
    values,rejected=advisor.validate_suggestions({'suggestions':[item]}, {'d_test:s0001':section()})
    assert values==[] and rejected==1

def test_invalid_relations_are_removed_and_chart_needs_data():
    item=suggestion();item['relations']=[{'source':'invented','target':'analysis','type':'activates'}]
    values,_=advisor.validate_suggestions({'suggestions':[item]}, {'d_test:s0001':section()})
    assert not values[0]['relations'] and values[0]['needs_confirmation']
    item['relations']=37;item['kind']='data_chart'
    values,_=advisor.validate_suggestions({'suggestions':[item]}, {'d_test:s0001':section()})
    assert not values[0]['relations'] and '原始数据' in values[0]['prompt']

def test_all_selected_sections_are_sent_before_merge_and_citations_survive(monkeypatch):
    documents=[{'id':'d_test','name':'protocol.txt','sections':[{'key':f's{i:04}','locator':f'Part {i}','text':QUOTE+'x'*9000} for i in range(1,5)]}]
    received=[]
    def fake(config,messages,**kwargs):
        body=json.loads(messages[-1]['content'])
        if 'sections' in body:
            received.extend(s['section_id'] for s in body['sections'])
            row=body['sections'][0]
            return json.dumps({'summary':'Part read','suggestions':[suggestion(row['section_id'],QUOTE,title=row['locator'])]})
        return json.dumps({'suggestions':body['candidate_figures']})
    monkeypatch.setattr(advisor.pipeline,'_chat',fake)
    result=advisor.analyze_documents(documents,{'text':{'model':'local-test'}})
    assert received==[f'd_test:s{i:04}' for i in range(1,5)]
    assert result['coverage']['sections']==4 and result['coverage']['all_selected_sections_read']
    assert len(result['suggestions'])==4
    assert all(c['prompt'] and c['kind_label']=='流程图' for c in result['suggestions'])

def test_cancel_after_model_response_discards_it(monkeypatch):
    cancelled=[False]
    def fake(*a,**k):cancelled[0]=True;return '{}'
    monkeypatch.setattr(advisor.pipeline,'_chat',fake)
    with pytest.raises(DocumentCancelled):
        advisor.analyze_documents([{'id':'d_test','name':'protocol','sections':[{'key':'s0001','locator':'1','text':QUOTE}]}],{},cancelled=lambda:cancelled[0])

def test_oversized_analysis_fails_before_any_model_call(monkeypatch):
    calls=[];monkeypatch.setattr(advisor.pipeline,'_chat',lambda *a,**k:calls.append(1))
    with pytest.raises(ValueError,match='36 万字'):
        advisor.analyze_documents([{'id':'d_test','name':'protocol','sections':[{'key':'s0001','locator':'1','text':'x'*360001}]}],{})
    assert not calls
