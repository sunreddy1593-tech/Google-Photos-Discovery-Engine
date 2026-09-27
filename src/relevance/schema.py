"""The object the relevance model is allowed to return.

``is_relevant`` is not a field. A supplied value is removed before validation
and then ignored. Extra keys fail validation rather than being kept.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.models.enums import ReasonCode, ScopeClass


class EvidencePayload(BaseModel):
    """One verbatim span as the model claimed it. Offsets are optional."""

    model_config = ConfigDict(extra="forbid")

    quote: str = Field(min_length=1)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)


class RelevancePayload(BaseModel):
    """Structured classifier output before it becomes a RelevanceDecision."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(min_length=1)
    scope_class: ScopeClass
    reason_code: ReasonCode
    reason_summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: EvidencePayload
