"""Seed split and offline relevance evaluation. No provider calls."""

from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest

from src.models.enums import (
    DecisionTechnicalState,
    EvidenceOwnerType,
    ReasonCode,
    ScopeClass,
    ValidationState,
)
from src.relevance.evaluate import (
    EvaluationError,
    OperationStats,
    evaluate_relevance,
    format_evaluation_summary,
    write_evaluation_artifacts,
)
from src.relevance.prompts import render_relevance_prompt
from src.relevance.seed import SeedRow
from src.relevance.split import (
    DEVELOPMENT_COUNTS,
    HOLDOUT_COUNTS,
    SPLIT_VERSION,
    SplitAssignment,
    SplitError,
    assign_split,
    holdout_indexes,
    write_split_manifest,
)
from tests.synthetic import make_decision, make_span

ROOT = Path(__file__).resolve().parents[1]


def _labeled(doc_id: str, scope: str, reason: str, notes: str = "note") -> SeedRow:
    return SeedRow(
        doc_id=doc_id,
        source_platform="reddit",
        source_type="post",
        title=doc_id,
        privacy_safe_excerpt=f"excerpt {doc_id}",
        prefilter_route="classify",
        prefilter_reason_codes="retained_for_recall",
        human_scope_class=scope,
        human_reason_code=reason,
        human_notes=notes,
    )


def _population() -> tuple[SeedRow, ...]:
    rows: list[SeedRow] = []
    rows.extend(
        _labeled(
            f"core-{index:02d}",
            ScopeClass.core_incomplete_recall.value,
            ReasonCode.known_item_with_incomplete_recall.value,
        )
        for index in range(12)
    )
    rows.extend(
        _labeled(
            f"adjacent-{index:02d}",
            ScopeClass.adjacent_known_item_retrieval.value,
            ReasonCode.known_item_with_precise_recall_failure.value,
        )
        for index in range(14)
    )
    rows.extend(
        _labeled(
            f"out-{index:02d}",
            ScopeClass.out_of_scope.value,
            ReasonCode.storage_backup_or_sync.value,
        )
        for index in range(24)
    )
    return tuple(rows)


def test_holdout_indexes_are_unique_and_evenly_spaced() -> None:
    assert holdout_indexes(12, 4) == (0, 3, 6, 9)
    assert holdout_indexes(14, 4) == (0, 3, 7, 10)
    assert holdout_indexes(24, 7) == (0, 3, 6, 10, 13, 17, 20)


def test_split_counts_are_exact_and_cover_every_document_once() -> None:
    assigned = assign_split(_population())
    assert len(assigned) == 50
    assert len({row.doc_id for row in assigned}) == 50
    development = [row for row in assigned if row.split == "development"]
    holdout = [row for row in assigned if row.split == "holdout"]
    assert len(development) == 35
    assert len(holdout) == 15
    assert {row.doc_id for row in development}.isdisjoint({row.doc_id for row in holdout})
    for scope, count in DEVELOPMENT_COUNTS.items():
        assert sum(1 for row in development if row.stratum == scope) == count
    for scope, count in HOLDOUT_COUNTS.items():
        assert sum(1 for row in holdout if row.stratum == scope) == count
    core = sorted(row.doc_id for row in _population() if row.human_scope_class.startswith("core"))
    holdout_core = {
        row.doc_id
        for row in holdout
        if row.stratum == ScopeClass.core_incomplete_recall.value
    }
    assert holdout_core == {core[index] for index in holdout_indexes(12, 4)}


def test_split_rerun_is_byte_identical_and_keeps_a_valid_manifest(tmp_path: Path) -> None:
    rows = _population()
    first = tmp_path / "a" / "relevance_split_manifest.csv"
    second = tmp_path / "b" / "relevance_split_manifest.csv"
    write_split_manifest(first, rows)
    write_split_manifest(second, rows)
    original = first.read_bytes()
    assert original == second.read_bytes()
    write_split_manifest(first, rows)
    assert first.read_bytes() == original

    text = original.decode("utf-8")
    swapped = text.replace("core-01,development", "core-01,holdout", 1)
    swapped = swapped.replace("core-00,holdout", "core-00,development", 1)
    first.write_bytes(swapped.encode("utf-8"))
    preserved = first.read_bytes()
    write_split_manifest(first, rows)
    assert first.read_bytes() == preserved

    broken = preserved.decode("utf-8").replace("core-01,holdout", "core-01,development", 1)
    first.write_bytes(broken.encode("utf-8"))
    snapshot = first.read_bytes()
    with pytest.raises(SplitError):
        write_split_manifest(first, rows)
    assert first.read_bytes() == snapshot


def test_classifier_prompt_does_not_load_human_labels() -> None:
    note = "HUMAN_NOTE_SENTINEL_not_in_the_post"
    prompt = render_relevance_prompt(doc_id="doc-1", raw_text_audit="I cannot find the photo.")
    assert note not in prompt
    for relative in (
        "src/relevance/prompts.py",
        "src/relevance/classifier.py",
        "src/relevance/schema.py",
        "src/llm/gateway.py",
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "relevance_seed_review" not in source
        assert "human_scope_class" not in source
        assert "human_notes" not in source
    tree = ast.parse((ROOT / "src/relevance/evaluate.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert "src.llm" not in imported
    assert not any(name.startswith("src.llm") for name in imported)


def _ok_decision(doc_id: str, decision_id: str, **overrides: object):
    evidence = overrides.pop(
        "evidence",
        (
            make_span(
                "scope_class",
                "I could not remember the exact date",
                owner_id=decision_id,
                owner_type=EvidenceOwnerType.relevance_decision,
                doc_id=doc_id,
            ),
        ),
    )
    return make_decision(
        doc_id=doc_id,
        decision_id=decision_id,
        evidence=evidence,
        **overrides,
    )


def test_confusion_matrix_binary_metrics_and_abstentions() -> None:
    labels = (
        _labeled("doc-core-hit", "core_incomplete_recall", "known_item_with_incomplete_recall"),
        _labeled("doc-adjacent", "adjacent_known_item_retrieval", "known_item_with_precise_recall_failure"),
        _labeled("doc-out", "out_of_scope", "storage_backup_or_sync"),
        _labeled("doc-core-missing", "core_incomplete_recall", "known_item_query_unformulable"),
    )
    assignments = tuple(
        SplitAssignment(doc_id=row.doc_id, split="development", stratum=row.human_scope_class)
        for row in labels
    )
    hit = _ok_decision(
        "doc-core-hit",
        "decision-hit",
        confidence=0.9,
    )
    wrong = _ok_decision(
        "doc-adjacent",
        "decision-wrong",
        scope_class=ScopeClass.out_of_scope,
        reason_code=ReasonCode.storage_backup_or_sync,
        confidence=0.4,
        needs_human_review=True,
    )
    failed = make_decision(
        doc_id="doc-out",
        decision_id="decision-failed",
        scope_class=None,
        reason_code=ReasonCode.provider_unavailable,
        confidence=None,
        evidence=(),
        technical_state=DecisionTechnicalState.provider_unavailable,
        needs_human_review=True,
    )
    report = evaluate_relevance(
        labels,
        (hit, wrong, failed),
        assignments,
        split_name="development",
        confidence_review_below=0.7,
        conflict_decision_ids=("decision-wrong",),
        operations=OperationStats(
            provider_calls=3,
            cache_hits=1,
            cache_misses=2,
            input_tokens=10,
            output_tokens=4,
            estimated_cost_usd=0.25,
            latency_seconds=(1.0, 3.0),
        ),
    )
    assert report.confusion["core_incomplete_recall"]["core_incomplete_recall"] == 1
    assert report.confusion["core_incomplete_recall"]["abstained"] == 1
    assert report.confusion["adjacent_known_item_retrieval"]["out_of_scope"] == 1
    assert report.confusion["out_of_scope"]["abstained"] == 1
    assert report.confusion["out_of_scope"]["out_of_scope"] == 0
    assert report.overall_exact_scope_accuracy == 0.25
    assert report.covered_only_exact_scope_accuracy == 0.5
    assert report.document_count == 4
    assert report.missing_doc_ids == ("doc-core-missing",)
    assert report.core_incomplete_recall_recall == 1.0
    assert report.binary_in_scope_precision == 1.0
    assert report.binary_in_scope_recall == pytest.approx(1 / 3, abs=1e-6)
    assert report.per_class["adjacent_known_item_retrieval"].predicted == 0
    assert report.per_class["adjacent_known_item_retrieval"].precision == 0.0
    assert report.per_class["adjacent_known_item_retrieval"].recall == 0.0
    assert report.exact_reason_code_accuracy == 0.25
    assert report.abstention_rate == 0.5
    assert report.technical_failure_rate == 0.25
    assert report.valid_completed_decision_coverage == 0.5
    assert report.low_confidence_rate == 0.25
    assert report.human_review_rate == 0.5
    assert report.prefilter_classifier_conflict_rate == 0.25
    assert report.decisions_requiring_evidence == 2
    assert report.valid_verbatim_evidence_rate == 1.0
    assert report.operations.provider_calls == 3
    assert report.operations.cache_hits == 1
    assert report.operations.input_tokens == 10
    assert report.to_json()["average_latency_seconds"] == 2.0
    assert report.to_json()["estimated_cost_usd"] == 0.25


def test_evidence_rates_reason_accuracy_and_zero_prediction_class() -> None:
    labels = (
        _labeled("doc-ok", "out_of_scope", "deletion_or_corruption"),
        _labeled("doc-fabricated", "core_incomplete_recall", "known_item_cue_not_recognized"),
        _labeled("doc-ambiguous", "adjacent_known_item_retrieval", "known_item_retrieval_journey_described"),
    )
    assignments = tuple(
        SplitAssignment(doc_id=row.doc_id, split="holdout", stratum=row.human_scope_class)
        for row in labels
    )
    bare = _ok_decision(
        "doc-ok",
        "decision-bare",
        scope_class=ScopeClass.out_of_scope,
        reason_code=ReasonCode.deletion_or_corruption,
    )
    fabricated = make_decision(
        doc_id="doc-fabricated",
        decision_id="decision-fabricated",
        scope_class=None,
        reason_code=ReasonCode.evidence_validation_failed,
        confidence=None,
        evidence=(),
        technical_state=DecisionTechnicalState.evidence_validation_failed,
        needs_human_review=True,
    )
    ambiguous = make_decision(
        doc_id="doc-ambiguous",
        decision_id="decision-ambiguous",
        scope_class=None,
        reason_code=ReasonCode.evidence_offsets_unresolved,
        confidence=None,
        evidence=(),
        technical_state=DecisionTechnicalState.evidence_validation_failed,
        needs_human_review=True,
    )
    report = evaluate_relevance(
        labels,
        (bare, fabricated, ambiguous),
        assignments,
        split_name="holdout",
    )
    assert report.decisions_requiring_evidence == 1
    assert report.missing_evidence_rate == 0.0
    assert report.valid_verbatim_evidence_rate == 1.0
    assert report.fabricated_evidence_rate == pytest.approx(1 / 3, abs=1e-6)
    assert report.ambiguous_span_rate == pytest.approx(1 / 3, abs=1e-6)
    assert report.exact_reason_code_accuracy == pytest.approx(1 / 3, abs=1e-6)
    assert report.per_class["adjacent_known_item_retrieval"].predicted == 0
    assert report.per_class["adjacent_known_item_retrieval"].f1 == 0.0
    assert report.per_class["core_incomplete_recall"].precision == 0.0


def test_missing_and_extra_doc_ids() -> None:
    label = _labeled("doc-1", "out_of_scope", "account_access")
    assignment = SplitAssignment(doc_id="doc-1", split="development", stratum="out_of_scope")
    report = evaluate_relevance((label,), (), (assignment,), split_name="development")
    assert report.missing_doc_ids == ("doc-1",)
    assert report.overall_exact_scope_accuracy == 0.0
    assert report.abstention_rate == 1.0
    extra = _ok_decision("doc-unknown", "decision-unknown")
    with pytest.raises(EvaluationError, match="not in the seed review"):
        evaluate_relevance((label,), (extra,), (assignment,), split_name="development")


def test_evaluation_artifacts_omit_notes_and_do_not_call_a_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("live network call")

    monkeypatch.setattr(socket, "create_connection", blocked)
    label = _labeled("doc-1", "out_of_scope", "account_access", notes="private human note")
    assignment = SplitAssignment(doc_id="doc-1", split="all", stratum="out_of_scope")
    report = evaluate_relevance((label,), (), (assignment,), split_name="all")
    json_path, markdown_path = write_evaluation_artifacts(tmp_path, report)
    body = json_path.read_text(encoding="utf-8") + markdown_path.read_text(encoding="utf-8")
    assert "private human note" not in body
    assert "human_notes" not in body
    assert "performance_claim" in body
    summary = format_evaluation_summary(report)
    assert "provider calls       0" in summary
    assert "private human note" not in summary


def test_valid_evidence_span_is_counted() -> None:
    label = _labeled("doc-1", "core_incomplete_recall", "known_item_with_incomplete_recall")
    assignment = SplitAssignment(
        doc_id="doc-1", split="development", stratum="core_incomplete_recall"
    )
    decision = _ok_decision("doc-1", "decision-1")
    assert decision.evidence[0].validation_state is ValidationState.valid
    report = evaluate_relevance((label,), (decision,), (assignment,), split_name="development")
    assert report.valid_verbatim_evidence_rate == 1.0
    assert report.missing_evidence_rate == 0.0


def test_cli_evaluates_without_a_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("live network call")

    monkeypatch.setattr(socket, "create_connection", blocked)
    seed = tmp_path / "relevance_seed_review.csv"
    from src.relevance.seed import write_seed_review

    write_seed_review(seed, list(_population()))
    from main import main

    manifest = tmp_path / "relevance_split_manifest.csv"
    code = main(
        [
            "evaluate",
            "--split",
            "all",
            "--seed",
            str(seed),
            "--decisions",
            str(tmp_path / "missing-decisions.jsonl"),
            "--manifest",
            str(manifest),
            "--reviews",
            str(tmp_path / "missing-reviews.jsonl"),
            "--run-manifest",
            str(tmp_path / "missing-run.json"),
            "--output",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert manifest.is_file()
    stored = json.loads((tmp_path / "relevance_evaluation.json").read_text(encoding="utf-8"))
    assert stored["document_count"] == 50
    assert stored["provider_calls"] == 0
    assert stored["performance_claim"] is False
    assert stored["missing_doc_ids"]
    assert len(stored["missing_doc_ids"]) == 50
    assert SPLIT_VERSION == stored["split_version"]
