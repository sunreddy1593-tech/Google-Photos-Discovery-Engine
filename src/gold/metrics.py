"""Phase 6 metric families. Missing inputs stay pending rather than zero."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations

from src.models.relevance import RELEVANT_SCOPE_CLASSES

SCALAR_FIELDS: tuple[str, ...] = (
    "known_item_status",
    "target_asset_type",
    "outcome",
    "severity",
    "reformulation_count",
)
OBSERVATION_FIELDS: tuple[str, ...] = tuple(
    f"{name}_observation" for name in SCALAR_FIELDS
)
MULTI_LABEL_FIELDS: tuple[str, ...] = (
    "target_subjects",
    "remembered_cues",
    "forgotten_information",
    "query_strategies",
    "system_responses",
    "workarounds",
    "impact_signals",
)
RELEVANT_SCOPES = frozenset(item.value for item in RELEVANT_SCOPE_CLASSES)
NARRATIVE_FIELDS: tuple[str, ...] = ("retrieval_trigger", "exact_query", "query_paraphrase", "problem_summary")

PREFILTER_RECALL_MIN = 0.90
RELEVANCE_PRECISION_MIN = 0.85
RELEVANCE_RECALL_MIN = 0.80


@dataclass(frozen=True)
class Counts:
    """True and false positives and negatives. Undefined rates stay None."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    def as_rates(self) -> dict[str, float | None]:
        precision = _rate(self.tp, self.tp + self.fp)
        recall = _rate(self.tp, self.tp + self.fn)
        return {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }


def scalar_accuracy(pairs: tuple | list) -> dict[str, float | None]:
    """A field matches only when both its value and its observation status match.

    ``scope_class`` has no observation status. Other scalar fields do.
    """
    results: dict[str, float | None] = {}
    scope_hits = 0
    scope_total = 0
    for gold, predicted in pairs:
        gold_scope = _enum_value(getattr(gold, "scope_class", None))
        predicted_scope = _enum_value(getattr(predicted, "scope_class", None))
        if gold_scope is not None and predicted_scope is not None:
            scope_total += 1
            scope_hits += int(gold_scope == predicted_scope)
    results["scope_class"] = _rate(scope_hits, scope_total)
    for name in (*SCALAR_FIELDS, *OBSERVATION_FIELDS):
        hits = 0
        total = 0
        for gold, predicted in pairs:
            expected = _lookup(_attr(gold, "expected_values", {}), name)
            actual = _lookup(_attr(predicted, "values", {}), name)
            if expected is None:
                continue
            total += 1
            hits += int(_scalar_match(name, expected, actual))
        results[name] = _rate(hits, total)
    return results


def multilabel_scores(pairs: tuple | list) -> dict[str, dict[str, dict[str, float | None]]]:
    """Micro and macro precision, recall, and F1, reported separately."""
    scores: dict[str, dict[str, dict[str, float | None]]] = {}
    for name in MULTI_LABEL_FIELDS:
        micro = Counts()
        per_label: dict[str, Counts] = {}
        seen = False
        for gold, predicted in pairs:
            expected = _labels(_field(_attr(gold, "expected_values", {}), name))
            actual = _labels(_field(_attr(predicted, "values", {}), name))
            if expected is None and actual is None:
                continue
            seen = True
            expected = expected or set()
            actual = actual or set()
            micro = Counts(
                micro.tp + len(expected & actual),
                micro.fp + len(actual - expected),
                micro.fn + len(expected - actual),
            )
            for label in expected | actual:
                current = per_label.get(label, Counts())
                per_label[label] = Counts(
                    current.tp + int(label in expected and label in actual),
                    current.fp + int(label in actual and label not in expected),
                    current.fn + int(label in expected and label not in actual),
                )
        if not seen:
            scores[name] = {"micro": Counts().as_rates(), "macro": Counts().as_rates()}
            continue
        macro_rates = [Counts(**item.__dict__).as_rates() for item in per_label.values()]
        scores[name] = {
            "micro": micro.as_rates(),
            "macro": {
                "precision": _mean(rate["precision"] for rate in macro_rates),
                "recall": _mean(rate["recall"] for rate in macro_rates),
                "f1": _mean(rate["f1"] for rate in macro_rates),
            },
        }
    return scores


def prefilter_recall(documents: tuple | list, predictions: dict[str, object]) -> float | None:
    """Gold ``prefilter_should_pass`` only. Classifier scope is not consulted."""
    hits = 0
    total = 0
    for document in documents:
        if not document.prefilter_should_pass:
            continue
        predicted = predictions.get(document.doc_id)
        if predicted is None or not _technical_ok(predicted):
            continue
        total += 1
        hits += int(bool(getattr(predicted, "prefilter_passed")))
    return _rate(hits, total)


def relevance_counts(documents: tuple | list, predictions: dict[str, object]) -> tuple[Counts, int]:
    """End-to-end relevance. A prefilter drop is predicted not-relevant.

    Returns the counts and the number of documents excluded for a non-ok
    technical state.
    """
    counts = Counts()
    excluded = 0
    for document in documents:
        predicted = predictions.get(document.doc_id)
        if predicted is None:
            continue
        if not _technical_ok(predicted):
            excluded += 1
            continue
        gold_relevant = _enum_value(document.scope_class) in RELEVANT_SCOPES
        predicted_relevant = bool(getattr(predicted, "prefilter_passed")) and (
            _enum_value(getattr(predicted, "scope_class", None)) in RELEVANT_SCOPES
        )
        counts = Counts(
            counts.tp + int(gold_relevant and predicted_relevant),
            counts.fp + int(predicted_relevant and not gold_relevant),
            counts.fn + int(gold_relevant and not predicted_relevant),
        )
    return counts, excluded


def unsupported_inference(pairs: tuple | list) -> dict[str, float | None]:
    """Share of non-empty extracted values whose evidence is missing, invalid, or contradicted."""
    per_field: dict[str, list[int]] = {}
    unassessed: set[str] = set()
    overall = [0, 0]
    fields = (*SCALAR_FIELDS, *MULTI_LABEL_FIELDS, *NARRATIVE_FIELDS)
    for _gold, predicted in pairs:
        values = _attr(predicted, "values", {}) or {}
        spans = tuple(_attr(predicted, "spans", ()) or ())
        for name in fields:
            raw = _field(values, name)
            if _is_empty_value(raw):
                continue
            structurally_unsupported = not _supported(name, raw, spans)
            expected_values = getattr(_gold, "expected_values", {})
            if name not in expected_values and not structurally_unsupported:
                # A real quote is not semantic approval. Without a reference
                # value, this field cannot be scored as semantically supported.
                unassessed.add(name)
                continue
            unsupported = int(
                structurally_unsupported or _contradicted(name, raw, expected_values)
            )
            per_field.setdefault(name, [0, 0])
            per_field[name][0] += unsupported
            per_field[name][1] += 1
            overall[0] += unsupported
            overall[1] += 1
    report = {name: _rate(hits, total) for name, (hits, total) in sorted(per_field.items())}
    for name in sorted(unassessed - set(per_field)):
        report[name] = None
    report["overall"] = _rate(overall[0], overall[1])
    return report


def span_validation_rate(cases: tuple | list) -> float | None:
    """Valid extracted spans divided by every extracted span."""
    valid = 0
    total = 0
    for case in cases:
        for span in getattr(case, "spans", ()) or ():
            total += 1
            valid += int(getattr(span, "validation_state", None) == "valid")
    return _rate(valid, total)


def agreement(documents: tuple | list) -> dict[str, float | None]:
    """Raw agreement and Cohen's kappa from pre-adjudication scope labels."""
    pairs: list[tuple[str, str]] = []
    for document in documents:
        labels = tuple(getattr(document, "pre_adjudication_labels", ()) or ())
        scopes = [(_labeler(label), _enum_value(getattr(label, "scope_class"))) for label in labels]
        scopes = [(labeler, scope) for labeler, scope in scopes if labeler and scope]
        for (left_labeler, left_scope), (right_labeler, right_scope) in combinations(scopes, 2):
            if left_labeler == right_labeler:
                continue
            pairs.append((left_scope, right_scope))
    if not pairs:
        return {"raw_agreement": None, "cohen_kappa": None, "pairs": 0}
    raw = sum(left == right for left, right in pairs) / len(pairs)
    return {
        "raw_agreement": raw,
        "cohen_kappa": _cohen_kappa(pairs, raw),
        "pairs": len(pairs),
    }


def confusion(documents: tuple | list, predictions: dict[str, object]) -> dict[str, dict[str, int]]:
    """Gold scope against the end-to-end prediction. Excluded records are omitted."""
    matrix: dict[str, Counter[str]] = {}
    for document in documents:
        predicted = predictions.get(document.doc_id)
        if predicted is None or not _technical_ok(predicted):
            continue
        gold_scope = _enum_value(document.scope_class) or ""
        if not getattr(predicted, "prefilter_passed"):
            predicted_scope = "prefilter_dropped"
        else:
            predicted_scope = _enum_value(getattr(predicted, "scope_class", None)) or ""
        matrix.setdefault(gold_scope, Counter())[predicted_scope] += 1
    return {gold: dict(columns) for gold, columns in sorted(matrix.items())}


def _scalar_match(name: str, expected: object, actual: object) -> bool:
    if name.endswith("_observation"):
        return _value_of(expected) == _value_of(actual)
    expected_value = _value_of(expected)
    actual_value = _value_of(actual)
    if expected_value != actual_value:
        return False
    if isinstance(expected, dict) and "observation" in expected:
        actual_observation = actual.get("observation") if isinstance(actual, dict) else None
        return actual_observation == expected.get("observation")
    return True


def _supported(name: str, raw: object, spans: tuple) -> bool:
    usable = [
        span
        for span in spans
        if getattr(span, "field_name", None) == name and getattr(span, "validation_state", None) == "valid"
    ]
    return bool(usable)


def _contradicted(name: str, raw: object, expected_values: dict) -> bool:
    expected = _field(expected_values, name)
    if expected is None:
        return False
    actual = raw if isinstance(raw, dict) else {"value": _value_of(raw)}
    if name in MULTI_LABEL_FIELDS:
        # Missing a reference label is a recall miss, not an unsupported
        # extracted value. Only extra predicted labels contradict the reference.
        return not (_labels(actual) or set()) <= (_labels(expected) or set())
    return not _scalar_match(name, expected, actual)


def _attr(obj: object, name: str, default: object) -> object:
    """Pydantic raises for a missing attribute, so a default must be explicit."""
    try:
        return getattr(obj, name)
    except AttributeError:
        return default


def _lookup(values: dict, name: str) -> object | None:
    """Read a scalar field, or an observation nested inside its value field."""
    direct = _field(values, name)
    if direct is not None or not name.endswith("_observation"):
        return direct
    parent = _field(values, name.removesuffix("_observation"))
    if isinstance(parent, dict) and "observation" in parent:
        return parent["observation"]
    return None


def _field(values: dict, name: str) -> object | None:
    if not isinstance(values, dict) or name not in values:
        return None
    return values[name]


def _value_of(payload: object) -> object:
    if isinstance(payload, dict) and "value" in payload:
        return payload["value"]
    return _enum_value(payload)


def _labels(payload: object) -> set[str] | None:
    if payload is None:
        return None
    value = _value_of(payload)
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    return {_enum_value(_value_of(item)) or str(_value_of(item)) for item in value}


def _is_empty_value(payload: object) -> bool:
    value = _value_of(payload)
    return value is None or value == "" or value == [] or value == ()


def _technical_ok(predicted: object) -> bool:
    return _enum_value(getattr(predicted, "technical_state", None)) == "ok"


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    nested = getattr(value, "value", None)
    if isinstance(nested, str):
        return nested
    return str(value)


def _labeler(label: object) -> str:
    return str(getattr(label, "labeler_id", ""))


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _mean(values) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _cohen_kappa(pairs: list[tuple[str, str]], raw: float) -> float | None:
    labels = sorted({left for left, _right in pairs} | {right for _left, right in pairs})
    total = len(pairs)
    left_counts = Counter(left for left, _right in pairs)
    right_counts = Counter(right for _left, right in pairs)
    expected = sum((left_counts[label] / total) * (right_counts[label] / total) for label in labels)
    if expected == 1:
        return 1.0
    return (raw - expected) / (1 - expected)
