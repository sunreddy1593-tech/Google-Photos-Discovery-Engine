"""One bounded collection check through the existing adapter, with safe diagnostics."""
from __future__ import annotations

import argparse
from datetime import datetime, UTC
import json
from pathlib import Path
import sys
from urllib.parse import parse_qsl, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import requests
from src.collect.community import collect_webhook, thread_id
from src.core.config import load_settings

KNOWN_SOURCE_FAILURES = frozenset({
    'no_verified_plain_original_post', 'unsupported_thread_bootstrap',
    'thread_identity_mismatch', 'ambiguous_original_post',
})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    settings = load_settings(project_root=ROOT)
    endpoint = settings.secrets.require('n8n_collection_webhook_url', needed_for='collection check')
    key = settings.secrets.require('n8n_webhook_key', needed_for='collection check')
    salt = settings.secrets.require('author_salt', needed_for='collection check')
    parts = urlsplit(args.url)
    if parts.fragment or parse_qsl(parts.query) not in ([], [('hl', 'en')]):
        raise ValueError('Only the optional hl=en language query can be removed')
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    item_id = thread_id(url)
    out, report = args.out.resolve(), args.report_dir.resolve()
    if out.exists() or report.exists():
        raise ValueError('Both destinations must be fresh; no repeat attempt')
    report.mkdir(parents=True)
    source = report / 'thread-urls.txt'
    source.write_text(url + '\n', encoding='utf-8')
    plan = {'supplied_url': args.url, 'requested_url': url, 'source_item_id': item_id,
            'document_limit': 1, 'source_request_budget': 1, 'maximum_webhook_requests': 1,
            'model_calls_requested': 0, 'retries': 0,
            'recorded_at': datetime.now(UTC).isoformat()}
    (report / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    diagnostic = {'webhook_requests_attempted': 0, 'http_status': None,
                  'source_requests_attested': None, 'model_calls_attested': None,
                  'provider_calls_in_local_collector': 0, 'collection_records_written': 0}

    def post(*positional, **kwargs):
        if diagnostic['webhook_requests_attempted']:
            raise ValueError('One-request bound already consumed')
        diagnostic['webhook_requests_attempted'] = 1
        # Reserve before sending: interruption is not authorization to rerun.
        (report / 'attempt-reserved.json').write_text('{"attempt": 1}\n', encoding='utf-8')
        response = requests.post(*positional, **kwargs)
        diagnostic['http_status'] = response.status_code
        try:
            payload = response.json()
        except ValueError:
            diagnostic['response_format'] = 'not_json'
            return response
        diagnostic['response_format'] = 'json'
        if isinstance(payload, dict):
            for incoming, outgoing in (('requests_made', 'source_requests_attested'),
                                        ('model_calls', 'model_calls_attested')):
                value = payload.get(incoming)
                if type(value) is int:
                    diagnostic[outgoing] = value
            if payload.get('contract') == 'community-collection/v1':
                diagnostic['contract'] = payload['contract']
            if isinstance(payload.get('execution_id'), (str, int)):
                execution = str(payload['execution_id'])
                if execution.isdigit():
                    diagnostic['execution_id'] = execution
            items = payload.get('items')
            if isinstance(items, list):
                diagnostic['items_returned'] = len(items)
            # Retain only known structural failure codes, never headers/author text.
            failures = payload.get('failures')
            if isinstance(failures, list):
                diagnostic['failures_returned'] = len(failures)
                diagnostic['failure_reasons'] = [
                    row['reason'] if isinstance(row, dict) and isinstance(row.get('reason'), str)
                    and row['reason'] in KNOWN_SOURCE_FAILURES else 'unrecognized_failure'
                    for row in failures
                ]
        return response

    try:
        result = collect_webhook(source, out, webhook_url=endpoint, key=key,
                                 author_salt=salt, document_limit=1, request_budget=1,
                                 transport=post)
        diagnostic['status'] = 'completed'
        diagnostic['collection_records_written'] = result['documents_written']
        diagnostic['collection_result'] = result
    except Exception as exc:
        # Exception details can contain request headers; never print or persist them.
        diagnostic['status'] = 'failed'
        diagnostic['failure_type'] = type(exc).__name__
    diagnostic['collection_output_created'] = out.exists()
    (report / 'diagnostic.json').write_text(json.dumps(diagnostic, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(diagnostic, indent=2))
    return int(diagnostic['status'] != 'completed')


if __name__ == '__main__':
    raise SystemExit(main())
