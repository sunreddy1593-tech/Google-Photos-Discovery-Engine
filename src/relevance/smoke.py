"""Six-document development smoke manifest.

Selection uses the development split and ``doc_id`` order. The written file
carries document ids and split metadata only. Human labels stay in the seed
sheet.
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.models.enums import ScopeClass
from src.relevance.split import SPLIT_DEVELOPMENT, SPLIT_VERSION, SplitAssignment

SCOPE_ORDER: tuple[str, ...] = (
    ScopeClass.core_incomplete_recall.value,
    ScopeClass.adjacent_known_item_retrieval.value,
    ScopeClass.out_of_scope.value,
)

SMOKE_VERSION = "relevance-smoke/v1"
SMOKE_PER_CLASS = 2
SMOKE_CALL_BUDGET = 6
SMOKE_COLUMNS: tuple[str, ...] = ("doc_id", "split", "split_version", "smoke_version")
FORBIDDEN_SMOKE_COLUMNS = frozenset(
    {
        "human_scope_class",
        "human_reason_code",
        "human_notes",
        "expected_label",
        "expected_scope",
        "stratum",
        "privacy_safe_excerpt",
    }
)


class SmokeSelectionError(ValueError):
    """The smoke manifest cannot be used for a development classification."""


def select_smoke_ids(
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
) -> tuple[str, ...]:
    """First two development ids in each scope class, then sorted by ``doc_id``."""
    chosen: list[str] = []
    for scope in SCOPE_ORDER:
        ordered = sorted(
            row.doc_id
            for row in assignments
            if row.split == SPLIT_DEVELOPMENT and row.stratum == scope
        )
        if len(ordered) < SMOKE_PER_CLASS:
            raise SmokeSelectionError(
                f"development {scope} has {len(ordered)} documents; smoke needs {SMOKE_PER_CLASS}"
            )
        chosen.extend(ordered[:SMOKE_PER_CLASS])
    return tuple(sorted(chosen))


def write_smoke_manifest(
    path: Path | str,
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
) -> tuple[str, ...]:
    """Write the six ids, or keep a valid manifest already on disk."""
    destination = Path(path)
    selected = select_smoke_ids(assignments)
    if destination.is_file():
        existing = load_smoke_manifest(destination, assignments)
        return existing
    _write(destination, selected)
    return selected


def load_smoke_manifest(
    path: Path | str,
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
) -> tuple[str, ...]:
    destination = Path(path)
    with destination.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = tuple(reader.fieldnames or ())
        leaked = FORBIDDEN_SMOKE_COLUMNS.intersection(columns)
        if leaked:
            raise SmokeSelectionError(
                "smoke manifest contains label columns: " + ", ".join(sorted(leaked))
            )
        if columns != SMOKE_COLUMNS:
            raise SmokeSelectionError(
                "smoke manifest columns are " + ", ".join(columns)
            )
        rows = list(reader)
    doc_ids = tuple(row["doc_id"] for row in rows)
    _require_smoke_ids(doc_ids, assignments)
    for row in rows:
        if row["split"] != SPLIT_DEVELOPMENT:
            raise SmokeSelectionError(f"{row['doc_id']} is not marked development")
        if row["split_version"] != SPLIT_VERSION or row["smoke_version"] != SMOKE_VERSION:
            raise SmokeSelectionError(f"{row['doc_id']} has a different smoke version")
    return doc_ids


def ensure_smoke_manifest(
    path: Path | str,
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
) -> tuple[str, ...]:
    return write_smoke_manifest(path, assignments)


def assert_development_smoke(
    doc_ids: tuple[str, ...] | list[str],
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
) -> tuple[str, ...]:
    """Reject holdout ids and any request above the six-call budget."""
    stored = tuple(doc_ids)
    if len(stored) > SMOKE_CALL_BUDGET:
        raise SmokeSelectionError(
            f"smoke refuses more than {SMOKE_CALL_BUDGET} provider calls"
        )
    _require_smoke_ids(stored, assignments)
    return stored


def _require_smoke_ids(
    doc_ids: tuple[str, ...],
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
) -> None:
    if len(doc_ids) != SMOKE_CALL_BUDGET or len(set(doc_ids)) != SMOKE_CALL_BUDGET:
        raise SmokeSelectionError("smoke manifest must contain six unique doc_ids")
    development = {
        row.doc_id: row.stratum
        for row in assignments
        if row.split == SPLIT_DEVELOPMENT
    }
    outside = [doc_id for doc_id in doc_ids if doc_id not in development]
    if outside:
        raise SmokeSelectionError(
            "smoke doc_ids are outside the development split: " + ", ".join(outside[:6])
        )
    counts = {scope: 0 for scope in SCOPE_ORDER}
    for doc_id in doc_ids:
        counts[development[doc_id]] += 1
    if any(count != SMOKE_PER_CLASS for count in counts.values()):
        raise SmokeSelectionError(f"smoke class counts are {counts}")


def _write(path: Path, doc_ids: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SMOKE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for doc_id in doc_ids:
            writer.writerow(
                {
                    "doc_id": doc_id,
                    "split": SPLIT_DEVELOPMENT,
                    "split_version": SPLIT_VERSION,
                    "smoke_version": SMOKE_VERSION,
                }
            )
    temporary.replace(path)
