"""Offline worksheets for the existing gold contracts.

A packet holds source text and blank fields. A completed review is converted
into ``GoldDocumentLabel`` and ``GoldCase`` records. Offsets are checked
against the packet text, then the quotes are stored in ``expected_evidence``,
which is the field the gold contract and the evaluator already use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.gold.evaluate import validate_gold_quotes
from src.gold.load import require_case_counts
from src.gold.metrics import MULTI_LABEL_FIELDS, SCALAR_FIELDS
from src.models.enums import GoldSplit
from src.models.gold import GoldCase, GoldDocumentLabel, PreAdjudicationLabel

VALUE_FIELDS: tuple[str, ...] = (
    *SCALAR_FIELDS,
    *MULTI_LABEL_FIELDS,
    "retrieval_trigger",
    "exact_query",
    "query_paraphrase",
)

REVIEWER_CHECKS: tuple[str, ...] = (
    "retrieval_trigger is the stated reason the item was needed, not the search method",
    "impact and severity need a quote that states that impact or severity",
    "problem_summary evidence must support every factual clause",
    "a quote must be one continuous span; invented, abbreviated, or spliced text is invalid",
    "an empty model response does not show that the source has no retrieval episode",
)


class AnnotationError(ValueError):
    """A completed review does not match the gold contracts or the source text."""


@dataclass(frozen=True)
class PackCheck:
    """What a validation pass found. Pending means no completed reviews yet."""

    documents: int
    reviews: int
    errors: tuple[str, ...]

    @property
    def pending(self) -> bool:
        return self.reviews == 0 and not self.errors


def blank_document(doc_id: str, split: str) -> dict[str, object]:
    """The document fields a reviewer fills. Split is already assigned."""
    return {
        "doc_id": doc_id,
        "split": split,
        "scope_class": None,
        "reason_code": None,
        "prefilter_should_pass": None,
        "expected_case_count": None,
        "labeler_id": None,
        "labeled_at": None,
        "adjudicated": False,
        "pre_adjudication_labels": [],
        "notes": None,
    }


def blank_case(doc_id: str) -> dict[str, object]:
    """One empty retrieval case. Copy it once per episode found in the source."""
    return {
        "ordinal": None,
        "expected_values": {
            name: {"observation": None, "value": None} for name in VALUE_FIELDS
        },
        "evidence": [
            {
                "field_name": None,
                "quote": None,
                "start_char": None,
                "end_char": None,
            }
        ],
        "notes": None,
        "gold_case_id_form": f"{doc_id}#g01",
    }


def reviewer_checks() -> list[dict[str, object]]:
    """Unanswered checks. They are not gold labels."""
    return [{"check": text, "passed": None, "notes": None} for text in REVIEWER_CHECKS]


def assert_exact_span(text: str, quote: str, start: int, end: int) -> None:
    """The quote must be the characters at the stored offsets and nowhere else substituted."""
    if not isinstance(quote, str) or not quote:
        raise AnnotationError("a supporting quote must be a non-empty string")
    if not isinstance(start, int) or not isinstance(end, int):
        raise AnnotationError("start_char and end_char must be integers")
    if start < 0 or end > len(text) or end <= start:
        raise AnnotationError(
            f"offsets [{start}, {end}) are outside the source text of length {len(text)}"
        )
    if text[start:end] != quote:
        raise AnnotationError(
            "the quote is not the source text at the stored offsets"
        )


def gold_from_review(
    review: dict,
    *,
    source_text: str,
    split: str,
) -> tuple[GoldDocumentLabel, tuple[GoldCase, ...]]:
    """Build gold records from one completed review. Blank fields are rejected."""
    doc_id = str(review.get("doc_id") or "")
    if not doc_id:
        raise AnnotationError("a review needs doc_id")
    if split != GoldSplit.dev.value:
        raise AnnotationError(f"{doc_id} is not a development gold document")
    cases = _cases_from_review(
        doc_id,
        review.get("cases") or [],
        source_text,
        labeler_id=str(review.get("labeler_id") or ""),
    )
    document = GoldDocumentLabel(
        doc_id=doc_id,
        split=GoldSplit(split),
        scope_class=review.get("scope_class"),
        reason_code=review.get("reason_code"),
        prefilter_should_pass=review.get("prefilter_should_pass"),
        expected_case_count=review.get("expected_case_count"),
        labeler_id=str(review.get("labeler_id") or ""),
        labeled_at=review.get("labeled_at"),
        adjudicated=bool(review.get("adjudicated", False)),
        pre_adjudication_labels=tuple(
            PreAdjudicationLabel.model_validate(row)
            for row in review.get("pre_adjudication_labels") or ()
        ),
        notes=review.get("notes"),
    )
    require_case_counts([document], cases)
    failures = validate_gold_quotes(cases, {doc_id: source_text})
    if failures:
        raise AnnotationError(f"{doc_id} has {failures} gold quotes that are not verbatim")
    return document, cases


def validate_pack(pack: Path | str, holdout_ids: tuple[str, ...] | list[str] = ()) -> PackCheck:
    """Check completed reviews. An empty label directory is pending, not a failure."""
    root = Path(pack)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    seated = {row["doc_id"]: row for row in manifest["documents"]}
    blocked = set(holdout_ids)
    errors: list[str] = []
    if blocked & set(seated):
        errors.append("the pack manifest contains a Phase 4 holdout document")
    reviews = 0
    label_root = root / "labels"
    found: dict[str, list[Path]] = {}
    if label_root.is_dir():
        for path in sorted(label_root.glob("*/*.json")):
            reviews += 1
            try:
                review = json.loads(path.read_text(encoding="utf-8"))
                doc_id = str(review.get("doc_id") or "")
                if doc_id in blocked or doc_id not in seated:
                    raise AnnotationError(f"{doc_id} is not in this development pack")
                packet = json.loads((root / "packets" / f"{doc_id}.json").read_text(encoding="utf-8"))
                if packet.get("gold_split") != GoldSplit.dev.value:
                    raise AnnotationError(f"{doc_id} is not seated as gold dev")
                gold_from_review(
                    review,
                    source_text=packet["source_text"],
                    split=packet["gold_split"],
                )
                found.setdefault(doc_id, []).append(path)
            except (AnnotationError, ValueError, KeyError, json.JSONDecodeError) as exc:
                errors.append(f"{path.name}: {exc}")
    for doc_id, paths in found.items():
        if len(paths) > 1 and not (root / "adjudicated" / f"{doc_id}.json").is_file():
            errors.append(
                f"{doc_id} has {len(paths)} independent reviews and no adjudication file"
            )
    return PackCheck(documents=len(seated), reviews=reviews, errors=tuple(errors))


def emit_gold(pack: Path | str, destination: Path | str, holdout_ids: tuple[str, ...] | list[str] = ()) -> int:
    """Write gold JSONL for documents whose required reviews are complete.

    Two independent reviews stay unmerged until an adjudication file retains both.
    """
    check = validate_pack(pack, holdout_ids)
    if check.errors:
        raise AnnotationError("; ".join(check.errors))
    root = Path(pack)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    documents: list[GoldDocumentLabel] = []
    cases: list[GoldCase] = []
    for row in manifest["documents"]:
        doc_id = row["doc_id"]
        reviews = sorted((root / "labels").glob(f"*/{doc_id}.json"))
        required = 2 if row.get("double_code") else 1
        if len(reviews) < required:
            continue
        packet = json.loads((root / "packets" / f"{doc_id}.json").read_text(encoding="utf-8"))
        if len(reviews) == 1:
            review = json.loads(reviews[0].read_text(encoding="utf-8"))
            review = _retain_independent_label(review)
        else:
            review = json.loads((root / "adjudicated" / f"{doc_id}.json").read_text(encoding="utf-8"))
            _require_retained_reviewers(review, reviews)
        document, gold_cases = gold_from_review(
            review,
            source_text=packet["source_text"],
            split=packet["gold_split"],
        )
        documents.append(document)
        cases.extend(gold_cases)
    if not documents:
        raise AnnotationError("pending: no document has its required reviews")
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    _write_jsonl(target / "documents.jsonl", documents)
    _write_jsonl(target / "cases.jsonl", cases)
    return len(documents)


def _cases_from_review(
    doc_id: str,
    rows: list,
    source_text: str,
    *,
    labeler_id: str,
) -> tuple[GoldCase, ...]:
    cases: list[GoldCase] = []
    for row in rows:
        ordinal = row.get("ordinal")
        if not isinstance(ordinal, int) or ordinal < 1:
            raise AnnotationError(f"{doc_id} case ordinal must be an integer starting at 1")
        evidence = []
        for span in row.get("evidence") or []:
            assert_exact_span(
                source_text,
                span.get("quote"),
                span.get("start_char"),
                span.get("end_char"),
            )
            if not str(span.get("field_name") or ""):
                raise AnnotationError(f"{doc_id} evidence needs the field name it supports")
            evidence.append(span["quote"])
        cases.append(
            GoldCase(
                gold_case_id=f"{doc_id}#g{ordinal:02d}",
                doc_id=doc_id,
                expected_values=_filled_values(row.get("expected_values") or {}),
                expected_evidence=tuple(evidence),
                labeler_id=str(row.get("labeler_id") or labeler_id),
                adjudicated=bool(row.get("adjudicated", False)),
                notes=row.get("notes"),
            )
        )
    return tuple(cases)


def _filled_values(values: dict) -> dict:
    """Drop template fields the reviewer left blank."""
    filled = {}
    for name, payload in values.items():
        if not isinstance(payload, dict) or payload.get("observation") is None:
            continue
        filled[name] = payload
    return filled


def _retain_independent_label(review: dict) -> dict:
    """Keep the single reviewer's label in ``pre_adjudication_labels`` without adjudicating."""
    retained = dict(review)
    retained["adjudicated"] = False
    retained["pre_adjudication_labels"] = [
        {
            "labeler_id": review["labeler_id"],
            "scope_class": review["scope_class"],
            "reason_code": review["reason_code"],
            "labeled_at": review["labeled_at"],
            "notes": review.get("notes"),
        }
    ]
    return retained


def _require_retained_reviewers(adjudicated: dict, reviews: list[Path]) -> None:
    if not adjudicated.get("adjudicated"):
        raise AnnotationError("two reviews require adjudicated=true before they can be scored")
    retained = {
        (row.get("labeler_id"), row.get("scope_class"), row.get("reason_code"))
        for row in adjudicated.get("pre_adjudication_labels") or []
    }
    independent = set()
    for path in reviews:
        review = json.loads(path.read_text(encoding="utf-8"))
        independent.add((review.get("labeler_id"), review.get("scope_class"), review.get("reason_code")))
    if retained != independent:
        raise AnnotationError(
            "pre_adjudication_labels must retain every independent reviewer label"
        )


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text(
        "".join(row.model_dump_json() + "\n" for row in rows),
        encoding="utf-8",
    )
