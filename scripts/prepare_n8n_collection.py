"""Prepare a collection-only derivative; preserve the owner's tagging workflow."""
from __future__ import annotations
import json
from pathlib import Path

VALIDATE = r"""
const b = $input.first().json.body || {};
if (b.contract !== 'community-collection/v1' || b.model_calls !== 0) throw new Error('collection contract required');
if (!Number.isInteger(b.document_limit) || b.document_limit < 1 || b.document_limit > 20 ||
    !Number.isInteger(b.request_budget) || b.request_budget < 1 || b.request_budget > 20) throw new Error('invalid bounds');
if (!Array.isArray(b.urls) || !b.urls.length) throw new Error('URLs required');
const urls = [...new Set(b.urls)];
if (urls.length > Math.min(b.document_limit,b.request_budget)) throw new Error('URL count exceeds bounds');
return urls.map(url => {
  const m = /^https:\/\/support\.google\.com\/photos\/thread\/(\d+)(?:\/[^/?#]*)?\/?$/.exec(url);
  if (!m) throw new Error('only direct Google Photos thread URLs allowed');
  return {json:{source_url:url,source_item_id:m[1]}};
});
"""

# Keep the deployable node code and prepared workflow generated from one source.
EXTRACT = (Path(__file__).resolve().parents[1] / "n8n" / "extract-original-post-v2.js").read_text(encoding="utf-8")

ENVELOPE = r"""
const rows = $input.all().map(i=>i.json);
return [{json:{contract:'community-collection/v1', execution_id:String($execution.id),
  requests_made:$('Validate bounds').all().length, model_calls:0,
  items:rows.filter(r=>!r.failure),
  failures:rows.filter(r=>r.failure).map(r=>({source_item_id:r.source_item_id,reason:r.failure}))}}];
"""


def prepare(destination: Path) -> None:
    if destination.exists():
        raise ValueError('Workflow destination must be fresh')
    nodes = [
        {'name':'Collection webhook','type':'n8n-nodes-base.webhook','typeVersion':2,
         'parameters':{'httpMethod':'POST','path':'discovery-original-posts-v1',
                       'authentication':'headerAuth','responseMode':'responseNode','options':{}}},
        {'name':'Validate bounds','type':'n8n-nodes-base.code','typeVersion':2,'parameters':{'jsCode':VALIDATE}},
        {'name':'Fetch original page','type':'n8n-nodes-base.httpRequest','typeVersion':4.2,
         'retryOnFail':False,'parameters':{'url':'={{ $json.source_url }}','options':{
             'timeout':15000,'redirect':{'redirect':{'followRedirects':False}},
             'response':{'response':{'responseFormat':'text','outputPropertyName':'html'}}}}},
        {'name':'Extract original post','type':'n8n-nodes-base.code','typeVersion':2,'parameters':{'jsCode':EXTRACT}},
        {'name':'Collection envelope','type':'n8n-nodes-base.code','typeVersion':2,'parameters':{'jsCode':ENVELOPE}},
        {'name':'Return collection','type':'n8n-nodes-base.respondToWebhook','typeVersion':1.4,
         'parameters':{'respondWith':'json','responseBody':'={{ $json }}','options':{}}},
    ]
    for i,node in enumerate(nodes):
        node['id'] = f'community-collection-{i}'
        node['position'] = [i*240,0]
    connections={a['name']:{'main':[[{'node':b['name'],'type':'main','index':0}]]}
                 for a,b in zip(nodes,nodes[1:])}
    workflow={'name':'Discovery engine — bounded original-post collection v1',
              'active':False,'nodes':nodes,'connections':connections,
              'settings':{'executionOrder':'v1'},
              'meta':{'contract':'community-collection/v1','source_access':'unverified; do not bypass blocked pages',
                      'reply_policy':'original post only; replies are not fetched',
                      'testing':'offline fixtures only; not exercised against n8n Cloud'}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(workflow,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


if __name__=='__main__':
    prepare(Path('n8n/discovery-original-posts-v1.json'))
