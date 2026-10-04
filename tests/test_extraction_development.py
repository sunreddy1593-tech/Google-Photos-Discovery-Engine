"""Development-split extraction bounds. Completions are mocked. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import main
from src.core.versions import prompt_version
from src.llm.cache import CacheEntry, ResponseCache
from src.models.enums import EvidenceOwnerType, ReasonCode, ScopeClass, ValidationState
from src.pipeline.extraction import PROMPT_ID, extraction_request_identity
from src.pipeline.extraction_development import (
    CORPUS_MAX_TOKENS,
    DevelopmentBoundsError,
    analysis_evidence_spans,
    count_stage_events,
    format_funnel,
    load_derived_for,
    run_development_extraction,
    verbatim_span_failures,
)
from src.pipeline.extraction_pilot import PILOT_MODEL, PILOT_PROVIDER
from tests.synthetic import case_scalar_spans, make_case, make_decision, make_span
from tests.test_extraction_pilot import CORE, CountingProvider, _decision, _derived


def test_analysis_span_count_includes_external_and_inline_evidence_once() -> None:
    case = make_case(validation_state=ValidationState.valid)
    inline = [s.model_dump(mode="json") for s in case.all_evidence_spans]
    external = [s.model_dump(mode="json") for s in case_scalar_spans()]
    union = analysis_evidence_spans([case.model_dump(mode="json")], inline + external)
    assert len(union) == len(inline) + len(external)
    assert {s["field_name"] for s in union} >= {"problem_summary", "remembered_cues", "severity"}
    assert len({s["evidence_id"] for s in union}) == len(union)


def test_analysis_span_count_excludes_failed_attempts() -> None:
    case = make_case(validation_state=ValidationState.valid)
    ledger = [s.model_dump(mode="json") for s in case_scalar_spans()]
    ledger.append(make_span("problem_summary", "last summer", owner_id="failed#u123").model_dump(mode="json"))
    union = analysis_evidence_spans([case.model_dump(mode="json")], ledger)
    assert all(s["owner_id"] == case.case_id for s in union)


def test_analysis_span_count_refuses_missing_scalar_evidence() -> None:
    case = make_case(validation_state=ValidationState.valid)
    with pytest.raises(DevelopmentBoundsError, match="current record gate"):
        analysis_evidence_spans([case.model_dump(mode="json")], [])


def test_analysis_span_count_refuses_repeated_case() -> None:
    case = make_case(validation_state=ValidationState.valid).model_dump(mode="json")
    with pytest.raises(DevelopmentBoundsError, match="unique"):
        analysis_evidence_spans([case, case], [s.model_dump(mode="json") for s in case_scalar_spans()])


def _pool():
    decisions = [
        _decision("doc-a", CORE),
        _decision("doc-b", CORE),
        make_decision(
            decision_id="decision-doc-c",
            doc_id="doc-c",
            scope_class=ScopeClass.out_of_scope,
            reason_code=ReasonCode.other_out_of_scope,
            evidence=(
                make_span(
                    "scope_class",
                    "I could not remember the exact date",
                    owner_id="decision-doc-c",
                    owner_type=EvidenceOwnerType.relevance_decision,
                    doc_id="doc-c",
                ),
            ),
            validation_state=ValidationState.valid,
        ),
    ]
    derived = {doc_id: _derived(doc_id) for doc_id in ("doc-a", "doc-b", "doc-c")}
    return decisions, derived


def _run(tmp_path: Path, provider, **kwargs):
    decisions, derived = _pool()
    options = dict(
        doc_ids=["doc-b", "doc-a", "doc-c"],
        development=["doc-a", "doc-b", "doc-c"],
        holdout=["holdout-secret"],
        model_decisions=decisions,
        human_decisions=[],
        derived_by_id=derived,
        output_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        provider_name=PILOT_PROVIDER,
        model_name=PILOT_MODEL,
        temperature=0.0,
        max_tokens=CORPUS_MAX_TOKENS,
        max_retries=1,
        call_budget=2,
        provider=provider,
        api_key="test-key",
    )
    options.update(kwargs)
    return run_development_extraction(**options)


def test_dry_run_makes_no_call_and_writes_nothing(tmp_path: Path) -> None:
    result = _run(tmp_path, None, dry_run=True, api_key=None)
    assert result.provider_calls == 0
    assert result.eligible == 2
    assert result.blocked == ("doc-c",)
    assert result.files_written == ()
    assert list(tmp_path.rglob("run_manifest.json")) == []


def test_budget_holdout_and_partial_split_are_refused(tmp_path: Path) -> None:
    provider = CountingProvider()
    with pytest.raises(DevelopmentBoundsError, match="external requests"):
        _run(tmp_path / "budget", provider, call_budget=1)
    assert provider.calls == 0

    with pytest.raises(DevelopmentBoundsError, match="holdout"):
        _run(
            tmp_path / "holdout",
            provider,
            doc_ids=["doc-a", "doc-b", "holdout-secret"],
            development=["doc-a", "doc-b", "holdout-secret"],
            holdout=["holdout-secret"],
        )
    assert provider.calls == 0

    with pytest.raises(DevelopmentBoundsError, match="full development split"):
        _run(tmp_path / "partial", provider, doc_ids=["doc-a", "doc-b"])
    assert provider.calls == 0
    assert list(tmp_path.rglob("run_manifest.json")) == []


def test_eligible_documents_are_called_once_and_blocked_documents_are_skipped(tmp_path: Path) -> None:
    provider = CountingProvider()
    result = _run(tmp_path, provider)
    assert provider.calls == 2
    assert result.cache_hits == 0
    assert result.valid_cases == 0
    assert set(result.blocked) == {"doc-c"}
    events = [
        json.loads(line)
        for line in next(tmp_path.rglob("stage_events.jsonl")).read_text(encoding="utf-8").splitlines()
    ]
    statuses = {row["target_id"]: row["status"] for row in events}
    assert statuses == {"doc-a": "succeeded", "doc-b": "succeeded", "doc-c": "skipped"}


def test_cache_hit_is_not_called_again(tmp_path: Path) -> None:
    _decisions, derived = _pool()
    identity = extraction_request_identity(
        derived["doc-a"],
        provider_name=PILOT_PROVIDER,
        model_name=PILOT_MODEL,
        temperature=0.0,
        max_tokens=CORPUS_MAX_TOKENS,
        prompt_version_value=prompt_version(PROMPT_ID),
    )
    cache = tmp_path / "cache"
    entry = CacheEntry(
        cache_key=str(identity["cache_key"]),
        provider=str(identity["provider"]),
        model=str(identity["model"]),
        prompt_id=str(identity["prompt_id"]),
        prompt_version=str(identity["prompt_version"]),
        schema_version=str(identity["schema_version"]),
        ruleset_version=None,
        content_hash=str(identity["content_hash"]),
        decoding_params=dict(identity["decoding_params"]),
        request_text=str(identity["request_text"]),
        raw_response=json.dumps({"doc_id": "doc-a", "cases": []}),
        input_tokens=3,
        output_tokens=1,
        cached_at="2026-10-03T00:00:00+00:00",
        finish_reason="stop",
    )
    ResponseCache(cache).write(entry)
    stored = ResponseCache(cache).path_for(PROMPT_ID, entry.cache_key)
    before = stored.read_bytes()
    provider = CountingProvider()
    result = _run(tmp_path / "run", provider, cache_dir=cache)
    assert provider.calls == 1
    assert result.cache_hits == 1
    assert stored.read_bytes() == before


def test_derived_loader_drops_unwanted_rows(tmp_path: Path) -> None:
    secret = "HOLDOUT-SECRET-TEXT"
    path = tmp_path / "derived.jsonl"
    path.write_text(
        "\n".join(
            [
                _derived("doc-a").model_dump_json(),
                json.dumps({"doc_id": "holdout-secret", "raw_text_audit": secret}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_derived_for(path, {"doc-a"})
    assert set(loaded) == {"doc-a"}
    assert secret not in repr(loaded)


def test_funnel_counts_only_named_documents_and_stages(tmp_path: Path) -> None:
    path = tmp_path / "stage_events.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"stage": "normalize", "status": "succeeded", "target_id": "doc-a"}),
                json.dumps({"stage": "normalize", "status": "succeeded", "target_id": "holdout-secret"}),
                json.dumps({"stage": "extract", "status": "failed", "target_id": "doc-a"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    counts = count_stage_events(((path, frozenset({"normalize"})),), {"doc-a"})
    assert counts == {"normalize": {"succeeded": 1}}
    assert "holdout" not in format_funnel(counts)


def test_verbatim_span_failures_use_stored_offsets() -> None:
    text = "A photo of the white Camaro is missing"
    quote = "white Camaro"
    start = text.index(quote)
    spans = [
        {
            "doc_id": "doc-a",
            "quote": quote,
            "start_char": start,
            "end_char": start + len(quote),
            "validation_state": "valid",
        },
        {
            "doc_id": "doc-a",
            "quote": "white Camaro",
            "start_char": 0,
            "end_char": 4,
            "validation_state": "valid",
        },
    ]
    assert verbatim_span_failures(spans, {"doc-a": text}) == 1


def test_command_dry_run_reports_the_development_split_without_a_provider_call(
    tmp_path: Path, capsys
) -> None:
    output = tmp_path / "development-corpus"
    code = main.main(
        [
            "run",
            "--stages",
            "extract",
            "--development-corpus",
            "--dry-run",
            "--provider",
            "groq",
            "--split",
            "development",
            "--call-budget",
            "21",
            "--max-retries",
            "1",
            "--cache",
            str(tmp_path / "cache"),
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "documents            35" in captured.out
    assert "eligible             21" in captured.out
    assert "provider calls       0" in captured.out
    assert "blocked              14" in captured.out
    assert not output.exists()
