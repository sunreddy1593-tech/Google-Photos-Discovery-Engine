"""Evaluate one gold split. An empty gold set is pending, not a zero score."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

from src.extract.validator import validate_span
from src.gold.load import load_gold_cases, load_gold_documents, require_case_counts
from src.gold.match import MATCH_VERSION, MatchSpan, match_cases
from src.gold.metrics import (
    PREFILTER_RECALL_MIN,
    RELEVANCE_PRECISION_MIN,
    RELEVANCE_RECALL_MIN,
    agreement,
    confusion,
    multilabel_scores,
    prefilter_recall,
    relevance_counts,
    scalar_accuracy,
    span_validation_rate,
    unsupported_inference,
)
from src.gold.split import GOLD_SPLIT_RULE, GOLD_SPLIT_SEED
from src.models.enums import EvidenceOwnerType, OffsetState, Speaker, ValidationState
from src.models.evidence import EvidenceSpan

SCHEMA_VALIDATION_MIN = 1.0
SPAN_VALIDATION_MIN = 1.0
EVALUATION_VERSION = "gold-evaluation/v2"


class HoldoutAnalysisError(ValueError):
    """Error analysis is a development-split artifact."""


def evaluate_gold(
    *,
    documents_path: Path | str,
    cases_path: Path | str,
    split: str,
    predictions: dict[str, object] | None = None,
    extracted_cases: tuple | list = (),
    texts: dict[str, str] | None = None,
    schema_failures: int = 0,
    processed_records: int | None = None,
    review_count: int | None = None,
    duplicate_count: int | None = None,
    failure_count: int | None = None,
    attempt_count: int | None = None,
    additional_spans_by_document: dict[str, tuple] | None = None,
) -> dict[str, object]:
    """Score one split. Holdout callers must not pass this result to the error-analysis writer."""
    documents = tuple(
        row for row in load_gold_documents(documents_path) if row.split.value == split
    )
    cases = load_gold_cases(cases_path)
    document_ids = {row.doc_id for row in documents}
    cases = tuple(row for row in cases if row.doc_id in document_ids)
    if not documents:
        return _pending(split)
    require_case_counts(documents, cases)
    quote_failures = validate_gold_quotes(cases, texts or {})
    predictions = predictions or {}
    split_predictions = {
        doc_id: row
        for doc_id, row in predictions.items()
        if doc_id in document_ids
    }
    relevance, excluded = relevance_counts(documents, split_predictions)
    matched = _matched_pairs(documents, cases, extracted_cases, texts or {})
    split_extracted = tuple(
        case for case in extracted_cases if getattr(case, "doc_id", None) in document_ids
    )
    validation_records = split_extracted + tuple(
        SimpleNamespace(spans=spans)
        for doc_id, spans in (additional_spans_by_document or {}).items()
        if doc_id in document_ids
    )
    schema_rate = None
    if processed_records:
        schema_rate = (processed_records - schema_failures) / processed_records
    report = {
        "status": "measured" if split_predictions or split_extracted else "pending",
        "evaluation_version": EVALUATION_VERSION,
        "split": split,
        "split_rule": GOLD_SPLIT_RULE,
        "split_seed": GOLD_SPLIT_SEED,
        "match_version": MATCH_VERSION,
        "documents": len(documents),
        "gold_cases": len(cases),
        "excluded_technical_failures": excluded,
        "gold_quote_failures": quote_failures,
        "schema_validation_rate": schema_rate,
        "span_validation_rate": span_validation_rate(validation_records),
        "prefilter_recall": prefilter_recall(documents, split_predictions),
        "relevance": relevance.as_rates(),
        "scalar_accuracy": scalar_accuracy(_scope_pairs(documents, split_predictions) + matched),
        "multilabel": multilabel_scores(matched),
        "unsupported_inference": unsupported_inference(matched),
        "agreement": agreement(documents),
        "confusion": confusion(documents, split_predictions),
        "review_rate": _optional_rate(review_count, len(documents)),
        "duplicate_rate": _optional_rate(duplicate_count, len(documents)),
        "failure_rate": _optional_rate(failure_count, attempt_count),
    }
    report["gates"] = _gates(report)
    report["prediction_coverage"] = {
        "documents_with_predictions": len(split_predictions),
        "documents_without_predictions": len(document_ids - set(split_predictions)),
    }
    report["case_coverage"] = {
        "gold_cases": len(cases), "accepted_model_cases": len(split_extracted),
        "matched_cases": len(matched), "unmatched_gold_cases": len(cases) - len(matched),
        "unmatched_model_cases": len(split_extracted) - len(matched),
        "gold_case_coverage": _optional_rate(len(matched), len(cases)),
        "field_metrics_basis": "matched cases only; unmatched gold cases and technical failures are not silently scored as field matches",
    }
    threshold_states = [gate["pass"] for gate in report["gates"].values()]
    report["quality_gate_status"] = (
        "development_only" if split == "dev" else
        "pending" if None in threshold_states or document_ids - set(split_predictions) or quote_failures else
        "numeric_thresholds_passed" if all(threshold_states) else "numeric_thresholds_failed"
    )
    if report["status"] == "pending":
        report["message"] = "pending: no model predictions or extraction outputs were supplied"
    return report


def validate_gold_quotes(cases: tuple | list, texts: dict[str, str]) -> int:
    """Count gold quotes that are not verbatim in the supplied document text.

    A document with no supplied text is not treated as a failure. A supplied
    text that does not contain the quote is.
    """
    failures = 0
    for case in cases:
        text = texts.get(case.doc_id)
        if text is None:
            continue
        for quote in case.expected_evidence:
            if not _quote_valid(case.doc_id, case.gold_case_id, quote, text):
                failures += 1
    return failures


def write_error_analysis(
    path: Path | str,
    *,
    split: str,
    documents: tuple | list,
    predictions: dict[str, object],
    texts: dict[str, str] | None = None,
) -> None:
    """Write disagreements for the development split only."""
    if split != "dev":
        raise HoldoutAnalysisError(
            "error analysis is refused for the holdout split"
        )
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    texts = texts or {}
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "doc_id",
                "gold_scope_class",
                "gold_reason_code",
                "predicted_scope_class",
                "predicted_reason_code",
                "document_text",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for document in documents:
            predicted = predictions.get(document.doc_id)
            gold_scope = _value(getattr(document, "scope_class", None))
            predicted_scope = None if predicted is None else _value(getattr(predicted, "scope_class", None))
            if predicted is not None and not getattr(predicted, "prefilter_passed", True):
                predicted_scope = "prefilter_dropped"
            if gold_scope == predicted_scope:
                continue
            writer.writerow(
                {
                    "doc_id": document.doc_id,
                    "gold_scope_class": gold_scope,
                    "gold_reason_code": _value(getattr(document, "reason_code", None)),
                    "predicted_scope_class": predicted_scope,
                    "predicted_reason_code": None
                    if predicted is None
                    else _value(getattr(predicted, "reason_code", None)),
                    "document_text": texts.get(document.doc_id, ""),
                }
            )


def write_report(directory: Path | str, report: dict[str, object]) -> None:
    """Write the metrics report. This writer does not create an error analysis."""
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _pending(split: str) -> dict[str, object]:
    return {
        "status": "pending",
        "evaluation_version": EVALUATION_VERSION,
        "split": split,
        "split_rule": GOLD_SPLIT_RULE,
        "split_seed": GOLD_SPLIT_SEED,
        "match_version": MATCH_VERSION,
        "documents": 0,
        "gold_cases": 0,
        "excluded_technical_failures": None,
        "message": "pending: the gold set has no documents in this split",
        "gates": {
            name: {"threshold": threshold, "value": None, "pass": None}
            for name, threshold in _thresholds().items()
        },
    }


def _gates(report: dict[str, object]) -> dict[str, dict[str, object]]:
    relevance = report["relevance"]
    assert isinstance(relevance, dict)
    values = {
        "schema_validation_rate": report["schema_validation_rate"],
        "span_validation_rate": report["span_validation_rate"],
        "prefilter_recall": report["prefilter_recall"],
        "relevance_precision": relevance["precision"],
        "relevance_recall": relevance["recall"],
    }
    gates = {}
    for name, threshold in _thresholds().items():
        value = values[name]
        gates[name] = {
            "threshold": threshold,
            "value": value,
            "pass": None if value is None else bool(value >= threshold),
        }
    return gates


def _thresholds() -> dict[str, float]:
    return {
        "schema_validation_rate": SCHEMA_VALIDATION_MIN,
        "span_validation_rate": SPAN_VALIDATION_MIN,
        "prefilter_recall": PREFILTER_RECALL_MIN,
        "relevance_precision": RELEVANCE_PRECISION_MIN,
        "relevance_recall": RELEVANCE_RECALL_MIN,
    }


def _matched_pairs(documents, cases, extracted_cases, texts: dict[str, str]):
    pairs = []
    extracted_by_doc: dict[str, list] = {}
    for case in extracted_cases:
        extracted_by_doc.setdefault(getattr(case, "doc_id"), []).append(case)
    gold_by_doc: dict[str, list] = {}
    for case in cases:
        gold_by_doc.setdefault(case.doc_id, []).append(case)
    for document in documents:
        if document.expected_case_count == 0:
            continue
        pairs.extend(
            match_cases(
                gold_by_doc.get(document.doc_id, []),
                extracted_by_doc.get(document.doc_id, []),
                texts.get(document.doc_id),
            )
        )
    return pairs


def _scope_pairs(documents, predictions: dict[str, object]) -> list[tuple[object, object]]:
    pairs = []
    for document in documents:
        predicted = predictions.get(document.doc_id)
        if predicted is None or _value(getattr(predicted, "technical_state", None)) != "ok":
            continue
        pairs.append((document, predicted))
    return pairs


def _quote_valid(doc_id: str, owner_id: str, quote: str, text: str) -> bool:
    candidate = EvidenceSpan(
        doc_id=doc_id,
        owner_type=EvidenceOwnerType.gold_case,
        owner_id=owner_id,
        field_name="problem_summary",
        quote=quote,
        start_char=None,
        end_char=None,
        speaker=Speaker.unattributed,
        offset_state=OffsetState.missing_unresolved,
        validation_state=ValidationState.pending,
    )
    return bool(validate_span(candidate, text).ok)


def _optional_rate(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _value(value: object) -> str | None:
    if value is None:
        return None
    nested = getattr(value, "value", None)
    if isinstance(nested, str):
        return nested
    return str(value)
