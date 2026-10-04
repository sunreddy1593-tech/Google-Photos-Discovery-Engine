"""Lexical retrieval returns nothing below the score threshold."""

from __future__ import annotations

import pytest

from src.retrieve.citations import evidence_panel, validate_citations
from src.retrieve.rank import search

RECORDS = [
    {
        "case_id": "older-photo",
        "source": "reddit",
        "scope_class": "core_incomplete_recall",
        "problem_summary": "find an older photo of the same item",
        "quotes": "I don't remember when I took the photo",
        "excerpt": "Trying to find an older photo",
        "labels": "photo",
    },
    {
        "case_id": "sleeping-video",
        "source": "reddit",
        "scope_class": "core_incomplete_recall",
        "problem_summary": "show videos of Suzie sleeping",
        "quotes": "Show me videos of Suzie sleeping",
        "excerpt": "white noise video",
        "labels": "video",
    },
    {
        "case_id": "album-face",
        "source": "google_support",
        "scope_class": "adjacent_known_item_retrieval",
        "problem_summary": "search a face inside one album",
        "quotes": "search for a face within a specific album",
        "excerpt": "album face search",
        "labels": "album",
    },
] * 1


@pytest.mark.synthetic
def test_unrelated_question_returns_no_evidence() -> None:
    assert search("best pizza in Naples", RECORDS) == []


@pytest.mark.synthetic
def test_relevant_question_ranks_the_matching_case() -> None:
    hits = search("older photo I don't remember", RECORDS)
    assert hits
    assert hits[0]["case_id"] == "older-photo"


@pytest.mark.synthetic
def test_filters_run_before_ranking() -> None:
    hits = search(
        "older photo",
        RECORDS,
        filters={"scope_class": "adjacent_known_item_retrieval"},
    )
    assert hits == []


@pytest.mark.synthetic
def test_source_cap_limits_one_source() -> None:
    hits = search("photo video album face", RECORDS, per_source_cap=1, min_score=0.01)
    sources = [hit["source"] for hit in hits]
    assert sources.count("reddit") <= 1


@pytest.mark.synthetic
def test_invalid_citation_is_rejected_and_panel_is_the_intersection() -> None:
    retrieved = {"older-photo", "sleeping-video"}
    panel = evidence_panel("See [older-photo] and [not-a-case].", retrieved)
    assert panel == ["older-photo"]
    rejected = validate_citations("See [not-a-case] and [still-missing].", retrieved)
    assert rejected.rejected is True
    assert evidence_panel("See [not-a-case] and [still-missing].", retrieved) == []


@pytest.mark.synthetic
def test_search_without_records_returns_nothing() -> None:
    assert search("how do people find screenshots") == []
    assert search("best pizza in Naples") == []
