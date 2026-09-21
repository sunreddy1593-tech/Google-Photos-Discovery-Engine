"""Evidence validation: the span ladder and the record gate.

Two functions carry the project's central claim.

:func:`validate_span` decides whether one quote is real. It walks the ladder in
ARCHITECTURE Section 9.3 — exact match, offset repair, whitespace-normalised
repair, reject — and the last rung is deliberately unforgiving. A paraphrase that
"nearly" matches is the exact failure spec Section 17 exists to prevent, and it
is how a fabricated quote enters a research corpus looking sourced.

:func:`validate_record` decides whether a record's claims are each supported. It
reads the evidence map and the observation-status gate from
:mod:`src.models.evidence_map` and derives ``all_evidence_spans`` as the union of
field-level spans, rejecting any span attached to no field. Before field-level
spans existed, a model could satisfy a bulk evidence check by attaching six
plausible quotes to the case and leaving every individual claim unevidenced — the
record looked thoroughly sourced and nothing in it was traceable.

**Why these are service functions and not model validators.** Span validation
needs the parent document's text, which a Pydantic field validator cannot see.
Keeping the check in the store layer at the validity gate is why
``validation_state`` is a stored value rather than an implicit property
(IMPLEMENTATION-PLAN Phase 1 design note).

Neither function coerces. A failure returns a result carrying the reason code
that routes the record to review; nothing here quietly rewrites a value to make
it pass (spec Section 29.12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from src.models.document_derived import RedactionSpan
from src.models.enums import (
    DimensionObservationStatus,
    OffsetState,
    ReasonCode,
    ValidationState,
)
from src.models.evidence import EvidenceSpan
from src.models.evidence_map import (
    INLINE_EVIDENCE_FIELDS,
    OBSERVATION_FIELD,
    RELEVANCE_DECISION,
    RETRIEVAL_CASE,
    STATUS_GATE,
    required_fields,
)
from src.models.relevance import RelevanceDecision
from src.models.retrieval_case import RetrievalCase, dedupe_spans

_WHITESPACE_RUN = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SpanValidation:
    """Outcome of running one span up the ladder.

    ``span`` is always returned — repaired, rejected, or unchanged — because the
    caller stores it either way. A rejected span is evidence that a fabrication
    was caught, and deleting it would erase the only record that the model
    claimed something the document does not say.
    """

    span: EvidenceSpan
    ok: bool
    reason_code: ReasonCode | None = None
    message: str = ""

    @property
    def repaired(self) -> bool:
        return self.span.repair_applied


@dataclass(frozen=True, slots=True)
class RecordValidation:
    """Outcome of applying the evidence map and status gate to one record."""

    ok: bool
    all_evidence_spans: tuple[EvidenceSpan, ...] = ()
    errors: tuple[str, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()

    def raise_for_status(self) -> None:
        """Raise :class:`~src.core.errors.EvidenceError` when validation failed."""
        if self.ok:
            return
        from src.core.errors import EvidenceError

        raise EvidenceError(
            "record failed evidence validation:\n  " + "\n  ".join(self.errors)
        )


@dataclass
class _Accumulator:
    errors: list[str] = field(default_factory=list)
    reason_codes: list[ReasonCode] = field(default_factory=list)

    def fail(self, message: str, reason_code: ReasonCode) -> None:
        self.errors.append(message)
        if reason_code not in self.reason_codes:
            self.reason_codes.append(reason_code)


# --------------------------------------------------------------------------- #
# Span validation (ARCHITECTURE 9.3, spec 26.3)
# --------------------------------------------------------------------------- #


def _occurrences(haystack: str, needle: str) -> list[int]:
    """Every start offset at which ``needle`` occurs, including overlaps."""
    found: list[int] = []
    start = haystack.find(needle)
    while start != -1:
        found.append(start)
        start = haystack.find(needle, start + 1)
    return found


def _collapse_whitespace(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs, returning the collapsed text and an index map.

    ``index_map[i]`` is the offset in the original text of the character that
    produced ``collapsed[i]``. The map is what makes whitespace repair honest:
    offsets are recovered in the *original* coordinate space, and the original
    substring is what gets stored, so a model that reflowed a line break into a
    space never causes a normalized form to be persisted as a quote
    (spec Section 15.2).
    """
    collapsed: list[str] = []
    index_map: list[int] = []
    in_run = False

    for position, char in enumerate(text):
        if char.isspace():
            if not in_run:
                collapsed.append(" ")
                index_map.append(position)
                in_run = True
        else:
            collapsed.append(char)
            index_map.append(position)
            in_run = False

    return "".join(collapsed), index_map


def _overlapping_redaction(
    redactions: Sequence[RedactionSpan] | Sequence[tuple[int, int]],
    start_char: int,
    end_char: int,
) -> tuple[int, int] | None:
    """The first redacted region intersecting ``[start_char, end_char)``."""
    for entry in redactions:
        if isinstance(entry, RedactionSpan):
            bounds = (entry.start_char, entry.end_char)
        else:
            bounds = (int(entry[0]), int(entry[1]))
        if start_char < bounds[1] and end_char > bounds[0]:
            return bounds
    return None


def _rebuild(span: EvidenceSpan, **updates: object) -> EvidenceSpan:
    """Re-validate ``span`` with ``updates`` applied, re-deriving ``evidence_id``.

    ``model_copy`` alone skips validation, which would let a repair produce a span
    whose ``offset_state`` and offsets disagree — the precise inconsistency the
    model's validators exist to catch. ``evidence_id`` is cleared so it is derived
    again from the new offsets: spec Section 26.1 builds it from them, and a
    repaired span keeping its old id would be unfindable from its stored
    coordinates.
    """
    payload = span.model_dump()
    payload.update(updates)
    payload["evidence_id"] = ""
    return EvidenceSpan.model_validate(payload)


def validate_span(
    span: EvidenceSpan,
    raw_text: str,
    redaction_spans: Sequence[RedactionSpan] | Sequence[tuple[int, int]] = (),
) -> SpanValidation:
    """Run one span up the validation ladder (ARCHITECTURE Section 9.3).

    ``raw_text`` is the document's collected text or its length-preserving
    redacted twin ``raw_text_audit``; the two share one coordinate space by
    construction, which is what lets the same span validate locally and in an
    export (ARCHITECTURE Section 9.2).

    The ladder:

    1. **Exact match** at the supplied offsets — valid, ``supplied_exact``.
    2. **Offset repair.** The quote is an exact substring elsewhere. One
       occurrence repairs the offsets (``repaired_unique``); several occurrences
       with a supplied position pick the nearest (``repaired_nearest``); several
       with no positional hint are **left unresolved** (``ambiguous_tied``).
    3. **Whitespace-normalised repair.** A match ignoring whitespace runs recovers
       offsets from the original text, and the original substring is what is
       stored (``repaired_whitespace``).
    4. **Reject.** Anything else is fabrication.

    Rung 2's tie is routed to a human rather than resolved by a heuristic.
    Picking the first occurrence would be arbitrary, and an arbitrary offset that
    validates is worse than a visible gap, because it looks verified
    (spec Section 26.3).

    A span overlapping a redacted region is rejected at any rung. Evidence must
    never depend on personal data, and this is a validation rule rather than a
    display rule (ARCHITECTURE Section 9.2).
    """
    quote = span.quote

    # Rung 1 — exact match at the supplied offsets.
    if span.start_char is not None and span.end_char is not None:
        if raw_text[span.start_char : span.end_char] == quote:
            # An already-repaired span that is re-validated keeps the state that
            # records the repair. Overwriting it with ``supplied_exact`` would
            # erase the audit trail on exactly the spans an auditor looks for.
            state = (
                span.offset_state
                if span.repair_applied
                else OffsetState.supplied_exact
            )
            return _finalise(
                span,
                span.start_char,
                span.end_char,
                state,
                repair_applied=span.repair_applied,
                redactions=redaction_spans,
            )

    # Rung 2 — exact substring elsewhere in the document.
    hits = _occurrences(raw_text, quote)
    if len(hits) == 1:
        start = hits[0]
        return _finalise(
            span,
            start,
            start + len(quote),
            OffsetState.repaired_unique,
            repair_applied=True,
            redactions=redaction_spans,
        )
    if len(hits) > 1:
        if span.start_char is not None:
            start = min(hits, key=lambda h: (abs(h - span.start_char), h))
            return _finalise(
                span,
                start,
                start + len(quote),
                OffsetState.repaired_nearest,
                repair_applied=True,
                redactions=redaction_spans,
            )
        return SpanValidation(
            span=_rebuild(
                span,
                start_char=None,
                end_char=None,
                offset_state=OffsetState.ambiguous_tied,
                repair_applied=False,
                validation_state=ValidationState.pending,
            ),
            ok=False,
            reason_code=ReasonCode.evidence_offsets_unresolved,
            message=(
                f"quote occurs at {len(hits)} positions {hits} and no positional "
                f"hint was supplied; left unresolved for review rather than "
                f"guessed (spec Section 26.3)"
            ),
        )

    # Rung 3 — whitespace-normalised repair.
    collapsed_text, index_map = _collapse_whitespace(raw_text)
    collapsed_quote = _WHITESPACE_RUN.sub(" ", quote).strip()
    if collapsed_quote:
        collapsed_hits = _occurrences(collapsed_text, collapsed_quote)
        chosen: int | None = None
        if len(collapsed_hits) == 1:
            chosen = collapsed_hits[0]
        elif len(collapsed_hits) > 1 and span.start_char is not None:
            chosen = min(
                collapsed_hits,
                key=lambda h: (abs(index_map[h] - span.start_char), h),  # type: ignore[operator]
            )
        elif len(collapsed_hits) > 1:
            return SpanValidation(
                span=_rebuild(
                    span,
                    start_char=None,
                    end_char=None,
                    offset_state=OffsetState.ambiguous_tied,
                    repair_applied=False,
                    validation_state=ValidationState.pending,
                ),
                ok=False,
                reason_code=ReasonCode.evidence_offsets_unresolved,
                message=(
                    f"whitespace-normalised quote occurs at "
                    f"{len(collapsed_hits)} positions with no positional hint; "
                    f"left unresolved for review"
                ),
            )

        if chosen is not None:
            start = index_map[chosen]
            end = index_map[chosen + len(collapsed_quote) - 1] + 1
            return _finalise(
                span,
                start,
                end,
                OffsetState.repaired_whitespace,
                repair_applied=True,
                redactions=redaction_spans,
                original_substring=raw_text[start:end],
            )

    # Rung 4 — fabrication.
    return SpanValidation(
        span=_rebuild(
            span,
            validation_state=ValidationState.rejected,
            offset_state=span.offset_state,
        ),
        ok=False,
        reason_code=ReasonCode.evidence_validation_failed,
        message=(
            f"quote does not occur in the document at any offset, with or "
            f"without whitespace normalisation: {quote!r}. Rejected as "
            f"fabrication (ARCHITECTURE Section 9.3 rung 4)."
        ),
    )


def _finalise(
    span: EvidenceSpan,
    start_char: int,
    end_char: int,
    offset_state: OffsetState,
    *,
    repair_applied: bool,
    redactions: Sequence[RedactionSpan] | Sequence[tuple[int, int]],
    original_substring: str | None = None,
) -> SpanValidation:
    """Apply the redaction check, then mark the span valid at these offsets.

    ``original_substring`` is supplied by the whitespace rung: the stored quote
    becomes the text as it appears in the document, never the normalised form the
    model sent (spec Section 15.2).
    """
    overlap = _overlapping_redaction(redactions, start_char, end_char)
    if overlap is not None:
        return SpanValidation(
            span=_rebuild(span, validation_state=ValidationState.rejected),
            ok=False,
            reason_code=ReasonCode.evidence_validation_failed,
            message=(
                f"span [{start_char}, {end_char}) overlaps the redacted region "
                f"[{overlap[0]}, {overlap[1]}); evidence must never depend on "
                f"personal data (ARCHITECTURE Section 9.2)"
            ),
        )

    updates: dict[str, object] = {
        "start_char": start_char,
        "end_char": end_char,
        "offset_state": offset_state,
        "repair_applied": repair_applied,
        "validation_state": ValidationState.valid,
    }
    if original_substring is not None:
        updates["quote"] = original_substring

    return SpanValidation(span=_rebuild(span, **updates), ok=True)


def validate_spans(
    spans: Iterable[EvidenceSpan],
    raw_text: str,
    redaction_spans: Sequence[RedactionSpan] | Sequence[tuple[int, int]] = (),
) -> tuple[SpanValidation, ...]:
    """Run :func:`validate_span` over many spans, preserving order."""
    return tuple(validate_span(span, raw_text, redaction_spans) for span in spans)


# --------------------------------------------------------------------------- #
# Record validation (spec 15.10)
# --------------------------------------------------------------------------- #


def _contract_name(record: RelevanceDecision | RetrievalCase) -> str:
    if isinstance(record, RelevanceDecision):
        return RELEVANCE_DECISION
    if isinstance(record, RetrievalCase):
        return RETRIEVAL_CASE
    raise TypeError(
        f"no evidence map entry for {type(record).__name__}; only "
        f"RelevanceDecision and RetrievalCase carry evidence-required fields"
    )


def _inline_spans(record: RelevanceDecision | RetrievalCase) -> tuple[EvidenceSpan, ...]:
    """Spans the record physically holds, whichever contract it is."""
    if isinstance(record, RelevanceDecision):
        return tuple(record.evidence)
    return record.inline_evidence_spans()


def _field_value(record: RelevanceDecision | RetrievalCase, field_name: str) -> object:
    return getattr(record, field_name, None)


def _status_for(
    record: RelevanceDecision | RetrievalCase, field_name: str
) -> DimensionObservationStatus:
    """The observation status gating one field.

    Fields with no paired ``*_observation`` — ``scope_class`` and
    ``problem_summary`` — are always present on a valid record, so there is no
    absence for a status to explain and ``stated`` is the only reading.
    """
    observation_field = OBSERVATION_FIELD.get(field_name)
    if observation_field is None:
        return DimensionObservationStatus.stated
    return getattr(record, observation_field)


def derive_all_evidence_spans(
    record: RelevanceDecision | RetrievalCase,
    external_spans: Iterable[EvidenceSpan] = (),
) -> tuple[EvidenceSpan, ...]:
    """The de-duplicated union of every field-level span (spec Section 15.10).

    ``external_spans`` are the record's rows from the ``evidence_spans`` store —
    the spans for scalar fields such as ``outcome`` and ``exact_query``, which are
    not carried inline. Inline spans come first so the union is stable regardless
    of the order the store returns rows in.
    """
    return dedupe_spans((*_inline_spans(record), *external_spans))


def validate_record(
    record: RelevanceDecision | RetrievalCase,
    spans: Iterable[EvidenceSpan] = (),
) -> RecordValidation:
    """Apply the evidence map and the status gate to one record.

    ``spans`` is the record's field-level span set from the store, excluding the
    spans the record already carries inline. Three things are checked:

    1. **Every span is attached to a field this contract enforces.** A span naming
       an exempt field, a field of another contract, or a field this record does
       not populate is a contradiction (spec Section 15.10 consequence 2).
    2. **Every evidence-required field satisfies its status gate.** ``stated``,
       ``explicitly_none``, and ``uncertain`` each need at least one *valid* span;
       ``not_stated`` and ``not_applicable`` need none and must carry none.
    3. **``all_evidence_spans`` is derived**, never read from the record.

    A record whose ``technical_state`` is not ``ok`` is exempt from the gate: no
    decision was produced, so there is no claim to support, and requiring evidence
    would turn a provider outage into a validation failure (invariant I15).
    """
    contract = _contract_name(record)
    acc = _Accumulator()

    if isinstance(record, RelevanceDecision) and record.technical_state.value != "ok":
        return RecordValidation(ok=True, all_evidence_spans=())

    enforced = required_fields(contract)
    union = derive_all_evidence_spans(record, spans)

    by_field: dict[str, list[EvidenceSpan]] = {}
    for span in union:
        if span.field_name not in enforced:
            acc.fail(
                f"span {span.evidence_id} names field {span.field_name!r}, which "
                f"is not an evidence-required field of {contract}; a span "
                f"attached to no field fails validation (spec Section 15.10)",
                ReasonCode.evidence_validation_failed,
            )
            continue
        if span.owner_id != _owner_id(record):
            acc.fail(
                f"span {span.evidence_id} belongs to owner {span.owner_id!r}, not "
                f"to this {contract} ({_owner_id(record)!r})",
                ReasonCode.evidence_validation_failed,
            )
            continue
        by_field.setdefault(span.field_name, []).append(span)

    for field_name in sorted(enforced):
        status = _status_for(record, field_name)
        rule = STATUS_GATE[status]
        attached = by_field.get(field_name, [])
        valid = [span for span in attached if span.is_valid]

        if rule.evidence_required and not valid:
            detail = (
                f"{len(attached)} span(s) attached but none validated"
                if attached
                else "no span attached"
            )
            acc.fail(
                f"{field_name} has observation status {status.value}, which "
                f"requires at least one valid evidence span; {detail}",
                _missing_evidence_reason(field_name),
            )
        if rule.evidence_must_be_empty and attached:
            acc.fail(
                f"{field_name} has observation status {status.value}, which "
                f"forbids evidence; {len(attached)} span(s) are attached. The "
                f"source being silent is not something a quote can support "
                f"(spec Section 17.17)",
                ReasonCode.observation_status_conflict,
            )

        value = _field_value(record, field_name)
        if rule.value_required and _is_empty_value(value):
            acc.fail(
                f"{field_name} has observation status {status.value}, which "
                f"requires a value, but the field is empty",
                ReasonCode.observation_status_conflict,
            )
        if rule.value_must_be_empty and not _is_empty_value(value):
            acc.fail(
                f"{field_name} has observation status {status.value}, which "
                f"requires an empty value, but the field holds {value!r}",
                ReasonCode.observation_status_conflict,
            )

    return RecordValidation(
        ok=not acc.errors,
        all_evidence_spans=union,
        errors=tuple(acc.errors),
        reason_codes=tuple(acc.reason_codes),
    )


def _missing_evidence_reason(field_name: str) -> ReasonCode:
    """Reason code for a required field with no *valid* span.

    Severity gets its own code because it is the one field where an unsupported
    value is a recognised temptation, and spec Section 16.8 gives it a dedicated
    review reason so the rate is separately countable (spec Section 18, risk R8).
    Whether the span is absent or merely rejected makes no difference to the
    finding: there is no valid evidence for the severity either way.
    """
    if field_name == "severity":
        return ReasonCode.severity_without_evidence
    return ReasonCode.evidence_validation_failed


def _is_empty_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (tuple, list, str)) and len(value) == 0:
        return True
    return False


def _owner_id(record: RelevanceDecision | RetrievalCase) -> str:
    return (
        record.decision_id
        if isinstance(record, RelevanceDecision)
        else record.case_id
    )


#: Where each required field's spans live when they are not in the store. Exposed
#: so the Phase 5 persistence layer does not re-derive it.
INLINE_FIELDS = INLINE_EVIDENCE_FIELDS
