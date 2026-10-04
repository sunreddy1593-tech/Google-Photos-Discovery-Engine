"""Phase 6 failure ledger. Development observations only; holdout stays closed."""

from types import SimpleNamespace

import pytest

from src.gold.evaluate import HoldoutAnalysisError
from src.gold.failures import CATEGORY_IDS, OFFICIAL_DEV_RUN_ID, build_development_failure_ledger
from src.gold.match import MatchSpan

SENTENCE = "UNIQUE_SOURCE_SENTENCE_ZX9 the rest of a private document"


def _document(doc_id: str, scope: str, *, prefilter: bool = True):
    return SimpleNamespace(doc_id=doc_id, scope_class=scope, prefilter_should_pass=prefilter)


def _prediction(scope: str, *, passed: bool = True, technical: str = "ok"):
    return SimpleNamespace(technical_state=technical, prefilter_passed=passed, scope_class=scope)


def _report(**extra):
    payload = {
        "split": "dev",
        "documents": 4,
        "gold_cases": 2,
        "prefilter_recall": 0.5,
        "excluded_technical_failures": 1,
        "relevance": {"precision": 0.5, "recall": 0.5},
        "agreement": {"pairs": 0, "raw_agreement": None, "cohen_kappa": None},
        "unsupported_inference": {"overall": 0.5, "retrieval_trigger": 1.0, "outcome": 0.0},
        "case_coverage": {"matched_cases": 1, "gold_cases": 2},
        "saved_inputs": {},
    }
    payload.update(extra)
    return payload


def test_holdout_failure_ledger_is_refused() -> None:
    with pytest.raises(HoldoutAnalysisError, match="holdout"):
        build_development_failure_ledger(
            report={"split": "holdout"}, documents=(), predictions={},
        )


def test_every_category_has_a_written_disposition_and_no_source_text() -> None:
    documents = (
        _document("keep", "core_incomplete_recall"),
        _document("drop", "core_incomplete_recall"),
        _document("noise", "out_of_scope", prefilter=False),
        _document("boundary", "adjacent_known_item_retrieval"),
    )
    predictions = {
        "keep": _prediction("core_incomplete_recall"),
        "drop": _prediction("out_of_scope", passed=False),
        "noise": _prediction("adjacent_known_item_retrieval"),
        "boundary": _prediction("core_incomplete_recall"),
        "broken": _prediction(None, technical="provider_error"),
    }
    gold_cases = (
        SimpleNamespace(doc_id="keep", gold_case_id="keep#g01", expected_evidence=("alpha",)),
        SimpleNamespace(doc_id="drop", gold_case_id="drop#g01", expected_evidence=("beta",)),
    )
    extracted = (
        SimpleNamespace(
            doc_id="keep", case_id="keep#c01",
            spans=(MatchSpan("alpha", 0, 5, "valid", "outcome"),),
        ),
        SimpleNamespace(
            doc_id="noise", case_id="noise#c01",
            spans=(MatchSpan("gamma", 0, 5, "valid", "outcome"),),
        ),
    )
    events = (
        {"stage": "extract", "status": "failed", "target_id": "noise", "reason_code": "provider_unavailable",
         "detail": {"provider_diagnostic": {"error_code": "json_validate_failed"}}},
        {"stage": "extract", "status": "failed", "target_id": "cat", "reason_code": "evidence_validation_failed",
         "detail": {}},
        {"stage": "extract", "status": "skipped", "target_id": "storage", "reason_code": "evidence_validation_failed",
         "detail": {"skip_cause": "out_of_scope"}},
        {"stage": "extract", "status": "succeeded", "target_id": "empty", "detail": {"case_count": 0}},
    )
    ledger = build_development_failure_ledger(
        report=_report(),
        documents=documents,
        predictions=predictions,
        gold_cases=gold_cases,
        extracted_cases=extracted,
        texts={"keep": SENTENCE},
        extraction_events=events,
    )
    assert [row["category"] for row in ledger["categories"]] == list(CATEGORY_IDS)
    assert all(row["statement"].strip() for row in ledger["categories"])
    assert all(row["disposition"] in {"corrective_action", "accepted_limitation"} for row in ledger["categories"])
    by_id = {row["category"]: row for row in ledger["categories"]}
    assert by_id["prefilter_false_drop"]["evidence"] == ["drop"]
    assert by_id["relevance_false_positive"]["evidence"] == ["noise"]
    assert by_id["relevance_false_negative"]["evidence"] == ["drop"]
    assert by_id["scope_boundary_disagreement"]["observed_count"] == 1
    assert by_id["provider_schema_rejection"]["evidence"] == ["noise"]
    assert by_id["evidence_span_rejection"]["evidence"] == ["cat"]
    assert "storage" not in by_id["evidence_span_rejection"]["evidence"]
    assert by_id["unmatched_gold_case"]["evidence"] == ["drop#g01"]
    assert by_id["unmatched_model_case"]["evidence"] == ["noise#c01"]
    assert by_id["accepted_empty_extraction"]["evidence"] == ["empty"]
    assert by_id["inter_reviewer_agreement"]["statement"].count("null") >= 1
    assert "Further gold labelling is closed" in by_id["gold_set_final"]["statement"]
    assert "does not open" in by_id["holdout_prior_exposure"]["statement"]
    assert ledger["thresholds"] == {
        "prefilter_recall": 0.90,
        "relevance_precision": 0.85,
        "relevance_recall": 0.80,
    }
    assert ledger["thresholds_lowered"] is False
    rendered = str(ledger)
    assert SENTENCE not in rendered
    assert "alpha" not in rendered


def test_official_development_run_records_project_limits_without_rescoring() -> None:
    report = _report(
        documents=10,
        gold_cases=6,
        saved_inputs={
            "run_id": OFFICIAL_DEV_RUN_ID,
            "schema_denominator": "accepted records only",
            "measured_prompts": {
                "extract": "extract/v4",
                "relevance": "relevance/v6",
                "extraction_manifest_relevance_pin": "relevance/v5",
            },
        },
        unsupported_inference={"overall": 0.0},
        case_coverage={"matched_cases": 4, "gold_cases": 6},
    )
    ledger = build_development_failure_ledger(report=report, documents=(), predictions={})
    by_id = {row["category"]: row for row in ledger["categories"]}
    assert "35 documents" in by_id["gold_set_final"]["statement"]
    assert "final gold set" in by_id["gold_set_final"]["statement"]
    assert "5 of 15" in by_id["holdout_prior_exposure"]["statement"]
    assert "7 of 15" in by_id["holdout_prior_exposure"]["statement"]
    assert "reddit-0d477b54fb9b#c01" in by_id["model_case_semantic_approval"]["statement"]
    assert by_id["model_case_semantic_approval"]["statement"].endswith("Approval was not extended by this ledger.") or (
        "stay unapproved" in by_id["model_case_semantic_approval"]["statement"]
    )
    assert by_id["cross_stage_prompt_label"]["disposition"] == "corrective_action"
    assert "relevance/v6" in by_id["cross_stage_prompt_label"]["statement"]
    assert by_id["accepted_empty_extraction"]["disposition"] == "corrective_action"
    assert by_id["accepted_record_schema_denominator"]["disposition"] == "accepted_limitation"
    assert ledger["holdout_rescored"] is False
    assert ledger["labels_edited"] is False
