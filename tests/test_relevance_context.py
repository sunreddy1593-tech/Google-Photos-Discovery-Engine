"""Parent context stays off holdout text, and evidence stays on the reply."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.core.ids import cache_key
from src.core.versions import RULESET_VERSION, SCHEMA_VERSION
from src.models.enums import DecisionTechnicalState, ReasonCode, ScopeClass
from src.pipeline.stages import classify_with_ladder
from src.relevance.context import (
    CONTEXT_INCOMPLETE,
    DocumentLink,
    ParentContext,
    cross_split_families,
    guarded_parent_contexts,
)
from src.relevance.interpretation import agreement_summary
from src.relevance.prompts import render_relevance_prompt
from src.relevance.schema import EvidencePayload, RelevancePayload

PHASE_INSTANT = datetime(2026, 9, 27, tzinfo=UTC)
SMOKE_IDS = (
    "app_store-5e60a403ce06",
    "app_store-b42c080472ee",
    "google_support-2a080da4b930",
    "google_support-3d15a7ae4cd0",
    "google_support-d7f386f347b7",
    "google_support-e1e5277da7e8",
)


def test_holdout_parent_text_is_not_read() -> None:
    read: list[str] = []
    links = (
        DocumentLink("reply", "reply-item", "thread-1"),
        DocumentLink("holdout-parent", "thread-1", None),
    )

    def title_of(doc_id: str) -> str:
        read.append(doc_id)
        return "Holdout title"

    def audit_of(doc_id: str) -> str:
        read.append("audit:" + doc_id)
        return "holdout body"

    context = guarded_parent_contexts(
        ["reply"],
        links,
        {"reply": "development", "holdout-parent": "holdout"},
        title_of,
        audit_of,
        lambda doc_id: "hash",
    )["reply"]
    assert context.status == CONTEXT_INCOMPLETE
    assert context.parent_doc_id == "holdout-parent"
    assert context.text is None
    assert read == []


def test_development_parent_is_separated_from_the_reply() -> None:
    links = (
        DocumentLink("reply", "reply-item", "thread-1"),
        DocumentLink("parent", "thread-1", None),
    )
    splits = {"reply": "development", "parent": "development"}
    context = guarded_parent_contexts(
        ["reply"],
        links,
        splits,
        lambda doc_id: "Where were these taken",
        lambda doc_id: "Parent only: the waterfall album.",
        lambda doc_id: "parent-hash",
    )["reply"]
    prompt = render_relevance_prompt(
        doc_id="reply",
        raw_text_audit="Reply only: search narrowed to the park.",
        parent_context=context,
    )
    user_open = prompt.index("\nUSER_POST\n")
    user_start = user_open + len("\nUSER_POST\n")
    user_end = prompt.index("\nUSER_POST\n", user_start)
    parent_open = prompt.index("\nPARENT_CONTEXT\n")
    parent_start = parent_open + len("\nPARENT_CONTEXT\n")
    parent_end = prompt.index("\nPARENT_CONTEXT\n", parent_start)
    assert prompt[user_start:user_end] == "Reply only: search narrowed to the park."
    assert "Parent only: the waterfall album." in prompt[parent_start:parent_end]
    assert "Parent only: the waterfall album." not in prompt[user_start:user_end]
    assert "document_id: parent" in prompt[parent_start:parent_end]
    source = Path("src/relevance/prompts.py").read_text(encoding="utf-8")
    for doc_id in SMOKE_IDS:
        assert doc_id not in source
        assert doc_id not in prompt


def test_context_hash_changes_the_cache_key() -> None:
    shared = dict(
        provider="groq",
        model="openai/gpt-oss-120b",
        prompt_id="relevance",
        prompt_version="relevance/v4",
        schema_version=SCHEMA_VERSION,
        content_hash_value="reply-hash",
        ruleset_version=RULESET_VERSION,
    )
    first = ParentContext(
        status="included",
        parent_doc_id="parent",
        parent_thread_id="thread-1",
        title="Title",
        text="one",
        content_hash="hash-a",
    )
    second = ParentContext(
        status="included",
        parent_doc_id="parent",
        parent_thread_id="thread-1",
        title="Title",
        text="two",
        content_hash="hash-b",
    )
    bare = cache_key(decoding_params={"temperature": 1e-8}, **shared)
    with_first = cache_key(decoding_params={"temperature": 1e-8, **first.cache_fields()}, **shared)
    with_second = cache_key(
        decoding_params={"temperature": 1e-8, **second.cache_fields()},
        **shared,
    )
    assert bare != with_first
    assert with_first != with_second


def test_parent_quote_is_not_evidence_for_the_reply() -> None:
    target = "Reply only: search narrowed to the park."
    parent_sentence = "Parent only: the waterfall album."
    payload = RelevancePayload(
        doc_id="reply",
        scope_class=ScopeClass.adjacent_known_item_retrieval,
        reason_code=ReasonCode.known_item_retrieval_journey_described,
        reason_summary="The reply describes a search.",
        confidence=0.8,
        evidence=EvidencePayload(quote=parent_sentence),
    )
    outcome = classify_with_ladder(
        payload,
        audit=target,
        redactions=(),
        content_hash="reply-hash",
        model_name="openai/gpt-oss-120b",
        prefilter=None,
        confidence_review_below=0.7,
        decided_at=PHASE_INSTANT,
        expected_doc_id="reply",
    )
    assert outcome.decision.technical_state is DecisionTechnicalState.evidence_validation_failed
    assert outcome.decision.evidence == ()
    supported = payload.model_copy(
        update={"evidence": EvidencePayload(quote="search narrowed to the park.")}
    )
    kept = classify_with_ladder(
        supported,
        audit=target,
        redactions=(),
        content_hash="reply-hash",
        model_name="openai/gpt-oss-120b",
        prefilter=None,
        confidence_review_below=0.7,
        decided_at=PHASE_INSTANT,
        expected_doc_id="reply",
    )
    assert kept.decision.technical_state is DecisionTechnicalState.ok
    assert kept.decision.evidence[0].quote == "search narrowed to the park."
    assert kept.decision.evidence[0].start_char == target.index("search narrowed to the park.")
    assert parent_sentence not in kept.decision.evidence[0].quote


def test_cross_split_families_use_ids_only() -> None:
    links = (
        DocumentLink("parent-a", "thread-a", None),
        DocumentLink("reply-dev", "reply-dev", "thread-a"),
        DocumentLink("reply-hold", "reply-hold", "thread-a"),
        DocumentLink("parent-b", "thread-b", None),
        DocumentLink("reply-b", "reply-b", "thread-b"),
    )
    splits = {
        "parent-a": "development",
        "reply-dev": "development",
        "reply-hold": "holdout",
        "parent-b": "development",
        "reply-b": "development",
    }
    families = cross_split_families(links, splits)
    assert len(families) == 1
    assert families[0]["parent_thread_id"] == "thread-a"
    encoded = str(families)
    assert "holdout body" not in encoded
    assert "title" not in encoded


def test_interpretation_flags_stay_inside_the_six_record_denominator() -> None:
    rows = tuple((doc_id, index % 2 == 0, index % 3 == 0) for index, doc_id in enumerate(SMOKE_IDS))
    summary = agreement_summary(
        rows,
        context_status={"google_support-3d15a7ae4cd0": "included"},
    )
    assert summary["document_count"] == 6
    assert summary["scope_agreement"] == 3
    assert summary["reason_agreement"] == 2
    flags = summary["interpretation_flags"]
    assert isinstance(flags, dict)
    assert "google_support-3d15a7ae4cd0" not in flags
    ledger = summary["context_comparability"]["google_support-3d15a7ae4cd0"]
    assert ledger["seed_row_text"] == "reply_only"
    assert ledger["model_context"] == "included"
    assert ledger["known_human_review_context"] == "linked_parent_thread"
    assert "human_model_context_differs" not in flags.get("google_support-3d15a7ae4cd0", ())
    assert "overlapping_inclusion_reasons" in flags["google_support-d7f386f347b7"]
    assert "core_adjacent_boundary" in flags["google_support-e1e5277da7e8"]
    incomplete = agreement_summary(
        rows,
        context_status={"google_support-3d15a7ae4cd0": "incomplete"},
    )
    waterfall = incomplete["interpretation_flags"]["google_support-3d15a7ae4cd0"]
    assert isinstance(waterfall, tuple)
    assert "context_incomplete" in waterfall
    assert incomplete["document_count"] == 6
