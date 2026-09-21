"""Canonical content hashing for rebuild equality (spec Section 26.4, ADR-26).

Two properties must hold together, and neither alone is sufficient. The hash must
ignore volatile run metadata, or the reproducibility check fails for reasons
unrelated to the data and gets switched off. And it must still catch a changed
data field, or it passes everything and checks nothing.
"""

from __future__ import annotations

import pytest

from src.core.hashing import (
    VOLATILE_FIELDS,
    artifact_hash,
    canonical_json,
    content_equivalence_hash,
    exclusion_list,
)


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "doc_id": "reddit-abc123abc123",
        "scope_class": "core_incomplete_recall",
        "content_hash": "f" * 64,
        "token_count": 42,
        "collected_at": "2026-09-01T10:00:00Z",
        "published_at": "2026-08-15T09:30:00Z",
        "run_id": "run-2026-09-21-001",
        "occurred_at": "2026-09-21T16:00:00Z",
        "duration_ms": 1234,
        "total_tokens": 5678,
        "cache_hit": False,
        "hostname": "build-box",
        "pid": 4242,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Volatile fields are ignored
# --------------------------------------------------------------------------- #


def test_hash_ignores_run_id_and_timestamps() -> None:
    first = content_equivalence_hash(_record())
    second = content_equivalence_hash(
        _record(
            run_id="run-2026-09-22-002",
            occurred_at="2026-09-22T08:00:00Z",
            duration_ms=99,
            total_tokens=1,
            cache_hit=True,
            hostname="laptop",
            pid=7,
        )
    )
    assert first == second


@pytest.mark.parametrize("field", sorted(VOLATILE_FIELDS))
def test_every_volatile_field_is_actually_excluded(field: str) -> None:
    baseline = content_equivalence_hash({"doc_id": "d", field: "value-a"})
    changed = content_equivalence_hash({"doc_id": "d", field: "value-b"})
    assert baseline == changed, f"{field} is listed as volatile but still hashed"


def test_volatile_fields_are_stripped_at_every_depth() -> None:
    """Nested stage records carry timestamps too."""
    shallow = content_equivalence_hash(
        {"id": "x", "stages": [{"stage": "extract", "occurred_at": "A"}]}
    )
    deep = content_equivalence_hash(
        {"id": "x", "stages": [{"stage": "extract", "occurred_at": "B"}]}
    )
    assert shallow == deep


# --------------------------------------------------------------------------- #
# Data fields are not ignored
# --------------------------------------------------------------------------- #


def test_hash_changes_when_a_data_field_changes() -> None:
    assert content_equivalence_hash(_record()) != content_equivalence_hash(
        _record(scope_class="out_of_scope")
    )


def test_collected_at_and_published_at_are_data_not_volatile() -> None:
    """Properties of the document, not of the run (spec Section 26.4)."""
    assert "collected_at" not in VOLATILE_FIELDS
    assert "published_at" not in VOLATILE_FIELDS

    baseline = content_equivalence_hash(_record())
    assert content_equivalence_hash(
        _record(collected_at="2026-09-02T10:00:00Z")
    ) != baseline
    assert content_equivalence_hash(
        _record(published_at="2026-08-16T09:30:00Z")
    ) != baseline


def test_token_count_is_a_data_field_despite_the_name_collision() -> None:
    """The spec excludes LLM *usage* counts, not DocumentDerived.token_count.

    Excluding it would drop the value the dedupe minimum-length rule reads
    (spec Section 19.6) and let non-determinism in tokenization pass unseen.
    """
    assert "token_count" not in VOLATILE_FIELDS
    assert "total_tokens" in VOLATILE_FIELDS

    assert content_equivalence_hash(_record(token_count=43)) != (
        content_equivalence_hash(_record())
    )


@pytest.mark.parametrize(
    "field",
    ["doc_id", "case_id", "content_hash", "simhash", "start_char", "end_char",
     "scope_class", "severity", "observation_status", "evidence_id"],
)
def test_identity_and_evidence_fields_are_never_volatile(field: str) -> None:
    assert field not in VOLATILE_FIELDS


# --------------------------------------------------------------------------- #
# Canonicalization
# --------------------------------------------------------------------------- #


def test_key_order_does_not_affect_the_hash() -> None:
    assert content_equivalence_hash({"a": 1, "b": 2}) == content_equivalence_hash(
        {"b": 2, "a": 1}
    )


def test_integral_floats_and_ints_compare_equal() -> None:
    """A JSON round-trip can change which one a number is; that is not data."""
    assert content_equivalence_hash({"n": 1.0}) == content_equivalence_hash({"n": 1})
    assert content_equivalence_hash({"n": -0.0}) == content_equivalence_hash({"n": 0})


def test_genuine_fractional_differences_still_register() -> None:
    assert content_equivalence_hash({"score": 0.85}) != content_equivalence_hash(
        {"score": 0.84}
    )


def test_booleans_are_not_coerced_to_integers() -> None:
    assert content_equivalence_hash({"flag": True}) != content_equivalence_hash(
        {"flag": 1}
    )


def test_list_order_is_significant() -> None:
    """Evidence span order within a record is data; export order is not."""
    assert content_equivalence_hash({"spans": [1, 2]}) != content_equivalence_hash(
        {"spans": [2, 1]}
    )


def test_canonical_json_is_compact_and_sorted() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_preserves_non_ascii() -> None:
    assert "café" in canonical_json({"q": "café"})


# --------------------------------------------------------------------------- #
# artifact_hash
# --------------------------------------------------------------------------- #


def test_artifact_hash_is_record_order_independent() -> None:
    records = [
        {"doc_id": "b", "value": 2},
        {"doc_id": "a", "value": 1},
        {"doc_id": "c", "value": 3},
    ]
    assert artifact_hash(records, "doc_id") == artifact_hash(
        list(reversed(records)), "doc_id"
    )


def test_artifact_hash_detects_a_changed_record() -> None:
    records = [{"doc_id": "a", "value": 1}]
    assert artifact_hash(records, "doc_id") != artifact_hash(
        [{"doc_id": "a", "value": 2}], "doc_id"
    )


def test_artifact_hash_supports_composite_keys() -> None:
    """retrieval_cases is keyed (case_id, extraction_fingerprint) per ADR-7."""
    records = [
        {"case_id": "c1", "extraction_fingerprint": "fp2", "v": 1},
        {"case_id": "c1", "extraction_fingerprint": "fp1", "v": 2},
    ]
    key = ("case_id", "extraction_fingerprint")
    assert artifact_hash(records, key) == artifact_hash(list(reversed(records)), key)


def test_artifact_hash_reports_a_missing_primary_key() -> None:
    with pytest.raises(KeyError, match="primary-key"):
        artifact_hash([{"value": 1}], "doc_id")


def test_artifact_hash_of_an_empty_artifact_is_stable() -> None:
    assert artifact_hash([], "doc_id") == artifact_hash([], "doc_id")


# --------------------------------------------------------------------------- #
# Manifest disclosure
# --------------------------------------------------------------------------- #


def test_exclusion_list_is_sorted_and_complete() -> None:
    """Recorded in the manifest, or the equality claim is unfalsifiable."""
    listed = exclusion_list()
    assert listed == sorted(listed)
    assert set(listed) == set(VOLATILE_FIELDS)
    assert "run_id" in listed
