"""`DuplicateLink` — deduplication output (spec Section 15.7).

Duplicate status is a **relationship between two documents**, not a state of
either one and not a lifecycle stage. A document with a link continues through
every downstream stage and keeps its extracted cases; it is excluded at the
analysis layer by the prevalence views, which is what preserves auditability
while preventing inflation (invariant I4).

A ``human_rejected`` link is retained rather than deleted. It records that a pair
was considered and found distinct, which is precisely the evidence a reader needs
in order to trust a duplicate rate — a corpus that only keeps its confirmations
cannot show its false-positive rate.
"""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from src.models.base import VersionedModel
from src.models.enums import (
    DuplicateDecidedBy,
    DuplicateDetectionMethod,
    DuplicateKind,
    DuplicateReviewState,
    REVIEW_REASON_CODES,
    ReasonCode,
)


class DuplicateLink(VersionedModel):
    """One duplicate relationship between two documents (spec Section 15.7)."""

    link_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1, description="The duplicate document.")
    canonical_doc_id: str = Field(
        min_length=1,
        description=(
            "The group's canonical document: the lowest doc_id under byte-wise "
            "ascending comparison, never the first collected (spec Section 26.1)."
        ),
    )

    duplicate_kind: DuplicateKind
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    method: DuplicateDetectionMethod
    method_version: str = Field(min_length=1)
    method_detail: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Raw comparison details, including the raw Hamming distance and both "
            "token counts, so a threshold change can be re-evaluated without "
            "re-running detection."
        ),
    )

    review_state: DuplicateReviewState
    decided_by: DuplicateDecidedBy
    decided_at: AwareDatetime
    review_reason_code: ReasonCode | None = None

    @model_validator(mode="after")
    def _check_distinct_documents(self) -> "DuplicateLink":
        if self.doc_id == self.canonical_doc_id:
            raise ValueError(
                f"a document cannot be its own duplicate: {self.doc_id!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_review_reason(self) -> "DuplicateLink":
        """Anything other than ``auto_confirmed`` states why (spec Section 15.7).

        A link sitting in review with no reason code cannot be triaged, and a
        pending-review link is excluded from the duplicate count until resolved,
        so the reason is what a reviewer works from.
        """
        if self.review_state is DuplicateReviewState.auto_confirmed:
            if self.review_reason_code is not None:
                raise ValueError(
                    "auto_confirmed links carry no review_reason_code; the "
                    "safety conditions in spec Section 19.6 all held"
                )
            return self

        if self.review_reason_code is None:
            raise ValueError(
                f"review_state={self.review_state.value} requires a "
                f"review_reason_code (spec Section 15.7)"
            )
        if self.review_reason_code not in REVIEW_REASON_CODES:
            raise ValueError(
                f"review_reason_code must come from the review and processing "
                f"group; {self.review_reason_code.value!r} does not "
                f"(spec Section 16.8)"
            )
        return self

    @model_validator(mode="after")
    def _check_human_decisions(self) -> "DuplicateLink":
        human_states = {
            DuplicateReviewState.human_confirmed,
            DuplicateReviewState.human_rejected,
        }
        if (
            self.review_state in human_states
            and self.decided_by is not DuplicateDecidedBy.human
        ):
            raise ValueError(
                f"review_state={self.review_state.value} requires decided_by=human"
            )
        return self

    @property
    def counts_as_duplicate(self) -> bool:
        """Whether analysis may treat this link as a confirmed duplicate.

        ``pending_review`` is excluded until resolved and reported on its own
        funnel line; ``human_rejected`` is retained but never counted
        (spec Section 16.11).
        """
        return self.review_state in {
            DuplicateReviewState.auto_confirmed,
            DuplicateReviewState.human_confirmed,
        }
