"""Deterministic identifier helpers (spec Section 26.1, ADR-20).

The central test here is ``test_doc_id_signature_rejects_content_hash``: it
asserts a *negative* about the function signature. ``doc_id`` previously fell back
to ``content_hash``, a Phase 3 value, which made the identifier undefinable at
import and meant a normalizer change silently altered every manually imported
row's identity. Asserting the parameter's absence is what stops a future edit from
quietly reintroducing the dependency.
"""

from __future__ import annotations

import inspect

import pytest

from src.core import ids


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #


def test_sha1_short_is_deterministic_and_length_bounded() -> None:
    assert ids.sha1_short("a", "b") == ids.sha1_short("a", "b")
    assert len(ids.sha1_short("a", "b")) == 12
    assert len(ids.sha1_short("a", "b", length=8)) == 8


def test_separator_prevents_field_boundary_collisions() -> None:
    """('a','b') and ('ab',) must not collide: field boundaries are significant."""
    assert ids.sha1_short("a", "b") != ids.sha1_short("ab")


def test_none_and_empty_string_render_alike_but_positions_differ() -> None:
    assert ids.sha1_short("x", None) == ids.sha1_short("x", "")
    assert ids.sha1_short("x", None) != ids.sha1_short(None, "x")


def test_raw_text_sha256_is_deterministic_and_sensitive() -> None:
    text = "I know I have a photo of that cafe somewhere"
    assert ids.raw_text_sha256(text) == ids.raw_text_sha256(text)
    assert len(ids.raw_text_sha256(text)) == 64
    assert ids.raw_text_sha256(text) != ids.raw_text_sha256(text + ".")


# --------------------------------------------------------------------------- #
# content_hash canonicalization
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Can't find my photos!", "can't find my photos"),     # case, trailing mark
        ("photo   of   a  cafe", "photo of a cafe"),            # whitespace runs
        ("search fails https://example.com/x", "search fails"),  # URL stripped
        ("  leading and trailing  ", "leading and trailing"),
        ("Photo, video, receipt", "photo video receipt"),       # separators
        ("caf\u00e9", "cafe\u0301"),                            # NFKC equivalence
    ],
)
def test_content_hash_ignores_canonicalized_differences(
    left: str, right: str
) -> None:
    assert ids.content_hash(left) == ids.content_hash(right)


def test_content_hash_distinguishes_real_text_differences() -> None:
    assert ids.content_hash("cannot find my photos") != ids.content_hash(
        "cannot find my videos"
    )


def test_punctuation_becomes_a_boundary_rather_than_being_deleted() -> None:
    """Documents the reading of "stripped punctuation" in spec Section 26.1.

    Deleting punctuation would merge ``photo,video`` into ``photovideo``, a token
    matching neither word. Replacing it with a boundary keeps tokens intact.
    """
    assert ids.canonicalize_for_hash("photo,video") == "photo video"
    assert ids.canonicalize_for_hash("Can't") == "can t"


def test_content_hash_does_not_bridge_contraction_spelling() -> None:
    """``can't`` and ``cant`` hash differently, and that is correct.

    ``content_hash`` detects *exact* duplicates: the same item re-ingested, or
    identical canonical text from one author (spec Section 19.6 rules 1-2). Two
    different typings are plausibly two different people, which is the case
    Section 19.6 insists must not be collapsed automatically. Catching them as
    *related* is simhash's job, under the review band and its safety conditions.
    """
    assert ids.content_hash("can't find my photos") != ids.content_hash(
        "cant find my photos"
    )


def test_canonicalize_strips_urls_before_punctuation() -> None:
    """Order matters: punctuation-first would shred a URL into surviving tokens."""
    canonical = ids.canonicalize_for_hash("see https://ex.com/a?b=c#d for detail")
    assert "ex" not in canonical
    assert canonical == "see for detail"


# --------------------------------------------------------------------------- #
# author_hash
# --------------------------------------------------------------------------- #


def test_author_hash_is_deterministic_with_the_same_salt() -> None:
    assert ids.author_hash("salt", "reddit", "user") == ids.author_hash(
        "salt", "reddit", "user"
    )


def test_author_hash_changes_with_the_salt() -> None:
    assert ids.author_hash("salt-a", "reddit", "user") != ids.author_hash(
        "salt-b", "reddit", "user"
    )


def test_author_hash_separates_platform_from_username() -> None:
    """The same handle on two platforms is two authors."""
    assert ids.author_hash("s", "reddit", "chris") != ids.author_hash(
        "s", "youtube", "chris"
    )


def test_author_hash_never_contains_the_plaintext() -> None:
    assert "distinctive_handle" not in ids.author_hash(
        "salt", "reddit", "distinctive_handle"
    )


def test_author_hash_rejects_an_empty_salt() -> None:
    """An unsalted hash over public usernames is trivially reversible."""
    with pytest.raises(ValueError, match="AUTHOR_SALT"):
        ids.author_hash("", "reddit", "user")


def test_author_salt_id_is_not_the_salt() -> None:
    assert ids.author_salt_id("my-secret-salt") != "my-secret-salt"
    assert ids.author_salt_id("a") != ids.author_salt_id("b")


# --------------------------------------------------------------------------- #
# source_url_key
# --------------------------------------------------------------------------- #


def test_source_url_key_lowercases_scheme_and_host_but_not_path() -> None:
    """Paths are case-sensitive on many hosts; a comment id must survive intact."""
    assert (
        ids.source_url_key("HTTPS://WWW.Reddit.com/r/GooglePixel/Comments/AbC")
        == "https://www.reddit.com/r/GooglePixel/Comments/AbC"
    )


def test_source_url_key_drops_fragment_and_tracking_params() -> None:
    assert (
        ids.source_url_key(
            "https://example.com/thread?utm_source=news&utm_medium=email"
            "&id=42&fbclid=xyz#comment-7"
        )
        == "https://example.com/thread?id=42"
    )


def test_source_url_key_collapses_trailing_slash_but_keeps_root() -> None:
    assert ids.source_url_key("https://example.com/a/b/") == "https://example.com/a/b"
    assert ids.source_url_key("https://example.com/") == "https://example.com/"


def test_source_url_key_sorts_remaining_query_for_stability() -> None:
    assert ids.source_url_key(
        "https://youtube.com/watch?lc=Ug1&v=abc"
    ) == ids.source_url_key("https://youtube.com/watch?v=abc&lc=Ug1")


def test_source_url_key_preserves_item_identifying_params() -> None:
    """Dropping v or lc would collapse two different comments into one key."""
    key = ids.source_url_key("https://www.youtube.com/watch?v=vid1&lc=comment1")
    assert "v=vid1" in key and "lc=comment1" in key
    assert ids.source_url_key(
        "https://www.youtube.com/watch?v=vid1&lc=comment1"
    ) != ids.source_url_key("https://www.youtube.com/watch?v=vid1&lc=comment2")


def test_source_url_key_is_idempotent() -> None:
    once = ids.source_url_key("https://Example.com/a/?utm_source=x#frag")
    assert ids.source_url_key(once) == once


# --------------------------------------------------------------------------- #
# doc_id — available at import, never dependent on a later stage
# --------------------------------------------------------------------------- #


def test_doc_id_signature_rejects_content_hash() -> None:
    """ADR-20 enforced structurally: the parameter must not exist.

    If a future edit wants content_hash in doc_id, it has to change this
    signature and this test, which makes the decision visible in review.
    """
    params = set(inspect.signature(ids.doc_id).parameters)
    assert "content_hash" not in params
    assert "normalized_text" not in params
    assert "simhash" not in params


def test_doc_id_prefers_source_item_id() -> None:
    assert ids.doc_id(
        "youtube", source_item_id="UgxAbc", url_key="https://x/y"
    ) == ids.doc_id("youtube", source_item_id="UgxAbc")


def test_doc_id_falls_back_to_url_key() -> None:
    assert ids.doc_id("reddit", url_key="https://reddit.com/a").startswith("reddit-")


def test_doc_id_third_fallback_uses_raw_text_sha256_only() -> None:
    """A manual row with no platform id and no URL still gets an id at import."""
    doc = ids.doc_id(
        "manual_other",
        source_name="Help Community",
        author_hash_value=None,
        published_at_iso=None,
        raw_text_hash=ids.raw_text_sha256("some collected text"),
    )
    assert doc.startswith("manual_other-")


def test_doc_id_is_computable_with_no_derived_value_present(
) -> None:
    """Invariant I11: no contract requires a field a later stage produces.

    Everything passed here is available the instant a document is imported.
    """
    raw_text = "I cannot find the receipt photo I took last spring"
    doc = ids.doc_id(
        "google_support",
        source_item_id=None,
        url_key=ids.source_url_key(
            "https://support.google.com/photos/thread/123?msgid=456"
        ),
        source_name="Google Photos Help Community",
        raw_text_hash=ids.raw_text_sha256(raw_text),
    )
    assert doc.startswith("google_support-")
    assert len(doc.split("-", 1)[1]) == 12


def test_doc_id_is_deterministic_across_calls() -> None:
    args = dict(source_item_id="item-1")
    assert ids.doc_id("reddit", **args) == ids.doc_id("reddit", **args)


def test_doc_id_separates_platforms_with_the_same_item_id() -> None:
    assert ids.doc_id("reddit", source_item_id="1") != ids.doc_id(
        "youtube", source_item_id="1"
    )


def test_doc_id_requires_at_least_one_natural_key() -> None:
    with pytest.raises(ValueError, match="all three were absent"):
        ids.doc_id("manual_other", source_name="nothing usable")


def test_doc_id_ignores_published_at_when_item_id_exists() -> None:
    """A source that revises a timestamp must not change a document's identity."""
    assert ids.doc_id(
        "reddit", source_item_id="x", published_at_iso="2026-01-01T00:00:00Z"
    ) == ids.doc_id("reddit", source_item_id="x")


# --------------------------------------------------------------------------- #
# Canonical duplicate selection
# --------------------------------------------------------------------------- #


def test_canonical_doc_id_is_the_lowest_and_order_independent() -> None:
    group = ["reddit-ffff00000000", "reddit-00aa11112222", "youtube-8888ffff0000"]
    expected = "reddit-00aa11112222"

    assert ids.canonical_doc_id(group) == expected
    assert ids.canonical_doc_id(reversed(group)) == expected
    assert ids.canonical_doc_id(sorted(group, reverse=True)) == expected


def test_canonical_doc_id_rejects_an_empty_group() -> None:
    with pytest.raises(ValueError, match="at least one"):
        ids.canonical_doc_id([])


# --------------------------------------------------------------------------- #
# case_id, evidence_id, link_id, event_id
# --------------------------------------------------------------------------- #


def test_case_id_ordered_format() -> None:
    assert ids.case_id_ordered("reddit-abc123abc123", 1) == "reddit-abc123abc123#c01"
    assert ids.case_id_ordered("reddit-abc123abc123", 12) == "reddit-abc123abc123#c12"


def test_case_id_ordinal_is_one_based() -> None:
    with pytest.raises(ValueError, match="1-based"):
        ids.case_id_ordered("reddit-abc", 0)


def test_case_id_unordered_marks_unresolved_offsets() -> None:
    case = ids.case_id_unordered("reddit-abc", '{"outcome":"not_found"}')
    assert case.startswith("reddit-abc#u")
    assert len(case.split("#u")[1]) == 8


def test_case_sort_key_orders_by_position_then_tie_breaks() -> None:
    assert ids.case_sort_key(5, 20, "q", "p") < ids.case_sort_key(9, 20, "q", "p")
    assert ids.case_sort_key(5, 10, "q", "p") < ids.case_sort_key(5, 20, "q", "p")


def test_case_sort_key_breaks_identical_offsets_by_quote_then_payload() -> None:
    """One sentence can support two distinct retrieval needs (spec Section 26.3)."""
    a = ids.case_sort_key(5, 20, "quote A", "payload")
    b = ids.case_sort_key(5, 20, "quote B", "payload")
    assert a != b
    assert {a, b} == {min(a, b), max(a, b)}

    c = ids.case_sort_key(5, 20, "same", "payload 1")
    d = ids.case_sort_key(5, 20, "same", "payload 2")
    assert c != d


def test_case_sort_key_refuses_unresolved_offsets() -> None:
    """An arbitrary offset that validates is worse than a visible gap."""
    with pytest.raises(ValueError, match="cannot be ordered"):
        ids.case_sort_key(None, None, "q", "p")


def test_evidence_id_is_field_scoped() -> None:
    """The same quote on two fields is two spans, or the map is unenforceable."""
    assert ids.evidence_id("case-1", "outcome", "gave up", 0, 7) != ids.evidence_id(
        "case-1", "severity", "gave up", 0, 7
    )


def test_evidence_id_changes_with_offsets_and_survives_their_absence() -> None:
    with_offsets = ids.evidence_id("case-1", "outcome", "gave up", 0, 7)
    shifted = ids.evidence_id("case-1", "outcome", "gave up", 10, 17)
    without = ids.evidence_id("case-1", "outcome", "gave up")

    assert with_offsets != shifted
    assert without not in {with_offsets, shifted}
    assert len(without) == 12


def test_link_id_is_directional_and_method_scoped() -> None:
    assert ids.link_id("a", "b", "exact_text") != ids.link_id("b", "a", "exact_text")
    assert ids.link_id("a", "b", "exact_text") != ids.link_id("a", "b", "near")


def test_event_id_distinguishes_retry_attempts() -> None:
    """Append-only history needs a retry to be a new event, not an overwrite."""
    assert ids.event_id("run1", "extract", "doc1", 1, "failed") != ids.event_id(
        "run1", "extract", "doc1", 2, "succeeded"
    )


# --------------------------------------------------------------------------- #
# Fingerprints — the taxonomy_version asymmetry (ADR-19)
# --------------------------------------------------------------------------- #


def test_extraction_fingerprint_has_no_taxonomy_parameter() -> None:
    """Enforced in the signature, so it cannot be passed by accident."""
    assert "taxonomy_version" not in inspect.signature(
        ids.extraction_fingerprint
    ).parameters


def test_assignment_fingerprint_is_the_only_one_with_taxonomy_version() -> None:
    assert "taxonomy_version" in inspect.signature(
        ids.assignment_fingerprint
    ).parameters
    assert "taxonomy_version" not in inspect.signature(
        ids.decision_fingerprint
    ).parameters


def test_assignment_fingerprint_moves_with_taxonomy_version() -> None:
    base = dict(
        model="m", prompt_version="1", schema_version="1", content_hash_value="h"
    )
    assert ids.assignment_fingerprint(taxonomy_version="v1", **base) != (
        ids.assignment_fingerprint(taxonomy_version="v2", **base)
    )


def test_fingerprints_are_ten_characters() -> None:
    assert len(ids.extraction_fingerprint("m", "1", "1", "h")) == 10
    assert len(ids.decision_fingerprint("m", "1", "1", "1", "h")) == 10


def test_extraction_fingerprint_moves_with_model_prompt_schema_and_content() -> None:
    base = ids.extraction_fingerprint("m", "1", "1", "h")
    assert ids.extraction_fingerprint("m2", "1", "1", "h") != base
    assert ids.extraction_fingerprint("m", "2", "1", "h") != base
    assert ids.extraction_fingerprint("m", "1", "2", "h") != base
    assert ids.extraction_fingerprint("m", "1", "1", "h2") != base


# --------------------------------------------------------------------------- #
# cache_key
# --------------------------------------------------------------------------- #


def _key(**overrides: object) -> str:
    base = dict(
        provider="anthropic",
        model="claude-sonnet-4-5",
        prompt_id="extraction",
        prompt_version="1.0.0",
        schema_version="1.0.0",
        content_hash_value="abc123",
    )
    base.update(overrides)
    return ids.cache_key(**base)  # type: ignore[arg-type]


def test_cache_key_omits_taxonomy_version_by_default() -> None:
    """Opt-in, so extraction cannot pick it up implicitly (ADR-19)."""
    assert _key() == _key(taxonomy_version=None)
    assert _key() != _key(taxonomy_version="v1")


def test_cache_key_moves_with_every_documented_input() -> None:
    base = _key()
    assert _key(provider="openai") != base
    assert _key(model="other") != base
    assert _key(prompt_id="relevance") != base
    assert _key(prompt_version="1.0.1") != base
    assert _key(schema_version="2.0.0") != base
    assert _key(content_hash_value="different") != base
    assert _key(decoding_params={"temperature": 0.7}) != base


def test_cache_key_is_insensitive_to_decoding_param_ordering() -> None:
    assert _key(decoding_params={"a": 1, "b": 2}) == _key(
        decoding_params={"b": 2, "a": 1}
    )


def test_cache_key_is_a_full_sha256() -> None:
    assert len(_key()) == 64
