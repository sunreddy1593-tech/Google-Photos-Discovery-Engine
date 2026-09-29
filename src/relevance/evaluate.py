"""Offline comparison of relevance decisions with the approved seed labels.

Human labels are an input to this module. Classification does not load them,
and nothing here calls a provider. A null scope or a non-``ok`` technical
state is an abstention. It is not ``out_of_scope``.

Overall exact-scope accuracy counts every ground-truth document, including
abstentions and missing predictions. Covered-only class metrics use only
``ok`` predictions with a scope. ADR-30 records that split. A Phase 4 number
is not final product performance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.models.enums import (
    DecisionTechnicalState,
    ReasonCode,
    ScopeClass,
    ValidationState,
)
from src.models.relevance import RELEVANT_SCOPE_CLASSES, RelevanceDecision
from src.relevance.seed import SeedRow
from src.relevance.split import (
    SPLIT_DEVELOPMENT,
    SPLIT_HOLDOUT,
    SPLIT_VERSION,
    SplitAssignment,
)

ABSTAINED = "abstained"
SCOPE_ORDER: tuple[str, ...] = (
    ScopeClass.core_incomplete_recall.value,
    ScopeClass.adjacent_known_item_retrieval.value,
    ScopeClass.out_of_scope.value,
)
PREDICTED_ORDER: tuple[str, ...] = SCOPE_ORDER + (ABSTAINED,)


class EvaluationError(ValueError):
    """The decisions cannot be scored against this ground truth."""


@dataclass(frozen=True)
class OperationStats:
    """Totals copied from a finished run. Evaluation does not measure a call."""

    provider_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    latency_seconds: tuple[float, ...] = ()


@dataclass(frozen=True)
class ClassScore:
    precision: float
    recall: float
    f1: float
    support: int
    predicted: int


@dataclass
class EvaluationReport:
    split_name: str
    split_version: str
    document_count: int
    missing_doc_ids: tuple[str, ...]
    confusion: dict[str, dict[str, int]]
    per_class: dict[str, ClassScore]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    overall_exact_scope_accuracy: float
    covered_only_exact_scope_accuracy: float
    core_incomplete_recall_recall: float
    binary_in_scope_precision: float
    binary_in_scope_recall: float
    exact_reason_code_accuracy: float
    covered_only_reason_code_accuracy: float
    valid_completed_decision_coverage: float
    abstention_rate: float
    technical_failure_rate: float
    human_review_rate: float
    low_confidence_rate: float
    prefilter_classifier_conflict_rate: float
    decisions_requiring_evidence: int
    valid_verbatim_evidence_rate: float
    missing_evidence_rate: float
    fabricated_evidence_rate: float
    ambiguous_span_rate: float
    operations: OperationStats
    documents: tuple[dict[str, object], ...] = field(default_factory=tuple)

    def to_json(self) -> dict[str, object]:
        average_latency = None
        if self.operations.latency_seconds:
            average_latency = round(
                sum(self.operations.latency_seconds) / len(self.operations.latency_seconds),
                6,
            )
        return {
            "split": self.split_name,
            "split_version": self.split_version,
            "performance_claim": False,
            "document_count": self.document_count,
            "missing_doc_ids": list(self.missing_doc_ids),
            "confusion_matrix": self.confusion,
            "per_class": {
                name: {
                    "precision": score.precision,
                    "recall": score.recall,
                    "f1": score.f1,
                    "support": score.support,
                    "predicted": score.predicted,
                }
                for name, score in self.per_class.items()
            },
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "overall_exact_scope_accuracy": self.overall_exact_scope_accuracy,
            "covered_only_exact_scope_accuracy": self.covered_only_exact_scope_accuracy,
            "core_incomplete_recall_recall": self.core_incomplete_recall_recall,
            "binary_in_scope_precision": self.binary_in_scope_precision,
            "binary_in_scope_recall": self.binary_in_scope_recall,
            "exact_reason_code_accuracy": self.exact_reason_code_accuracy,
            "covered_only_reason_code_accuracy": self.covered_only_reason_code_accuracy,
            "valid_completed_decision_coverage": self.valid_completed_decision_coverage,
            "abstention_rate": self.abstention_rate,
            "technical_failure_rate": self.technical_failure_rate,
            "human_review_rate": self.human_review_rate,
            "low_confidence_rate": self.low_confidence_rate,
            "prefilter_classifier_conflict_rate": self.prefilter_classifier_conflict_rate,
            "decisions_requiring_evidence": self.decisions_requiring_evidence,
            "valid_verbatim_evidence_rate": self.valid_verbatim_evidence_rate,
            "missing_evidence_rate": self.missing_evidence_rate,
            "fabricated_evidence_rate": self.fabricated_evidence_rate,
            "ambiguous_span_rate": self.ambiguous_span_rate,
            "provider_calls": self.operations.provider_calls,
            "cache_hits": self.operations.cache_hits,
            "cache_misses": self.operations.cache_misses,
            "input_tokens": self.operations.input_tokens,
            "output_tokens": self.operations.output_tokens,
            "estimated_cost_usd": self.operations.estimated_cost_usd,
            "average_latency_seconds": average_latency,
            "documents": list(self.documents),
        }


def evaluate_relevance(
    labels: tuple[SeedRow, ...] | list[SeedRow],
    decisions: tuple[RelevanceDecision, ...] | list[RelevanceDecision],
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
    *,
    split_name: str,
    confidence_review_below: float = 0.7,
    conflict_decision_ids: tuple[str, ...] | list[str] = (),
    operations: OperationStats | None = None,
) -> EvaluationReport:
    """Score ``split_name``. Labels are matched to decisions by ``doc_id``."""
    if split_name not in {SPLIT_DEVELOPMENT, SPLIT_HOLDOUT, "all"}:
        raise EvaluationError(f"unknown split {split_name!r}")
    label_by_id = _labels_by_id(labels)
    chosen = [
        row
        for row in assignments
        if split_name == "all" or row.split == split_name
    ]
    if not chosen:
        raise EvaluationError(f"split {split_name!r} has no documents")
    unknown = sorted(
        {
            decision.doc_id
            for decision in decisions
            if decision.doc_id not in label_by_id
        }
    )
    if unknown:
        raise EvaluationError(
            "decisions include doc_ids that are not in the seed review: "
            + ", ".join(unknown[:10])
        )
    by_decision: dict[str, RelevanceDecision] = {}
    for decision in decisions:
        if decision.doc_id in by_decision:
            raise EvaluationError(
                f"more than one decision is stored for {decision.doc_id}"
            )
        by_decision[decision.doc_id] = decision

    stats = operations or OperationStats()
    conflicts = set(conflict_decision_ids)
    confusion = {
        gold: {predicted: 0 for predicted in PREDICTED_ORDER} for gold in SCOPE_ORDER
    }
    documents: list[dict[str, object]] = []
    scope_matches = 0
    reason_matches = 0
    covered = 0
    covered_reason_matches = 0
    abstentions = 0
    technical_failures = 0
    human_reviews = 0
    low_confidence = 0
    conflict_count = 0
    requiring_evidence = 0
    valid_evidence = 0
    missing_evidence = 0
    fabricated = 0
    ambiguous = 0
    binary_tp = 0
    binary_fp = 0
    binary_fn = 0
    missing: list[str] = []
    class_tp = {scope: 0 for scope in SCOPE_ORDER}
    class_fp = {scope: 0 for scope in SCOPE_ORDER}
    class_fn = {scope: 0 for scope in SCOPE_ORDER}
    class_predicted = {scope: 0 for scope in SCOPE_ORDER}

    for assignment in sorted(chosen, key=lambda item: item.doc_id):
        label = label_by_id.get(assignment.doc_id)
        if label is None:
            raise EvaluationError(
                f"{assignment.doc_id} is in the split but not in the seed review"
            )
        gold = label.human_scope_class
        if gold not in confusion:
            raise EvaluationError(f"{assignment.doc_id} has no completed human scope")
        decision = by_decision.get(assignment.doc_id)
        if decision is None:
            missing.append(assignment.doc_id)
            predicted = ABSTAINED
            abstentions += 1
            confusion[gold][predicted] += 1
            if gold in {scope.value for scope in RELEVANT_SCOPE_CLASSES}:
                binary_fn += 1
            documents.append(
                _document_row(assignment.doc_id, gold, None, None, True, False, False)
            )
            continue

        completed = _is_completed(decision)
        predicted = decision.scope_class.value if completed and decision.scope_class else ABSTAINED
        if not completed or decision.scope_class is None:
            abstentions += 1
            if decision.technical_state is not DecisionTechnicalState.ok:
                technical_failures += 1
        confusion[gold][predicted] += 1
        scope_match = completed and decision.scope_class is not None and decision.scope_class.value == gold
        reason_match = (
            completed
            and decision.reason_code.value == label.human_reason_code
        )
        if scope_match:
            scope_matches += 1
            class_tp[gold] += 1
        elif completed and decision.scope_class is not None:
            class_fn[gold] += 1
        if completed and decision.scope_class is not None:
            covered += 1
            class_predicted[decision.scope_class.value] += 1
            if decision.scope_class.value != gold:
                class_fp[decision.scope_class.value] += 1
            requiring_evidence += 1
            if decision.evidence and all(
                span.validation_state is ValidationState.valid and span.quote
                for span in decision.evidence
            ):
                valid_evidence += 1
            if not decision.evidence:
                missing_evidence += 1
        if reason_match:
            reason_matches += 1
            covered_reason_matches += 1
        if decision.needs_human_review:
            human_reviews += 1
        if decision.confidence is not None and decision.confidence < confidence_review_below:
            low_confidence += 1
        if decision.decision_id in conflicts:
            conflict_count += 1
        if (
            decision.technical_state is DecisionTechnicalState.evidence_validation_failed
            and decision.reason_code is ReasonCode.evidence_validation_failed
        ):
            fabricated += 1
        if decision.reason_code is ReasonCode.evidence_offsets_unresolved:
            ambiguous += 1
        gold_in = gold in {scope.value for scope in RELEVANT_SCOPE_CLASSES}
        predicted_in = (
            completed
            and decision.scope_class is not None
            and decision.scope_class in RELEVANT_SCOPE_CLASSES
        )
        if gold_in and predicted_in:
            binary_tp += 1
        elif predicted_in and not gold_in:
            binary_fp += 1
        elif gold_in and not predicted_in:
            binary_fn += 1
        documents.append(
            _document_row(
                assignment.doc_id,
                gold,
                None if decision.scope_class is None else decision.scope_class.value,
                decision.technical_state.value,
                predicted == ABSTAINED,
                scope_match,
                reason_match,
            )
        )

    count = len(chosen)
    per_class = {
        scope: _class_score(
            class_tp[scope],
            class_fp[scope],
            class_fn[scope],
            sum(1 for row in chosen if label_by_id[row.doc_id].human_scope_class == scope),
            class_predicted[scope],
        )
        for scope in SCOPE_ORDER
    }
    macro_precision = _mean(score.precision for score in per_class.values())
    macro_recall = _mean(score.recall for score in per_class.values())
    macro_f1 = _mean(score.f1 for score in per_class.values())
    binary_precision, binary_recall, _binary_f1 = _prf(binary_tp, binary_fp, binary_fn)
    return EvaluationReport(
        split_name=split_name,
        split_version=SPLIT_VERSION,
        document_count=count,
        missing_doc_ids=tuple(missing),
        confusion=confusion,
        per_class=per_class,
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1=macro_f1,
        overall_exact_scope_accuracy=_rate(scope_matches, count),
        covered_only_exact_scope_accuracy=_rate(scope_matches, covered),
        core_incomplete_recall_recall=per_class[
            ScopeClass.core_incomplete_recall.value
        ].recall,
        binary_in_scope_precision=binary_precision,
        binary_in_scope_recall=binary_recall,
        exact_reason_code_accuracy=_rate(reason_matches, count),
        covered_only_reason_code_accuracy=_rate(covered_reason_matches, covered),
        valid_completed_decision_coverage=_rate(covered, count),
        abstention_rate=_rate(abstentions, count),
        technical_failure_rate=_rate(technical_failures, count),
        human_review_rate=_rate(human_reviews, count),
        low_confidence_rate=_rate(low_confidence, count),
        prefilter_classifier_conflict_rate=_rate(conflict_count, count),
        decisions_requiring_evidence=requiring_evidence,
        valid_verbatim_evidence_rate=_rate(valid_evidence, requiring_evidence),
        missing_evidence_rate=_rate(missing_evidence, requiring_evidence),
        fabricated_evidence_rate=_rate(fabricated, count),
        ambiguous_span_rate=_rate(ambiguous, count),
        operations=stats,
        documents=tuple(documents),
    )


def write_evaluation_artifacts(
    directory: Path | str,
    report: EvaluationReport,
) -> tuple[Path, Path]:
    """Write JSON and Markdown. Neither file contains human notes or excerpts."""
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    payload = report.to_json()
    json_path = destination / "relevance_evaluation.json"
    markdown_path = destination / "relevance_evaluation.md"
    json_path.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def format_evaluation_summary(report: EvaluationReport) -> str:
    """Counts only. No notes, excerpts, or author identifiers."""
    lines = [
        "Relevance evaluation",
        f"  split                {report.split_name}",
        f"  documents            {report.document_count}",
        f"  missing predictions  {len(report.missing_doc_ids)}",
        f"  overall accuracy     {report.overall_exact_scope_accuracy:.6f}",
        f"  covered accuracy     {report.covered_only_exact_scope_accuracy:.6f}",
        f"  abstention rate      {report.abstention_rate:.6f}",
        f"  provider calls       {report.operations.provider_calls}",
        "  performance claim    false",
    ]
    return "\n".join(lines) + "\n"


def _labels_by_id(labels: tuple[SeedRow, ...] | list[SeedRow]) -> dict[str, SeedRow]:
    stored: dict[str, SeedRow] = {}
    for row in labels:
        if row.doc_id in stored:
            raise EvaluationError(f"seed review repeats doc_id {row.doc_id}")
        stored[row.doc_id] = row
    return stored


def _is_completed(decision: RelevanceDecision) -> bool:
    return (
        decision.technical_state is DecisionTechnicalState.ok
        and decision.scope_class is not None
    )


def _document_row(
    doc_id: str,
    gold_scope: str,
    predicted_scope: str | None,
    technical_state: str | None,
    abstained: bool,
    scope_match: bool,
    reason_match: bool,
) -> dict[str, object]:
    return {
        "doc_id": doc_id,
        "gold_scope_class": gold_scope,
        "predicted_scope_class": predicted_scope,
        "technical_state": technical_state,
        "abstained": abstained,
        "scope_match": scope_match,
        "reason_match": reason_match,
    }


def _class_score(tp: int, fp: int, fn: int, support: int, predicted: int) -> ClassScore:
    precision, recall, f1 = _prf(tp, fp, fn)
    return ClassScore(
        precision=precision,
        recall=recall,
        f1=f1,
        support=support,
        predicted=predicted,
    )


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = _rate(tp, tp + fp)
    recall = _rate(tp, tp + fn)
    f1 = 0.0 if precision + recall == 0 else round((2 * precision * recall) / (precision + recall), 6)
    return precision, recall, f1


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _mean(values) -> float:
    stored = list(values)
    if not stored:
        return 0.0
    return round(sum(stored) / len(stored), 6)


def _markdown(report: EvaluationReport) -> str:
    payload = report.to_json()
    lines = [
        "# Relevance seed evaluation",
        "",
        "This report compares stored decisions with the approved seed labels.",
        "It is not a performance claim. No provider is called while it is written.",
        "The holdout split is not a prompt-tuning set.",
        "",
        f"- Split: `{report.split_name}`",
        f"- Split version: `{report.split_version}`",
        f"- Documents: {report.document_count}",
        f"- Missing predictions: {len(report.missing_doc_ids)}",
        "",
        "## Classification",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Overall exact scope accuracy | {report.overall_exact_scope_accuracy:.6f} |",
        f"| Covered-only exact scope accuracy | {report.covered_only_exact_scope_accuracy:.6f} |",
        f"| Macro precision | {report.macro_precision:.6f} |",
        f"| Macro recall | {report.macro_recall:.6f} |",
        f"| Macro F1 | {report.macro_f1:.6f} |",
        f"| Core incomplete-recall recall, covered only | {report.core_incomplete_recall_recall:.6f} |",
        f"| Binary in-scope precision | {report.binary_in_scope_precision:.6f} |",
        f"| Binary in-scope recall | {report.binary_in_scope_recall:.6f} |",
        f"| Exact reason-code accuracy | {report.exact_reason_code_accuracy:.6f} |",
        f"| Covered-only reason-code accuracy | {report.covered_only_reason_code_accuracy:.6f} |",
        "",
        "## Confusion matrix",
        "",
        "Rows are the human scope. Columns are the predicted scope. "
        f"`{ABSTAINED}` is a missing prediction or a decision that is not `ok`.",
        "",
        "| Gold \\ Predicted | "
        + " | ".join(PREDICTED_ORDER)
        + " |",
        "|---|" + "|".join("---" for _ in PREDICTED_ORDER) + "|",
    ]
    for gold in SCOPE_ORDER:
        cells = " | ".join(str(report.confusion[gold][predicted]) for predicted in PREDICTED_ORDER)
        lines.append(f"| {gold} | {cells} |")
    lines.extend(
        [
            "",
            "## Coverage and review",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Valid completed-decision coverage | {report.valid_completed_decision_coverage:.6f} |",
            f"| Abstention rate | {report.abstention_rate:.6f} |",
            f"| Technical-failure rate | {report.technical_failure_rate:.6f} |",
            f"| Human-review rate | {report.human_review_rate:.6f} |",
            f"| Low-confidence rate | {report.low_confidence_rate:.6f} |",
            f"| Prefilter/classifier conflict rate | {report.prefilter_classifier_conflict_rate:.6f} |",
            "",
            "## Evidence",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Decisions requiring evidence | {report.decisions_requiring_evidence} |",
            f"| Valid verbatim evidence rate | {report.valid_verbatim_evidence_rate:.6f} |",
            f"| Missing-evidence rate | {report.missing_evidence_rate:.6f} |",
            f"| Fabricated-evidence rate | {report.fabricated_evidence_rate:.6f} |",
            f"| Ambiguous or unresolved-span rate | {report.ambiguous_span_rate:.6f} |",
            "",
            "## Operations",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Provider calls | {report.operations.provider_calls} |",
            f"| Cache hits | {report.operations.cache_hits} |",
            f"| Cache misses | {report.operations.cache_misses} |",
            f"| Input tokens | {report.operations.input_tokens} |",
            f"| Output tokens | {report.operations.output_tokens} |",
            f"| Estimated cost USD | {report.operations.estimated_cost_usd:.6f} |",
            "| Average latency seconds | "
            + (
                "unavailable"
                if payload["average_latency_seconds"] is None
                else f"{payload['average_latency_seconds']:.6f}"
            )
            + " |",
            "",
        ]
    )
    if report.missing_doc_ids:
        lines.append("## Missing predictions")
        lines.append("")
        lines.extend(f"- `{doc_id}`" for doc_id in report.missing_doc_ids)
        lines.append("")
    return "\n".join(lines)
