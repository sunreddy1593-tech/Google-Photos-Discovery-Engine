"""Span validation tests (spec Section 25 "Evidence", ARCHITECTURE Section 9.3).

The ladder has four rungs and each one is a decision about how much benefit of
the doubt a model gets. These tests pin all four, and the fourth is the one that
matters most: a quote that does not occur in the document is rejected, not
rounded to the nearest sentence.
"""

from __future__ import annotations

import io
import json
import logging

import pytest
from pydantic import ValidationError

from src.core.errors import EvidenceError
from src.core.logging import LOGGER_NAMESPACE, configure_logging
from src.extract.validator import (
    _REVIEW_PRIORITY,
    RecordValidation,
    SpanValidation,
    derive_all_evidence_spans,
    gate_for_analysis,
    select_valid_for_analysis,
    validate_record,
    validate_span,
    validate_spans,
)
from src.models.enums import (
    REVIEW_REASON_CODES,
    DimensionObservationStatus,
    EvidenceOwnerType,
    OffsetState,
    ReasonCode,
    RedactionType,
    ScopeClass,
    ValidationState,
)
from src.models.document_derived import RedactionSpan
from src.models.evidence import EvidenceSpan
from src.models.evidence_map import (
    ALL_EVIDENCE_FIELD_NAMES,
    ALL_EXEMPT_FIELD_NAMES,
    EVIDENCE_CONTAINER_FIELDS,
    SCOPE_INHERITANCE_CONDITIONS,
)
from src.models.export import ExportedEvidenceSpan
from src.models.retrieval_case import RetrievalCase, dedupe_spans
from tests.synthetic import (
    CASE_ID,
    DECISION_ID,
    EMAIL_END,
    EMAIL_START,
    RAW_TEXT,
    RAW_TEXT_AUDIT,
    REDACTIONS,
    case_scalar_spans,
    make_case,
    make_decision,
    make_span,
    offsets_of,
)

#: A short text with one repeated phrase, for the ambiguity rungs. Kept separate
#: from the main fixture so the repetition is obviously deliberate.
REPEATED = (
    "I searched for the cake photo and found nothing. "
    "Later I searched for the cake photo again and gave up."
)


def _unvalidated(quote: str, **overrides: object):  # type: ignore[no-untyped-def]
    """A pending span, which is what a model response produces."""
    return make_span(
        "outcome",
        quote,
        validated=False,
        **overrides,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- #
# Rung 1 — exact match
# --------------------------------------------------------------------------- #


def test_exact_quote_and_offsets_validate() -> None:
    span = _unvalidated("never found the")

    result = validate_span(span, RAW_TEXT)

    assert result.ok
    assert result.span.validation_state is ValidationState.valid
    assert result.span.offset_state is OffsetState.supplied_exact
    assert not result.span.repair_applied
    assert RAW_TEXT[result.span.start_char : result.span.end_char] == span.quote


def test_span_validates_against_the_length_preserving_audit_text() -> None:
    """ARCHITECTURE Section 9.2: one coordinate space, two texts. This is the
    property that lets the same span be checked locally, sent to a provider, and
    shown to an evaluator without three offset systems."""
    span = _unvalidated("never found the")

    assert validate_span(span, RAW_TEXT).ok
    assert validate_span(span, RAW_TEXT_AUDIT).ok
    assert len(RAW_TEXT_AUDIT) == len(RAW_TEXT)


# --------------------------------------------------------------------------- #
# Rung 4 — fabrication (tested early because it is the point)
# --------------------------------------------------------------------------- #


def test_fabricated_quote_is_rejected() -> None:
    """A paraphrase that "nearly" matches is exactly the failure spec Section 17
    exists to prevent, so rung 4 is unforgiving by design."""
    span = _unvalidated(
        "I looked everywhere for the birthday picture", with_offsets=False
    )

    result = validate_span(span, RAW_TEXT)

    assert not result.ok
    assert result.span.validation_state is ValidationState.rejected
    assert result.reason_code is ReasonCode.evidence_validation_failed
    assert "fabrication" in result.message


def test_paraphrase_of_real_text_is_still_rejected() -> None:
    """The dangerous case: every word appears in the document, in a different
    order. Substring matching rejects it; a bag-of-words check would not."""
    span = _unvalidated("the photo of my sister was never found", with_offsets=False)

    assert not validate_span(span, RAW_TEXT).ok


def test_rejected_span_is_returned_rather_than_dropped() -> None:
    """A rejected span is the evidence that a fabrication was caught; deleting it
    would erase the only record that the model claimed something untrue."""
    span = _unvalidated("entirely invented sentence", with_offsets=False)

    result = validate_span(span, RAW_TEXT)

    assert result.span.quote == "entirely invented sentence"
    assert result.span.validation_state is ValidationState.rejected


# --------------------------------------------------------------------------- #
# Rung 2 — offset repair
# --------------------------------------------------------------------------- #


def test_wrong_offsets_with_a_unique_quote_are_repaired() -> None:
    start, end = offsets_of("never found the")
    span = _unvalidated("never found the", start_char=3, end_char=3 + len("never found the"))

    result = validate_span(span, RAW_TEXT)

    assert result.ok
    assert result.span.offset_state is OffsetState.repaired_unique
    assert result.span.repair_applied
    assert (result.span.start_char, result.span.end_char) == (start, end)


def test_missing_offsets_with_a_unique_occurrence_are_recovered() -> None:
    span = _unvalidated("never found the", with_offsets=False)

    result = validate_span(span, RAW_TEXT)

    assert result.ok
    assert result.span.offset_state is OffsetState.repaired_unique
    assert (result.span.start_char, result.span.end_char) == offsets_of(
        "never found the"
    )


def test_duplicate_occurrence_with_a_positional_hint_picks_the_nearest() -> None:
    """Spec Section 26.3: a hint makes the choice non-arbitrary, and
    ``repair_applied`` records that a choice was made at all."""
    second = REPEATED.index("searched for the cake photo", 40)
    span = _unvalidated(
        "searched for the cake photo", start_char=second + 2, end_char=second + 29
    )

    result = validate_span(span, REPEATED)

    assert result.ok
    assert result.span.offset_state is OffsetState.repaired_nearest
    assert result.span.repair_applied
    assert result.span.start_char == second


def test_duplicate_occurrence_without_a_hint_is_left_unresolved() -> None:
    """The deliberate gap. Picking the first occurrence would be arbitrary, and an
    arbitrary offset that validates is worse than a visible gap because it looks
    verified (spec Section 26.3)."""
    span = _unvalidated("searched for the cake photo", with_offsets=False)

    result = validate_span(span, REPEATED)

    assert not result.ok
    assert result.span.offset_state is OffsetState.ambiguous_tied
    assert result.span.start_char is None
    assert result.span.validation_state is ValidationState.pending
    assert result.reason_code is ReasonCode.evidence_offsets_unresolved
    assert not result.span.repair_applied


def test_unresolved_span_is_not_rejected_as_fabrication() -> None:
    """Ambiguity and invention are different failures with different remedies:
    one needs a human to choose, the other needs the claim withdrawn."""
    result = validate_span(
        _unvalidated("searched for the cake photo", with_offsets=False), REPEATED
    )

    assert result.span.validation_state is not ValidationState.rejected
    assert result.reason_code is not ReasonCode.evidence_validation_failed


# --------------------------------------------------------------------------- #
# Rung 3 — whitespace-normalised repair
# --------------------------------------------------------------------------- #


def test_whitespace_repair_preserves_the_original_displayed_text() -> None:
    """Spec Section 15.2: the normalised form is never persisted as ``quote``.

    A model that reflowed a line break into a space is describing the same text;
    storing its reflowed version would mean the evidence browser displayed
    something the document does not contain.
    """
    text = "I searched for\n   the cake photo and gave up."
    span = _unvalidated("searched for the cake photo", with_offsets=False)

    result = validate_span(span, text)

    assert result.ok
    assert result.span.offset_state is OffsetState.repaired_whitespace
    assert result.span.repair_applied
    assert result.span.quote == "searched for\n   the cake photo"
    assert text[result.span.start_char : result.span.end_char] == result.span.quote


def test_whitespace_repair_round_trips_through_the_document() -> None:
    """The invariant that makes a repair trustworthy: after repair, the stored
    quote is still an exact substring at the stored offsets.

    Re-validating keeps ``repaired_whitespace`` rather than resetting to
    ``supplied_exact``. The repair record is what an auditor filters on, and a
    second validation pass must not quietly launder it.
    """
    text = "The photo\tof my  sister is missing."
    result = validate_span(
        _unvalidated("photo of my sister", with_offsets=False), text
    )

    assert result.ok
    assert text[result.span.start_char : result.span.end_char] == result.span.quote

    revalidated = validate_span(result.span, text)
    assert revalidated.ok
    assert revalidated.span.offset_state is OffsetState.repaired_whitespace
    assert revalidated.span.repair_applied


def test_ambiguous_whitespace_repair_is_also_left_unresolved() -> None:
    text = "searched for\nthe cake photo, then searched for  the cake photo."
    result = validate_span(
        _unvalidated("searched for the cake photo", with_offsets=False), text
    )

    assert not result.ok
    assert result.span.offset_state is OffsetState.ambiguous_tied


# --------------------------------------------------------------------------- #
# Redaction overlap (ARCHITECTURE 9.2)
# --------------------------------------------------------------------------- #


def test_span_overlapping_a_redaction_is_rejected() -> None:
    """Evidence must never depend on personal data. A validation rule, not a
    display rule: the span is rejected even though it matches exactly."""
    quote = RAW_TEXT_AUDIT[EMAIL_START - 12 : EMAIL_END]
    span = make_span("outcome", quote, text=RAW_TEXT_AUDIT, validated=False)

    result = validate_span(span, RAW_TEXT_AUDIT, REDACTIONS)

    assert not result.ok
    assert result.span.validation_state is ValidationState.rejected
    assert "redacted region" in result.message


def test_span_adjacent_to_a_redaction_is_accepted() -> None:
    """Half-open intervals: a span ending exactly where a mask begins touches no
    personal data, and rejecting it would make ordinary evidence unusable."""
    quote = RAW_TEXT_AUDIT[EMAIL_START - 12 : EMAIL_START]
    span = make_span("outcome", quote, text=RAW_TEXT_AUDIT, validated=False)

    assert validate_span(span, RAW_TEXT_AUDIT, REDACTIONS).ok


def test_redaction_spans_may_be_supplied_as_model_objects() -> None:
    redaction = RedactionSpan(
        start_char=EMAIL_START,
        end_char=EMAIL_END,
        redaction_type=RedactionType.email,
        detector_version="1.0.0",
    )
    quote = RAW_TEXT_AUDIT[EMAIL_START : EMAIL_END]
    span = make_span("outcome", quote, text=RAW_TEXT_AUDIT, validated=False)

    result = validate_span(span, RAW_TEXT_AUDIT, (redaction,))

    assert not result.ok


def test_repaired_offsets_are_still_checked_against_redactions() -> None:
    """The check runs after the ladder resolves offsets, so a repair cannot walk
    a span into a masked region unnoticed."""
    quote = RAW_TEXT_AUDIT[EMAIL_START : EMAIL_END]
    span = make_span(
        "outcome",
        quote,
        text=RAW_TEXT_AUDIT,
        validated=False,
        start_char=0,
        end_char=len(quote),
    )

    assert not validate_span(span, RAW_TEXT_AUDIT, REDACTIONS).ok


# --------------------------------------------------------------------------- #
# Identity and batching
# --------------------------------------------------------------------------- #


def test_repair_rederives_the_evidence_id() -> None:
    """Spec Section 26.1 builds ``evidence_id`` from the offsets, so a repaired
    span keeping its old id would be unfindable from its stored coordinates."""
    span = _unvalidated("never found the", start_char=0, end_char=15)

    result = validate_span(span, RAW_TEXT)

    assert result.ok
    assert result.span.evidence_id != span.evidence_id


def test_validate_spans_preserves_order_and_independence() -> None:
    spans = [
        _unvalidated("never found the"),
        _unvalidated("wholly invented", with_offsets=False),
        _unvalidated("I spent an hour"),
    ]

    results = validate_spans(spans, RAW_TEXT)

    assert [result.ok for result in results] == [True, False, True]
    assert isinstance(results[0], SpanValidation)


def test_validation_does_not_mutate_the_input_span() -> None:
    """Records are frozen and the validator returns copies; a validator that
    edited in place would make the pre-validation state unrecoverable."""
    span = _unvalidated("never found the", start_char=0, end_char=15)

    validate_span(span, RAW_TEXT)

    assert span.start_char == 0
    assert span.validation_state is ValidationState.pending


def test_evidence_error_is_a_validation_error() -> None:
    """Fabricated evidence is a contract failure, not a separate category, so a
    caller that catches ``ValidationError`` catches it too."""
    from src.core.errors import ValidationError

    assert issubclass(EvidenceError, ValidationError)


def test_severity_span_validates_like_any_other() -> None:
    """No field gets a softer check because its value is inconvenient to
    evidence (spec Section 18)."""
    span = make_span(
        "severity",
        "I scrolled for twenty minutes",
        owner_id=CASE_ID,
        owner_type=EvidenceOwnerType.severity,
        validated=False,
    )

    assert validate_span(span, RAW_TEXT).ok


def test_ambiguous_whitespace_repair_with_a_hint_picks_the_nearest() -> None:
    """The whitespace rung honours a positional hint for the same reason the
    exact rung does: a hint makes the choice the model's, not the validator's."""
    text = "searched for\nthe cake photo, then searched for  the cake photo."
    second = text.rindex("searched for")
    span = _unvalidated(
        "searched for the cake photo", start_char=second, end_char=second + 30
    )

    result = validate_span(span, text)

    assert result.ok
    assert result.span.offset_state is OffsetState.repaired_whitespace
    assert result.span.start_char == second


def test_span_validation_reports_whether_a_repair_happened() -> None:
    """``SpanValidation.repaired`` is what the Phase 5 report counts, so the two
    rungs that move offsets have to be distinguishable from the one that does
    not."""
    untouched = validate_span(_unvalidated("never found the"), RAW_TEXT)
    moved = validate_span(
        _unvalidated("never found the", start_char=0, end_char=15), RAW_TEXT
    )

    assert not untouched.repaired
    assert moved.repaired


@pytest.mark.parametrize("text", [RAW_TEXT, RAW_TEXT_AUDIT])
def test_a_quote_spanning_the_whole_document_validates(text: str) -> None:
    span = make_span("problem_summary", text, text=text, validated=False)

    result = validate_span(span, text)

    assert result.ok
    assert (result.span.start_char, result.span.end_char) == (0, len(text))


# --------------------------------------------------------------------------- #
# Rung 4's consequences (ARCHITECTURE 9.3: invalidate, log, review, withhold)
# --------------------------------------------------------------------------- #
#
# The ladder rejecting a span is only the first step of the chain. The rest —
# the parent record is invalidated, the failure is logged, the record enters
# review, and nothing reaches analysis until it is corrected — is what these
# tests pin, because each leg is a place the chain could quietly stop.


def _rejected_span(field_name: str = "outcome") -> EvidenceSpan:
    """A span the ladder has actually rejected, not one hand-labelled rejected."""
    result = validate_span(
        make_span(
            field_name,
            "the app crashed on launch",
            validated=False,
            with_offsets=False,
        ),
        RAW_TEXT,
    )
    assert not result.ok
    assert result.span.validation_state is ValidationState.rejected
    return result.span


def test_a_rejected_span_invalidates_the_record_it_belongs_to() -> None:
    """The record, not merely the field.

    ``outcome`` here also carries a perfectly good span, so a field-level check
    alone would pass this record: one claim is properly evidenced and one quote
    is invented. Persisting that as valid would put a fabrication into the
    corpus wearing the same badge as verified evidence.
    """
    case = make_case()

    result = validate_record(case, (*case_scalar_spans(), _rejected_span()))

    assert not result.ok
    assert result.review_reason_code is ReasonCode.evidence_validation_failed
    assert any("rejected by the validation ladder" in e for e in result.errors)


def test_an_unresolved_span_invalidates_the_record_with_its_own_code() -> None:
    """A tied quote is not a fabrication and must not be filed as one.

    The distinction is the whole point of spec Section 26.3: the quote is real,
    the position is unknowable, and the review a human has to do is different in
    each case.
    """
    tied = validate_span(
        make_span(
            "outcome",
            "searched for the cake photo",
            text=REPEATED,
            validated=False,
            with_offsets=False,
        ),
        REPEATED,
    ).span
    assert tied.offset_state is OffsetState.ambiguous_tied

    result = validate_record(make_case(), (*case_scalar_spans(), tied))

    assert not result.ok
    assert result.review_reason_code is ReasonCode.evidence_offsets_unresolved
    assert any("unresolved offsets" in e for e in result.errors)


def test_a_span_that_never_went_up_the_ladder_is_not_evidence() -> None:
    """``pending`` with usable offsets is the shape of a span straight out of a
    model response. It looks complete, which is exactly why an unchecked span
    must not count towards a field's evidence."""
    unchecked = make_span("outcome", "I spent an hour looking", validated=False)
    assert unchecked.validation_state is ValidationState.pending

    result = validate_record(make_case(), (*case_scalar_spans(), unchecked))

    assert not result.ok
    assert any("has not been through the validation ladder" in e for e in result.errors)


def test_a_fabrication_outranks_other_findings_when_filing_for_review() -> None:
    """A record can fail several ways at once; the queue files it under one.

    A fabricated quote stays the headline whatever else is wrong, because a
    status conflict is a bookkeeping error and an invented quote is not.
    """
    case = RetrievalCase.model_construct(
        **{
            **make_case().__dict__,
            "reformulation_count": 4,
            "reformulation_count_observation": DimensionObservationStatus.not_stated,
        }
    )

    result = validate_record(case, (*case_scalar_spans(), _rejected_span()))

    assert ReasonCode.observation_status_conflict in result.reason_codes
    assert result.review_reason_code is ReasonCode.evidence_validation_failed


def test_every_code_the_validator_emits_has_a_review_priority() -> None:
    """Otherwise a new failure mode falls through to "whichever code came
    first", which is the arbitrary filing the priority list exists to avoid."""
    emitted = {
        ReasonCode.evidence_validation_failed,
        ReasonCode.evidence_offsets_unresolved,
        ReasonCode.severity_without_evidence,
        ReasonCode.observation_status_conflict,
    }

    assert emitted.issubset(set(_REVIEW_PRIORITY))
    assert set(_REVIEW_PRIORITY).issubset(REVIEW_REASON_CODES)


def test_an_unranked_code_still_files_rather_than_vanishing() -> None:
    """The fallback exists so a code added without a priority produces a wrong
    filing rather than no filing; a review item with no reason is unactionable."""
    result = RecordValidation(
        ok=False,
        errors=("something new went wrong",),
        reason_codes=(ReasonCode.repair_ladder_exhausted,),
    )

    assert result.review_reason_code is ReasonCode.repair_ladder_exhausted


def test_an_invalidated_record_is_routed_to_review() -> None:
    result = validate_record(make_case(), (*case_scalar_spans(), _rejected_span()))

    assert result.requires_review
    assert result.review_reason_code in REVIEW_REASON_CODES


def test_a_clean_record_is_not_routed_to_review() -> None:
    result = validate_record(make_case(), case_scalar_spans())

    assert result.ok
    assert not result.requires_review
    assert result.review_reason_code is None


def test_the_failure_is_logged_with_the_fields_a_report_filters_on() -> None:
    """Section 29.14 wants failures logged; Section 28 wants them countable.

    Asserting on the parsed JSON rather than the message text is deliberate: a
    report filters on ``review_reason_code``, so that key existing is the actual
    requirement, and a test matching prose would pass while the key was missing.
    """
    stream = io.StringIO()
    configure_logging(stream=stream)
    try:
        validate_record(make_case(), (*case_scalar_spans(), _rejected_span()))
    finally:
        logging.getLogger(LOGGER_NAMESPACE).handlers.clear()

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(lines) == 1
    entry = lines[0]
    assert entry["level"] == "WARNING"
    assert entry["review_reason_code"] == ReasonCode.evidence_validation_failed.value
    assert entry["requires_review"] is True
    assert entry["owner_id"] == CASE_ID
    assert entry["contract"] == "RetrievalCase"
    assert entry["error_count"] >= 1


def test_a_passing_record_logs_nothing() -> None:
    """A warning per valid record would bury the failures in the noise."""
    stream = io.StringIO()
    configure_logging(stream=stream)
    try:
        validate_record(make_case(), case_scalar_spans())
    finally:
        logging.getLogger(LOGGER_NAMESPACE).handlers.clear()

    assert stream.getvalue() == ""


def test_analysis_cannot_obtain_evidence_from_an_invalidated_record() -> None:
    """The last leg: no processed or analysis output until it is corrected."""
    with pytest.raises(EvidenceError, match="failed evidence validation"):
        gate_for_analysis(make_case(), (*case_scalar_spans(), _rejected_span()))


def test_the_gate_returns_the_evidence_union_for_a_valid_record() -> None:
    """The gate returns the spans rather than a boolean, so analysis code cannot
    get its evidence without passing through it."""
    case = make_case()

    spans = gate_for_analysis(case, case_scalar_spans())

    assert spans == derive_all_evidence_spans(case, case_scalar_spans())
    assert all(span.is_valid for span in spans)


def test_the_invalid_candidate_is_retained_for_review() -> None:
    """Spec Section 29.12 forbids silently rewriting a value, and a rejection
    with no surviving candidate is the same loss by a different route: a reviewer
    would be told a field failed without being shown what the model offered."""
    fabricated = _rejected_span()

    result = validate_record(make_case(), (*case_scalar_spans(), fabricated))

    assert fabricated.evidence_id in {s.evidence_id for s in result.retained_spans}
    retained = next(
        s for s in result.retained_spans if s.evidence_id == fabricated.evidence_id
    )
    assert retained.quote == "the app crashed on launch"
    assert retained.validation_state is ValidationState.rejected
    assert "outcome" in result.invalid_fields


def test_the_ladder_keeps_the_candidate_exactly_as_it_arrived() -> None:
    """A whitespace repair rewrites the quote and moves the offsets, both
    legitimately. Without the original there is no way to see what was
    repaired, which makes the repair rate unauditable."""
    text = "I searched for\nthe cake photo."
    claimed = make_span(
        "outcome",
        "searched for the cake photo",
        text=text,
        validated=False,
        with_offsets=False,
    )

    result = validate_span(claimed, text)

    assert result.ok
    assert result.span.quote == "searched for\nthe cake photo"
    assert result.original is claimed
    assert result.original.quote == "searched for the cake photo"
    assert result.original.start_char is None


def test_dedupe_keeps_the_rejected_twin_not_the_valid_one() -> None:
    """``evidence_id`` is derived from the quote and offsets, so a span that was
    validated twice with different outcomes collides with itself.

    Keeping whichever arrived first deleted the fabrication whenever a valid
    twin happened to be stored ahead of it, and the union then reported the
    record as fully evidenced — field-dropping through a helper nobody suspects.
    """
    good = make_span("outcome", "never found the")
    bad = make_span(
        "outcome", "never found the", validation_state=ValidationState.rejected
    )
    assert good.evidence_id == bad.evidence_id

    assert dedupe_spans([good, bad])[0].validation_state is ValidationState.rejected
    assert dedupe_spans([bad, good])[0].validation_state is ValidationState.rejected


def test_no_invalid_candidate_appears_in_a_valid_output_query() -> None:
    """The analysis dataset is a query over ``validation_state``, so an
    invalidated record has to be absent from it rather than merely flagged."""
    clean = validate_record(make_case(), case_scalar_spans()).apply(make_case())
    poisoned_result = validate_record(
        make_case(), (*case_scalar_spans(), _rejected_span())
    )
    poisoned = poisoned_result.apply(make_case())

    assert clean.validation_state is ValidationState.valid
    assert poisoned.validation_state is ValidationState.pending
    assert poisoned.needs_human_review

    visible = select_valid_for_analysis([clean, poisoned])

    assert visible == (clean,)


def test_a_record_cannot_be_marked_valid_while_holding_a_bad_span() -> None:
    """The model-level half of the gate, so a store that skips the validator
    still cannot write a valid record over invalid evidence."""
    case = make_case()
    bad_severity = (
        make_span(
            "severity",
            "I scrolled for twenty minutes",
            owner_type=EvidenceOwnerType.severity,
            validation_state=ValidationState.rejected,
        ),
    )

    with pytest.raises(ValidationError, match="only as valid as the evidence"):
        make_case(
            severity_evidence=bad_severity,
            validation_state=ValidationState.valid,
        )

    assert make_case(
        severity_evidence=bad_severity,
        validation_state=ValidationState.pending,
    ).validation_state is ValidationState.pending
    assert case.validation_state is ValidationState.pending


def test_a_decision_cannot_be_marked_valid_while_holding_a_bad_span() -> None:
    with pytest.raises(ValidationError, match="not a decision"):
        make_decision(
            evidence=(
                make_span(
                    "scope_class",
                    "I could not remember the exact date",
                    owner_id=DECISION_ID,
                    owner_type=EvidenceOwnerType.relevance_decision,
                    validation_state=ValidationState.rejected,
                ),
            ),
            validation_state=ValidationState.valid,
        )


def test_records_default_to_pending_rather_than_valid() -> None:
    """A record is unchecked until the validator checks it. Defaulting to valid
    would mean anything that never reached the gate is indistinguishable from
    something that passed it."""
    assert make_case().validation_state is ValidationState.pending
    assert make_decision().validation_state is ValidationState.pending


def test_correcting_the_fabrication_reopens_the_gate() -> None:
    """"Until corrected" has to mean something: the same record with the
    fabricated span removed passes, so review is a route back in rather than a
    permanent quarantine."""
    case = make_case()
    poisoned = (*case_scalar_spans(), _rejected_span())

    with pytest.raises(EvidenceError):
        gate_for_analysis(case, poisoned)

    corrected = tuple(span for span in poisoned if span.is_valid)
    assert gate_for_analysis(case, corrected)


# --------------------------------------------------------------------------- #
# Inherited scope_class (spec 15.4) and the paraphrase exemptions (15.10)
# --------------------------------------------------------------------------- #
#
# RetrievalCase.scope_class is evidence-exempt because it is inherited from a
# decision that already evidenced it. That exemption is only honest while the
# inheritance is real, so these tests pin the three conditions.


def _valid_decision(**overrides: object):  # type: ignore[no-untyped-def]
    """A decision that has passed the gate, so it has evidence to lend."""
    decision = make_decision(**overrides)
    return validate_record(decision).apply(decision)


def test_a_case_inherits_scope_class_from_a_matching_valid_decision() -> None:
    result = validate_record(
        make_case(), case_scalar_spans(), decision=_valid_decision()
    )

    assert result.ok


def test_a_case_may_not_inherit_a_scope_class_from_another_document() -> None:
    """A decision about a different document is borrowing a verdict, not
    inheriting one."""
    other_doc_id = "reddit-0000000000-999999"
    elsewhere = make_decision(
        doc_id=other_doc_id,
        evidence=(
            make_span(
                "scope_class",
                "I could not remember the exact date",
                doc_id=other_doc_id,
                owner_id=DECISION_ID,
                owner_type=EvidenceOwnerType.relevance_decision,
            ),
        ),
    )
    other_doc = validate_record(elsewhere).apply(elsewhere)

    result = validate_record(make_case(), case_scalar_spans(), decision=other_doc)

    assert not result.ok
    assert "scope_class" in result.invalid_fields
    assert any("another document" in e for e in result.errors)


def test_a_mismatched_inherited_scope_class_is_rejected() -> None:
    """A case claiming in-scope under an out-of-scope decision is overruling it,
    and would inflate the in-scope count with excluded documents."""
    excluded = make_decision(
        scope_class=ScopeClass.out_of_scope,
        reason_code=ReasonCode.storage_backup_or_sync,
    )
    decision = validate_record(excluded).apply(excluded)

    result = validate_record(make_case(), case_scalar_spans(), decision=decision)

    assert not result.ok
    assert "scope_class" in result.invalid_fields
    assert any("never overrule" in e for e in result.errors)


def test_a_case_may_not_inherit_from_an_unvalidated_decision() -> None:
    """A pending decision has no validated evidence to lend, so inheriting from
    it manufactures support out of nothing."""
    result = validate_record(
        make_case(), case_scalar_spans(), decision=make_decision()
    )

    assert not result.ok
    assert any("no validated evidence to lend" in e for e in result.errors)


def test_scope_inheritance_is_only_checked_when_the_decision_is_supplied() -> None:
    """The case contract carries no decision_id, so the validator cannot fetch
    the decision itself. Silently passing when it is absent is the honest
    behaviour; claiming to have checked would be worse than not checking."""
    assert validate_record(make_case(), case_scalar_spans()).ok
    assert len(SCOPE_INHERITANCE_CONDITIONS) == 3


def test_reason_summary_cannot_make_an_evidence_free_decision_valid() -> None:
    """R5's core: the paraphrase is exempt from needing evidence, not a
    substitute for it. A long, plausible summary buys nothing."""
    with pytest.raises(ValidationError, match="every decision requires evidence"):
        make_decision(
            evidence=(),
            reason_summary=(
                "The user clearly describes searching for a specific remembered "
                "photograph over an extended period and failing to find it, "
                "which places this squarely in the core scope."
            ),
        )


def test_reason_summary_cannot_rescue_a_decision_whose_only_span_is_fabricated() -> None:
    """The model-level check above only sees an empty tuple. This is the
    validator-level twin: a decision that looks evidenced and is not."""
    fabricated = validate_span(
        make_span(
            "scope_class",
            "the user gave up immediately",
            owner_id=DECISION_ID,
            owner_type=EvidenceOwnerType.relevance_decision,
            validated=False,
            with_offsets=False,
        ),
        RAW_TEXT,
    ).span
    decision = make_decision(evidence=(fabricated,))

    result = validate_record(decision)

    assert not result.ok
    assert "scope_class" in result.invalid_fields
    assert result.review_reason_code is ReasonCode.evidence_validation_failed


@pytest.mark.parametrize(
    "exempt_field", ["reason_summary", "evidence", "severity_evidence", "confidence"]
)
def test_an_exempt_field_is_never_exportable_as_a_quotation(
    exempt_field: str,
) -> None:
    """Spec Section 17.19: a paraphrase is never displayed in quotation marks.

    ``ExportedEvidenceSpan`` is what the evidence browser highlights, so a span
    admitted here is rendered as though the user wrote it. ``reason_summary`` is
    the case that matters — it is the model's own prose, and quoting it back as
    user evidence is the fabrication the architecture exists to prevent,
    arriving at the last step.
    """
    with pytest.raises(ValidationError, match="never be exported as a quotation"):
        ExportedEvidenceSpan(
            field_name=exempt_field,
            quote="The user could not find a known photo.",
            excerpt_start_char=0,
            excerpt_end_char=38,
            document_start_char=0,
            document_end_char=38,
        )


def test_problem_summary_remains_quotable_because_it_is_evidence_required() -> None:
    """A deliberate asymmetry between the two summary fields.

    ``problem_summary`` is a paraphrase *and* an evidence-required field, so its
    span quotes the source text that supports the summary — not the summary.
    ``reason_summary`` is exempt, so a span naming it could only be quoting the
    model. Hence one is exportable and the other is not.
    """
    span = ExportedEvidenceSpan(
        field_name="problem_summary",
        quote="never found the",
        excerpt_start_char=0,
        excerpt_end_char=15,
        document_start_char=0,
        document_end_char=15,
    )

    assert span.field_name in ALL_EVIDENCE_FIELD_NAMES
    assert "reason_summary" in ALL_EXEMPT_FIELD_NAMES


@pytest.mark.parametrize("container", sorted(EVIDENCE_CONTAINER_FIELDS))
def test_evidence_containers_are_never_themselves_evidence_required(
    container: str,
) -> None:
    """R6: requiring evidence for an evidence container is recursive — the span
    supporting ``severity_evidence`` would itself need a span."""
    assert container not in ALL_EVIDENCE_FIELD_NAMES
    assert container in ALL_EXEMPT_FIELD_NAMES

    with pytest.raises(ValidationError, match="not an evidence-required field"):
        make_span(container, "never found the")
