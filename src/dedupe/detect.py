"""Duplicate links for one corpus (spec Sections 15.7 and 19.6).

Pairs are considered in ``doc_id`` order. The canonical document of a pair or
of an exact-hash group is the lowest ``doc_id`` under byte-wise comparison
(ADR-20, spec Section 26.1). ``collected_at`` is not a selection key. The
Phase 3 plan rejects first-collected because it follows ingestion order.
``CollectedDocument.collected_at`` is required, so a null timestamp never
reaches this stage.

A shared listing or thread URL is not a duplicate. ``same_source_item`` requires
the same ``source_item_id``, or one missing identifier whose value is carried
in both canonical URLs (a permalink and its share-link form of that same item).

``author_hash`` is ``HMAC(salt, source_platform | username)``. The same
username on two platforms therefore has two different hashes, and equal hashes
are not evidence of one person across platforms. A cross-platform content
match is ``cross_post`` and stays in review.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations

from src.core.config import DedupeConfig
from src.core.ids import canonical_doc_id, link_id
from src.core.versions import DEDUPE_VERSION
from src.dedupe.safety import review_reason
from src.dedupe.simhash import hamming_distance
from src.models.duplicate_link import DuplicateLink
from src.models.enums import (
    DuplicateDecidedBy,
    DuplicateDetectionMethod,
    DuplicateKind,
    DuplicateReviewState,
    ReasonCode,
)


@dataclass(frozen=True)
class PreparedDocument:
    """The fields dedupe is allowed to see. No raw text, no salt."""

    doc_id: str
    source_platform: str
    source_item_id: str | None
    canonical_url: str
    author_hash: str | None
    content_hash: str
    simhash: str
    token_count: int
    normalized_text: str


def detect_links(
    documents: list[PreparedDocument] | tuple[PreparedDocument, ...],
    config: DedupeConfig,
    *,
    decided_at: datetime,
) -> tuple[DuplicateLink, ...]:
    """Return one link per duplicate relationship, sorted by ``link_id``."""
    ordered = tuple(sorted(documents, key=lambda document: document.doc_id))
    by_id = {document.doc_id: document for document in ordered}
    linked: set[frozenset[str]] = set()
    links: list[DuplicateLink] = []

    for left, right in combinations(ordered, 2):
        if _same_source_item(left, right):
            links.append(
                _link(
                    left,
                    right,
                    kind=DuplicateKind.same_source_item,
                    method=DuplicateDetectionMethod.source_item_key,
                    reason=None,
                    config=config,
                    decided_at=decided_at,
                )
            )
            linked.add(frozenset((left.doc_id, right.doc_id)))

    groups: dict[str, list[PreparedDocument]] = defaultdict(list)
    for document in ordered:
        groups[document.content_hash].append(document)
    for group in groups.values():
        if len(group) < 2:
            continue
        keeper = by_id[canonical_doc_id(document.doc_id for document in group)]
        member_ids = [document.doc_id for document in group]
        for duplicate_id in member_ids:
            if duplicate_id == keeper.doc_id:
                continue
            key = frozenset((keeper.doc_id, duplicate_id))
            if key in linked:
                continue
            links.append(
                _link(
                    keeper,
                    by_id[duplicate_id],
                    kind=_text_kind(keeper, by_id[duplicate_id], hashes_equal=True),
                    method=DuplicateDetectionMethod.content_hash,
                    reason=_reason(keeper, by_id[duplicate_id], quoted=False, config=config),
                    config=config,
                    decided_at=decided_at,
                )
            )
        for left_id, right_id in combinations(member_ids, 2):
            linked.add(frozenset((left_id, right_id)))

    for left, right in combinations(ordered, 2):
        key = frozenset((left.doc_id, right.doc_id))
        if key in linked:
            continue
        quoted = _quoted(left, right)
        distance = hamming_distance(left.simhash, right.simhash)
        if not quoted and distance > config.simhash_review_band_max:
            continue
        links.append(
            _link(
                left,
                right,
                kind=_text_kind(left, right, hashes_equal=False, quoted=quoted),
                method=DuplicateDetectionMethod.simhash,
                reason=_reason(left, right, quoted=quoted, config=config),
                config=config,
                decided_at=decided_at,
            )
        )

    links.sort(key=lambda item: item.link_id)
    return tuple(links)


def _same_source_item(left: PreparedDocument, right: PreparedDocument) -> bool:
    """Platform identity, not a shared listing URL."""
    if left.source_item_id and left.source_item_id == right.source_item_id:
        return True
    if left.canonical_url != right.canonical_url:
        return False
    present = left.source_item_id or right.source_item_id
    if not present or (left.source_item_id and right.source_item_id):
        return False
    return present in left.canonical_url and present in right.canonical_url


def _text_kind(
    left: PreparedDocument,
    right: PreparedDocument,
    *,
    hashes_equal: bool,
    quoted: bool = False,
) -> DuplicateKind:
    """Classify from content and platform, not from author-hash equality.

    ``cross_post`` means substantially the same text on two platforms. It does
    not mean the hashes identify one person: those hashes include the platform.
    """
    different_platform = left.source_platform != right.source_platform
    if quoted and not hashes_equal:
        return DuplicateKind.quoted_repeat
    if different_platform:
        return DuplicateKind.cross_post
    if hashes_equal:
        return DuplicateKind.exact_text
    return DuplicateKind.near


def _reason(
    left: PreparedDocument,
    right: PreparedDocument,
    *,
    quoted: bool,
    config: DedupeConfig,
) -> object:
    return review_reason(
        token_count_left=left.token_count,
        token_count_right=right.token_count,
        author_left=left.author_hash,
        author_right=right.author_hash,
        hamming=hamming_distance(left.simhash, right.simhash),
        content_hashes_equal=left.content_hash == right.content_hash,
        quoted=quoted,
        cross_platform=left.source_platform != right.source_platform,
        config=config,
    )


def _quoted(left: PreparedDocument, right: PreparedDocument) -> bool:
    """One text reproduces a substantial contiguous stretch of the other.

    Eight tokens, and at least half of the shorter text. Equal texts are exact
    duplicates, not quotes. Short generic phrases stay under the threshold.
    """
    if left.normalized_text == right.normalized_text:
        return False
    left_tokens = left.normalized_text.split()
    right_tokens = right.normalized_text.split()
    shorter, longer = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    if len(shorter) < 8 or len(longer) == len(shorter):
        return False
    overlap = _longest_contiguous(shorter, longer)
    return overlap >= 8 and overlap * 2 >= len(shorter)


def _longest_contiguous(shorter: list[str], longer: list[str]) -> int:
    best = 0
    for start in range(len(longer)):
        length = 0
        while (
            length < len(shorter)
            and start + length < len(longer)
            and shorter[length] == longer[start + length]
        ):
            length += 1
        if length > best:
            best = length
    for left_start in range(len(shorter)):
        for right_start in range(len(longer)):
            length = 0
            while (
                left_start + length < len(shorter)
                and right_start + length < len(longer)
                and shorter[left_start + length] == longer[right_start + length]
            ):
                length += 1
            if length > best:
                best = length
    return best


def _link(
    left: PreparedDocument,
    right: PreparedDocument,
    *,
    kind: DuplicateKind,
    method: DuplicateDetectionMethod,
    reason: ReasonCode | None,
    config: DedupeConfig,
    decided_at: datetime,
) -> DuplicateLink:
    keeper_id = canonical_doc_id((left.doc_id, right.doc_id))
    keeper = left if left.doc_id == keeper_id else right
    duplicate = right if keeper is left else left
    distance = hamming_distance(left.simhash, right.simhash)
    pending = reason is not None
    return DuplicateLink(
        link_id=link_id(duplicate.doc_id, keeper.doc_id, method.value),
        doc_id=duplicate.doc_id,
        canonical_doc_id=keeper.doc_id,
        duplicate_kind=kind,
        similarity=(64 - distance) / 64,
        method=method,
        method_version=DEDUPE_VERSION,
        method_detail={
            "hamming_distance": distance,
            "token_count_canonical": keeper.token_count,
            "token_count_duplicate": duplicate.token_count,
            "min_tokens": config.min_tokens,
            "simhash_duplicate_max": config.simhash_duplicate_max,
            "simhash_review_band_max": config.simhash_review_band_max,
            "cross_platform": left.source_platform != right.source_platform,
        },
        review_state=(
            DuplicateReviewState.pending_review
            if pending
            else DuplicateReviewState.auto_confirmed
        ),
        decided_by=DuplicateDecidedBy.rules,
        decided_at=decided_at,
        review_reason_code=reason,
    )
