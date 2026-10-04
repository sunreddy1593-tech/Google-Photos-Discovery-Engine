"""Build a human relevance decision and check its quote against the target.

The review package owns the override row. This module applies the evidence
ladder, because review is not allowed to import the extractor. A quote that
does not validate, or that the researcher does not accept as support, stays
pending. Model confidence is never copied.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.core.ids import sha1_short
from src.extract.validator import validate_span
from src.models.enums import (
    DecidedBy,
    DecisionTechnicalState,
    EvidenceOwnerType,
    OffsetState,
    Speaker,
    ValidationState,
)
from src.models.evidence import EvidenceSpan
from src.models.relevance import RelevanceDecision
from src.review.overrides import RelevanceOverride


def human_decision_id(override_id: str) -> str:
    """One override produces one decision id."""
    return sha1_short("human-relevance-decision", override_id)


def human_decision_fingerprint(
    *,
    doc_id: str,
    scope_value: str,
    reason_value: str,
    content_hash: str,
    quote: str,
) -> str:
    """Identity of a human decision. It is not a model fingerprint."""
    return sha1_short(
        "human-relevance",
        doc_id,
        scope_value,
        reason_value,
        content_hash,
        quote,
        length=10,
    )


def build_human_relevance_decision(
    override: RelevanceOverride,
    *,
    audit: str,
    content_hash: str,
    decided_at: datetime,
    redactions: tuple[tuple[int, int], ...] = (),
    confidence: float | None = None,
    supports_decision: bool = True,
) -> RelevanceDecision:
    """Validate ``override.quote`` against the target audit and store the result.

    ``supports_decision`` is the researcher's judgment that the quote supports
    the approved scope. A verbatim quote that does not support the decision
    stays pending. Human notes stay in ``reason_summary`` and are not the quote.
    """
    decision_id = human_decision_id(override.override_id)
    candidate = EvidenceSpan(
        doc_id=override.doc_id,
        owner_type=EvidenceOwnerType.relevance_decision,
        owner_id=decision_id,
        field_name="scope_class",
        quote=override.quote,
        start_char=None,
        end_char=None,
        speaker=Speaker.unattributed,
        offset_state=OffsetState.missing_unresolved,
        validation_state=ValidationState.pending,
    )
    checked = validate_span(candidate, audit, redactions)
    span = checked.span
    if span.doc_id != override.doc_id or span.owner_id != decision_id:
        raise ValueError("validated evidence is not addressed to this override")
    accepted = bool(checked.ok and supports_decision)
    if checked.ok and not supports_decision:
        span = span.model_copy(update={"validation_state": ValidationState.pending})
    fingerprint = human_decision_fingerprint(
        doc_id=override.doc_id,
        scope_value=override.scope_class.value,
        reason_value=override.reason_code.value,
        content_hash=content_hash,
        quote=override.quote,
    )
    return RelevanceDecision(
        decision_id=decision_id,
        doc_id=override.doc_id,
        scope_class=override.scope_class,
        reason_code=override.reason_code,
        reason_summary=override.rationale,
        confidence=confidence,
        technical_state=DecisionTechnicalState.ok,
        evidence=(span,),
        decided_by=DecidedBy.human,
        model_name=None,
        prompt_version=None,
        ruleset_version=None,
        decision_fingerprint=fingerprint,
        decided_at=decided_at,
        needs_human_review=not accepted,
        validation_state=ValidationState.valid if accepted else ValidationState.pending,
    )


def load_human_decisions(path: Path | str) -> tuple[RelevanceDecision, ...]:
    """Read stored human decisions. A missing file is empty."""
    source = Path(path)
    if not source.is_file():
        return ()
    return tuple(
        RelevanceDecision.model_validate_json(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def append_human_decisions(
    path: Path | str,
    incoming: tuple[RelevanceDecision, ...] | list[RelevanceDecision],
) -> tuple[RelevanceDecision, ...]:
    """Append decisions whose ids are new. Existing lines stay byte-for-byte."""
    destination = Path(path)
    existing = load_human_decisions(destination)
    seen = {row.decision_id for row in existing}
    added = [row for row in incoming if row.decision_id not in seen]
    if not added:
        return existing
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8", newline="\n") as handle:
        for row in added:
            handle.write(
                json.dumps(row.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
                + "\n"
            )
    return existing + tuple(added)
