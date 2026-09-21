"""Span validation tests (spec Section 25 "Evidence", ARCHITECTURE Section 9.3).

The ladder has four rungs and each one is a decision about how much benefit of
the doubt a model gets. These tests pin all four, and the fourth is the one that
matters most: a quote that does not occur in the document is rejected, not
rounded to the nearest sentence.
"""

from __future__ import annotations

import pytest

from src.core.errors import EvidenceError
from src.extract.validator import (
    SpanValidation,
    validate_span,
    validate_spans,
)
from src.models.enums import (
    EvidenceOwnerType,
    OffsetState,
    ReasonCode,
    RedactionType,
    ValidationState,
)
from src.models.document_derived import RedactionSpan
from tests.synthetic import (
    CASE_ID,
    EMAIL_END,
    EMAIL_START,
    RAW_TEXT,
    RAW_TEXT_AUDIT,
    REDACTIONS,
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
