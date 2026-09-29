"""Human seed sheet for Phase 4 smoke checks.

This is not the Phase 6 gold set. It has no model prediction. Human columns
start blank and are kept on a later run, matched by ``doc_id``. Only the three
scope classes and the inclusion or exclusion reason codes are accepted.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from src.models.enums import (
    EXCLUSION_REASON_CODES,
    INCLUSION_REASON_CODES,
    ScopeClass,
)
from src.relevance.rules import PrefilterResult

EXCERPT_CHARS = 500

COLUMNS: tuple[str, ...] = (
    "doc_id",
    "source_platform",
    "source_type",
    "title",
    "privacy_safe_excerpt",
    "prefilter_route",
    "prefilter_reason_codes",
    "human_scope_class",
    "human_reason_code",
    "human_notes",
)

_SCOPE_VALUES = frozenset(member.value for member in ScopeClass)
_INCLUSION = frozenset(code.value for code in INCLUSION_REASON_CODES)
_EXCLUSION = frozenset(code.value for code in EXCLUSION_REASON_CODES)
_REASON_VALUES = _INCLUSION | _EXCLUSION


class SeedReviewError(ValueError):
    """The existing sheet has a human value this ruleset cannot keep."""


@dataclass(frozen=True)
class SeedRow:
    doc_id: str
    source_platform: str
    source_type: str
    title: str
    privacy_safe_excerpt: str
    prefilter_route: str
    prefilter_reason_codes: str
    human_scope_class: str = ""
    human_reason_code: str = ""
    human_notes: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "doc_id": self.doc_id,
            "source_platform": self.source_platform,
            "source_type": self.source_type,
            "title": self.title,
            "privacy_safe_excerpt": self.privacy_safe_excerpt,
            "prefilter_route": self.prefilter_route,
            "prefilter_reason_codes": self.prefilter_reason_codes,
            "human_scope_class": self.human_scope_class,
            "human_reason_code": self.human_reason_code,
            "human_notes": self.human_notes,
        }


def excerpt(raw_text_audit: str) -> str:
    """A short slice of the redacted audit text. No characters are added."""
    return " ".join(raw_text_audit.split())[:EXCERPT_CHARS]


def seed_row_from_prefilter(
    *,
    doc_id: str,
    source_platform: str,
    source_type: str,
    title: str | None,
    raw_text_audit: str,
    prefilter: PrefilterResult,
) -> SeedRow:
    return SeedRow(
        doc_id=doc_id,
        source_platform=source_platform,
        source_type=source_type,
        title=title or "",
        privacy_safe_excerpt=excerpt(raw_text_audit),
        prefilter_route=prefilter.route,
        prefilter_reason_codes="|".join(prefilter.reason_labels),
    )


def load_seed_review(path: Path | str) -> tuple[SeedRow, ...]:
    """Load the sheet in ``doc_id`` order. Invalid human fields raise."""
    stored = _load(Path(path))
    return tuple(stored[doc_id] for doc_id in sorted(stored))


def write_seed_review(path: Path | str, rows: list[SeedRow]) -> None:
    """Write the sheet. Invalid human fields leave the existing file in place."""
    _require_unique_doc_ids([row.doc_id for row in rows])
    destination = Path(path)
    prior = _load(destination)
    merged = _merge(rows, prior)
    for row in merged:
        _check_human(row)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in merged:
            writer.writerow(row.as_dict())
    temporary.replace(destination)


def _merge(rows: list[SeedRow], prior: dict[str, SeedRow]) -> list[SeedRow]:
    incoming = {row.doc_id: row for row in rows}
    doc_ids = sorted(set(incoming) | set(prior))
    merged: list[SeedRow] = []
    for doc_id in doc_ids:
        fresh = incoming.get(doc_id)
        old = prior.get(doc_id)
        if fresh is None and old is not None:
            merged.append(old)
            continue
        assert fresh is not None
        if old is None:
            merged.append(fresh)
            continue
        merged.append(
            SeedRow(
                doc_id=fresh.doc_id,
                source_platform=fresh.source_platform,
                source_type=fresh.source_type,
                title=fresh.title,
                privacy_safe_excerpt=fresh.privacy_safe_excerpt,
                prefilter_route=fresh.prefilter_route,
                prefilter_reason_codes=fresh.prefilter_reason_codes,
                human_scope_class=old.human_scope_class,
                human_reason_code=old.human_reason_code,
                human_notes=old.human_notes,
            )
        )
    return merged


def _load(path: Path) -> dict[str, SeedRow]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return {}
        missing = set(COLUMNS) - set(reader.fieldnames)
        if missing:
            raise SeedReviewError(
                "seed review sheet is missing columns: " + ", ".join(sorted(missing))
            )
        stored: dict[str, SeedRow] = {}
        seen: list[str] = []
        for record in reader:
            seen.append(record["doc_id"])
            row = SeedRow(
                doc_id=record["doc_id"],
                source_platform=record["source_platform"],
                source_type=record["source_type"],
                title=record["title"],
                privacy_safe_excerpt=record["privacy_safe_excerpt"],
                prefilter_route=record["prefilter_route"],
                prefilter_reason_codes=record["prefilter_reason_codes"],
                human_scope_class=record["human_scope_class"],
                human_reason_code=record["human_reason_code"],
                human_notes=record["human_notes"],
            )
            _check_human(row)
            stored[row.doc_id] = row
        _require_unique_doc_ids(seen)
    return stored


def _require_unique_doc_ids(doc_ids: list[str]) -> None:
    """Reject a blank or repeated document id before any row is replaced."""
    seen: set[str] = set()
    for doc_id in doc_ids:
        if not doc_id.strip():
            raise SeedReviewError("seed review sheet has a row with an empty doc_id")
        if doc_id in seen:
            raise SeedReviewError(f"seed review sheet repeats doc_id {doc_id}")
        seen.add(doc_id)


def _check_human(row: SeedRow) -> None:
    scope = row.human_scope_class
    reason = row.human_reason_code
    if scope not in {""} | _SCOPE_VALUES:
        raise SeedReviewError(
            f"human_scope_class for {row.doc_id} must be one of the three scope classes or blank"
        )
    if reason not in {""} | _REASON_VALUES:
        raise SeedReviewError(
            f"human_reason_code for {row.doc_id} must be an inclusion or exclusion code or blank"
        )
    if reason and not scope:
        raise SeedReviewError(
            f"human_reason_code for {row.doc_id} needs a human_scope_class"
        )
    if scope == ScopeClass.out_of_scope.value and reason and reason not in _EXCLUSION:
        raise SeedReviewError(
            f"human_reason_code for {row.doc_id} is not an exclusion code"
        )
    if scope in {
        ScopeClass.core_incomplete_recall.value,
        ScopeClass.adjacent_known_item_retrieval.value,
    } and reason and reason not in _INCLUSION:
        raise SeedReviewError(
            f"human_reason_code for {row.doc_id} is not an inclusion code"
        )
