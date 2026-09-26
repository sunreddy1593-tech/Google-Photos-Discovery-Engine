"""Evidence-map and record-gate tests (spec Sections 15.10, 25 "Evidence").

The completeness test at the top is the one that keeps the rest honest. It walks
the Pydantic field sets of both contracts and asserts every field is classified,
so a substantive field added in a later phase fails the suite until somebody
decides whether it is a claim about a user. Documentation cannot do that; a test
over the model definitions can.
"""

from __future__ import annotations

import pytest

from src.core.errors import EvidenceError
from src.extract.validator import (
    derive_all_evidence_spans,
    validate_record,
)
from src.models.enums import (
    DimensionObservationStatus,
    EvidenceOwnerType,
    ForgottenInfo,
    ReasonCode,
    RememberedCue,
    ScopeClass,
    ValidationState,
    Workaround,
)
from src.models.evidence import ObservedValue
from src.models.evidence_map import (
    ALL_EVIDENCE_FIELD_NAMES,
    EVIDENCE_CONTAINER_FIELDS,
    EVIDENCE_EXEMPT,
    EVIDENCE_REQUIRED,
    EXEMPT_ADDITIONS_RATIONALE,
    OBSERVATION_FIELD,
    RELEVANCE_DECISION,
    RETRIEVAL_CASE,
    SCOPE_INHERITANCE_CONDITIONS,
    STATUS_GATE,
    classify,
    exempt_fields,
    is_evidence_required,
)
from src.models.relevance import RelevanceDecision
from src.models.retrieval_case import (
    _OBSERVED_VALUE_FIELDS,
    RetrievalCase,
    dedupe_spans,
)
from tests.synthetic import (
    CASE_ID,
    DECISION_ID,
    case_scalar_spans,
    make_case,
    make_decision,
    make_observed_cue,
    make_span,
)

CONTRACTS = {
    RELEVANCE_DECISION: RelevanceDecision,
    RETRIEVAL_CASE: RetrievalCase,
}


def _field_names(model: type) -> set[str]:
    """Declared fields plus computed ones, since both are part of the contract."""
    return set(model.model_fields) | set(model.model_computed_fields)


# --------------------------------------------------------------------------- #
# Completeness (spec 15.10, ARCHITECTURE 9.5)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("contract", "model"), CONTRACTS.items())
def test_every_field_is_classified_exactly_once(contract: str, model: type) -> None:
    """The mechanism that stops a new field escaping enforcement.

    ``scope_class`` is the one field whose classification differs by contract: a
    substantive claim on ``RelevanceDecision``, an inherited validated value on
    ``RetrievalCase``. That is why the exempt set is taken per contract rather
    than globally.
    """
    required = EVIDENCE_REQUIRED[contract]
    exempt = exempt_fields(contract)

    assert not (required & exempt), sorted(required & exempt)

    unclassified = _field_names(model) - required - exempt
    assert not unclassified, (
        f"{contract} fields in neither list: {sorted(unclassified)}. Classify "
        f"them in src/models/evidence_map.py before they can be stored."
    )


@pytest.mark.parametrize(("contract", "model"), CONTRACTS.items())
def test_classify_returns_one_answer_for_every_field(
    contract: str, model: type
) -> None:
    for field_name in sorted(_field_names(model)):
        assert classify(contract, field_name)


def test_classify_rejects_an_unclassified_field() -> None:
    with pytest.raises(KeyError, match="neither"):
        classify(RETRIEVAL_CASE, "candidate_cluster")


def test_required_map_names_only_real_fields() -> None:
    """The map and the models must agree in both directions; a required field
    that does not exist would be silently unenforceable."""
    for contract, model in CONTRACTS.items():
        missing = EVIDENCE_REQUIRED[contract] - _field_names(model)
        assert not missing, f"{contract} map names absent fields {sorted(missing)}"


def test_every_addition_to_the_closed_exempt_list_has_a_rationale() -> None:
    """Spec Section 15.10's five categories do not mention these four fields, yet
    the same section requires every field to be classified. Each addition is
    named and justified rather than folded into a spec category."""
    added = (
        EVIDENCE_EXEMPT["evidence_containers"]
        | EVIDENCE_EXEMPT["inherited_validated"]
        | EVIDENCE_EXEMPT["decision_narrative"]
    )

    assert added == set(EXEMPT_ADDITIONS_RATIONALE)
    assert all(len(reason) > 40 for reason in EXEMPT_ADDITIONS_RATIONALE.values())


def test_scope_class_is_required_on_the_decision_and_exempt_on_the_case() -> None:
    assert is_evidence_required(RELEVANCE_DECISION, "scope_class")
    assert not is_evidence_required(RETRIEVAL_CASE, "scope_class")
    assert classify(RETRIEVAL_CASE, "scope_class") == "inherited_validated"


def test_every_required_field_has_a_status_entry() -> None:
    for contract, fields in EVIDENCE_REQUIRED.items():
        for field_name in fields:
            assert field_name in OBSERVATION_FIELD, f"{contract}.{field_name}"


def test_observation_fields_exist_on_the_case() -> None:
    for field_name, observation_field in OBSERVATION_FIELD.items():
        if observation_field is None:
            continue
        assert observation_field in RetrievalCase.model_fields
        assert field_name in RetrievalCase.model_fields


def test_observed_value_field_list_matches_the_model() -> None:
    """``all_evidence_spans`` iterates this tuple, so a dimension missing from it
    would silently contribute no spans to the union."""
    declared = {
        name
        for name, info in RetrievalCase.model_fields.items()
        if "ObservedValue" in str(info.annotation)
    }
    assert set(_OBSERVED_VALUE_FIELDS) == declared


def test_all_evidence_field_names_covers_both_contracts() -> None:
    assert ALL_EVIDENCE_FIELD_NAMES == (
        EVIDENCE_REQUIRED[RELEVANCE_DECISION] | EVIDENCE_REQUIRED[RETRIEVAL_CASE]
    )


# --------------------------------------------------------------------------- #
# The status gate (spec 15.10, 16.9)
# --------------------------------------------------------------------------- #


def test_every_observation_status_has_a_gate_rule() -> None:
    assert set(STATUS_GATE) == set(DimensionObservationStatus)


@pytest.mark.parametrize("status", list(DimensionObservationStatus))
def test_each_status_is_exercised_end_to_end(
    status: DimensionObservationStatus,
) -> None:
    """Every status in spec Section 16.9, run through the real gate.

    The three evidence-requiring statuses get a span; the two silent ones get
    none. A status that had no test could change meaning without anything
    noticing.
    """
    rule = STATUS_GATE[status]
    needs_value = rule.value_required

    workarounds = (
        (
            ObservedValue[Workaround](
                value=Workaround.manual_scrolling,
                evidence=make_span(
                    "workarounds",
                    "I scrolled for twenty minutes",
                    owner_type=EvidenceOwnerType.observed_value,
                ),
            ),
        )
        if needs_value
        else ()
    )
    case = make_case(workarounds=workarounds, workarounds_observation=status)

    external = list(case_scalar_spans())
    if rule.evidence_required and not workarounds:
        external.append(make_span("workarounds", "I scrolled for twenty minutes"))

    result = validate_record(case, external)

    assert result.ok, result.errors


@pytest.mark.parametrize(
    "status",
    [
        DimensionObservationStatus.explicitly_none,
        DimensionObservationStatus.uncertain,
    ],
)
def test_statuses_that_require_evidence_fail_without_it(
    status: DimensionObservationStatus,
) -> None:
    """``explicitly_none`` is the interesting one: "the user said there was none"
    is a finding in its own right and needs proof, exactly like a stated value.

    ``stated`` is absent from this parametrisation because it cannot reach the
    gate with no evidence: the value would have to be present, and for a
    multi-label dimension a present value carries its span inline. Its failure
    mode is the empty-value one, covered by
    :func:`test_a_stated_field_with_no_value_is_rejected`.
    """
    case = make_case(workarounds=(), workarounds_observation=status)

    result = validate_record(case, case_scalar_spans())

    assert not result.ok
    assert any("requires at least one valid evidence span" in e for e in result.errors)


@pytest.mark.parametrize(
    "status",
    [
        DimensionObservationStatus.not_stated,
        DimensionObservationStatus.not_applicable,
    ],
)
def test_a_silent_status_carrying_evidence_is_rejected(
    status: DimensionObservationStatus,
) -> None:
    """Spec Section 17.17. The source being silent is not something a quote can
    support, so a span here means either the status or the extraction is wrong —
    and only a human can say which, which is why it routes to review."""
    case = make_case(workarounds=(), workarounds_observation=status)
    spans = [
        *case_scalar_spans(),
        make_span("workarounds", "I scrolled for twenty minutes"),
    ]

    result = validate_record(case, spans)

    assert not result.ok
    assert ReasonCode.observation_status_conflict in result.reason_codes


def test_a_stated_field_with_no_value_is_rejected() -> None:
    with pytest.raises(Exception, match="requires a value"):
        make_case(
            outcome=None, outcome_observation=DimensionObservationStatus.stated
        )


def test_a_not_stated_field_with_a_value_is_rejected() -> None:
    with pytest.raises(Exception, match="requires .* to be empty"):
        make_case(
            reformulation_count=3,
            reformulation_count_observation=DimensionObservationStatus.not_stated,
        )


def test_zero_is_a_value_not_an_absence() -> None:
    """``reformulation_count = 0`` means the user reformulated nothing, which is
    a countable observation rather than a gap."""
    case = make_case(
        reformulation_count=0,
        reformulation_count_observation=DimensionObservationStatus.stated,
    )
    spans = [
        *case_scalar_spans(),
        make_span("reformulation_count", "I searched for cake"),
    ]

    assert validate_record(case, spans).ok


def test_not_stated_and_explicitly_none_produce_different_gate_outcomes() -> None:
    """The two statuses must not be interchangeable anywhere, including here:
    one forbids evidence and the other requires it."""
    silent = STATUS_GATE[DimensionObservationStatus.not_stated]
    affirmed = STATUS_GATE[DimensionObservationStatus.explicitly_none]

    assert silent.evidence_must_be_empty and not silent.evidence_required
    assert affirmed.evidence_required and not affirmed.evidence_must_be_empty
    assert silent.value_must_be_empty and affirmed.value_must_be_empty


# --------------------------------------------------------------------------- #
# Required-field enforcement
# --------------------------------------------------------------------------- #


def test_a_fully_evidenced_case_passes() -> None:
    result = validate_record(make_case(), case_scalar_spans())

    assert result.ok
    assert result.errors == ()


def test_removing_a_fields_evidence_fails_validation() -> None:
    """Spec Section 25: the direct statement of the required map's purpose."""
    spans = [
        span for span in case_scalar_spans() if span.field_name != "outcome"
    ]

    result = validate_record(make_case(), spans)

    assert not result.ok
    assert any(e.startswith("outcome has observation status stated") for e in result.errors)


def test_problem_summary_always_needs_evidence() -> None:
    """It has no observation status, so there is no absence for a status to
    explain: an interpretation of a user's problem is still a claim about them."""
    spans = [
        span for span in case_scalar_spans() if span.field_name != "problem_summary"
    ]

    result = validate_record(make_case(), spans)

    assert not result.ok
    assert any("problem_summary" in e for e in result.errors)


def test_an_unvalidated_span_does_not_satisfy_the_requirement() -> None:
    """"At least one *valid* span": a pending or rejected span is a claim that
    has not been checked, which is what the requirement exists to prevent."""
    spans = [
        span.model_copy(update={"validation_state": ValidationState.pending})
        for span in case_scalar_spans()
    ]

    result = validate_record(make_case(), spans)

    assert not result.ok
    assert any("none validated" in e for e in result.errors)


def test_severity_backed_only_by_an_unvalidated_span_is_rejected() -> None:
    """Spec Section 18 and risk R8: severity is the field where an unsupported
    value is a recognised temptation, so its failure carries its own reason code
    and is separately countable.

    The model already rejects a severity with *no* spans, so the remaining route
    to an unsupported rating is a span that never passed the ladder. From the
    finding's point of view the two are the same: there is no valid evidence for
    the number.
    """
    case = make_case(
        severity_evidence=(
            make_span(
                "severity",
                "I scrolled for twenty minutes",
                owner_id=CASE_ID,
                owner_type=EvidenceOwnerType.severity,
                validated=False,
            ),
        )
    )

    result = validate_record(case, case_scalar_spans())

    assert not result.ok
    assert ReasonCode.severity_without_evidence in result.reason_codes


def test_raise_for_status_surfaces_every_error() -> None:
    result = validate_record(make_case(), ())

    with pytest.raises(EvidenceError) as caught:
        result.raise_for_status()
    assert "problem_summary" in str(caught.value)


# --------------------------------------------------------------------------- #
# Spans attached to no field
# --------------------------------------------------------------------------- #


def test_a_span_attached_to_no_field_fails_validation() -> None:
    """Spec Section 15.10 consequence 2, at the record level. The model rejects
    an unknown ``field_name``; this covers a span naming a field that is real but
    not evidence-required on this contract."""
    stray = make_span("scope_class", "I spent an hour", owner_id=CASE_ID)

    result = validate_record(make_case(), [*case_scalar_spans(), stray])

    assert not result.ok
    assert any("not an evidence-required field of RetrievalCase" in e for e in result.errors)


def test_a_span_belonging_to_another_record_fails_validation() -> None:
    borrowed = make_span("outcome", "never found the", owner_id="some-other-case")

    result = validate_record(make_case(), [*case_scalar_spans(), borrowed])

    assert not result.ok
    assert any("belongs to owner" in e for e in result.errors)


# --------------------------------------------------------------------------- #
# all_evidence_spans as a derived union (spec 15.10)
# --------------------------------------------------------------------------- #


def test_all_evidence_spans_equals_the_union_of_field_level_spans() -> None:
    case = make_case()
    external = case_scalar_spans()

    union = derive_all_evidence_spans(case, external)

    expected = {span.evidence_id for span in case.inline_evidence_spans()} | {
        span.evidence_id for span in external
    }
    assert {span.evidence_id for span in union} == expected
    assert len(union) == len(expected)


def test_removing_a_fields_evidence_changes_the_union() -> None:
    """Spec Section 15.10 consequence 3, asserted directly."""
    case = make_case()
    full = derive_all_evidence_spans(case, case_scalar_spans())
    fewer = derive_all_evidence_spans(
        case, [s for s in case_scalar_spans() if s.field_name != "outcome"]
    )

    assert len(fewer) == len(full) - 1
    assert "outcome" not in {span.field_name for span in fewer}


def test_a_model_supplied_union_is_discarded() -> None:
    """The union is a convenience over field-level spans, never a substitute. A
    model could otherwise attach six plausible quotes to the case, leave every
    individual claim unevidenced, and look thoroughly sourced."""
    fabricated = make_span("outcome", "I spent an hour")
    case = make_case(all_evidence_spans=(fabricated,))

    assert fabricated.evidence_id not in {
        span.evidence_id for span in case.all_evidence_spans
    }


def test_the_union_is_deduplicated_by_evidence_id() -> None:
    span = make_span("outcome", "never found the")

    assert len(dedupe_spans([span, span, span])) == 1


def test_the_same_quote_supporting_two_fields_is_two_spans() -> None:
    """``evidence_id`` incorporates ``field_name``: collapsing them would make the
    field-level map unenforceable, because one span would satisfy two claims."""
    quote = "never found the"
    first = make_span("outcome", quote)
    second = make_span("problem_summary", quote)

    assert first.evidence_id != second.evidence_id
    assert len(dedupe_spans([first, second])) == 2


def test_inline_and_external_spans_both_enter_the_union() -> None:
    case = make_case(
        forgotten_information=(
            ObservedValue[ForgottenInfo](
                value=ForgottenInfo.exact_date,
                evidence=make_span(
                    "forgotten_information",
                    "I could not remember the exact date",
                    owner_type=EvidenceOwnerType.observed_value,
                ),
            ),
        ),
        forgotten_information_observation=DimensionObservationStatus.stated,
    )

    union = derive_all_evidence_spans(case, case_scalar_spans())
    fields = {span.field_name for span in union}

    assert {"remembered_cues", "forgotten_information", "severity"} <= fields
    assert {"known_item_status", "outcome", "problem_summary"} <= fields


def test_forgotten_information_is_not_inferred_from_silence() -> None:
    """Spec Section 17.5. The default is silence, it carries no evidence, and it
    is a different record from "the user said they forgot nothing"."""
    silent = make_case()

    assert silent.forgotten_information == ()
    assert silent.forgotten_information_observation is (
        DimensionObservationStatus.not_stated
    )
    assert "forgotten_information" not in {
        span.field_name for span in derive_all_evidence_spans(silent, case_scalar_spans())
    }
    assert validate_record(silent, case_scalar_spans()).ok


# --------------------------------------------------------------------------- #
# RelevanceDecision through the same gate
# --------------------------------------------------------------------------- #


def test_relevance_decision_passes_the_gate_with_its_inline_evidence() -> None:
    result = validate_record(make_decision())

    assert result.ok
    assert {span.field_name for span in result.all_evidence_spans} == {"scope_class"}


def test_out_of_scope_decision_is_gated_the_same_way() -> None:
    decision = make_decision(
        scope_class=ScopeClass.out_of_scope,
        reason_code=ReasonCode.billing_or_subscription,
        evidence=(
            make_span(
                "scope_class",
                "I spent an hour",
                owner_id=DECISION_ID,
                owner_type=EvidenceOwnerType.relevance_decision,
            ),
        ),
    )

    assert validate_record(decision).ok


def test_a_technically_failed_decision_is_exempt_from_the_gate() -> None:
    """Invariant I15: no decision was produced, so there is no claim to support.
    Requiring evidence here would turn a provider outage into a validation
    failure and then into an exclusion."""
    from src.models.enums import DecisionTechnicalState

    decision = make_decision(
        scope_class=None,
        technical_state=DecisionTechnicalState.provider_unavailable,
        reason_code=ReasonCode.provider_unavailable,
        confidence=None,
        evidence=(),
        needs_human_review=True,
    )

    result = validate_record(decision)

    assert result.ok
    assert result.all_evidence_spans == ()


def test_an_unknown_contract_is_a_type_error_not_a_silent_pass() -> None:
    """An empty required set would disable enforcement for a record type the
    validator does not recognise, which is the worst possible default."""
    with pytest.raises(TypeError, match="no evidence map entry"):
        validate_record(make_observed_cue())  # type: ignore[arg-type]


def test_the_two_evidence_containers_are_exempt_without_a_condition() -> None:
    """R6, as data rather than as a comment.

    ``evidence`` and ``severity_evidence`` hold spans; they make no claim of
    their own. Requiring evidence for them would be recursive — the span
    supporting ``severity_evidence`` would itself need a span — so their
    exemption is unconditional, unlike ``scope_class``, whose exemption depends
    on a real inheritance.
    """
    assert EVIDENCE_CONTAINER_FIELDS == frozenset({"evidence", "severity_evidence"})

    for container in EVIDENCE_CONTAINER_FIELDS:
        assert classify(RETRIEVAL_CASE, container) == "evidence_containers"
        assert classify(RELEVANCE_DECISION, container) == "evidence_containers"
        assert not is_evidence_required(RETRIEVAL_CASE, container)
        assert container in EXEMPT_ADDITIONS_RATIONALE
        assert container in EVIDENCE_EXEMPT["evidence_containers"]


def test_the_scope_class_exemption_records_what_it_depends_on() -> None:
    """The exemption and its conditions live beside each other so a reader who
    finds one cannot miss the other."""
    assert len(SCOPE_INHERITANCE_CONDITIONS) == 3
    assert classify(RETRIEVAL_CASE, "scope_class") == "inherited_validated"
    assert is_evidence_required(RELEVANCE_DECISION, "scope_class")
    assert "SCOPE_INHERITANCE_CONDITIONS" in EXEMPT_ADDITIONS_RATIONALE["scope_class"]


def test_the_reason_summary_rationale_states_it_is_not_a_substitute() -> None:
    assert classify(RELEVANCE_DECISION, "reason_summary") == "decision_narrative"
    rationale = EXEMPT_ADDITIONS_RATIONALE["reason_summary"]
    assert "never displayed in quotation marks" in rationale
    assert "never stand in for evidence" in rationale


def test_the_record_level_validation_state_is_classified_as_exempt() -> None:
    """The field added for the invalidation chain is state, not a claim, so the
    completeness test needed it on the exempt side rather than the required
    one."""
    for contract in (RELEVANCE_DECISION, RETRIEVAL_CASE):
        assert classify(contract, "validation_state") == "uncertainty_metadata"
        assert classify(contract, "needs_human_review") == "uncertainty_metadata"
        assert not is_evidence_required(contract, "validation_state")


def test_the_gate_still_holds_for_a_record_rebuilt_without_validation() -> None:
    """Defence in depth for the store layer.

    ``model_construct`` skips validation, which is how a persistence layer
    rehydrates rows it believes it already checked. If the value half of the gate
    lived only on the model, a corrupted row would then sail through the
    validator, so :func:`validate_record` re-applies it rather than assuming.
    """
    valid = make_case()

    stated_but_empty = RetrievalCase.model_construct(
        **{**valid.__dict__, "outcome": None}
    )
    silent_but_valued = RetrievalCase.model_construct(
        **{
            **valid.__dict__,
            "workarounds_observation": DimensionObservationStatus.not_stated,
            "reformulation_count": 4,
            "reformulation_count_observation": DimensionObservationStatus.not_stated,
        }
    )

    first = validate_record(stated_but_empty, case_scalar_spans())
    assert not first.ok
    assert any("requires a value" in e for e in first.errors)

    second = validate_record(silent_but_valued, case_scalar_spans())
    assert not second.ok
    assert any("requires an empty value" in e for e in second.errors)
    assert ReasonCode.observation_status_conflict in second.reason_codes


def test_raise_for_status_is_silent_when_validation_passed() -> None:
    validate_record(make_case(), case_scalar_spans()).raise_for_status()


def test_cue_dimension_rejects_a_value_from_another_vocabulary() -> None:
    with pytest.raises(Exception):
        ObservedValue[RememberedCue](
            value=ForgottenInfo.exact_date,
            evidence=make_span(
                "remembered_cues",
                "last summer",
                owner_type=EvidenceOwnerType.observed_value,
            ),
        )
