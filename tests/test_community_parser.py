"""Synthetic saved-page parsing, with no network or executable page data."""
import json
import subprocess

import pytest

from scripts.prepare_n8n_collection import EXTRACT

pytestmark = pytest.mark.synthetic


def bootstrap(*, text='Exact source.\nQuoted "date" and café 🐈.', thread_id=12345,
              canonical_id=12345, author_id=789, author_record_id=789,
              created='1618586869885306', extra='', encode_hex=False):
    thread = [None] * 39
    thread[0] = [thread_id, created, 24053, 1624382232323011]
    thread[6] = author_id
    thread[8] = 'Original question'
    thread[12] = text
    view = [None] * 46
    view[1] = thread
    view[3] = [['private-author'], [None, 1618508986403995, 0], author_record_id, 1]
    # Reply arrays deliberately contain tempting, unrelated source text.
    view[16] = [[[['reply ID', 'Reply must never replace the original']]]]
    view[39] = [[[['reply ID', '<div>Another reply</div>']]]]
    encoded = json.dumps(view, ensure_ascii=False).replace('\\', '\\\\').replace("'", "\\'")
    if encode_hex:
        encoded = encoded.replace('"', '\\x22')
    return (f'<html data-page-type="SUPPORT_FORUM_THREAD">'
            f'<link href="https://support.google.com/photos/thread/{canonical_id}?hl=en" rel="canonical">'
            f"<script>var thread_view='{encoded}';{extra}</script></html>")


def parse(html):
    script = """
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
// The harness executes only our node code. Supplied page scripts are strings.
const parser=new Function('$input','$',input.code);
const rows=parser({all:()=>[{json:{html:input.html}}]},()=>({all:()=>[
  {json:{source_url:'https://support.google.com/photos/thread/12345',source_item_id:'12345'}}]}));
if(globalThis.pageScriptExecuted)throw Error('page script executed');
process.stdout.write(JSON.stringify(rows[0].json));
"""
    result = subprocess.run(['node', '-e', script], input=json.dumps({'code': EXTRACT, 'html': html}),
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_plain_bootstrap_preserves_exact_text_unicode_author_and_created_date():
    text = '  First-person source.\n"screenshot", café 🐈, \\literal, and apostrophe\'s.  '
    result = parse(bootstrap(text=text, encode_hex=True, extra='globalThis.pageScriptExecuted=true;'))
    assert result['raw_text'] == text
    assert result['source_text_path'] == 'thread_view[1][12]'
    assert result['title'] == 'Original question'
    assert result['author_name'] == 'private-author'
    assert result['published_at'] == '2021-04-16T15:27:49.885Z'
    assert result['replies_complete'] is False


@pytest.mark.parametrize('changes,reason', [
    ({'thread_id': 99999}, 'thread_identity_mismatch'),
    ({'canonical_id': 99999}, 'thread_identity_mismatch'),
    ({'text': ''}, 'unsupported_thread_bootstrap'),
    ({'text': '<div>Original rich HTML</div>'}, 'unsupported_thread_bootstrap'),
    ({'text': None}, 'unsupported_thread_bootstrap'),
])
def test_refusal_does_not_substitute_replies_or_boilerplate(changes, reason):
    result = parse(bootstrap(**changes))
    assert result == {'failure': reason, 'source_item_id': '12345'}


def test_unknown_dates_and_unbound_author_are_not_invented():
    result = parse(bootstrap(created='not-a-date', author_record_id=888))
    assert result['published_at'] is None
    assert result['author_name'] is None


@pytest.mark.parametrize('transform', [
    lambda h: h.replace('SUPPORT_FORUM_THREAD', 'OTHER_PAGE'),
    lambda h: h.replace('thread_view=', 'unsupported_view='),
    lambda h: h.replace('<link ', '<notalink '),
    lambda h: h.replace('var thread_view=', 'var thread_view=').replace("';</script>", "';var thread_view='[]';</script>"),
    lambda h: h.replace('Exact source.', r'\q unsupported escape'),
    lambda h: h.replace('var thread_view=', 'var thread_view=JSON.parse('),
])
def test_unsupported_or_ambiguous_bootstrap_fails_closed(transform):
    assert 'failure' in parse(transform(bootstrap()))


def test_structured_data_compatibility_and_ambiguity():
    data = {'@type': 'QAPage', 'mainEntity': {'text': 'Exact original.\nNext line.'}}
    block = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
    assert parse(block)['raw_text'] == data['mainEntity']['text']
    assert parse(block + block)['failure'] == 'ambiguous_original_post'
    data['mainEntity']['url'] = 'https://support.google.com/photos/thread/99999'
    assert parse('<script type="application/ld+json">' + json.dumps(data) + '</script>')['failure'] == 'thread_identity_mismatch'


def test_builder_uses_exact_paste_ready_code():
    from pathlib import Path
    assert EXTRACT == (Path(__file__).resolve().parents[1] / 'n8n/extract-original-post-v2.js').read_text(encoding='utf-8')
