"""Synthetic contract and request-boundary tests, no n8n or source calls."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.collect.community import import_payload, collect_webhook
from src.core.errors import ConfigError
from src.core.ids import author_hash
from scripts.prepare_n8n_collection import VALIDATE, EXTRACT

pytestmark=pytest.mark.synthetic


def envelope():
    return {'contract':'community-collection/v1','model_calls':0,'execution_id':'123', 'requests_made':1,
            'items':[{'source_url':'https://support.google.com/photos/thread/12345','source_item_id':'12345',
                'raw_text':'I remember the picnic.\nI cannot recall its date.', 'author_name':'private-author',
                'text_kind':'original_post','replies_complete':False,'collected_at':'2026-10-04T00:00:00Z'}]}


def test_original_text_author_privacy_and_reimport(tmp_path):
    a=envelope()
    assert import_payload(a,tmp_path,author_salt='synthetic-salt',document_limit=1)['documents_written']==1
    before=(tmp_path/'collected_documents.jsonl').read_bytes()
    assert import_payload(a,tmp_path,author_salt='synthetic-salt',document_limit=1)['already_present']==1
    assert (tmp_path/'collected_documents.jsonl').read_bytes()==before
    row=json.loads(before)
    assert row['raw_text']==a['items'][0]['raw_text']
    assert row['author_hash']==author_hash('synthetic-salt','google_support','private-author')
    assert 'private-author' not in before.decode()
    assert row['metadata']['replies_complete'] is False
    a['items'][0]['raw_text']='Edited source'
    with pytest.raises(ValueError,match='changed'):
        import_payload(a,tmp_path,author_salt='synthetic-salt',document_limit=1)
    assert (tmp_path/'collected_documents.jsonl').read_bytes()==before


@pytest.mark.parametrize('change',[{'contract':'tags'},{'model_calls':1},{'items':[{'summary':'fake source'}]}])
def test_incompatible_contract_does_not_create_output(tmp_path,change):
    a=envelope(); a.update(change)
    with pytest.raises((ValueError,KeyError)):
        import_payload(a,tmp_path/'out',author_salt='salt',document_limit=1)
    assert not (tmp_path/'out').exists()


def test_import_dry_run_and_missing_salt(tmp_path):
    out=tmp_path/'out'
    assert import_payload(envelope(),out,author_salt='salt',document_limit=1,dry_run=True)['documents_written']==0
    assert not out.exists()
    with pytest.raises(ConfigError): import_payload(envelope(),out,author_salt='',document_limit=1)
    assert not out.exists()


def test_webhook_bounded_single_request_and_dry_run(tmp_path):
    urls=tmp_path/'urls.txt'; urls.write_text('https://support.google.com/photos/thread/12345\n')
    calls=[]
    def post(*args,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200,json=lambda:envelope())
    common=dict(webhook_url='https://example.app.n8n.cloud/webhook/discovery-original-posts-v1',key='synthetic-key',
                author_salt='salt',document_limit=1,request_budget=1,transport=post)
    assert collect_webhook(urls,tmp_path/'dry',dry_run=True,**common)['webhook_requests']==0
    assert not calls and not (tmp_path/'dry').exists()
    assert collect_webhook(urls,tmp_path/'live',**common)['webhook_requests']==1
    assert len(calls)==1 and calls[0]['allow_redirects'] is False
    assert calls[0]['json']['model_calls']==0


def test_webhook_credentials_fail_before_transport(tmp_path):
    with pytest.raises(ConfigError):
        collect_webhook(tmp_path/'missing',tmp_path/'out',webhook_url='',key='',author_salt='',document_limit=1,request_budget=1)
    assert not (tmp_path/'out').exists()


def test_old_tagging_webhook_refused_without_requests(tmp_path):
    with pytest.raises(ValueError,match='tagging route'):
        collect_webhook(tmp_path/'missing',tmp_path/'out',
            webhook_url='https://example.app.n8n.cloud/webhook/photo-discovery',key='synthetic-key',
            author_salt='salt',document_limit=1,request_budget=1,
            transport=lambda *a,**k:pytest.fail('old tagging route must not be called'))
    assert not (tmp_path/'out').exists()


def test_workflow_js_preserves_original_and_refuses_missing_structured_text():
    script='''const validate = new Function('$input', %s);
const rows = validate({first:()=>({json:{body:{contract:'community-collection/v1',model_calls:0,document_limit:1,request_budget:1,urls:['https://support.google.com/photos/thread/12345']}}})});
const code = new Function('$input','$', %s);
const $ = () => ({all:()=>rows});
const text='First line.\\nSecond line.';
const html='<script type="application/ld+json">'+JSON.stringify({'@type':'QAPage',mainEntity:{text}})+'</script>';
const good=code({all:()=>[{json:{html}}]},$)[0].json;
const bad=code({all:()=>[{json:{html:'<body>Boilerplate and tags</body>'}}]},$)[0].json;
if(good.raw_text!==text || good.replies_complete!==false || !bad.failure) throw Error('contract failure');
try {validate({first:()=>({json:{body:{contract:'community-collection/v1',model_calls:0,document_limit:1,request_budget:1,urls:['https://evil.example']}}})}); throw Error('accepted unsafe URL');} catch(e) {if(e.message==='accepted unsafe URL')throw e;}
'''%(json.dumps(VALIDATE),json.dumps(EXTRACT))
    result=subprocess.run(['node','-e',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
