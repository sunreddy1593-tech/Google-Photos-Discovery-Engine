"""`EvidenceSpan` (spec 15.2) and `ObservedValue` (spec 15.5).

These two contracts are why the project can claim anything at all. Every
substantive statement about a user resolves, eventually, to a span of characters
in a document somebody can open.

**What this module cannot check.** ``quote == raw_text[start_char:end_char]`` is
the defining requirement of a span, and no field validator here can evaluate it:
the parent document's text is not in scope during model validation. That check
lives in :mod:`src.extract.validator`, called by the store layer at the validity
gate, which is also why ``validation_state`` is a stored value rather than an
implicit property (IMPLEMENTATION-PLAN Phase 1 design note).

What this module *does* check is everything that is decidable from the span
alone: the offsets are well-formed and mutually consistent, the ``offset_state``
agrees with whether offsets exist, ``valid`` is unreachable without resolved
offsets, and ``field_name`` names a field the evidence map actually enforces.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import Field, model_validator

from src.core.ids import evidence_id as derive_evidence_id
from src.models.base import ResearchModel, VersionedModel
from src.models.enums import (
    EvidenceOwnerType,
    OffsetState,
    Speaker,
    ValidationState,
)
from src.models.evidence_map import ALL_EVIDENCE_FIELD_NAMES

#: Offset states that assert a position in ``raw_text`` was determined.
RESOLVED_OFFSET_STATES = frozenset(
    {
        OffsetState.supplied_exact,
        OffsetState.repaired_unique,
        OffsetState.repaired_nearest,
        OffsetState.repaired_whitespace,
    }
)

#: Offset states that record a position could *not* be determined. Spec Section
#: 26.3 routes both to review rather than to a guess: an arbitrary offset that
#: validates is worse than a visible gap, because it looks verified.
UNRESOLVED_OFFSET_STATES = frozenset(
    {OffsetState.missing_unresolved, OffsetState.ambiguous_tied}
)

#: Offset states reached only by moving the offsets the model supplied.
REPAIRED_OFFSET_STATES = frozenset(
    {
        OffsetState.repaired_unique,
        OffsetState.repaired_nearest,
        OffsetState.repaired_whitespace,
    }
)


class EvidenceSpan(VersionedModel):
    """A verbatim substring of one document's ``raw_text`` (spec Section 15.2)."""

    evidence_id: str = Field(
        default="",
        description=(
            "Deterministic identifier (spec Section 26.1). Derived on "
            "construction when not supplied."
        ),
    )
    doc_id: str = Field(
        min_length=1,
        description="Document whose raw_text is the coordinate space.",
    )
    owner_type: EvidenceOwnerType
    owner_id: str = Field(min_length=1)
    field_name: str = Field(
        min_length=1,
        description=(
            "The exact contract field this span supports. Must be a member of "
            "the evidence-required field map (spec Section 15.10)."
        ),
    )
    quote: str = Field(
        min_length=1,
        description=(
            "Exact substring of the document's raw_text. Never a paraphrase, "
            "never a normalized form (spec Section 17.1)."
        ),
    )
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    speaker: Speaker
    offset_state: OffsetState = OffsetState.supplied_exact
    validation_state: ValidationState = ValidationState.pending
    repair_applied: bool = False

    # ---------------------------------------------------------------- checks #

    @model_validator(mode="after")
    def _check_field_name_is_enforced(self) -> "EvidenceSpan":
        """A span must name a field the evidence map enforces.

        Spec Section 15.10 consequence 2: a span attached to no field is a
        contradiction. Catching it here means a model cannot invent a
        ``field_name`` that no validator will ever look at, which is the bulk-
        evidence loophole in miniature.
        """
        if self.field_name not in ALL_EVIDENCE_FIELD_NAMES:
            raise ValueError(
                f"field_name {self.field_name!r} is not an evidence-required "
                f"field; a span attached to no field is not storable "
                f"(spec Section 15.10). Known fields: "
                f"{sorted(ALL_EVIDENCE_FIELD_NAMES)}"
            )
        return self

    @model_validator(mode="after")
    def _check_offsets_are_well_formed(self) -> "EvidenceSpan":
        """Offsets are both present or both absent, and non-empty when present."""
        has_start = self.start_char is not None
        has_end = self.end_char is not None

        if has_start != has_end:
            raise ValueError(
                "start_char and end_char must be supplied together; a half-"
                "resolved span cannot address anything"
            )
        if has_start and self.end_char <= self.start_char:  # type: ignore[operator]
            raise ValueError(
                f"end_char is exclusive and must exceed start_char, got "
                f"start_char={self.start_char}, end_char={self.end_char}"
            )
        return self

    @model_validator(mode="after")
    def _check_offset_state_agrees_with_offsets(self) -> "EvidenceSpan":
        """``offset_state`` describes how offsets were arrived at, so it cannot
        claim a resolution the span does not have."""
        resolved = self.start_char is not None

        if self.offset_state in RESOLVED_OFFSET_STATES and not resolved:
            raise ValueError(
                f"offset_state {self.offset_state.value!r} asserts resolved "
                f"offsets but start_char and end_char are null"
            )
        if self.offset_state in UNRESOLVED_OFFSET_STATES and resolved:
            raise ValueError(
                f"offset_state {self.offset_state.value!r} asserts unresolved "
                f"offsets but start_char={self.start_char} was supplied"
            )
        if self.repair_applied and self.offset_state not in REPAIRED_OFFSET_STATES:
            raise ValueError(
                f"repair_applied is true but offset_state is "
                f"{self.offset_state.value!r}, which records no repair"
            )
        return self

    @model_validator(mode="after")
    def _check_valid_requires_resolved_offsets(self) -> "EvidenceSpan":
        """A span with no offsets can never be valid (spec Section 26.3).

        The substring equality that makes a span valid is stated in terms of
        offsets. Without them there is nothing to check, so ``valid`` would be an
        assertion nobody made.
        """
        if self.validation_state is ValidationState.valid and self.start_char is None:
            raise ValueError(
                "validation_state=valid requires resolved offsets; an unresolved "
                "span enters review with reason code evidence_offsets_unresolved"
            )
        return self

    @model_validator(mode="after")
    def _fill_evidence_id(self) -> "EvidenceSpan":
        """Derive ``evidence_id`` when the caller did not supply one.

        Uses ``object.__setattr__`` because the model is frozen; the alternative
        is a ``mode="before"`` validator that would have to re-implement field
        defaulting to see the values it hashes.
        """
        if not self.evidence_id:
            object.__setattr__(
                self,
                "evidence_id",
                derive_evidence_id(
                    self.owner_id,
                    self.field_name,
                    self.quote,
                    self.start_char,
                    self.end_char,
                ),
            )
        return self

    # ------------------------------------------------------------ properties #

    @property
    def is_resolved(self) -> bool:
        """Whether this span addresses a position in the document."""
        return self.start_char is not None and self.end_char is not None

    @property
    def is_valid(self) -> bool:
        """Whether the validator has confirmed this span against its document."""
        return self.validation_state is ValidationState.valid


ValueT = TypeVar("ValueT")


class ObservedValue(ResearchModel, Generic[ValueT]):
    """One controlled label plus the span that supports it (spec Section 15.5).

    Also referred to as an evidence-backed label. Evidence is **required**, not
    optional: a value without a span is not storable, which is what keeps a
    multi-label distribution countable. Every entry in ``target_subjects``,
    ``remembered_cues``, ``forgotten_information``, ``query_strategies``,
    ``system_responses``, ``workarounds``, and ``impact_signals`` is one of
    these.

    The type parameter carries the dimension's vocabulary, so
    ``ObservedValue[RememberedCue]`` rejects a ``Workaround`` member at
    validation time rather than at analysis time.
    """

    value: ValueT
    detail: str | None = Field(
        default=None,
        description=(
            "Optional free text, permitted only where the dimension allows it "
            "(currently target_subjects). A paraphrase, never a quote."
        ),
    )
    evidence: EvidenceSpan

    @model_validator(mode="after")
    def _check_detail_is_permitted(self) -> "ObservedValue[ValueT]":
        """``detail`` exists for ``target_subjects`` and nowhere else.

        Spec Section 16.7 gives ``subject_detail`` to subjects alone. Allowing it
        everywhere would create an unaudited free-text channel on every
        dimension, and free text cannot be counted honestly (spec Section 17.19).
        """
        if self.detail is not None and self.evidence.field_name != "target_subjects":
            raise ValueError(
                f"detail is permitted only on target_subjects, not on "
                f"{self.evidence.field_name!r} (spec Section 16.7)"
            )
        if self.detail is not None and not self.detail.strip():
            raise ValueError("detail must be meaningful text or null, not blank")
        return self


#: Spec Section 15.5's heading calls this contract an evidence-backed label.
#: Both names appear in the specification, so both resolve here rather than
#: leaving a reader to guess whether two contracts exist.
EvidenceBackedLabel = ObservedValue
