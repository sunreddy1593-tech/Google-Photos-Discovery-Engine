"""Taxonomy candidates stay unnamed, and assignment does not touch extraction cache."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.core.ids import assignment_fingerprint, cache_key, extraction_fingerprint
from src.taxonomy.assign import assign_cases, is_established
from src.taxonomy.candidates import propose_groupings

WHEN = datetime(2026, 10, 4, tzinfo=timezone.utc)


@pytest.mark.synthetic
def test_candidates_do_not_name_a_cluster() -> None:
    groups = propose_groupings(
        [
            {"case_id": "a", "technical_state": "ok", "scope_class": "core_incomplete_recall"},
            {"case_id": "b", "technical_state": "ok", "scope_class": "core_incomplete_recall"},
            {"case_id": "c", "technical_state": "provider_error", "scope_class": "core_incomplete_recall"},
        ]
    )
    assert groups[0]["case_ids"] == ("a", "b")
    assert "cluster_id" not in groups[0]


@pytest.mark.synthetic
def test_established_requires_five_documents_and_two_sources() -> None:
    assert is_established(["d1", "d2", "d3", "d4"], ["reddit", "youtube"]) is False
    assert is_established(["d1", "d2", "d3", "d4", "d5"], ["reddit"]) is False
    assert is_established(["d1", "d2", "d3", "d4", "d5"], ["reddit", "youtube"]) is True


@pytest.mark.synthetic
def test_reassignment_preserves_prior_rows_and_extraction_cache_ignores_taxonomy() -> None:
    prior = assign_cases(
        [{"case_id": "case-1", "content_hash": "abc"}],
        taxonomy_version="reviewed-1",
        clusters=[{"cluster_id": "named-by-review", "case_ids": ["case-1"]}],
        assigned_at=WHEN,
    )
    later = assign_cases(
        [{"case_id": "case-1", "content_hash": "abc"}],
        taxonomy_version="reviewed-2",
        clusters=[{"cluster_id": "renamed-by-review", "case_ids": []}],
        assigned_at=WHEN,
        prior=prior,
    )
    assert [row.taxonomy_version for row in later] == ["reviewed-1", "reviewed-2"]
    assert later[0].cluster_id == "named-by-review"
    assert later[1].cluster_id == "uncertain"
    assert assign_cases(
        [{"case_id": "case-1"}],
        taxonomy_version="0-unassigned",
        clusters=[{"cluster_id": "should-not-apply", "case_ids": ["case-1"]}],
        assigned_at=WHEN,
    ) == []
    base = dict(
        provider="groq",
        model="openai/gpt-oss-120b",
        prompt_id="extract",
        prompt_version="extract/v2",
        schema_version="1.0.0",
        content_hash_value="abc",
    )
    assert cache_key(**base) == cache_key(**base, taxonomy_version=None)
    assert extraction_fingerprint("m", "extract/v2", "1.0.0", "abc") == extraction_fingerprint(
        "m", "extract/v2", "1.0.0", "abc"
    )
    assert assignment_fingerprint("rules", "p", "1.0.0", "reviewed-1", "abc") != (
        assignment_fingerprint("rules", "p", "1.0.0", "reviewed-2", "abc")
    )


@pytest.mark.synthetic
def test_publishing_a_taxonomy_version_does_not_change_the_extraction_key() -> None:
    without = cache_key(
        provider="groq",
        model="openai/gpt-oss-120b",
        prompt_id="extract",
        prompt_version="extract/v2",
        schema_version="1.0.0",
        content_hash_value="same-case",
    )
    still_without = cache_key(
        provider="groq",
        model="openai/gpt-oss-120b",
        prompt_id="extract",
        prompt_version="extract/v2",
        schema_version="1.0.0",
        content_hash_value="same-case",
    )
    assert without == still_without
