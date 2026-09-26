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
from dataclasses import dataclass, field, replace
from typing import Final, Iterable, Sequence, TypeVar

from src.core.logging import get_logger
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

_LOG = get_logger("extract.validator")

#: The two contracts that carry evidence-required fields, as a type variable so
#: :meth:`RecordValidation.apply` returns the contract it was given rather than
#: their union.
RecordT = TypeVar("RecordT", RelevanceDecision, RetrievalCase)

#: Offset states that mean the span has no usable coordinates. A case evidenced
#: only by these cannot be ordered, so it takes the ``#u`` identifier form and
#: never enters analysis (spec Section 26.3).
_UNRESOLVED_OFFSET_STATES: Final[frozenset[OffsetState]] = frozenset(
    {OffsetState.missing_unresolved, OffsetState.ambiguous_tied}
)


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

    ``candidate`` is the span exactly as it arrived, before any rung touched it.
    The ladder is allowed to move offsets and to replace a whitespace-normalised
    quote with the document's own characters, so ``span`` is not always what the
    model actually claimed. Keeping both means a reviewer can see the claim and
    the verdict side by side, which is the difference between an auditable
    rejection and an assertion that something was wrong.
    """

    span: EvidenceSpan
    ok: bool
    reason_code: ReasonCode | None = None
    message: str = ""
    candidate: EvidenceSpan | None = None

    @property
    def repaired(self) -> bool:
        return self.span.repair_applied

    @property
    def original(self) -> EvidenceSpan:
        """The span as received. Identical to ``span`` when no rung changed it."""
        return self.candidate if self.candidate is not None else self.span


@dataclass(frozen=True, slots=True)
class RecordValidation:
    """Outcome of applying the evidence map and status gate to one record.

    The three properties below are the rest of ARCHITECTURE Section 9.3 rung 4 —
    "the parent record is invalidated, the failure is logged, and the document
    enters the review queue" — expressed as data a later phase consumes.
    ``ok`` is the invalidation, :attr:`requires_review` is the routing decision,
    and :attr:`review_reason_code` is the code the Phase 3 queue files it under.
    Phase 1 produces the routing decision; it does not build the queue (ADR-24).
    """

    ok: bool
    all_evidence_spans: tuple[EvidenceSpan, ...] = ()
    errors: tuple[str, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    invalid_fields: tuple[str, ...] = ()
    retained_spans: tuple[EvidenceSpan, ...] = ()

    def apply(
        self, record: RecordT
    ) -> RecordT:
        """Return ``record`` marked with this outcome.

        On success the record becomes ``valid`` and is eligible for processed and
        analysis output. On failure it becomes ``pending`` — not ``rejected`` —
        and ``needs_human_review`` is set, because the record is not wrong so
        much as unconfirmed, and review is a route back in rather than a verdict
        (spec Section 19.4 step 5).

        The record is returned rather than mutated because both contracts are
        frozen, and re-validating through ``model_validate`` means a marked
        record still has to satisfy every model rule — including the one that
        refuses ``valid`` while a non-valid span is attached.
        """
        payload = record.model_dump()
        payload.pop("is_relevant", None)
        payload["validation_state"] = (
            ValidationState.valid if self.ok else ValidationState.pending
        )
        if not self.ok:
            payload["needs_human_review"] = True
        return type(record).model_validate(payload)

    @property
    def requires_review(self) -> bool:
        """Whether this record must be routed to a human before it can be used.

        Every evidence failure needs a human, so this currently tracks ``ok``
        exactly. It is a separate property rather than ``not ok`` at the call
        site because the two answer different questions — "may this be stored as
        valid" and "who has to look at it" — and Phase 3 adds review items that
        are not validation failures at all, such as a duplicate in the simhash
        review band.
        """
        return not self.ok

    @property
    def review_reason_code(self) -> ReasonCode | None:
        """The single code this record is filed under, or ``None`` if it passed.

        A failing record often collects several codes; a queue item needs one.
        The order in :data:`_REVIEW_PRIORITY` is by how badly the finding
        undermines the record: a fabricated quote is a fabrication whatever else
        is also wrong with the record, and it must not be filed as a status
        conflict just because that check happened to run first.
        """
        for candidate in _REVIEW_PRIORITY:
            if candidate in self.reason_codes:
                return candidate
        return self.reason_codes[0] if self.reason_codes else None

    def raise_for_status(self) -> None:
        """Raise :class:`~src.core.errors.EvidenceError` when validation failed."""
        if self.ok:
            return
        from src.core.errors import EvidenceError

        raise EvidenceError(
            "record failed evidence validation:\n  " + "\n  ".join(self.errors)
        )


#: Review codes in descending order of how much they invalidate a record, used to
#: pick one filing code from several findings.
_REVIEW_PRIORITY: Final[tuple[ReasonCode, ...]] = (
    ReasonCode.evidence_validation_failed,
    ReasonCode.evidence_offsets_unresolved,
    ReasonCode.severity_without_evidence,
    ReasonCode.observation_status_conflict,
)


@dataclass
class _Accumulator:
    errors: list[str] = field(default_factory=list)
    reason_codes: list[ReasonCode] = field(default_factory=list)
    invalid_fields: list[str] = field(default_factory=list)
    retained: list[EvidenceSpan] = field(default_factory=list)

    def fail(
        self,
        message: str,
        reason_code: ReasonCode,
        *,
        field_name: str | None = None,
        span: EvidenceSpan | None = None,
    ) -> None:
        """Record one failure, the field it affects, and the span that caused it.

        ``field_name`` and ``span`` are what make the failure actionable rather
        than merely reported: a reviewer needs to know which claim is
        unsupported and what the model actually offered in support of it. The
        prose message is for a human reading a log; these two are for the review
        interface and for the counts.
        """
        self.errors.append(message)
        if reason_code not in self.reason_codes:
            self.reason_codes.append(reason_code)
        if field_name is not None and field_name not in self.invalid_fields:
            self.invalid_fields.append(field_name)
        if span is not None and all(
            span.evidence_id != kept.evidence_id for kept in self.retained
        ):
            self.retained.append(span)


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
    """Run one span up the ladder, retaining the candidate as received.

    A thin wrapper over :func:`_run_ladder` so that every rung's return value
    carries the original claim without each one having to remember to attach it.
    Retention is not optional: spec Section 29.12 forbids silently rewriting a
    value, and a repair that leaves no trace of what it repaired is exactly that.
    """
    result = _run_ladder(span, raw_text, redaction_spans)
    return replace(result, candidate=span)


def _run_ladder(
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
    decision: RelevanceDecision | None = None,
) -> RecordValidation:
    """Apply the evidence map and the status gate to one record.

    ``spans`` is the record's field-level span set from the store, excluding the
    spans the record already carries inline. ``decision`` is the
    ``RelevanceDecision`` a ``RetrievalCase`` inherited its ``scope_class`` from;
    supply it and the inheritance conditions are checked too. Four things are
    checked:

    1. **Every span is attached to a field this contract enforces.** A span naming
       an exempt field, a field of another contract, or a field this record does
       not populate is a contradiction (spec Section 15.10 consequence 2).
    2. **Every evidence-required field satisfies its status gate.** ``stated``,
       ``explicitly_none``, and ``uncertain`` each need at least one *valid* span;
       ``not_stated`` and ``not_applicable`` need none and must carry none.
    3. **No span attached to the record is unusable.** A rejected, unresolved, or
       unchecked span invalidates the record itself, so an invalid claim can
       never be resolved by dropping the field and keeping the remainder.
    4. **An inherited ``scope_class`` is genuinely inherited**, when the decision
       is supplied.

    ``all_evidence_spans`` is derived here, never read from the record.

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

    if isinstance(record, RetrievalCase) and decision is not None:
        _check_scope_inheritance(record, decision, acc)

    by_field: dict[str, list[EvidenceSpan]] = {}
    for span in union:
        if span.field_name not in enforced:
            acc.fail(
                f"span {span.evidence_id} names field {span.field_name!r}, which "
                f"is not an evidence-required field of {contract}; a span "
                f"attached to no field fails validation (spec Section 15.10)",
                ReasonCode.evidence_validation_failed,
                field_name=span.field_name,
                span=span,
            )
            continue
        if span.owner_id != _owner_id(record):
            acc.fail(
                f"span {span.evidence_id} belongs to owner {span.owner_id!r}, not "
                f"to this {contract} ({_owner_id(record)!r})",
                ReasonCode.evidence_validation_failed,
                field_name=span.field_name,
                span=span,
            )
            continue
        if not span.is_valid:
            message, reason_code = _unusable_span_failure(span, contract)
            acc.fail(
                message, reason_code, field_name=span.field_name, span=span
            )
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
                field_name=field_name,
            )
        if rule.evidence_must_be_empty and attached:
            acc.fail(
                f"{field_name} has observation status {status.value}, which "
                f"forbids evidence; {len(attached)} span(s) are attached. The "
                f"source being silent is not something a quote can support "
                f"(spec Section 17.17)",
                ReasonCode.observation_status_conflict,
                field_name=field_name,
            )

        value = _field_value(record, field_name)
        if rule.value_required and _is_empty_value(value):
            acc.fail(
                f"{field_name} has observation status {status.value}, which "
                f"requires a value, but the field is empty",
                ReasonCode.observation_status_conflict,
                field_name=field_name,
            )
        if rule.value_must_be_empty and not _is_empty_value(value):
            acc.fail(
                f"{field_name} has observation status {status.value}, which "
                f"requires an empty value, but the field holds {value!r}",
                ReasonCode.observation_status_conflict,
                field_name=field_name,
            )

    result = RecordValidation(
        ok=not acc.errors,
        all_evidence_spans=union,
        errors=tuple(acc.errors),
        reason_codes=tuple(acc.reason_codes),
        invalid_fields=tuple(acc.invalid_fields),
        retained_spans=tuple(acc.retained),
    )
    if not result.ok:
        _log_invalidation(record, contract, result)
    return result


def _log_invalidation(
    record: RelevanceDecision | RetrievalCase,
    contract: str,
    result: RecordValidation,
) -> None:
    """Emit the failure line for an invalidated record.

    Logging happens here rather than at the call site because the chain in
    ARCHITECTURE Section 9.3 is not advice to the caller — a caller that forgets
    to log leaves a fabrication invisible, and the one thing worse than a
    fabricated quote is a fabricated quote nobody counted. The fields are
    emitted as structured keys so Phase 8 can count review reasons by filtering
    the log rather than parsing it (spec Section 29.14).
    """
    _LOG.warning(
        "record invalidated by evidence validation",
        extra={
            "contract": contract,
            "owner_id": _owner_id(record),
            "doc_id": record.doc_id,
            "review_reason_code": (
                result.review_reason_code.value
                if result.review_reason_code is not None
                else None
            ),
            "reason_codes": [code.value for code in result.reason_codes],
            "invalid_fields": list(result.invalid_fields),
            "retained_span_ids": [
                span.evidence_id for span in result.retained_spans
            ],
            "error_count": len(result.errors),
            "errors": list(result.errors),
            "requires_review": result.requires_review,
        },
    )


def _check_scope_inheritance(
    case: RetrievalCase, decision: RelevanceDecision, acc: _Accumulator
) -> None:
    """The three conditions under which a case may inherit its ``scope_class``.

    ``RetrievalCase.scope_class`` is evidence-exempt on the grounds that it is
    already-validated and inherited, and its span lives on the decision. That
    exemption is only honest while the inheritance is real. Without these checks
    a case could assert any scope class it liked, cite no span for it, and pass
    the gate — the exemption would have become a hole exactly the size of the
    project's central claim.

    Each condition fails for a different reason:

    * **Same ``doc_id``.** A decision about another document says nothing about
      this one; inheriting across documents is borrowing a verdict.
    * **Matching value.** A case claiming ``core_incomplete_recall`` under an
      ``out_of_scope`` decision is not inheriting, it is overruling — and it
      would inflate the in-scope count with documents the decision excluded.
    * **The decision is valid.** An unconfirmed or rejected decision has no
      evidence to lend, so inheriting from it manufactures support from nothing.
    """
    if case.doc_id != decision.doc_id:
        acc.fail(
            f"scope_class cannot be inherited from a decision about another "
            f"document: case doc_id {case.doc_id!r} but decision "
            f"{decision.decision_id!r} concerns {decision.doc_id!r}",
            ReasonCode.evidence_validation_failed,
            field_name="scope_class",
        )
    if case.scope_class is not decision.scope_class:
        acc.fail(
            f"scope_class={case.scope_class.value!r} does not match the "
            f"inherited decision's {None if decision.scope_class is None else decision.scope_class.value!r}; "
            f"a case may inherit a scope class but never overrule one "
            f"(spec Section 15.4)",
            ReasonCode.evidence_validation_failed,
            field_name="scope_class",
        )
    if decision.validation_state is not ValidationState.valid:
        acc.fail(
            f"decision {decision.decision_id!r} is "
            f"{decision.validation_state.value}, so it has no validated "
            f"evidence to lend; scope_class cannot be inherited from an "
            f"unconfirmed decision",
            ReasonCode.evidence_validation_failed,
            field_name="scope_class",
        )


def _unusable_span_failure(
    span: EvidenceSpan, contract: str
) -> tuple[str, ReasonCode]:
    """Why one non-valid span invalidates its parent record.

    ARCHITECTURE Section 9.3 rung 4 invalidates the *record*, not merely the
    field. Checking only that each required field has at least one valid span
    would let a record carrying one good quote and one fabricated one persist as
    valid, and the fabrication would never be counted — which is precisely the
    finding this project exists to measure (spec Section 18, risk R8).
    """
    if span.validation_state is ValidationState.rejected:
        return (
            f"span {span.evidence_id} on {span.field_name} was rejected by the "
            f"validation ladder; a {contract} carrying a rejected span is "
            f"invalid even where the field has other valid spans "
            f"(ARCHITECTURE Section 9.3 rung 4)",
            ReasonCode.evidence_validation_failed,
        )
    if span.offset_state in _UNRESOLVED_OFFSET_STATES:
        return (
            f"span {span.evidence_id} on {span.field_name} has unresolved "
            f"offsets ({span.offset_state.value}); the record cannot be ordered "
            f"or cited and is never persisted as valid (spec Section 26.3)",
            ReasonCode.evidence_offsets_unresolved,
        )
    return (
        f"span {span.evidence_id} on {span.field_name} is still "
        f"{span.validation_state.value} and has not been through the validation "
        f"ladder; an unchecked span is not evidence",
        ReasonCode.evidence_validation_failed,
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


def gate_for_analysis(
    record: RelevanceDecision | RetrievalCase,
    spans: Iterable[EvidenceSpan] = (),
    decision: RelevanceDecision | None = None,
) -> tuple[EvidenceSpan, ...]:
    """Return the evidence union for a record, or refuse to return anything.

    The last leg of ARCHITECTURE Section 9.3 rung 4: an invalidated record
    produces no processed or analysis output until a human corrects it
    (spec Section 17.12, Section 26.3).

    The signature is the enforcement. A boolean ``is_eligible`` would be a check
    an aggregation could forget to call and still get its data; returning the
    spans means the analysis code cannot obtain its evidence without passing
    through the gate. Raises :class:`~src.core.errors.EvidenceError`, which is a
    ``ValidationError`` and so is already caught by the pipeline's failure
    handling rather than needing a new branch.
    """
    result = validate_record(record, spans, decision)
    result.raise_for_status()
    return result.all_evidence_spans


def select_valid_for_analysis(
    records: Iterable[RecordT],
) -> tuple[RecordT, ...]:
    """The records eligible for processed and analysis output.

    Phase 1's stand-in for the ``v_*`` SQL views Phase 3 builds: eligibility is
    a stored ``validation_state``, so the filter is the same predicate whether it
    runs here or in a ``WHERE`` clause, and the two cannot drift.

    Filtering on ``validation_state is valid`` rather than on ``not
    needs_human_review`` is deliberate. The two differ on the record that has
    been reviewed but not yet re-validated, and on the ``pending`` record nobody
    has looked at — both of which a review flag alone would wave through
    (spec Section 17.12).
    """
    return tuple(
        record
        for record in records
        if record.validation_state is ValidationState.valid
    )


#: Where each required field's spans live when they are not in the store. Exposed
#: so the Phase 5 persistence layer does not re-derive it.
INLINE_FIELDS = INLINE_EVIDENCE_FIELDS
