"""Review queue for duplicate decisions (ADR-24, ARCHITECTURE Section 11).

Dedupe is the first stage that produces review items, so the queue lives here
rather than beside a later classifier. Opening an item appends a row. Resolving
one appends another row and leaves the open row in place.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import AwareDatetime, Field

from src.core.ids import sha1_short
from src.models.base import ResearchModel
from src.models.duplicate_link import DuplicateLink
from src.models.enums import DuplicateReviewState, ReasonCode

_PRIORITY: dict[ReasonCode, int] = {
    ReasonCode.near_duplicate_in_review_band: 1,
    ReasonCode.quoted_repeat_ambiguous: 1,
    ReasonCode.different_authors_identical_text: 2,
    ReasonCode.short_text_below_dedupe_minimum: 2,
}


class ReviewItem(ResearchModel):
    """One queue row. Matches the ``review_queue`` columns in ARCHITECTURE Section 6.1."""

    item_id: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    reason_code: ReasonCode
    priority: int = Field(ge=1)
    state: str = Field(min_length=1)
    opened_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    resolver: str | None = None
    researcher_decision: str = ""


def open_items(
    links: tuple[DuplicateLink, ...] | list[DuplicateLink],
    *,
    opened_at: datetime,
) -> tuple[ReviewItem, ...]:
    """One open item per pending link. Auto-confirmed links are not queued."""
    items: list[ReviewItem] = []
    for link in links:
        if link.review_state is not DuplicateReviewState.pending_review:
            continue
        if link.review_reason_code is None:
            continue
        items.append(
            ReviewItem(
                item_id=sha1_short("review", link.link_id, link.review_reason_code.value),
                target_type="duplicate_link",
                target_id=link.link_id,
                reason_code=link.review_reason_code,
                priority=_PRIORITY.get(link.review_reason_code, 3),
                state="open",
                opened_at=opened_at,
            )
        )
    items.sort(key=lambda item: (item.priority, item.item_id))
    return tuple(items)


_RELEVANCE_PRIORITY: dict[ReasonCode, int] = {
    ReasonCode.prefilter_classifier_conflict: 1,
    ReasonCode.evidence_validation_failed: 1,
    ReasonCode.evidence_offsets_unresolved: 1,
    ReasonCode.repair_ladder_exhausted: 1,
    ReasonCode.schema_validation_failed: 1,
    ReasonCode.response_parse_failed: 2,
    ReasonCode.low_confidence: 2,
    ReasonCode.rate_limited: 2,
    ReasonCode.provider_unavailable: 3,
}


def open_extraction_items(
    pairs: list[tuple[str, str, ReasonCode]] | tuple[tuple[str, str, ReasonCode], ...],
    *,
    opened_at: datetime,
) -> tuple[ReviewItem, ...]:
    """One open item per extraction target and reason. Duplicate pairs collapse."""
    items: list[ReviewItem] = []
    seen: set[tuple[str, str, str]] = set()
    for target_type, target_id, reason in pairs:
        key = (target_type, target_id, reason.value)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            ReviewItem(
                item_id=sha1_short("review", "extraction", target_type, target_id, reason.value),
                target_type=target_type,
                target_id=target_id,
                reason_code=reason,
                priority=_RELEVANCE_PRIORITY.get(reason, 3),
                state="open",
                opened_at=opened_at,
            )
        )
    items.sort(key=lambda item: (item.priority, item.item_id))
    return tuple(items)


def open_relevance_items(
    pairs: list[tuple[str, ReasonCode]] | tuple[tuple[str, ReasonCode], ...],
    *,
    opened_at: datetime,
) -> tuple[ReviewItem, ...]:
    """One open item per decision id and reason. Duplicate pairs collapse."""
    items: list[ReviewItem] = []
    seen: set[tuple[str, str]] = set()
    for target_id, reason in pairs:
        key = (target_id, reason.value)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            ReviewItem(
                item_id=sha1_short("review", "relevance_decision", target_id, reason.value),
                target_type="relevance_decision",
                target_id=target_id,
                reason_code=reason,
                priority=_RELEVANCE_PRIORITY.get(reason, 3),
                state="open",
                opened_at=opened_at,
            )
        )
    items.sort(key=lambda item: (item.priority, item.item_id))
    return tuple(items)


def merge_items(
    existing: tuple[ReviewItem, ...] | list[ReviewItem],
    incoming: tuple[ReviewItem, ...] | list[ReviewItem],
) -> tuple[ReviewItem, ...]:
    """Append new open items. Existing rows, including resolutions, stay."""
    kept = list(existing)
    have = {item.item_id for item in existing}
    for item in incoming:
        if item.item_id not in have:
            kept.append(item)
            have.add(item.item_id)
    kept.sort(key=lambda item: (item.priority, item.item_id, item.state))
    return tuple(kept)


def append_resolution(
    items: tuple[ReviewItem, ...] | list[ReviewItem],
    item_id: str,
    *,
    decision: str,
    resolver: str,
    resolved_at: datetime,
) -> tuple[ReviewItem, ...]:
    """Append a resolved row. The open row is still in the returned tuple."""
    original = next((item for item in items if item.item_id == item_id), None)
    if original is None:
        raise KeyError(f"review item {item_id} is not in the queue")
    if original.state != "open":
        raise ValueError(f"review item {item_id} is not open")
    resolved = original.model_copy(
        update={
            "item_id": sha1_short("resolved", item_id, decision),
            "state": "resolved",
            "resolved_at": resolved_at,
            "resolver": resolver,
            "researcher_decision": decision,
        }
    )
    return tuple(items) + (resolved,)
