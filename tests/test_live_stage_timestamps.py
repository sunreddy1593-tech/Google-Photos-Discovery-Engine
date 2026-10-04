"""Mocked live stages record execution dates without any network access."""
import json
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.llm.providers.base import ProviderDiagnostic, provider_failed
from src.pipeline.stages import run_phase4
from src.normalize.derive import derive_document
from tests.synthetic import make_document
from tests.test_extraction import FakeProvider, case_body, jsonl, response, run, valid_decision, DOC_ID

WHEN = datetime(2030, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*args, **kwargs):
        raise AssertionError("Offline timestamp regression attempted a network call")
    monkeypatch.setattr(socket, "socket", reject)


class FailedProvider(FakeProvider):
    def complete_structured(self, *args, **kwargs):
        self.calls += 1
        raise provider_failed("provider_error", diagnostic=ProviderDiagnostic(
            category="invalid_request", http_status=400, error_code="json_validate_failed",
        ))


def test_failed_extraction_records_one_injected_run_date(tmp_path):
    provider = FailedProvider()
    result = run(tmp_path, provider, [valid_decision()], recorded_at=WHEN)
    root = Path(result.output_dir)
    assert provider.calls == 1
    assert result.failed_candidates == 1
    for name, field in [("extraction_failures.jsonl", "occurred_at"),
                        ("stage_events.jsonl", "occurred_at"), ("review_queue.jsonl", "opened_at")]:
        for row in jsonl(root / name):
            assert datetime.fromisoformat(row[field]) == WHEN
    manifest = json.loads((root / "run_manifest.json").read_text())
    assert datetime.fromisoformat(manifest["generated_at"]) == WHEN
    assert not manifest["tokens"]["usage_totals_complete"]
    assert manifest["tokens"]["provider_calls_without_recorded_usage"] == 1


def test_successful_extraction_records_current_live_date(tmp_path):
    before = datetime.now(UTC)
    result = run(tmp_path, FakeProvider(response(DOC_ID, [case_body()])), [valid_decision()])
    after = datetime.now(UTC)
    case, = jsonl(Path(result.output_dir) / "retrieval_cases.jsonl")
    assert before <= datetime.fromisoformat(case["extracted_at"]) <= after


def test_relevance_records_injected_date_across_artifacts(tmp_path):
    document = make_document(raw_text="I cannot find the photo in my Google Photos library.")
    provider = FailedProvider()
    run_phase4([document], [derive_document(document, derived_at=WHEN)], [], output_dir=tmp_path,
               stages=["prefilter", "relevance"], provider=provider, provider_name="fake",
               model_name="synthetic-model",
               max_retries=1, provider_call_budget=1, recorded_at=WHEN)
    assert provider.calls == 1
    for name, field in [("relevance_decisions.jsonl", "decided_at"),
                        ("stage_events.jsonl", "occurred_at"), ("review_queue.jsonl", "opened_at")]:
        rows = jsonl(tmp_path / name)
        assert rows
        for row in rows:
            assert datetime.fromisoformat(row[field]) == WHEN
    manifest = json.loads((tmp_path / "run_manifest.json").read_text())
    assert datetime.fromisoformat(manifest["generated_at"]) == WHEN
