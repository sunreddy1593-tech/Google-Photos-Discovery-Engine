"""Append-only human relevance overrides.

An override does not edit the model decision it names. A later resolver may
prefer a validated human decision; the model row stays where it was written.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import AwareDatetime, Field

from src.core.ids import sha1_short
from src.models.base import ResearchModel
from src.models.enums import (
    DecidedBy,
    DecisionTechnicalState,
    ExtractorType,
    ReasonCode,
    ScopeClass,
    ValidationState,
)
from src.models.relevance import RelevanceDecision
from src.models.retrieval_case import RetrievalCase

OVERRIDE_TARGET_TYPE = "relevance_decision"
CASE_OVERRIDE_TARGET_TYPE = "retrieval_case"


class RelevanceOverride(ResearchModel):
    """One append-only row. Human notes live in ``rationale``, not in evidence."""

    override_id: str = Field(min_length=1)
    target_type: str = Field(default=OVERRIDE_TARGET_TYPE, min_length=1)
    target_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    scope_class: ScopeClass
    reason_code: ReasonCode
    author: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    approval_provenance: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    created_at: AwareDatetime


def override_id_for(
    *,
    doc_id: str,
    target_id: str,
    scope_class: ScopeClass,
    reason_code: ReasonCode,
    author: str,
    rationale: str,
    approval_provenance: str,
    quote: str,
) -> str:
    """Same inputs always name the same override. Time is not part of the id."""
    return sha1_short(
        "human-relevance-override",
        doc_id,
        target_id,
        scope_class.value,
        reason_code.value,
        author,
        rationale,
        approval_provenance,
        quote,
    )


def make_override(
    *,
    doc_id: str,
    target_id: str,
    scope_class: ScopeClass,
    reason_code: ReasonCode,
    author: str,
    rationale: str,
    approval_provenance: str,
    quote: str,
    created_at: datetime,
) -> RelevanceOverride:
    """Build one row. ``target_id`` is the original model ``decision_id``."""
    return RelevanceOverride(
        override_id=override_id_for(
            doc_id=doc_id,
            target_id=target_id,
            scope_class=scope_class,
            reason_code=reason_code,
            author=author,
            rationale=rationale,
            approval_provenance=approval_provenance,
            quote=quote,
        ),
        target_id=target_id,
        doc_id=doc_id,
        scope_class=scope_class,
        reason_code=reason_code,
        author=author,
        rationale=rationale,
        approval_provenance=approval_provenance,
        quote=quote,
        created_at=created_at,
    )


def load_overrides(path: Path | str) -> tuple[RelevanceOverride, ...]:
    """Read an append-only file. A missing file is an empty ledger."""
    source = Path(path)
    if not source.is_file():
        return ()
    rows: list[RelevanceOverride] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(RelevanceOverride.model_validate_json(line))
    return tuple(rows)


def append_overrides(
    path: Path | str,
    incoming: tuple[RelevanceOverride, ...] | list[RelevanceOverride],
) -> tuple[RelevanceOverride, ...]:
    """Append rows whose ids are new. Existing lines are not rewritten."""
    destination = Path(path)
    existing = load_overrides(destination)
    seen = {row.override_id for row in existing}
    added: list[RelevanceOverride] = []
    for row in incoming:
        if row.override_id in seen:
            continue
        added.append(row)
        seen.add(row.override_id)
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


def effective_decision(
    model_decision: RelevanceDecision,
    human_decisions: tuple[RelevanceDecision, ...] | list[RelevanceDecision],
) -> RelevanceDecision:
    """Prefer one validated human decision for the same document.

    A pending or failed human record does not replace the model. The model
    object is returned unchanged when no eligible human decision exists.
    """
    eligible = [
        item
        for item in human_decisions
        if item.doc_id == model_decision.doc_id
        and item.decided_by is DecidedBy.human
        and item.technical_state is DecisionTechnicalState.ok
        and item.validation_state is ValidationState.valid
    ]
    if not eligible:
        return model_decision
    return min(eligible, key=lambda item: item.decision_id)


class CaseOverride(ResearchModel):
    """Append-only correction of one model case. The model row is not edited."""

    override_id: str = Field(min_length=1)
    target_type: str = Field(default=CASE_OVERRIDE_TARGET_TYPE, min_length=1)
    target_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    author: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_quote: str | None = None
    created_at: AwareDatetime


def case_override_id_for(
    *,
    doc_id: str,
    target_id: str,
    author: str,
    rationale: str,
    evidence_quote: str | None,
) -> str:
    """Same inputs always name the same case override. Time is not part of the id."""
    return sha1_short(
        "human-case-override",
        doc_id,
        target_id,
        author,
        rationale,
        "" if evidence_quote is None else evidence_quote,
    )


def make_case_override(
    *,
    doc_id: str,
    target_id: str,
    author: str,
    rationale: str,
    created_at: datetime,
    evidence_quote: str | None = None,
) -> CaseOverride:
    """Build one row. ``target_id`` is the model ``case_id``."""
    if not target_id.startswith(f"{doc_id}#"):
        raise ValueError("case override target must belong to its document")
    return CaseOverride(
        override_id=case_override_id_for(
            doc_id=doc_id,
            target_id=target_id,
            author=author,
            rationale=rationale,
            evidence_quote=evidence_quote,
        ),
        target_id=target_id,
        doc_id=doc_id,
        author=author,
        rationale=rationale,
        evidence_quote=evidence_quote,
        created_at=created_at,
    )


def load_case_overrides(path: Path | str) -> tuple[CaseOverride, ...]:
    """Read an append-only case ledger. A missing file is empty."""
    source = Path(path)
    if not source.is_file():
        return ()
    rows: list[CaseOverride] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(CaseOverride.model_validate_json(line))
    return tuple(rows)


def append_case_overrides(
    path: Path | str,
    incoming: tuple[CaseOverride, ...] | list[CaseOverride],
) -> tuple[CaseOverride, ...]:
    """Append rows whose ids are new. Existing lines are not rewritten."""
    destination = Path(path)
    existing = load_case_overrides(destination)
    seen = {row.override_id for row in existing}
    added = [row for row in incoming if row.override_id not in seen]
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


def v_current_cases(
    cases: tuple[RetrievalCase, ...] | list[RetrievalCase],
) -> tuple[RetrievalCase, ...]:
    """One current row per case id. A valid human row wins; every input row stays.

    Precedence is the human override, not recency. A pending human row does not
    replace the model. The input sequence is not modified.
    """
    grouped: dict[str, list[RetrievalCase]] = {}
    for case in cases:
        grouped.setdefault(case.case_id, []).append(case)
    chosen: list[RetrievalCase] = []
    for case_id in sorted(grouped):
        rows = grouped[case_id]
        human = [
            row
            for row in rows
            if row.extractor_type is ExtractorType.human
            and row.validation_state is ValidationState.valid
        ]
        if human:
            pool = human
        else:
            pool = [row for row in rows if row.extractor_type is not ExtractorType.human] or rows
        chosen.append(max(pool, key=lambda row: (row.extracted_at, row.extraction_fingerprint)))
    return tuple(chosen)
