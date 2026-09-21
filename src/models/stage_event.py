"""`StageEvent` — append-only processing status (spec Section 15.8).

This contract replaces the single ``doc_state`` lifecycle column entirely, and
the reason is worth stating plainly: no single column can describe where a
document is, because a document is simultaneously imported, normalized, marked as
a duplicate, prefilter-passed, classified, and extracted. A lifecycle column
forces one of those facts to win, and the funnel built on it then disagrees with
the data (ARCHITECTURE Section 5.1, invariant I14).

Events are append-only. A later event never rewrites an earlier one; the history
of what the pipeline did *is* the audit trail. The current status of a document at
a stage is the latest event for that ``(target_id, stage)`` pair, and the Phase 8
funnel is computed per stage from these rows, so a document correctly appears at
every stage it reached.

Failure and unavailability are ordinary statuses with reason codes rather than
absences to be inferred, which is what makes them countable on their own funnel
lines.
"""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from src.models.base import VersionedModel
from src.models.enums import (
    REVIEW_REASON_CODES,
    ReasonCode,
    Stage,
    StageEventTargetType,
    StageStatus,
)


class StageEvent(VersionedModel):
    """One thing that happened to one target at one stage (spec Section 15.8)."""

    event_id: str = Field(min_length=1)
    target_type: StageEventTargetType
    target_id: str = Field(
        min_length=1, description="doc_id, case_id, or ingest_batch_id."
    )
    stage: Stage
    status: StageStatus
    reason_code: ReasonCode | None = Field(
        default=None,
        description="Required for every status other than succeeded.",
    )
    attempt: int = Field(
        default=1,
        ge=1,
        description=(
            "Attempt number within the run. Participates in event_id so a retry "
            "is a distinct event rather than an overwrite."
        ),
    )
    run_id: str = Field(min_length=1)
    occurred_at: AwareDatetime
    detail: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Stage-specific payload — matched prefilter rules, validation error "
            "classes, and the like."
        ),
    )

    @model_validator(mode="after")
    def _check_reason_code(self) -> "StageEvent":
        """Every non-success status says why (spec Section 15.8).

        ``started`` is the exception: it reports that work began, and there is no
        reason for beginning. Without this rule a funnel could show documents
        disappearing between stages with nothing to attribute the loss to, which
        is the condition the prefilter risk (R1) depends on being visible.
        """
        if self.status in {StageStatus.succeeded, StageStatus.started}:
            if self.reason_code is not None:
                raise ValueError(
                    f"status={self.status.value} carries no reason_code, got "
                    f"{self.reason_code.value!r}"
                )
            return self

        if self.reason_code is None:
            raise ValueError(
                f"status={self.status.value} requires a reason_code so the "
                f"funnel can attribute the loss (spec Section 15.8)"
            )
        if self.reason_code not in REVIEW_REASON_CODES:
            raise ValueError(
                f"stage events take reason codes from the review and processing "
                f"group; {self.reason_code.value!r} is an inclusion or exclusion "
                f"code (spec Section 16.8)"
            )
        return self
