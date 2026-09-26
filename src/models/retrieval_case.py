"""`RetrievalCase` — one retrieval attempt extracted from one document.

Spec Section 15.4. A document yields zero, one, or many of these (spec Section
8.5), which is why the case rather than the document is the unit of analysis.

**Every substantive field is paired with a ``*_observation`` status.** The pair is
the mechanism that keeps silence from becoming a finding: a user who never
mentions what they forgot produces ``forgotten_information = ()`` with
``forgotten_information_observation = not_stated``, which reads as "the source is
silent" everywhere downstream. ``explicitly_none`` is the only value that means
"the user said there was none", and the two are never merged (spec Section 16.9).
This model enforces the value half of that contract — a ``stated`` status with no
value, or a ``not_stated`` status with one, is rejected here. The evidence half
needs the span store and lives in :mod:`src.extract.validator`.

**Three fields are deliberately absent** (spec Section 15.4, invariant I10):

===================== ===================================== =====================
Absent field          Lives in                              Why
===================== ===================================== =====================
``candidate_cluster`` ``ClusterAssignment.cluster_id``       A cluster label on the
``cluster_confidence````ClusterAssignment.confidence``       extraction record makes
``taxonomy_version``  ``ClusterAssignment.taxonomy_version`` extraction depend on a
                                                             taxonomy Section 20
                                                             forbids until after
                                                             pilot review — and
                                                             forces a paid
                                                             re-extraction of the
                                                             whole corpus on every
                                                             taxonomy revision.
===================== ===================================== =====================

Because ``extra="forbid"`` is inherited, passing any of them raises. There is no
cluster field to leave null, so there is nothing for a prompt to fill in.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import AwareDatetime, Field, computed_field, model_validator

from src.models.base import VersionedModel
from src.models.enums import (
    DimensionObservationStatus,
    EvidenceOwnerType,
    ExtractorType,
    ForgottenInfo,
    ImpactSignal,
    KnownItemStatus,
    Outcome,
    QueryStrategy,
    RememberedCue,
    ScopeClass,
    SubjectType,
    SystemResponse,
    TargetAssetType,
    ValidationState,
    Workaround,
)
from src.models.evidence import EvidenceSpan, ObservedValue
from src.models.evidence_map import (
    OBSERVATION_FIELD,
    RETRIEVAL_CASE,
    STATUS_GATE,
)


def _is_empty(value: Any) -> bool:
    """Whether a field holds no value, for the purposes of the status gate.

    ``0`` and ``False`` are values, not absences: ``reformulation_count = 0``
    means the user reformulated nothing, which is a countable observation.
    """
    if value is None:
        return True
    if isinstance(value, (tuple, list, str)) and len(value) == 0:
        return True
    return False


class RetrievalCase(VersionedModel):
    """One extracted retrieval case (spec Section 15.4)."""

    case_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    scope_class: ScopeClass = Field(
        description="Inherited validated scope class from the relevance decision."
    )

    known_item_status: KnownItemStatus | None = None
    known_item_status_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    target_asset_type: TargetAssetType | None = None
    target_asset_type_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    target_subjects: tuple[ObservedValue[SubjectType], ...] = ()
    target_subjects_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    retrieval_trigger: str | None = Field(
        default=None,
        description="Why the user needed the item, when explicitly stated.",
    )
    retrieval_trigger_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    remembered_cues: tuple[ObservedValue[RememberedCue], ...] = ()
    remembered_cues_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    forgotten_information: tuple[ObservedValue[ForgottenInfo], ...] = ()
    forgotten_information_observation: DimensionObservationStatus = Field(
        default=DimensionObservationStatus.not_stated,
        description=(
            "not_stated is the default and must never be read as 'forgot "
            "nothing'; explicitly_none is the only value carrying that meaning."
        ),
    )

    exact_query: str | None = Field(
        default=None,
        description=(
            "Only when directly quoted or clearly delimited in the source "
            "(spec Section 17.3)."
        ),
    )
    exact_query_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    query_paraphrase: str | None = Field(
        default=None,
        description=(
            "Clearly labelled summary when no exact query exists. Never rendered "
            "in quotation marks, and still evidence-required."
        ),
    )
    query_paraphrase_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    query_strategies: tuple[ObservedValue[QueryStrategy], ...] = ()
    query_strategies_observation: DimensionObservationStatus = Field(
        default=DimensionObservationStatus.not_stated,
        description=(
            "explicitly_none covers a user who states they could not formulate "
            "any query (spec Section 9.1)."
        ),
    )

    reformulation_count: int | None = Field(default=None, ge=0)
    reformulation_count_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    system_responses: tuple[ObservedValue[SystemResponse], ...] = ()
    system_responses_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    workarounds: tuple[ObservedValue[Workaround], ...] = ()
    workarounds_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    outcome: Outcome | None = None
    outcome_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    impact_signals: tuple[ObservedValue[ImpactSignal], ...] = ()
    impact_signals_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )

    severity: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Evidence-based rating using spec Section 18's rubric.",
    )
    severity_observation: DimensionObservationStatus = (
        DimensionObservationStatus.not_stated
    )
    severity_evidence: tuple[EvidenceSpan, ...] = Field(
        default=(),
        description="Required and non-empty whenever severity is not null.",
    )

    problem_summary: str = Field(
        min_length=1,
        description=(
            "Concise interpretation. A paraphrase: never presented as a user "
            "quote (spec Section 17.19)."
        ),
    )

    uncertainty_notes: tuple[str, ...] = ()

    extractor_type: ExtractorType
    model_name: str | None = None
    prompt_version: str = Field(min_length=1)
    extraction_fingerprint: str = Field(
        min_length=1,
        description="Spec Section 26.2. Does not include taxonomy_version.",
    )
    extracted_at: AwareDatetime
    needs_human_review: bool = False
    validation_state: ValidationState = Field(
        default=ValidationState.pending,
        description=(
            "Whether this case passed the evidence gate. Defaults to pending: a "
            "record is unchecked until src.extract.validator checks it, and "
            "only a valid record reaches processed or analysis output "
            "(spec Section 17.12)."
        ),
    )

    # -------------------------------------------------------------- derived #

    @model_validator(mode="before")
    @classmethod
    def _discard_supplied_all_evidence_spans(cls, data: Any) -> Any:
        """Drop any ``all_evidence_spans`` a model or analyst supplied.

        Spec Section 15.10: the union is computed, never authored. Dropping it
        rather than rejecting it is what the specification asks for here — unlike
        ``is_relevant``, a supplied union is not a contradictory *claim*, it is a
        convenience field the model was not asked for, and the computed value
        replaces it in full.
        """
        if isinstance(data, Mapping) and "all_evidence_spans" in data:
            return {k: v for k, v in data.items() if k != "all_evidence_spans"}
        return data

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_evidence_spans(self) -> tuple[EvidenceSpan, ...]:
        """De-duplicated union of every field-level span the case itself holds.

        That is ``severity_evidence`` plus every ``ObservedValue.evidence``.
        Spans for scalar fields — ``outcome``, ``exact_query``,
        ``known_item_status`` and the rest — are stored in the ``evidence_spans``
        store keyed by ``owner_id`` and ``field_name``, not inline on the case, so
        the authoritative union for a persisted record is the one
        :func:`src.extract.validator.derive_all_evidence_spans` returns when given
        both. This property is that function's inline half, and the two agree by
        construction on a case whose spans are all inline.

        De-duplication is by ``evidence_id``, which already incorporates the
        field name: the same quote supporting two different fields is two spans,
        because collapsing them would make the field-level map unenforceable.
        """
        return dedupe_spans(self.inline_evidence_spans())

    def inline_evidence_spans(self) -> tuple[EvidenceSpan, ...]:
        """Every span physically stored on this record, in field order."""
        spans: list[EvidenceSpan] = []
        for field_name in _OBSERVED_VALUE_FIELDS:
            for observed in getattr(self, field_name):
                spans.append(observed.evidence)
        spans.extend(self.severity_evidence)
        return tuple(spans)

    # ---------------------------------------------------------------- rules #

    @model_validator(mode="after")
    def _check_case_id_form(self) -> "RetrievalCase":
        """``case_id`` is ``{doc_id}#cNN`` or ``{doc_id}#u{hash}`` (spec 26.3)."""
        if not (
            self.case_id.startswith(f"{self.doc_id}#c")
            or self.case_id.startswith(f"{self.doc_id}#u")
        ):
            raise ValueError(
                f"case_id {self.case_id!r} must be {self.doc_id}#cNN for an "
                f"ordered case or {self.doc_id}#u<hash> for one whose offsets "
                f"are unresolved (spec Section 26.3)"
            )
        return self

    @model_validator(mode="after")
    def _check_status_value_agreement(self) -> "RetrievalCase":
        """Apply the value half of spec Section 15.10's status gate.

        A ``stated`` status with no value and a ``not_stated`` status with a value
        are both rejected rather than coerced (spec Section 17.17). Coercion would
        pick one of the two to believe, and there is no principled way to choose:
        either the status or the value is wrong, and only a human can say which.
        """
        problems: list[str] = []

        for field_name, observation_field in OBSERVATION_FIELD.items():
            if observation_field is None or field_name not in type(self).model_fields:
                continue

            status: DimensionObservationStatus = getattr(self, observation_field)
            value = getattr(self, field_name)
            rule = STATUS_GATE[status]
            empty = _is_empty(value)

            if rule.value_required and empty:
                problems.append(
                    f"{observation_field}={status.value} requires a value, but "
                    f"{field_name} is empty"
                )
            if rule.value_must_be_empty and not empty:
                problems.append(
                    f"{observation_field}={status.value} requires {field_name} to "
                    f"be empty, but it holds {value!r}"
                )

        if problems:
            raise ValueError(
                "observation status conflicts with value (spec Section 15.10):\n  "
                + "\n  ".join(problems)
            )
        return self

    @model_validator(mode="after")
    def _check_severity_evidence(self) -> "RetrievalCase":
        """Severity is the one evidence-required field whose spans live inline.

        Spec Section 17.7 and Section 18: a non-null severity always needs
        supporting spans, and a negative adjective is not one of them. The
        inverse also holds — ``not_stated`` severity carrying evidence is the
        status conflict in Section 17.17, and null severity is better than
        unsupported precision.
        """
        rule = STATUS_GATE[self.severity_observation]

        if self.severity is not None and not self.severity_evidence:
            raise ValueError(
                f"severity={self.severity} requires non-empty severity_evidence "
                f"(spec Section 17.7). Null severity is better than unsupported "
                f"precision (spec Section 18)."
            )
        if rule.evidence_required and not self.severity_evidence:
            raise ValueError(
                f"severity_observation={self.severity_observation.value} requires "
                f"at least one severity_evidence span"
            )
        if rule.evidence_must_be_empty and self.severity_evidence:
            raise ValueError(
                f"severity_observation={self.severity_observation.value} forbids "
                f"evidence, but {len(self.severity_evidence)} span(s) are attached"
            )

        for span in self.severity_evidence:
            if span.field_name != "severity":
                raise ValueError(
                    f"severity_evidence holds a span for field_name="
                    f"{span.field_name!r}"
                )
            if span.owner_type is not EvidenceOwnerType.severity:
                raise ValueError(
                    f"severity_evidence span owner_type must be severity, got "
                    f"{span.owner_type.value!r}"
                )
        return self

    @model_validator(mode="after")
    def _check_valid_records_carry_only_valid_spans(self) -> "RetrievalCase":
        """A case marked ``valid`` cannot hold a span that is not.

        This is the half of the record-level gate that is decidable without the
        document, and it is what stops the invalid-evidence path from being
        resolved by dropping the affected field and keeping the rest: the case
        cannot be marked valid while the fabricated span is attached, and
        detaching the span leaves the field unevidenced, which the status gate in
        :mod:`src.extract.validator` then rejects. Both exits are closed, so the
        only way forward is review (spec Section 17.12).
        """
        if self.validation_state is not ValidationState.valid:
            return self

        unusable = [
            span for span in self.inline_evidence_spans() if not span.is_valid
        ]
        if unusable:
            raise ValueError(
                f"validation_state=valid but {len(unusable)} inline span(s) are "
                f"not valid: "
                f"{', '.join(f'{s.field_name}={s.validation_state.value}' for s in unusable)}. "
                f"A record is only as valid as the evidence it carries."
            )
        return self

    @model_validator(mode="after")
    def _check_observed_value_spans(self) -> "RetrievalCase":
        """Each ``ObservedValue``'s span must name the dimension it sits in.

        Without this, a span supporting ``remembered_cues`` could be attached to
        a ``workarounds`` entry and the field-level map would still appear
        satisfied, which is the bulk-evidence loophole spec Section 15.10 closes.
        """
        for field_name in _OBSERVED_VALUE_FIELDS:
            for observed in getattr(self, field_name):
                span = observed.evidence
                if span.field_name != field_name:
                    raise ValueError(
                        f"{field_name} entry carries a span for field_name="
                        f"{span.field_name!r}"
                    )
                if span.doc_id != self.doc_id:
                    raise ValueError(
                        f"{field_name} span doc_id {span.doc_id!r} does not match "
                        f"case doc_id {self.doc_id!r}"
                    )
                if span.owner_type is not EvidenceOwnerType.observed_value:
                    raise ValueError(
                        f"{field_name} span owner_type must be observed_value, "
                        f"got {span.owner_type.value!r}"
                    )
        return self

    @model_validator(mode="after")
    def _check_provenance(self) -> "RetrievalCase":
        """``model_name`` belongs to model-produced cases only (invariant I7)."""
        model_backed = self.extractor_type in {
            ExtractorType.llm,
            ExtractorType.hybrid,
        }
        if model_backed and not self.model_name:
            raise ValueError(
                f"extractor_type={self.extractor_type.value} requires model_name"
            )
        if not model_backed and self.model_name:
            raise ValueError(
                f"extractor_type={self.extractor_type.value} must leave "
                f"model_name null"
            )
        return self


#: The seven multi-label dimensions, in the order their spans enter the union.
#: Fixed order rather than set iteration, so ``all_evidence_spans`` is stable
#: across runs and can participate in a content-equivalence hash.
#: ``tests/test_evidence_map.py`` asserts this tuple matches the ``ObservedValue``
#: fields the model actually declares.
_OBSERVED_VALUE_FIELDS: tuple[str, ...] = (
    "target_subjects",
    "remembered_cues",
    "forgotten_information",
    "query_strategies",
    "system_responses",
    "workarounds",
    "impact_signals",
)


#: Which state survives when two spans share an ``evidence_id``. Ascending
#: trust: the *least* trusted state wins, so de-duplication can never improve a
#: span's standing.
_STATE_PRECEDENCE: dict[ValidationState, int] = {
    ValidationState.rejected: 0,
    ValidationState.pending: 1,
    ValidationState.valid: 2,
}


def dedupe_spans(spans: Sequence[EvidenceSpan]) -> tuple[EvidenceSpan, ...]:
    """De-duplicate spans by ``evidence_id``, preserving first-seen order.

    Order is preserved so the union is stable across runs and therefore usable in
    a content-equivalence hash (spec Section 26.4).

    **The least-trusted duplicate is the one kept.** ``evidence_id`` is derived
    from the owner, field, quote, and offsets, so a rejected span and a valid one
    can collide — the same claimed quote, validated twice with different
    outcomes. Keeping whichever arrived first meant a fabricated span was
    silently deleted whenever a valid twin happened to be stored ahead of it, and
    the union then reported the record as fully evidenced. That is the
    field-dropping the evidence architecture forbids, arriving through the back
    door of a helper nobody suspects (spec Section 17.12).
    """
    seen: dict[str, EvidenceSpan] = {}
    for span in spans:
        existing = seen.get(span.evidence_id)
        if existing is None or (
            _STATE_PRECEDENCE[span.validation_state]
            < _STATE_PRECEDENCE[existing.validation_state]
        ):
            seen[span.evidence_id] = span
    return tuple(seen.values())


#: Contract name used by the evidence map and the validator.
CONTRACT_NAME = RETRIEVAL_CASE
