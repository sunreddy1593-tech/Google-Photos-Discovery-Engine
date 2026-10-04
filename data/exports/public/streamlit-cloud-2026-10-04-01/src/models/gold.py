"""Gold-set contracts (spec Section 15.11).

Document-level relevance labelling and case-level extraction labelling are
**separate records in separate files**, because they answer different questions
and are measured with different metrics. A document can be relevant and still
yield no extractable case; a gold set that cannot express that cannot measure
over-extraction at all, which is why ``expected_case_count = 0`` is a valid and
expected label rather than a gap.

``pre_adjudication_labels`` retains every independent reviewer label. Inter-coder
disagreement is itself a finding about how clear the definitions are, and it
disappears the moment you adjudicate, so it has to be captured before that
(ADR-25).
"""

from __future__ import annotations

from typing import Any

from pydantic import AwareDatetime, Field, model_validator

from src.models.base import ResearchModel, VersionedModel
from src.models.enums import (
    EXCLUSION_REASON_CODES,
    GoldSplit,
    INCLUSION_REASON_CODES,
    ReasonCode,
    ScopeClass,
)
from src.models.relevance import derive_is_relevant


class PreAdjudicationLabel(ResearchModel):
    """One reviewer's independent label, retained after adjudication."""

    labeler_id: str = Field(min_length=1)
    scope_class: ScopeClass
    reason_code: ReasonCode
    labeled_at: AwareDatetime
    notes: str | None = None


class GoldDocumentLabel(VersionedModel):
    """Exactly one per gold document (spec Section 15.11)."""

    doc_id: str = Field(min_length=1)
    split: GoldSplit = Field(
        description=(
            "dev is read freely for iteration; holdout is frozen and read once "
            "per reported configuration (ADR-25)."
        )
    )
    scope_class: ScopeClass
    reason_code: ReasonCode
    prefilter_should_pass: bool = Field(
        description=(
            "Whether a correct high-recall prefilter must let this document "
            "through. Judged independently of the classifier, because a "
            "prefilter drop is otherwise invisible to every later stage."
        )
    )
    expected_case_count: int = Field(
        ge=0,
        description="0, 1, or more. Zero is a valid and expected label.",
    )

    labeler_id: str = Field(min_length=1)
    labeled_at: AwareDatetime
    adjudicated: bool = False
    pre_adjudication_labels: tuple[PreAdjudicationLabel, ...] = ()
    notes: str | None = None

    @property
    def is_relevant(self) -> bool:
        """Derived from ``scope_class`` by the same rule as the production record.

        Gold labels and pipeline output must agree on what relevance *means*, or
        the precision and recall numbers compare two different questions.
        """
        derived = derive_is_relevant(self.scope_class)
        assert derived is not None  # scope_class is non-null on a gold label
        return derived

    @model_validator(mode="after")
    def _check_reason_code_group(self) -> "GoldDocumentLabel":
        permitted = (
            EXCLUSION_REASON_CODES
            if self.scope_class is ScopeClass.out_of_scope
            else INCLUSION_REASON_CODES
        )
        if self.reason_code not in permitted:
            raise ValueError(
                f"gold scope_class={self.scope_class.value!r} requires a matching "
                f"reason code; {self.reason_code.value!r} is from another group "
                f"(spec Section 16.8)"
            )
        return self

    @model_validator(mode="after")
    def _check_adjudication_has_labels(self) -> "GoldDocumentLabel":
        """An adjudicated label must retain what it adjudicated between.

        Otherwise agreement can only be computed after the disagreement has been
        erased, which reports perfect agreement on every double-coded document.
        """
        if self.adjudicated and len(self.pre_adjudication_labels) < 2:
            raise ValueError(
                "adjudicated=True requires at least two pre_adjudication_labels; "
                "inter-reviewer agreement is computed from them, before "
                "adjudication (spec Section 15.11)"
            )
        return self


class GoldCase(VersionedModel):
    """Zero, one, or many per document (spec Section 15.11)."""

    gold_case_id: str = Field(min_length=1, description="{doc_id}#g{ordinal:02d}")
    doc_id: str = Field(min_length=1)
    expected_values: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Per-field expected {observation, value} pairs, using the same "
            "vocabularies as spec Section 15.4."
        ),
    )
    expected_evidence: tuple[str, ...] = Field(
        default=(),
        description=(
            "Verbatim quotes the reviewer considers sufficient support. Validated "
            "against raw_text by the production validator — a paraphrase in a "
            "gold label is a defect in the gold set."
        ),
    )
    labeler_id: str = Field(min_length=1)
    adjudicated: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def _check_gold_case_id_form(self) -> "GoldCase":
        if not self.gold_case_id.startswith(f"{self.doc_id}#g"):
            raise ValueError(
                f"gold_case_id {self.gold_case_id!r} must be "
                f"{self.doc_id}#g<ordinal> (spec Section 15.11)"
            )
        return self
