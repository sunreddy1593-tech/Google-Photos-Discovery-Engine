"""Mocked diagnostics for the one-attempt owner collection check."""
import json
from types import SimpleNamespace

import pytest
import requests
from src.core.errors import ConfigError
from scripts import verify_n8n_once as check

pytestmark = pytest.mark.synthetic


def configure(monkeypatch, tmp_path, *, missing=False):
    values = {'n8n_collection_webhook_url': 'https://example.app.n8n.cloud/webhook/discovery-original-posts-v1',
              'n8n_webhook_key': 'synthetic-private-value', 'author_salt': 'synthetic-salt'}
    def require(name, **kwargs):
        if missing:
            raise ConfigError('Required setting missing')
        return values[name]
    monkeypatch.setattr(check, 'load_settings', lambda **kwargs: SimpleNamespace(
        secrets=SimpleNamespace(require=require)))
    out, report = tmp_path / 'collected', tmp_path / 'diagnostic'
    monkeypatch.setattr(check.sys, 'argv', ['verify_n8n_once.py', '--url',
        'https://support.google.com/photos/thread/12345/example?hl=en',
        '--out', str(out), '--report-dir', str(report)])
    return out, report


@pytest.mark.parametrize('reason', [
    'no_verified_plain_original_post', 'unsupported_thread_bootstrap',
    'thread_identity_mismatch', 'ambiguous_original_post', 'synthetic-private-value',
])
def test_one_call_preserves_user_url_and_retains_source_failure(monkeypatch, tmp_path, capsys, reason):
    out, report = configure(monkeypatch, tmp_path)
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {
            'contract': 'community-collection/v1', 'model_calls': 0, 'requests_made': 1,
            'execution_id': '14', 'items': [],
            'failures': [{'reason': reason}]})
    monkeypatch.setattr(check.requests, 'post', post)
    assert check.main() == 0
    assert len(calls) == 1 and calls[0]['allow_redirects'] is False
    assert calls[0]['json']['urls'] == ['https://support.google.com/photos/thread/12345/example']
    plan = json.loads((report / 'plan.json').read_text())
    assert plan['supplied_url'].endswith('?hl=en')
    saved = json.loads((report / 'diagnostic.json').read_text())
    assert saved['collection_records_written'] == 0
    assert saved['failure_reasons'] == [reason if reason in check.KNOWN_SOURCE_FAILURES else 'unrecognized_failure']
    assert (out / 'collected_documents.jsonl').read_bytes() == b''
    with pytest.raises(ValueError, match='fresh'):
        check.main()
    assert len(calls) == 1
    assert 'synthetic-private-value' not in capsys.readouterr().out


def test_transport_failure_has_no_retry_and_no_secret_diagnostics(monkeypatch, tmp_path, capsys):
    out, report = configure(monkeypatch, tmp_path)
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        raise requests.Timeout('synthetic-private-value in unsafe error details')
    monkeypatch.setattr(check.requests, 'post', post)
    assert check.main() == 1
    assert len(calls) == 1 and not out.exists()
    assert (report / 'attempt-reserved.json').exists()
    saved = (report / 'diagnostic.json').read_text()
    assert 'synthetic-private-value' not in saved + capsys.readouterr().out
    assert json.loads(saved)['source_requests_attested'] is None


def test_missing_credentials_fail_before_diagnostic_creation(monkeypatch, tmp_path):
    out, report = configure(monkeypatch, tmp_path, missing=True)
    monkeypatch.setattr(check.requests, 'post', lambda *a, **k: pytest.fail('Unexpected request'))
    with pytest.raises(ConfigError):
        check.main()
    assert not out.exists() and not report.exists()
