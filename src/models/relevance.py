"""`RelevanceDecision` — scope classification (spec Section 15.3).

Three rules in this contract are worth reading before the code, because each one
closes a specific failure that a permissive schema would allow.

**``is_relevant`` is derived, never predicted** (invariant I13). Predicting scope
and relevance separately let two fields disagree about the same document with
nothing to arbitrate between them. Here it is a computed property of
``scope_class``: a value arriving from a model is discarded by
:meth:`RelevanceDecision.from_model_payload`, and a *stored* value that
contradicts the scope class is rejected on load, which is the case that matters
for a corpus somebody else re-reads.

**Every decision carries evidence, including ``out_of_scope``.** Excluding a
document is a substantive claim about it and needs a span showing why — the
storage complaint, the billing question, the editorial framing. "No evidence
because nothing was relevant" is exactly the reasoning that makes an exclusion
unauditable, and it is what quietly deflates a recall number.

**A technical failure is not a scope class.** When the provider is unavailable or
the response will not parse, there is no decision: ``scope_class``,
``is_relevant``, and ``confidence`` are null, ``evidence`` is empty, and the
reason lives in ``technical_state``. Such records are counted on their own funnel
line and never as ``out_of_scope``, because a provider outage is not a finding
about a user (invariant I15).
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import AwareDatetime, Field, computed_field, model_validator

from src.models.base import VersionedModel
from src.models.enums import (
    DecidedBy,
    DecisionTechnicalState,
    EvidenceOwnerType,
    ReasonCode,
    ScopeClass,
    ValidationState,
    EXCLUSION_REASON_CODES,
    INCLUSION_REASON_CODES,
    REVIEW_REASON_CODES,
)
from src.models.evidence import EvidenceSpan

#: The two scope classes that mean a document is in scope. Spec Section 15.3
#: states the derivation as a set membership, and it is written that way here so
#: adding a scope class forces a decision about which side it falls on.
RELEVANT_SCOPE_CLASSES = frozenset(
    {ScopeClass.core_incomplete_recall, ScopeClass.adjacent_known_item_retrieval}
)


def derive_is_relevant(scope_class: ScopeClass | None) -> bool | None:
    """``is_relevant`` from ``scope_class`` (spec Section 15.3).

    Null in, null out: a record with no scope class has no relevance verdict,
    which is different from a verdict of ``False``. Collapsing the two is how a
    provider outage becomes an exclusion.
    """
    if scope_class is None:
        return None
    return scope_class in RELEVANT_SCOPE_CLASSES


class RelevanceDecision(VersionedModel):
    """One scope decision about one document (spec Section 15.3)."""

    decision_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)

    scope_class: ScopeClass | None = Field(
        default=None,
        description="Null only when technical_state is not ok.",
    )
    reason_code: ReasonCode
    reason_summary: str = Field(
        min_length=1,
        description=(
            "Concise model or analyst explanation. A paraphrase: never displayed "
            "in quotation marks and never used as evidence (spec Section 17.19)."
        ),
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    technical_state: DecisionTechnicalState = DecisionTechnicalState.ok

    evidence: tuple[EvidenceSpan, ...] = Field(
        default=(),
        description=(
            "Non-empty for every decision, including out_of_scope. Empty only "
            "when technical_state is not ok."
        ),
    )

    decided_by: DecidedBy
    model_name: str | None = None
    prompt_version: str | None = None
    ruleset_version: str | None = None
    decision_fingerprint: str = Field(min_length=1)
    decided_at: AwareDatetime
    needs_human_review: bool = False
    validation_state: ValidationState = Field(
        default=ValidationState.pending,
        description=(
            "Whether this decision passed the evidence gate. Defaults to "
            "pending: a record is unchecked until src.extract.validator checks "
            "it, and only a valid record reaches processed or analysis output "
            "(spec Section 17.12)."
        ),
    )

    # -------------------------------------------------------------- derived #

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_relevant(self) -> bool | None:
        """Derived from ``scope_class``; never read from a model response."""
        return derive_is_relevant(self.scope_class)

    # --------------------------------------------------------------- inputs #

    @model_validator(mode="before")
    @classmethod
    def _reject_conflicting_is_relevant(cls, data: Any) -> Any:
        """Discard a supplied ``is_relevant`` that agrees; reject one that does not.

        Two paths reach this validator and they need different treatment. A
        *stored* record round-trips through here, because ``is_relevant`` is a
        computed field and therefore appears in ``model_dump()``; silently
        dropping a stored value that contradicts its scope class would hide
        exactly the corruption spec Section 15.3 asks us to catch. A *model
        response* should never carry the field at all, which is what
        :meth:`from_model_payload` guarantees before construction.
        """
        if not isinstance(data, Mapping) or "is_relevant" not in data:
            return data

        supplied = data["is_relevant"]
        remainder = {k: v for k, v in data.items() if k != "is_relevant"}

        raw_scope = remainder.get("scope_class")
        scope = (
            raw_scope
            if raw_scope is None or isinstance(raw_scope, ScopeClass)
            else ScopeClass(raw_scope)
        )
        derived = derive_is_relevant(scope)

        if supplied != derived:
            raise ValueError(
                f"is_relevant={supplied!r} contradicts scope_class="
                f"{None if scope is None else scope.value!r}, which derives "
                f"{derived!r}. is_relevant is derived, never stored independently "
                f"(spec Section 15.3, invariant I13)."
            )
        return remainder

    @classmethod
    def from_model_payload(cls, payload: Mapping[str, Any]) -> "RelevanceDecision":
        """Build from a model response, discarding any ``is_relevant`` it supplied.

        Spec Section 15.3: the value is discarded *before* validation, so a model
        that answers the question it was not asked cannot influence the record
        even by agreeing. The prompt does not request the field (ADR-17); this is
        the belt to that prompt's braces.
        """
        cleaned = {k: v for k, v in payload.items() if k != "is_relevant"}
        return cls.model_validate(cleaned)

    # ---------------------------------------------------------------- rules #

    @model_validator(mode="after")
    def _check_technical_state_contract(self) -> "RelevanceDecision":
        """Apply spec Section 15.3's technical-state table.

        ============================ ============ ============ =============
        ``technical_state``          scope_class  confidence   evidence
        ============================ ============ ============ =============
        ``ok``                       required     optional     non-empty
        anything else                null         null         empty
        ============================ ============ ============ =============
        """
        if self.technical_state is DecisionTechnicalState.ok:
            if self.scope_class is None:
                raise ValueError(
                    "technical_state=ok means a decision was produced, so "
                    "scope_class is required"
                )
            if not self.evidence:
                raise ValueError(
                    "every decision requires evidence, including out_of_scope: "
                    "an exclusion is a claim about the document and must be "
                    "supportable (spec Section 17.14)"
                )
            return self

        failures = []
        if self.scope_class is not None:
            failures.append(f"scope_class={self.scope_class.value!r}")
        if self.confidence is not None:
            failures.append(f"confidence={self.confidence!r}")
        if self.evidence:
            failures.append(f"{len(self.evidence)} evidence span(s)")
        if failures:
            raise ValueError(
                f"technical_state={self.technical_state.value!r} means no "
                f"decision exists, so scope_class, confidence, and evidence must "
                f"be empty; found {', '.join(failures)}. A technical failure is "
                f"never a finding (spec Section 16.10, invariant I15)."
            )
        if not self.needs_human_review:
            raise ValueError(
                f"technical_state={self.technical_state.value!r} must set "
                f"needs_human_review so the record is visible in the queue"
            )
        return self

    @model_validator(mode="after")
    def _check_reason_code_group(self) -> "RelevanceDecision":
        """A reason code from the wrong group is a validation error (spec 16.8)."""
        if self.technical_state is not DecisionTechnicalState.ok:
            if self.reason_code not in REVIEW_REASON_CODES:
                raise ValueError(
                    f"a technically failed attempt takes a review or processing "
                    f"reason code, not {self.reason_code.value!r}"
                )
            return self

        assert self.scope_class is not None  # guaranteed above
        if self.scope_class is ScopeClass.out_of_scope:
            permitted, group = EXCLUSION_REASON_CODES, "exclusion"
        else:
            permitted, group = INCLUSION_REASON_CODES, "inclusion"

        if self.reason_code not in permitted:
            raise ValueError(
                f"scope_class={self.scope_class.value!r} requires an {group} "
                f"reason code; {self.reason_code.value!r} is not one. Review and "
                f"processing codes are never valid on a completed decision "
                f"(spec Section 16.8)."
            )
        return self

    @model_validator(mode="after")
    def _check_evidence_is_attached_to_scope_class(self) -> "RelevanceDecision":
        """Spans on this record support ``scope_class`` and nothing else.

        The evidence map gives ``RelevanceDecision`` exactly one evidence-required
        field. A span naming another field here would be attached to no field of
        this record, which spec Section 15.10 makes a contradiction.
        """
        for span in self.evidence:
            if span.field_name != "scope_class":
                raise ValueError(
                    f"RelevanceDecision evidence supports scope_class; found a "
                    f"span for field_name={span.field_name!r}"
                )
            if span.owner_type is not EvidenceOwnerType.relevance_decision:
                raise ValueError(
                    f"span owner_type must be relevance_decision, got "
                    f"{span.owner_type.value!r}"
                )
            if span.owner_id != self.decision_id:
                raise ValueError(
                    f"span owner_id {span.owner_id!r} does not match "
                    f"decision_id {self.decision_id!r}"
                )
            if span.doc_id != self.doc_id:
                raise ValueError(
                    f"span doc_id {span.doc_id!r} does not match decision doc_id "
                    f"{self.doc_id!r}"
                )
        return self

    @model_validator(mode="after")
    def _check_valid_records_carry_only_valid_spans(self) -> "RelevanceDecision":
        """A decision marked ``valid`` cannot hold a span that is not.

        ``scope_class`` is this contract's only evidence-required field, so a
        rejected span here is never something the record can survive by
        discarding the field: dropping it would leave ``scope_class`` null, which
        the technical-state table already forbids on an ``ok`` decision. The
        record has to go to review (spec Section 17.12).
        """
        if self.validation_state is not ValidationState.valid:
            return self

        unusable = [span for span in self.evidence if not span.is_valid]
        if unusable:
            raise ValueError(
                f"validation_state=valid but {len(unusable)} evidence span(s) "
                f"are not valid: "
                f"{', '.join(s.validation_state.value for s in unusable)}. An "
                f"unsupported scope decision is not a decision."
            )
        return self

    @model_validator(mode="after")
    def _check_provenance(self) -> "RelevanceDecision":
        """Model and prompt versions belong to model decisions only (spec 15.3).

        A rules or human decision carrying a model name would make the corpus
        look model-derived where it is not, and invariant I7 depends on the
        opposite being reliable.
        """
        if self.decided_by is DecidedBy.llm:
            missing = [
                name
                for name, value in (
                    ("model_name", self.model_name),
                    ("prompt_version", self.prompt_version),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"decided_by=llm requires {', '.join(missing)} (invariant I7)"
                )
        else:
            present = [
                name
                for name, value in (
                    ("model_name", self.model_name),
                    ("prompt_version", self.prompt_version),
                )
                if value
            ]
            if present:
                raise ValueError(
                    f"decided_by={self.decided_by.value!r} must leave "
                    f"{', '.join(present)} null"
                )
        return self
