"""Metric families on a synthetic gold set. No corpus files and no provider."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.gold.evaluate import HoldoutAnalysisError, evaluate_gold, write_error_analysis, write_report
from src.gold.match import MatchSpan
from src.gold.metrics import (
    PREFILTER_RECALL_MIN,
    RELEVANCE_PRECISION_MIN,
    RELEVANCE_RECALL_MIN,
    multilabel_scores,
    scalar_accuracy,
)
from src.models.enums import GoldSplit, ReasonCode, ScopeClass
from src.models.gold import GoldCase, GoldDocumentLabel, PreAdjudicationLabel
from tests.synthetic import NOW


def test_scalar_accuracy_requires_value_and_observation() -> None:
    gold = SimpleNamespace(
        scope_class=None,
        expected_values={"outcome": {"observation": "stated", "value": "not_found"}},
    )
    same_value = SimpleNamespace(
        scope_class=None,
        values={"outcome": {"observation": "not_stated", "value": "not_found"}},
    )
    both = SimpleNamespace(
        scope_class=None,
        values={"outcome": {"observation": "stated", "value": "not_found"}},
    )
    assert scalar_accuracy([(gold, same_value)])["outcome"] == 0
    assert scalar_accuracy([(gold, both)])["outcome"] == 1


def test_micro_and_macro_differ_on_an_imbalanced_fixture() -> None:
    def pair(expected: list[str], actual: list[str]):
        return (
            SimpleNamespace(expected_values={"remembered_cues": {"value": expected}}),
            SimpleNamespace(values={"remembered_cues": {"value": actual}}),
        )

    pairs = [
        pair(["common"], ["common"]),
        pair(["common"], ["common"]),
        pair(["common"], ["common"]),
        pair(["rare"], []),
    ]
    scores = multilabel_scores(pairs)["remembered_cues"]
    assert scores["micro"]["f1"] != scores["macro"]["f1"]
    assert scores["macro"]["recall"] < scores["micro"]["recall"]


def test_prefilter_recall_uses_the_gold_flag_not_the_classifier(tmp_path: Path) -> None:
    _write_gold(
        tmp_path,
        [
            _document("keep", prefilter=True, scope=ScopeClass.core_incomplete_recall),
            _document("drop", prefilter=True, scope=ScopeClass.core_incomplete_recall),
        ],
        [],
    )
    report = evaluate_gold(
        documents_path=tmp_path / "documents.jsonl",
        cases_path=tmp_path / "cases.jsonl",
        split="dev",
        predictions={
            "keep": _prediction("keep", "out_of_scope", passed=True),
            "drop": _prediction("drop", "core_incomplete_recall", passed=False),
        },
        processed_records=2,
    )
    assert report["prefilter_recall"] == 0.5


def test_prefilter_drop_counts_as_not_relevant(tmp_path: Path) -> None:
    _write_gold(
        tmp_path,
        [_document("doc", prefilter=True, scope=ScopeClass.core_incomplete_recall)],
        [],
    )
    report = evaluate_gold(
        documents_path=tmp_path / "documents.jsonl",
        cases_path=tmp_path / "cases.jsonl",
        split="dev",
        predictions={"doc": _prediction("doc", "core_incomplete_recall", passed=False)},
        processed_records=1,
    )
    assert report["relevance"]["recall"] == 0


def test_unsupported_inference_is_per_field(tmp_path: Path) -> None:
    text = "I looked for the birthday cake photo."
    gold_case = GoldCase(
        gold_case_id="doc#g01",
        doc_id="doc",
        expected_values={"outcome": {"observation": "stated", "value": "not_found"}},
        expected_evidence=("birthday cake photo",),
        labeler_id="reviewer-a",
    )
    _write_gold(
        tmp_path,
        [_document("doc", prefilter=True, scope=ScopeClass.core_incomplete_recall, cases=1)],
        [gold_case],
    )
    extracted = SimpleNamespace(
        doc_id="doc",
        case_id="doc#c01",
        values={
            "outcome": {"observation": "stated", "value": "found"},
            "severity": {"observation": "stated", "value": 3},
        },
        spans=(
            MatchSpan("birthday cake photo", text.index("birthday cake photo"), text.index("birthday cake photo") + len("birthday cake photo"), "valid", "outcome"),
            MatchSpan("not in source", None, None, "rejected", "severity"),
        ),
    )
    report = evaluate_gold(
        documents_path=tmp_path / "documents.jsonl",
        cases_path=tmp_path / "cases.jsonl",
        split="dev",
        predictions={"doc": _prediction("doc", "core_incomplete_recall", passed=True)},
        extracted_cases=(extracted,),
        texts={"doc": text},
        processed_records=1,
    )
    rates = report["unsupported_inference"]
    assert rates["outcome"] == 1
    assert rates["severity"] == 1
    assert rates["overall"] == 1


def test_agreement_uses_labels_from_before_adjudication(tmp_path: Path) -> None:
    document = _document("doc", prefilter=True, scope=ScopeClass.core_incomplete_recall)
    document = document.model_copy(
        update={
            "adjudicated": True,
            "pre_adjudication_labels": (
                PreAdjudicationLabel(
                    labeler_id="reviewer-a",
                    scope_class=ScopeClass.core_incomplete_recall,
                    reason_code=ReasonCode.known_item_with_incomplete_recall,
                    labeled_at=NOW,
                ),
                PreAdjudicationLabel(
                    labeler_id="reviewer-b",
                    scope_class=ScopeClass.out_of_scope,
                    reason_code=ReasonCode.storage_backup_or_sync,
                    labeled_at=NOW,
                ),
            ),
        }
    )
    _write_gold(tmp_path, [document], [])
    report = evaluate_gold(
        documents_path=tmp_path / "documents.jsonl",
        cases_path=tmp_path / "cases.jsonl",
        split="dev",
        predictions={"doc": _prediction("doc", "core_incomplete_recall", passed=True)},
        processed_records=1,
    )
    assert report["agreement"]["raw_agreement"] == 0
    assert report["agreement"]["pairs"] == 1


def test_technical_failures_are_excluded_and_counted(tmp_path: Path) -> None:
    _write_gold(
        tmp_path,
        [
            _document("ok", prefilter=True, scope=ScopeClass.core_incomplete_recall),
            _document("bad", prefilter=True, scope=ScopeClass.core_incomplete_recall),
        ],
        [],
    )
    failed = _prediction("bad", None, passed=True)
    failed.technical_state = "provider_error"
    report = evaluate_gold(
        documents_path=tmp_path / "documents.jsonl",
        cases_path=tmp_path / "cases.jsonl",
        split="dev",
        predictions={
            "ok": _prediction("ok", "core_incomplete_recall", passed=True),
            "bad": failed,
        },
        processed_records=2,
    )
    assert report["excluded_technical_failures"] == 1
    assert report["relevance"]["recall"] == 1


def test_empty_gold_set_is_pending_not_zero(tmp_path: Path) -> None:
    documents = tmp_path / "documents.jsonl"
    cases = tmp_path / "cases.jsonl"
    documents.write_text("", encoding="utf-8")
    cases.write_text("", encoding="utf-8")
    report = evaluate_gold(documents_path=documents, cases_path=cases, split="holdout")
    assert report["status"] == "pending"
    assert report["relevance"] if False else report["gates"]["relevance_precision"]["value"] is None
    assert report["gates"]["relevance_precision"]["pass"] is None
    assert "0.0" not in report["message"]


def test_holdout_error_analysis_is_refused(tmp_path: Path) -> None:
    with pytest.raises(HoldoutAnalysisError):
        write_error_analysis(tmp_path / "disagreements.csv", split="holdout", documents=(), predictions={})


def test_thresholds_are_the_spec_gates() -> None:
    assert PREFILTER_RECALL_MIN == 0.90
    assert RELEVANCE_PRECISION_MIN == 0.85
    assert RELEVANCE_RECALL_MIN == 0.80


def test_command_reports_pending_for_an_empty_gold_set(tmp_path: Path) -> None:
    gold = tmp_path / "gold"
    gold.mkdir()
    (gold / "documents.jsonl").write_text("", encoding="utf-8")
    (gold / "cases.jsonl").write_text("", encoding="utf-8")
    out = tmp_path / "out"
    import scripts.evaluate as evaluate

    assert evaluate.main(["--gold", str(gold), "--split", "holdout", "--out", str(out)]) == 0
    assert not (out / "disagreements.csv").exists()
    report = evaluate_gold(
        documents_path=gold / "documents.jsonl",
        cases_path=gold / "cases.jsonl",
        split="dev",
    )
    write_report(out, report)
    assert (out / "report.json").is_file()


def _document(doc_id: str, *, prefilter: bool, scope: ScopeClass, cases: int = 0) -> GoldDocumentLabel:
    reason = (
        ReasonCode.storage_backup_or_sync
        if scope is ScopeClass.out_of_scope
        else ReasonCode.known_item_with_incomplete_recall
    )
    return GoldDocumentLabel(
        doc_id=doc_id,
        split=GoldSplit.dev,
        scope_class=scope,
        reason_code=reason,
        prefilter_should_pass=prefilter,
        expected_case_count=cases,
        labeler_id="reviewer-a",
        labeled_at=NOW,
    )


def _prediction(doc_id: str, scope: str | None, *, passed: bool):
    return SimpleNamespace(
        doc_id=doc_id,
        technical_state="ok",
        scope_class=scope,
        reason_code="known_item_with_incomplete_recall",
        prefilter_passed=passed,
    )


def _write_gold(directory: Path, documents: list[GoldDocumentLabel], cases: list[GoldCase]) -> None:
    (directory / "documents.jsonl").write_text(
        "".join(row.model_dump_json() + "\n" for row in documents),
        encoding="utf-8",
    )
    (directory / "cases.jsonl").write_text(
        "".join(row.model_dump_json() + "\n" for row in cases),
        encoding="utf-8",
    )
