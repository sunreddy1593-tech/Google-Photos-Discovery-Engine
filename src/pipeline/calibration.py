"""Local ADR-11 calibration sheet.

This is not a duplicate decision. ``duplicate_review.csv`` remains the
operational queue, built only from ``DuplicateLink`` rows. Pairs outside the
configured Hamming bands are written here as negative controls and are not
linked, counted, or queued.

An eligible pair is any two different documents. ``left_doc_id`` is the
byte-wise lesser id. Every pair at or inside ``simhash_review_band_max`` is
included. Up to ten farther pairs are added, nearest distance first. Ties
break by ``left_doc_id``, then ``right_doc_id``.

Rewriting the sheet refreshes generated columns. ``researcher_decision`` and
``researcher_notes`` are kept for the same two document ids, whichever column
holds which id. A decision other than blank, ``distinct``, or ``duplicate``
is rejected and the previous file is left in place. These fields do not
create duplicate links or review-queue items.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from itertools import combinations
from pathlib import Path

from src.core.config import DedupeConfig
from src.dedupe.detect import PreparedDocument
from src.dedupe.simhash import hamming_distance
from src.models.duplicate_link import DuplicateLink

NEGATIVE_CONTROL_LIMIT: int = 10
EXCERPT_CHARS: int = 160

AUTOMATIC_BAND: str = "automatic_band"
REVIEW_BAND: str = "review_band"
NEAREST_NEGATIVE_CONTROL: str = "nearest_negative_control"
NO_LINK: str = "no_link"

#: Blank means the pair has not been reviewed. ``duplicate`` is allowed so a
#: later positive example can be recorded. Anything else is rejected.
ALLOWED_DECISIONS: frozenset[str] = frozenset({"", "distinct", "duplicate"})

COLUMNS: tuple[str, ...] = (
    "calibration_rank",
    "selection_reason",
    "left_doc_id",
    "right_doc_id",
    "left_source_platform",
    "right_source_platform",
    "left_token_count",
    "right_token_count",
    "hamming_distance",
    "system_action_under_current_threshold",
    "left_privacy_safe_excerpt",
    "right_privacy_safe_excerpt",
    "researcher_decision",
    "researcher_notes",
)


@dataclass(frozen=True)
class CalibrationRow:
    """One sheet row. Researcher fields stay blank until a person fills them."""

    calibration_rank: int
    selection_reason: str
    left_doc_id: str
    right_doc_id: str
    left_source_platform: str
    right_source_platform: str
    left_token_count: int
    right_token_count: int
    hamming_distance: int
    system_action_under_current_threshold: str
    left_privacy_safe_excerpt: str
    right_privacy_safe_excerpt: str
    researcher_decision: str = ""
    researcher_notes: str = ""


def select_calibration_rows(
    documents: list[PreparedDocument] | tuple[PreparedDocument, ...],
    audits: dict[str, str],
    links: tuple[DuplicateLink, ...] | list[DuplicateLink],
    config: DedupeConfig,
    *,
    negative_control_limit: int = NEGATIVE_CONTROL_LIMIT,
) -> tuple[CalibrationRow, ...]:
    """Band pairs, plus the nearest out-of-band pairs, in rank order."""
    ordered = tuple(sorted(documents, key=lambda document: document.doc_id))
    actions = _actions(links)
    in_band: list[CalibrationRow] = []
    out_of_band: list[CalibrationRow] = []
    for left, right in combinations(ordered, 2):
        distance = hamming_distance(left.simhash, right.simhash)
        reason = _selection_reason(distance, config)
        row = _row(left, right, distance, reason, audits, actions)
        if reason == NEAREST_NEGATIVE_CONTROL:
            out_of_band.append(row)
        else:
            in_band.append(row)
    out_of_band.sort(key=_sort_key)
    chosen = in_band + out_of_band[:negative_control_limit]
    chosen.sort(key=_sort_key)
    return tuple(
        CalibrationRow(
            calibration_rank=index,
            selection_reason=row.selection_reason,
            left_doc_id=row.left_doc_id,
            right_doc_id=row.right_doc_id,
            left_source_platform=row.left_source_platform,
            right_source_platform=row.right_source_platform,
            left_token_count=row.left_token_count,
            right_token_count=row.right_token_count,
            hamming_distance=row.hamming_distance,
            system_action_under_current_threshold=row.system_action_under_current_threshold,
            left_privacy_safe_excerpt=row.left_privacy_safe_excerpt,
            right_privacy_safe_excerpt=row.right_privacy_safe_excerpt,
        )
        for index, row in enumerate(chosen, start=1)
    )


def write_calibration_csv(path: Path, rows: tuple[CalibrationRow, ...] | list[CalibrationRow]) -> None:
    """Refresh generated columns and keep researcher fields for the same pair.

    The pair key is the two ``doc_id`` values in byte-wise ascending order, so
    which column is ``left`` does not matter. An existing decision or note is
    copied onto the new row. A value outside :data:`ALLOWED_DECISIONS` raises
    before the file is replaced.
    """
    prior = _load_researcher_fields(path)
    merged = tuple(_with_researcher_fields(row, prior) for row in rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in merged:
            writer.writerow(
                {
                    "calibration_rank": row.calibration_rank,
                    "selection_reason": row.selection_reason,
                    "left_doc_id": row.left_doc_id,
                    "right_doc_id": row.right_doc_id,
                    "left_source_platform": row.left_source_platform,
                    "right_source_platform": row.right_source_platform,
                    "left_token_count": row.left_token_count,
                    "right_token_count": row.right_token_count,
                    "hamming_distance": row.hamming_distance,
                    "system_action_under_current_threshold": (
                        row.system_action_under_current_threshold
                    ),
                    "left_privacy_safe_excerpt": row.left_privacy_safe_excerpt,
                    "right_privacy_safe_excerpt": row.right_privacy_safe_excerpt,
                    "researcher_decision": row.researcher_decision,
                    "researcher_notes": row.researcher_notes,
                }
            )


def pair_key(left_doc_id: str, right_doc_id: str) -> tuple[str, str]:
    """Order-independent identity of a calibration pair."""
    if left_doc_id <= right_doc_id:
        return (left_doc_id, right_doc_id)
    return (right_doc_id, left_doc_id)


def _selection_reason(distance: int, config: DedupeConfig) -> str:
    if distance <= config.simhash_duplicate_max:
        return AUTOMATIC_BAND
    if distance <= config.simhash_review_band_max:
        return REVIEW_BAND
    return NEAREST_NEGATIVE_CONTROL


def _actions(links: tuple[DuplicateLink, ...] | list[DuplicateLink]) -> dict[frozenset[str], str]:
    actions: dict[frozenset[str], str] = {}
    for link in sorted(links, key=lambda item: item.link_id):
        actions.setdefault(
            frozenset((link.doc_id, link.canonical_doc_id)),
            link.review_state.value,
        )
    return actions


def _row(
    left: PreparedDocument,
    right: PreparedDocument,
    distance: int,
    reason: str,
    audits: dict[str, str],
    actions: dict[frozenset[str], str],
) -> CalibrationRow:
    first, second = (left, right) if left.doc_id <= right.doc_id else (right, left)
    return CalibrationRow(
        calibration_rank=0,
        selection_reason=reason,
        left_doc_id=first.doc_id,
        right_doc_id=second.doc_id,
        left_source_platform=first.source_platform,
        right_source_platform=second.source_platform,
        left_token_count=first.token_count,
        right_token_count=second.token_count,
        hamming_distance=distance,
        system_action_under_current_threshold=actions.get(
            frozenset((first.doc_id, second.doc_id)),
            NO_LINK,
        ),
        left_privacy_safe_excerpt=_excerpt(audits.get(first.doc_id, "")),
        right_privacy_safe_excerpt=_excerpt(audits.get(second.doc_id, "")),
    )


def _sort_key(row: CalibrationRow) -> tuple[int, str, str]:
    return (row.hamming_distance, row.left_doc_id, row.right_doc_id)


def _excerpt(audit: str) -> str:
    return " ".join(audit.split())[:EXCERPT_CHARS]


def _load_researcher_fields(path: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """Read decisions already stored for each pair. Missing file means none."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return {}
        missing = {"left_doc_id", "right_doc_id", "researcher_decision", "researcher_notes"} - set(
            reader.fieldnames
        )
        if missing:
            raise ValueError(
                "calibration sheet is missing columns: " + ", ".join(sorted(missing))
            )
        stored: dict[tuple[str, str], tuple[str, str]] = {}
        for record in reader:
            key = pair_key(record["left_doc_id"], record["right_doc_id"])
            decision = _check_decision(record["researcher_decision"], key)
            notes = record["researcher_notes"]
            previous = stored.get(key)
            if previous is not None and previous != (decision, notes):
                raise ValueError(
                    "calibration pair "
                    + "|".join(key)
                    + " has two different researcher entries"
                )
            stored[key] = (decision, notes)
    return stored


def _with_researcher_fields(
    row: CalibrationRow,
    prior: dict[tuple[str, str], tuple[str, str]],
) -> CalibrationRow:
    key = pair_key(row.left_doc_id, row.right_doc_id)
    decision, notes = prior.get(key, (row.researcher_decision, row.researcher_notes))
    decision = _check_decision(decision, key)
    return replace(row, researcher_decision=decision, researcher_notes=notes)


def _check_decision(decision: str, key: tuple[str, str]) -> str:
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(
            "calibration decision for "
            + "|".join(key)
            + " must be blank, distinct, or duplicate"
        )
    return decision
