"""Turn a validated model payload into a RelevanceDecision.

Evidence offsets are applied by the pipeline, which owns the evidence ladder.
This module decides what a ladder verdict means: a repaired span can be stored,
and a fabricated or ambiguous span becomes a technical failure with empty
evidence. ``is_relevant`` is never read from the payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError as PydanticValidationError

from src.core.ids import decision_fingerprint, sha1_short
from src.core.versions import RULESET_VERSION, SCHEMA_VERSION, prompt_version
from src.models.enums import (
    DecidedBy,
    DecisionTechnicalState,
    EvidenceOwnerType,
    OffsetState,
    ReasonCode,
    ScopeClass,
    Speaker,
    ValidationState,
)
from src.models.evidence import EvidenceSpan
from src.models.relevance import RelevanceDecision
from src.relevance.prompts import PROMPT_ID
from src.relevance.rules import PrefilterResult
from src.relevance.schema import RelevancePayload

# Spec 16.10 has timeout and provider_error. Spec 16.8 has no matching reason
# codes. The technical state keeps the distinction. The reason code has to be
# one the decision contract allows, so both use provider_unavailable.
_STATE_REASON: dict[DecisionTechnicalState, ReasonCode] = {
    DecisionTechnicalState.provider_unavailable: ReasonCode.provider_unavailable,
    DecisionTechnicalState.provider_error: ReasonCode.provider_unavailable,
    DecisionTechnicalState.timeout: ReasonCode.provider_unavailable,
    DecisionTechnicalState.rate_limited: ReasonCode.rate_limited,
    DecisionTechnicalState.response_parse_failed: ReasonCode.response_parse_failed,
    DecisionTechnicalState.schema_validation_failed: ReasonCode.schema_validation_failed,
    DecisionTechnicalState.evidence_validation_failed: ReasonCode.evidence_validation_failed,
    DecisionTechnicalState.skipped_dry_run: ReasonCode.provider_unavailable,
}


@dataclass(frozen=True)
class SpanVerdict:
    """Ladder outcome without importing the extractor."""

    ok: bool
    reason_code: ReasonCode | None
    quote: str
    start_char: int | None
    end_char: int | None
    offset_state: OffsetState
    repair_applied: bool
    validation_state: ValidationState
    message: str = ""


@dataclass(frozen=True)
class ClassificationOutcome:
    """A decision plus the review reasons the queue should open."""

    decision: RelevanceDecision
    review_reasons: tuple[ReasonCode, ...]
    retained_quote: str | None = None
    failure_message: str = ""
    diagnostic: object | None = None


def parse_payload(data: dict[str, object]) -> RelevancePayload:
    """Validate a JSON object. A supplied ``is_relevant`` is discarded first."""
    cleaned = {key: value for key, value in data.items() if key != "is_relevant"}
    return RelevancePayload.model_validate(cleaned)


def pending_span(payload: RelevancePayload, decision_id: str) -> EvidenceSpan:
    """The model's span, still unchecked, addressed to this decision."""
    start = payload.evidence.start_char
    end = payload.evidence.end_char
    has_offsets = start is not None and end is not None
    return EvidenceSpan(
        doc_id=payload.doc_id,
        owner_type=EvidenceOwnerType.relevance_decision,
        owner_id=decision_id,
        field_name="scope_class",
        quote=payload.evidence.quote,
        start_char=start if has_offsets else None,
        end_char=end if has_offsets else None,
        speaker=Speaker.unattributed,
        offset_state=(
            OffsetState.supplied_exact if has_offsets else OffsetState.missing_unresolved
        ),
        validation_state=ValidationState.pending,
    )


def assemble_decision(
    payload: RelevancePayload,
    verdict: SpanVerdict | None,
    *,
    expected_doc_id: str,
    content_hash: str,
    model_name: str,
    prefilter: PrefilterResult | None,
    confidence_review_below: float,
    decided_at: datetime,
    failure_state: DecisionTechnicalState | None = None,
    failure_message: str = "",
) -> ClassificationOutcome:
    """Build the stored decision. Invalid evidence does not stay on the record."""
    fingerprint = decision_fingerprint(
        model_name,
        prompt_version(PROMPT_ID),
        RULESET_VERSION,
        SCHEMA_VERSION,
        content_hash,
    )
    if payload.doc_id != expected_doc_id:
        return _schema_failure(
            payload,
            fingerprint,
            model_name,
            decided_at,
            "doc_id did not match the document that was sent",
            doc_id=expected_doc_id,
        )
    if failure_state is not None and failure_state is not DecisionTechnicalState.ok:
        return ClassificationOutcome(
            decision=_failure(
            doc_id=expected_doc_id,
            state=failure_state,
                fingerprint=fingerprint,
                model_name=model_name,
                decided_at=decided_at,
                summary=failure_message or "No decision was produced.",
            ),
            review_reasons=(_STATE_REASON[failure_state],),
            retained_quote=payload.evidence.quote,
            failure_message=failure_message,
        )

    if verdict is None or not verdict.ok:
        reason = (
            verdict.reason_code
            if verdict is not None and verdict.reason_code is not None
            else ReasonCode.evidence_validation_failed
        )
        state = DecisionTechnicalState.evidence_validation_failed
        decision = _failure(
            doc_id=expected_doc_id,
            state=state,
            fingerprint=fingerprint,
            model_name=model_name,
            decided_at=decided_at,
            summary="Evidence did not validate.",
            reason_code=reason,
        )
        return ClassificationOutcome(
            decision=decision,
            review_reasons=(reason,),
            retained_quote=None if verdict is None else verdict.quote,
            failure_message="" if verdict is None else verdict.message,
        )

    assert verdict.start_char is not None and verdict.end_char is not None
    decision_id = _decision_id(expected_doc_id, fingerprint, DecisionTechnicalState.ok)
    span = EvidenceSpan(
        doc_id=expected_doc_id,
        owner_type=EvidenceOwnerType.relevance_decision,
        owner_id=decision_id,
        field_name="scope_class",
        quote=verdict.quote,
        start_char=verdict.start_char,
        end_char=verdict.end_char,
        speaker=Speaker.unattributed,
        offset_state=verdict.offset_state,
        validation_state=ValidationState.valid,
        repair_applied=verdict.repair_applied,
    )
    reviews: list[ReasonCode] = []
    if payload.confidence < confidence_review_below:
        reviews.append(ReasonCode.low_confidence)
    if prefilter is not None and _contradicts(prefilter, payload.scope_class):
        reviews.append(ReasonCode.prefilter_classifier_conflict)
    try:
        decision = RelevanceDecision(
            decision_id=decision_id,
            doc_id=expected_doc_id,
            scope_class=payload.scope_class,
            reason_code=payload.reason_code,
            reason_summary=payload.reason_summary,
            confidence=payload.confidence,
            technical_state=DecisionTechnicalState.ok,
            evidence=(span,),
            decided_by=DecidedBy.llm,
            model_name=model_name,
            prompt_version=prompt_version(PROMPT_ID),
            ruleset_version=RULESET_VERSION,
            decision_fingerprint=fingerprint,
            decided_at=decided_at,
            needs_human_review=bool(reviews),
            validation_state=ValidationState.valid,
        )
    except (PydanticValidationError, ValueError) as exc:
        return _schema_failure(
            payload,
            fingerprint,
            model_name,
            decided_at,
            str(exc)[:300],
            doc_id=expected_doc_id,
        )
    return ClassificationOutcome(decision=decision, review_reasons=tuple(reviews))


def failure_outcome(
    *,
    doc_id: str,
    content_hash: str,
    model_name: str,
    state: DecisionTechnicalState,
    decided_at: datetime,
    message: str,
    diagnostic: object | None = None,
) -> ClassificationOutcome:
    """A technical failure with no scope class and no evidence."""
    fingerprint = decision_fingerprint(
        model_name,
        prompt_version(PROMPT_ID),
        RULESET_VERSION,
        SCHEMA_VERSION,
        content_hash,
    )
    reason = _STATE_REASON[state]
    return ClassificationOutcome(
        decision=_failure(
            doc_id=doc_id,
            state=state,
            fingerprint=fingerprint,
            model_name=model_name,
            decided_at=decided_at,
            summary=message or "No decision was produced.",
            reason_code=reason,
        ),
        review_reasons=(reason,),
        failure_message=message,
        diagnostic=diagnostic,
    )


def _schema_failure(
    payload: RelevancePayload,
    fingerprint: str,
    model_name: str,
    decided_at: datetime,
    message: str,
    doc_id: str | None = None,
) -> ClassificationOutcome:
    return ClassificationOutcome(
        decision=_failure(
            doc_id=doc_id or payload.doc_id,
            state=DecisionTechnicalState.schema_validation_failed,
            fingerprint=fingerprint,
            model_name=model_name,
            decided_at=decided_at,
            summary="The response did not match the decision contract.",
        ),
        review_reasons=(ReasonCode.schema_validation_failed,),
        retained_quote=payload.evidence.quote,
        failure_message=message,
    )


def _failure(
    *,
    doc_id: str,
    state: DecisionTechnicalState,
    fingerprint: str,
    model_name: str,
    decided_at: datetime,
    summary: str,
    reason_code: ReasonCode | None = None,
) -> RelevanceDecision:
    reason = reason_code or _STATE_REASON[state]
    text = summary.strip() or "No decision was produced."
    return RelevanceDecision(
        decision_id=_decision_id(doc_id, fingerprint, state),
        doc_id=doc_id,
        scope_class=None,
        reason_code=reason,
        reason_summary=text,
        confidence=None,
        technical_state=state,
        evidence=(),
        decided_by=DecidedBy.llm,
        model_name=model_name,
        prompt_version=prompt_version(PROMPT_ID),
        ruleset_version=RULESET_VERSION,
        decision_fingerprint=fingerprint,
        decided_at=decided_at,
        needs_human_review=True,
        validation_state=ValidationState.pending,
    )


def _decision_id(doc_id: str, fingerprint: str, state: DecisionTechnicalState) -> str:
    return sha1_short("relevance", doc_id, fingerprint, state.value, length=12)


def _contradicts(prefilter: PrefilterResult, scope: ScopeClass) -> bool:
    hinted = prefilter.candidate_scope_class
    if hinted is None:
        return False
    return hinted != scope.value
