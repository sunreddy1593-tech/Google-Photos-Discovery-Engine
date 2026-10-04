"""Deterministic gold split.

Documents are grouped by source platform and scope class. Inside a stratum they
are ordered by a hash of ``doc_id``, and the first two of every five seats are
``dev``. The rest are ``holdout``. The stored label is the freeze: evaluation
reads that field and does not assign the split again.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.models.enums import GoldSplit

GOLD_SPLIT_RULE = "gold-split/v1"
GOLD_SPLIT_SEED = "gold-split/v1"
DEV_SHARE_NUMERATOR = 2
DEV_SHARE_DENOMINATOR = 5


@dataclass(frozen=True)
class SplitMember:
    """One document at the moment the split is assigned."""

    doc_id: str
    source_platform: str
    scope_class: str


def assign_gold_splits(members: tuple[SplitMember, ...] | list[SplitMember]) -> dict[str, GoldSplit]:
    """Assign every member once. The same set always produces the same splits."""
    grouped: dict[tuple[str, str], list[SplitMember]] = {}
    for member in members:
        grouped.setdefault((member.source_platform, member.scope_class), []).append(member)
    assigned: dict[str, GoldSplit] = {}
    for stratum in sorted(grouped):
        ordered = sorted(grouped[stratum], key=lambda item: (_doc_hash(item.doc_id), item.doc_id))
        dev_count = (len(ordered) * DEV_SHARE_NUMERATOR) // DEV_SHARE_DENOMINATOR
        for index, member in enumerate(ordered):
            if member.doc_id in assigned:
                raise ValueError(f"duplicate doc_id in gold split input: {member.doc_id}")
            assigned[member.doc_id] = GoldSplit.dev if index < dev_count else GoldSplit.holdout
    return assigned


def _doc_hash(doc_id: str) -> str:
    payload = f"{GOLD_SPLIT_SEED}\n{doc_id}".encode()
    return hashlib.sha256(payload).hexdigest()
