"""Deterministic development/holdout split for the Phase 4 seed review.

This is not the Phase 6 gold split. ADR-25 assigns a gold set by hashing
``doc_id``, about 40 percent development and 60 percent holdout. The seed
review uses fixed stratum counts instead, so a 50-document sheet always
yields 35 development rows and 15 holdout rows.

Within one scope class, documents are ordered by ``doc_id``. Holdout seats
are ``floor(i * n / k)`` for ``i`` in ``0 .. k-1``. The rest are development.
The written file is sorted by ``doc_id``.

A manifest that already covers the same documents, version, and counts is
left byte-for-byte alone. An invalid manifest is rejected and not rewritten.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from src.models.enums import ScopeClass
from src.relevance.seed import SeedRow, load_seed_review

SPLIT_VERSION = "relevance-seed-split/v1"
SPLIT_DEVELOPMENT = "development"
SPLIT_HOLDOUT = "holdout"
SEED_SPLIT_ROLE = "phase4-prompt-development"

#: ADR-25 Phase 6 gold split. Not implemented here and not replaced by the seed split.
PHASE6_GOLD_SPLIT: dict[str, object] = {
    "role": "final-product-performance",
    "method": "hash(doc_id)",
    "development_fraction": 0.4,
    "holdout_fraction": 0.6,
    "strata": ("source_platform", "scope_class"),
}

COLUMNS: tuple[str, ...] = ("doc_id", "split", "stratum", "split_version")

DEVELOPMENT_COUNTS: dict[str, int] = {
    ScopeClass.core_incomplete_recall.value: 8,
    ScopeClass.adjacent_known_item_retrieval.value: 10,
    ScopeClass.out_of_scope.value: 17,
}
HOLDOUT_COUNTS: dict[str, int] = {
    ScopeClass.core_incomplete_recall.value: 4,
    ScopeClass.adjacent_known_item_retrieval.value: 4,
    ScopeClass.out_of_scope.value: 7,
}


class SplitError(ValueError):
    """The seed sheet or the existing manifest cannot be used as a split."""


@dataclass(frozen=True)
class SplitAssignment:
    doc_id: str
    split: str
    stratum: str
    split_version: str = SPLIT_VERSION

    def as_dict(self) -> dict[str, str]:
        return {
            "doc_id": self.doc_id,
            "split": self.split,
            "stratum": self.stratum,
            "split_version": self.split_version,
        }


def holdout_indexes(count: int, holdout_count: int) -> tuple[int, ...]:
    """Evenly spaced indexes into a sorted stratum. Empty when ``holdout_count`` is 0."""
    if holdout_count < 0 or count < holdout_count:
        raise SplitError(
            f"cannot place {holdout_count} holdout rows in a stratum of {count}"
        )
    if holdout_count == 0:
        return ()
    indexes = tuple((index * count) // holdout_count for index in range(holdout_count))
    if len(set(indexes)) != holdout_count:
        raise SplitError("holdout indexes collided; the split rule needs a new version")
    return indexes


def assign_split(rows: tuple[SeedRow, ...] | list[SeedRow]) -> tuple[SplitAssignment, ...]:
    """Assign every labeled document once. Blank human scope is rejected."""
    grouped: dict[str, list[str]] = {scope: [] for scope in DEVELOPMENT_COUNTS}
    seen: set[str] = set()
    for row in rows:
        if not row.doc_id.strip():
            raise SplitError("a seed row has an empty doc_id")
        if row.doc_id in seen:
            raise SplitError(f"seed review repeats doc_id {row.doc_id}")
        seen.add(row.doc_id)
        scope = row.human_scope_class
        if scope not in grouped:
            raise SplitError(
                f"{row.doc_id} has no completed scope class for stratification"
            )
        grouped[scope].append(row.doc_id)

    assignments: list[SplitAssignment] = []
    for scope, doc_ids in grouped.items():
        ordered = tuple(sorted(doc_ids))
        expected = DEVELOPMENT_COUNTS[scope] + HOLDOUT_COUNTS[scope]
        if len(ordered) != expected:
            raise SplitError(
                f"{scope} has {len(ordered)} documents; the split expects {expected}"
            )
        holdout_at = set(holdout_indexes(len(ordered), HOLDOUT_COUNTS[scope]))
        for index, doc_id in enumerate(ordered):
            split = SPLIT_HOLDOUT if index in holdout_at else SPLIT_DEVELOPMENT
            assignments.append(
                SplitAssignment(doc_id=doc_id, split=split, stratum=scope)
            )
    assignments.sort(key=lambda item: item.doc_id)
    _require_counts(assignments)
    return tuple(assignments)


def write_split_manifest(
    path: Path | str,
    rows: tuple[SeedRow, ...] | list[SeedRow],
) -> tuple[SplitAssignment, ...]:
    """Write the manifest, or keep a valid one already on disk."""
    destination = Path(path)
    incoming = assign_split(rows)
    if destination.is_file():
        existing = load_split_manifest(destination)
        _require_same_documents(existing, incoming)
        _require_counts(existing)
        return existing
    _write(destination, incoming)
    return incoming


def load_split_manifest(path: Path | str) -> tuple[SplitAssignment, ...]:
    destination = Path(path)
    with destination.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise SplitError(
                "split manifest columns are "
                + ", ".join(reader.fieldnames or ())
            )
        loaded = tuple(
            SplitAssignment(
                doc_id=record["doc_id"],
                split=record["split"],
                stratum=record["stratum"],
                split_version=record["split_version"],
            )
            for record in reader
        )
    _require_counts(loaded)
    return loaded


def doc_ids_for_split(
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
    split_name: str,
) -> tuple[str, ...]:
    """Document ids for one live split. ``all`` is both sides."""
    if split_name == "all":
        chosen = assignments
    else:
        chosen = [row for row in assignments if row.split == split_name]
    return tuple(sorted(row.doc_id for row in chosen))


def ensure_split_manifest(
    path: Path | str,
    seed_path: Path | str,
) -> tuple[SplitAssignment, ...]:
    """Load the seed labels, then write or preserve the manifest."""
    return write_split_manifest(path, load_seed_review(seed_path))


def _require_counts(rows: tuple[SplitAssignment, ...] | list[SplitAssignment]) -> None:
    doc_ids = [row.doc_id for row in rows]
    if any(not doc_id.strip() for doc_id in doc_ids):
        raise SplitError("split manifest has an empty doc_id")
    if len(doc_ids) != len(set(doc_ids)):
        raise SplitError("split manifest repeats a doc_id")
    versions = {row.split_version for row in rows}
    if versions != {SPLIT_VERSION}:
        raise SplitError(
            "split manifest version must be "
            + SPLIT_VERSION
            + "; found "
            + ", ".join(sorted(versions) or ["none"])
        )
    development: dict[str, int] = {scope: 0 for scope in DEVELOPMENT_COUNTS}
    holdout: dict[str, int] = {scope: 0 for scope in HOLDOUT_COUNTS}
    for row in rows:
        if row.split == SPLIT_DEVELOPMENT:
            target = development
        elif row.split == SPLIT_HOLDOUT:
            target = holdout
        else:
            raise SplitError(f"{row.doc_id} has split {row.split!r}")
        if row.stratum not in target:
            raise SplitError(f"{row.doc_id} has stratum {row.stratum!r}")
        target[row.stratum] += 1
    if development != DEVELOPMENT_COUNTS or holdout != HOLDOUT_COUNTS:
        raise SplitError(
            "split counts do not match the Phase 4 seed plan: "
            f"development={development}, holdout={holdout}"
        )


def _require_same_documents(
    existing: tuple[SplitAssignment, ...],
    incoming: tuple[SplitAssignment, ...],
) -> None:
    existing_ids = {row.doc_id for row in existing}
    incoming_ids = {row.doc_id for row in incoming}
    if existing_ids != incoming_ids:
        raise SplitError(
            "the existing split manifest does not cover the current seed documents; "
            "it was not rewritten"
        )
    by_existing = {row.doc_id: row.stratum for row in existing}
    by_incoming = {row.doc_id: row.stratum for row in incoming}
    moved = [
        doc_id
        for doc_id in sorted(existing_ids)
        if by_existing[doc_id] != by_incoming[doc_id]
    ]
    if moved:
        raise SplitError(
            "the existing split manifest strata no longer match the seed labels; "
            "it was not rewritten"
        )


def _write(path: Path, rows: tuple[SplitAssignment, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_dict())
    temporary.replace(path)
