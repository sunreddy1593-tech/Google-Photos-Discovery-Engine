"""Offline human relevance overrides. No provider is constructed."""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.enums import DecidedBy, ReasonCode, ScopeClass, ValidationState
from src.pipeline.human_relevance import (
    append_human_decisions,
    build_human_relevance_decision,
)
from src.review.overrides import append_overrides, effective_decision, make_override
from tests.synthetic import DOC_ID, make_decision

STAMP = datetime(2026, 9, 30, tzinfo=UTC)
PROJECT = Path(__file__).resolve().parents[1]


def _override(
    *,
    doc_id: str = "doc-a",
    target_id: str = "model-decision-1",
    quote: str = "I searched for edited and found nothing.",
    scope: ScopeClass = ScopeClass.adjacent_known_item_retrieval,
    reason: ReasonCode = ReasonCode.known_item_with_precise_recall_failure,
    rationale: str = "The attempted query is known and the search failed.",
):
    return make_override(
        doc_id=doc_id,
        target_id=target_id,
        scope_class=scope,
        reason_code=reason,
        author="researcher",
        rationale=rationale,
        approval_provenance="Approved seed label.",
        quote=quote,
        created_at=STAMP,
    )


def test_append_preserves_existing_rows_and_reruns_do_not_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "overrides.jsonl"
    first = _override(target_id="model-1", quote="I searched for edited and found nothing.")
    second = _override(target_id="model-2", quote="Search for dog returned about 40 photos.")
    append_overrides(path, [first])
    before = path.read_bytes()
    append_overrides(path, [second])
    after_second = path.read_bytes()
    assert after_second.startswith(before)
    assert after_second.count(b"\n") == 2
    again = append_overrides(path, [first, second])
    assert path.read_bytes() == after_second
    assert [row.override_id for row in again] == [first.override_id, second.override_id]
    assert first.override_id == _override(
        target_id="model-1", quote="I searched for edited and found nothing."
    ).override_id


def test_human_decision_has_human_provenance_and_null_confidence() -> None:
    audit = "I searched for edited and found nothing."
    override = _override(quote=audit)
    decision = build_human_relevance_decision(
        override,
        audit=audit,
        content_hash="abc",
        decided_at=STAMP,
    )
    assert decision.decided_by is DecidedBy.human
    assert decision.model_name is None
    assert decision.prompt_version is None
    assert decision.confidence is None
    assert decision.validation_state is ValidationState.valid
    supplied = build_human_relevance_decision(
        override,
        audit=audit,
        content_hash="abc",
        decided_at=STAMP,
        confidence=0.4,
    )
    assert supplied.confidence == 0.4


def test_scope_and_reason_must_pair() -> None:
    override = _override(
        scope=ScopeClass.core_incomplete_recall,
        reason=ReasonCode.no_retrieval_need_or_attempt,
    )
    with pytest.raises(ValidationError):
        build_human_relevance_decision(
            override,
            audit=override.quote,
            content_hash="abc",
            decided_at=STAMP,
        )


def test_evidence_validation_and_pending_failures() -> None:
    quote = "I searched for edited and found nothing."
    valid = build_human_relevance_decision(
        _override(quote=quote),
        audit=quote,
        content_hash="abc",
        decided_at=STAMP,
    )
    assert valid.validation_state is ValidationState.valid
    assert valid.evidence[0].doc_id == "doc-a"
    assert valid.needs_human_review is False

    missing = build_human_relevance_decision(
        _override(quote="this sentence is not in the target"),
        audit=quote,
        content_hash="abc",
        decided_at=STAMP,
    )
    assert missing.validation_state is ValidationState.pending
    assert missing.needs_human_review is True
    assert missing.evidence[0].is_valid is False

    ambiguous = build_human_relevance_decision(
        _override(quote="photo"),
        audit="photo and photo",
        content_hash="abc",
        decided_at=STAMP,
    )
    assert ambiguous.validation_state is ValidationState.pending

    unsupported = build_human_relevance_decision(
        _override(quote=quote),
        audit=quote,
        content_hash="abc",
        decided_at=STAMP,
        supports_decision=False,
    )
    assert unsupported.validation_state is ValidationState.pending
    assert unsupported.evidence[0].quote == quote


def test_override_stays_on_its_document() -> None:
    quote = "I searched for edited and found nothing."
    other = "A different document talks about albums."
    decision = build_human_relevance_decision(
        _override(doc_id="doc-a", quote=quote),
        audit=other,
        content_hash="other",
        decided_at=STAMP,
    )
    assert decision.doc_id == "doc-a"
    assert decision.evidence[0].doc_id == "doc-a"
    assert decision.validation_state is ValidationState.pending


def test_validated_human_decision_precedes_without_rewriting_the_model(tmp_path: Path) -> None:
    audit = "I searched for edited and found nothing."
    model = make_decision(
        decision_id="model-decision-1",
        scope_class=ScopeClass.out_of_scope,
        reason_code=ReasonCode.editing_sharing_or_printing,
        confidence=0.97,
    )
    before = model.model_dump()
    human = build_human_relevance_decision(
        _override(doc_id=DOC_ID, target_id=model.decision_id, quote=audit),
        audit=audit,
        content_hash="abc",
        decided_at=STAMP,
    )
    chosen = effective_decision(model, [human])
    assert chosen.decision_id == human.decision_id
    assert chosen.decided_by is DecidedBy.human
    assert model.model_dump() == before
    assert model.confidence == 0.97
    assert chosen.confidence is None

    pending = build_human_relevance_decision(
        _override(doc_id=DOC_ID, target_id=model.decision_id, quote="not present"),
        audit=audit,
        content_hash="abc",
        decided_at=STAMP,
    )
    assert effective_decision(model, [pending]) is model
    path = tmp_path / "human.jsonl"
    append_human_decisions(path, [human])
    append_human_decisions(path, [human])
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_modules_do_not_call_a_provider() -> None:
    for relative in (
        "src/review/overrides.py",
        "src/pipeline/human_relevance.py",
    ):
        tree = ast.parse((PROJECT / relative).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not any(name.split(".")[0] in {"groq", "anthropic", "openai"} for name in imported)
        assert not any(name == "src.llm" or name.startswith("src.llm.") for name in imported)
