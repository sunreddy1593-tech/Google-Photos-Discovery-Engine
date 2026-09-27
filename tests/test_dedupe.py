"""Deduplication rules, safety conditions, and a deterministic second run."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime

import pytest

from src.core.config import DedupeConfig
from src.core.ids import author_hash, content_hash, raw_text_sha256, source_url_key
from src.dedupe.detect import PreparedDocument, detect_links
from src.dedupe.simhash import hamming_distance
from src.models.enums import DuplicateKind, DuplicateReviewState, SourcePlatform
from src.normalize.derive import derive_document
from src.normalize.simhash import simhash_hex
from src.normalize.text import normalized_text
from src.pipeline.calibration import (
    pair_key,
    select_calibration_rows,
    write_calibration_csv,
)
from src.pipeline.runner import RULESET_INSTANT, run_normalize_dedupe
from src.review.queue import open_items
from tests.synthetic import make_document

CONFIG = DedupeConfig(
    simhash_duplicate_max=3,
    simhash_review_band_max=6,
    min_tokens=25,
)

LONG = (
    "I cannot find the photo I know I took at the beach last summer because "
    "search only returns recent screenshots and never the picture of the red "
    "boat near the pier after sunset"
)


def _document(doc_id: str, text: str, **overrides: object):
    url = str(
        overrides.pop(
            "source_url",
            f"https://www.reddit.com/r/googlephotos/comments/{doc_id}/",
        )
    )
    fields: dict[str, object] = {
        "doc_id": doc_id,
        "source_item_id": overrides.pop("source_item_id", doc_id),
        "raw_text": text,
        "raw_text_sha256": raw_text_sha256(text),
        "source_url": url,
        "source_url_key": source_url_key(url),
        "author_hash": overrides.pop("author_hash", "aaaaaaaaaaaaaaaa"),
        "collected_at": overrides.pop("collected_at", datetime(2024, 1, 1, tzinfo=UTC)),
    }
    fields.update(overrides)
    return make_document(**fields)


def _prepared(document) -> PreparedDocument:
    row = derive_document(document, derived_at=RULESET_INSTANT)
    return PreparedDocument(
        doc_id=document.doc_id,
        source_platform=document.source_platform.value,
        source_item_id=document.source_item_id,
        canonical_url=row.canonical_url,
        author_hash=document.author_hash,
        content_hash=row.content_hash,
        simhash=row.simhash,
        token_count=row.token_count,
        normalized_text=row.normalized_text,
    )


def _links(*documents):
    return detect_links(
        [_prepared(document) for document in documents],
        CONFIG,
        decided_at=RULESET_INSTANT,
    )


def _variant(base: str, low: int, high: int) -> str:
    words = base.split()
    base_hash = simhash_hex(normalized_text(base))
    for index in range(len(words)):
        for replacement in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot"):
            trial_words = words[:]
            trial_words[index] = replacement
            trial = " ".join(trial_words)
            if content_hash(trial) == content_hash(base):
                continue
            distance = hamming_distance(base_hash, simhash_hex(normalized_text(trial)))
            if low <= distance <= high:
                return trial
    raise AssertionError(f"no variant with Hamming distance {low}-{high}")


def test_exact_duplicate_uses_lowest_doc_id_not_collection_time() -> None:
    """ADR-20 and the Phase 3 plan: lowest doc_id, not earliest collected_at.

    The earlier document here has the later doc_id. Input order is reversed
    on the second call. A null collected_at cannot be constructed: the
    collected-document contract requires the timestamp.
    """
    early = datetime(2020, 1, 1, tzinfo=UTC)
    late = datetime(2026, 6, 1, tzinfo=UTC)
    first_collected = _document("reddit-zzz", LONG, collected_at=early)
    later = _document("reddit-aaa", LONG, collected_at=late)

    forward = _links(first_collected, later)
    backward = _links(later, first_collected)

    assert len(forward) == 1
    link = forward[0]
    assert link.duplicate_kind is DuplicateKind.exact_text
    assert link.review_state is DuplicateReviewState.auto_confirmed
    assert link.canonical_doc_id == "reddit-aaa"
    assert link.doc_id == "reddit-zzz"
    assert link.canonical_doc_id != first_collected.doc_id
    assert backward[0].canonical_doc_id == link.canonical_doc_id
    assert backward[0].link_id == link.link_id


def test_exact_group_keeps_every_document_and_one_canonical() -> None:
    documents = [
        _document("reddit-mmm", LONG),
        _document("reddit-zzz", LONG),
        _document("reddit-aaa", LONG),
    ]
    links = _links(*reversed(documents))

    assert {link.canonical_doc_id for link in links} == {"reddit-aaa"}
    assert {link.doc_id for link in links} == {"reddit-mmm", "reddit-zzz"}
    assert len(links) == 2


def test_near_duplicate_is_marked_inside_the_confident_band() -> None:
    variant = _variant(LONG, 1, CONFIG.simhash_duplicate_max)
    links = _links(
        _document("reddit-aaa", LONG),
        _document("reddit-bbb", variant),
    )

    assert len(links) == 1
    link = links[0]
    assert link.duplicate_kind is DuplicateKind.near
    assert link.review_state is DuplicateReviewState.auto_confirmed
    assert 1 <= link.method_detail["hamming_distance"] <= 3
    assert link.canonical_doc_id == "reddit-aaa"


def test_review_band_is_pending_and_not_counted() -> None:
    variant = _variant(LONG, 4, CONFIG.simhash_review_band_max)
    links = _links(
        _document("reddit-aaa", LONG),
        _document("reddit-bbb", variant),
    )

    assert len(links) == 1
    link = links[0]
    assert link.review_state is DuplicateReviewState.pending_review
    assert link.review_reason_code is not None
    assert link.review_reason_code.value == "near_duplicate_in_review_band"
    assert link.counts_as_duplicate is False
    assert 4 <= link.method_detail["hamming_distance"] <= 6


def test_cross_post_uses_content_and_platform_not_author_identity() -> None:
    """Same public name, hashed with the real function, on two platforms.

    The hashes differ because the platform is part of the HMAC input. The
    pair is still a cross-post proposal from the identical text, and it stays
    in review. A copied hash string is not treated as proof of one person.
    """
    salt = "phase3-cross-post-salt"
    username = "public-name"
    reddit_hash = author_hash(salt, SourcePlatform.reddit.value, username)
    youtube_hash = author_hash(salt, SourcePlatform.youtube.value, username)
    assert reddit_hash != youtube_hash

    reddit = _document(
        "reddit-zzz",
        LONG,
        author_hash=reddit_hash,
        source_platform=SourcePlatform.reddit,
    )
    youtube = _document(
        "youtube-aaa",
        LONG,
        author_hash=youtube_hash,
        source_platform=SourcePlatform.youtube,
        source_url="https://www.youtube.com/watch?v=abcdefghijk&lc=commentzzz",
        source_item_id="commentzzz",
    )
    forward = _links(reddit, youtube)
    backward = _links(youtube, reddit)

    assert len(forward) == 1
    link = forward[0]
    assert link.duplicate_kind is DuplicateKind.cross_post
    assert link.review_state is DuplicateReviewState.pending_review
    assert link.review_reason_code is not None
    assert link.review_reason_code.value == "different_authors_identical_text"
    assert link.counts_as_duplicate is False
    assert link.canonical_doc_id == "reddit-zzz"
    assert link.doc_id == "youtube-aaa"
    assert link.method_detail["cross_platform"] is True
    assert backward[0].link_id == link.link_id
    assert backward[0].canonical_doc_id == link.canonical_doc_id

    copied = _links(
        _document("reddit-zzz", LONG, author_hash=reddit_hash),
        _document(
            "youtube-aaa",
            LONG,
            author_hash=reddit_hash,
            source_platform=SourcePlatform.youtube,
            source_url="https://www.youtube.com/watch?v=abcdefghijk&lc=commentzzz",
            source_item_id="commentzzz",
        ),
    )
    assert copied[0].duplicate_kind is DuplicateKind.cross_post
    assert copied[0].review_state is DuplicateReviewState.pending_review
    assert copied[0].review_reason_code is not None
    assert copied[0].review_reason_code.value == "low_confidence"
    assert copied[0].counts_as_duplicate is False


def test_quoted_text_inside_a_reply_goes_to_review() -> None:
    parent = (
        "I cannot find the photo I know I took at the beach last summer"
    )
    reply = parent + " and then the search failed again after I tried faces."
    links = _links(
        _document("reddit-parent", parent, source_item_id="parent-1"),
        _document(
            "reddit-reply",
            reply,
            source_item_id="reply-1",
            parent_thread_id="parent-1",
        ),
    )

    assert len(links) == 1
    assert links[0].duplicate_kind is DuplicateKind.quoted_repeat
    assert links[0].review_state is DuplicateReviewState.pending_review
    assert links[0].review_reason_code is not None
    assert links[0].review_reason_code.value == "quoted_repeat_ambiguous"
    assert links[0].counts_as_duplicate is False


def test_short_generic_text_is_not_auto_collapsed() -> None:
    short = "search is useless now"
    links = _links(
        _document("reddit-aaa", short, author_hash="aaaaaaaaaaaaaaaa"),
        _document("reddit-bbb", short, author_hash="bbbbbbbbbbbbbbbb"),
    )

    assert len(links) == 1
    assert links[0].review_state is DuplicateReviewState.pending_review
    assert links[0].review_reason_code is not None
    assert links[0].review_reason_code.value == "short_text_below_dedupe_minimum"
    assert links[0].counts_as_duplicate is False


def test_identical_long_text_from_different_authors_is_not_auto_collapsed() -> None:
    links = _links(
        _document("reddit-aaa", LONG, author_hash="aaaaaaaaaaaaaaaa"),
        _document("reddit-bbb", LONG, author_hash="bbbbbbbbbbbbbbbb"),
    )

    assert len(links) == 1
    assert links[0].duplicate_kind is DuplicateKind.exact_text
    assert {links[0].doc_id, links[0].canonical_doc_id} == {"reddit-aaa", "reddit-bbb"}
    assert links[0].review_state is DuplicateReviewState.pending_review
    assert links[0].review_reason_code is not None
    assert links[0].review_reason_code.value == "different_authors_identical_text"
    assert links[0].counts_as_duplicate is False


def test_shared_listing_url_with_distinct_content_is_not_a_duplicate() -> None:
    url = (
        "https://play.google.com/store/apps/details?id=com.google.android.apps.photos"
        "&utm_source=newsletter"
    )
    other = (
        "The backup queue stalled overnight and none of the videos from the trip "
        "appeared on the second phone even after I left both devices charging"
    )
    links = _links(
        _document("play-aaa", LONG, source_url=url, source_item_id="review-aaa"),
        _document("play-bbb", other, source_url=url, source_item_id="review-bbb"),
    )
    assert links == ()


def test_share_link_of_the_same_comment_is_same_source_item() -> None:
    watch = "https://www.youtube.com/watch?v=abcdefghijk&lc=comment1&utm_source=share"
    short = "https://youtu.be/abcdefghijk?lc=comment1"
    links = _links(
        _document(
            "yt-aaa",
            LONG,
            source_url=watch,
            source_item_id="comment1",
            source_platform=SourcePlatform.youtube,
        ),
        _document(
            "yt-zzz",
            "A shorter recap that is not the same wording at all here today.",
            source_url=short,
            source_item_id=None,
            source_platform=SourcePlatform.youtube,
        ),
    )

    assert len(links) == 1
    assert links[0].duplicate_kind is DuplicateKind.same_source_item
    assert links[0].review_state is DuplicateReviewState.auto_confirmed


def test_min_tokens_is_read_from_configuration() -> None:
    strict = DedupeConfig(
        simhash_duplicate_max=3,
        simhash_review_band_max=6,
        min_tokens=100,
    )
    prepared = [
        _prepared(_document("reddit-aaa", LONG)),
        _prepared(_document("reddit-bbb", LONG)),
    ]
    links = detect_links(prepared, strict, decided_at=RULESET_INSTANT)

    assert links[0].review_reason_code is not None
    assert links[0].review_reason_code.value == "short_text_below_dedupe_minimum"
    assert links[0].method_detail["min_tokens"] == 100


def test_second_run_matches_byte_for_byte(tmp_path) -> None:
    documents = [
        _document("reddit-zzz", LONG, collected_at=datetime(2020, 1, 1, tzinfo=UTC)),
        _document("reddit-aaa", LONG, collected_at=datetime(2026, 1, 1, tzinfo=UTC)),
        _document(
            "reddit-ccc",
            "Email me@example.com about a completely different camera problem "
            "that has nothing to do with the beach photo or the red boat story",
            author_hash="cccccccccccccccc",
        ),
    ]
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = run_normalize_dedupe(documents, CONFIG, first_dir)
    second = run_normalize_dedupe(list(reversed(documents)), CONFIG, second_dir)

    assert first.derived_hash == second.derived_hash
    assert first.link_hash == second.link_hash
    assert first.document_count == 3
    names = (
        "documents_derived.jsonl",
        "duplicate_links.jsonl",
        "stage_events.jsonl",
        "review_queue.jsonl",
        "duplicate_review.csv",
        "duplicate_calibration.csv",
        "phase3_summary.json",
    )
    for name in names:
        assert (first_dir / name).read_bytes() == (second_dir / name).read_bytes()
    derived_text = (first_dir / "documents_derived.jsonl").read_text(encoding="utf-8")
    review = (first_dir / "duplicate_review.csv").read_text(encoding="utf-8")
    calibration = (first_dir / "duplicate_calibration.csv").read_text(encoding="utf-8")
    assert "me@example.com" not in review
    assert "me@example.com" not in calibration
    assert "cccccccccccccccc" not in calibration
    assert "researcher_decision" in review
    assert "researcher_notes" in calibration
    link_ids = {
        (json.loads(line)["doc_id"], json.loads(line)["canonical_doc_id"])
        for line in (first_dir / "duplicate_links.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    control_rows = [
        row
        for row in csv.DictReader(calibration.splitlines())
        if row["selection_reason"] == "nearest_negative_control"
    ]
    assert control_rows
    assert all(row["system_action_under_current_threshold"] == "no_link" for row in control_rows)
    assert all(row["researcher_decision"] == "" and row["researcher_notes"] == "" for row in control_rows)
    for row in control_rows:
        assert (row["right_doc_id"], row["left_doc_id"]) not in link_ids
        assert (row["left_doc_id"], row["right_doc_id"]) not in link_ids
    assert len(derived_text.splitlines()) == 3
    for line in derived_text.splitlines():
        assert "me@example.com" not in json.loads(line)["raw_text_audit"]


def test_parent_that_was_not_collected_is_not_invented(tmp_path) -> None:
    document = _document(
        "reddit-child",
        LONG,
        parent_thread_id="missing-parent",
        source_item_id="child-1",
    )
    result = run_normalize_dedupe([document], CONFIG, tmp_path / "out")
    assert result.document_count == 1
    assert result.link_count == 0
    stored = (tmp_path / "out" / "documents_derived.jsonl").read_text(encoding="utf-8")
    assert "missing-parent" not in stored


def _bits(start: int, width: int) -> str:
    return f"{((1 << width) - 1) << start:016x}"


def _sim_document(doc_id: str, simhash: str) -> PreparedDocument:
    words = " ".join(f"{doc_id}w{index}" for index in range(30))
    return PreparedDocument(
        doc_id=doc_id,
        source_platform="reddit",
        source_item_id=doc_id,
        canonical_url=f"https://www.reddit.com/r/googlephotos/comments/{doc_id}",
        author_hash="aaaaaaaaaaaaaaaa",
        content_hash=doc_id,
        simhash=simhash,
        token_count=30,
        normalized_text=words,
    )


def test_calibration_keeps_band_pairs_and_the_ten_nearest_controls(tmp_path) -> None:
    """Distances are disjoint bit blocks, so each pair's Hamming distance is the sum of its blocks.

    In band: hub-auto = 2, hub-revw = 5.
    Out of band at distance 7: auto-revw, then hub with f00..f07.
    The tenth control is auto-f00 at distance 9. auto-f01 is the next pair and stays off the sheet.
    """
    documents = [
        _sim_document("hub", _bits(0, 0)),
        _sim_document("auto", _bits(0, 2)),
        _sim_document("revw", _bits(2, 5)),
    ]
    far_start = 8
    for index in range(8):
        documents.append(_sim_document(f"f{index:02d}", _bits(far_start, 7)))
        far_start += 7
    audits = {document.doc_id: f"Photo note {document.doc_id} only." for document in documents}
    audits["auto"] = "Email " + ("#" * len("nobody@example.invalid")) + " about a missing beach photo."
    reversed_documents = list(reversed(documents))
    links = detect_links(documents, CONFIG, decided_at=RULESET_INSTANT)
    again = detect_links(reversed_documents, CONFIG, decided_at=RULESET_INSTANT)
    rows = select_calibration_rows(reversed_documents, audits, links, CONFIG)
    same = select_calibration_rows(documents, audits, again, CONFIG)

    assert [(row.calibration_rank, row.left_doc_id, row.right_doc_id, row.hamming_distance, row.selection_reason) for row in rows] == [
        (1, "auto", "hub", 2, "automatic_band"),
        (2, "hub", "revw", 5, "review_band"),
        (3, "auto", "revw", 7, "nearest_negative_control"),
        (4, "f00", "hub", 7, "nearest_negative_control"),
        (5, "f01", "hub", 7, "nearest_negative_control"),
        (6, "f02", "hub", 7, "nearest_negative_control"),
        (7, "f03", "hub", 7, "nearest_negative_control"),
        (8, "f04", "hub", 7, "nearest_negative_control"),
        (9, "f05", "hub", 7, "nearest_negative_control"),
        (10, "f06", "hub", 7, "nearest_negative_control"),
        (11, "f07", "hub", 7, "nearest_negative_control"),
        (12, "auto", "f00", 9, "nearest_negative_control"),
    ]
    assert [(row.left_doc_id, row.right_doc_id, row.calibration_rank) for row in same] == [
        (row.left_doc_id, row.right_doc_id, row.calibration_rank) for row in rows
    ]
    assert all(row.researcher_decision == "" and row.researcher_notes == "" for row in rows)
    assert rows[0].system_action_under_current_threshold == "auto_confirmed"
    assert rows[1].system_action_under_current_threshold == "pending_review"
    assert rows[0].left_privacy_safe_excerpt.startswith("Email ")
    assert "nobody@example.invalid" not in rows[0].left_privacy_safe_excerpt
    assert "#" in rows[0].left_privacy_safe_excerpt

    linked = {frozenset((link.doc_id, link.canonical_doc_id)) for link in links}
    controls = [row for row in rows if row.selection_reason == "nearest_negative_control"]
    assert len(controls) == 10
    assert all(frozenset((row.left_doc_id, row.right_doc_id)) not in linked for row in controls)
    queued = open_items(links, opened_at=RULESET_INSTANT)
    queued_links = {item.target_id for item in queued}
    assert {link.link_id for link in links if link.review_state is DuplicateReviewState.pending_review} == queued_links
    assert len(links) == 2

    path = tmp_path / "duplicate_calibration.csv"
    write_calibration_csv(path, rows)
    write_calibration_csv(tmp_path / "again.csv", same)
    assert path.read_bytes() == (tmp_path / "again.csv").read_bytes()
    stored = path.read_text(encoding="utf-8")
    assert "nobody@example.invalid" not in stored
    assert "aaaaaaaaaaaaaaaa" not in stored


def test_rerun_preserves_researcher_decisions_without_new_links(tmp_path) -> None:
    documents = [
        _document("reddit-zzz", LONG, collected_at=datetime(2020, 1, 1, tzinfo=UTC)),
        _document("reddit-aaa", LONG, collected_at=datetime(2026, 1, 1, tzinfo=UTC)),
        _document(
            "reddit-ccc",
            "A separate camera complaint about albums that will not stay sorted "
            "after the phone backup finishes and the library is reopened",
            author_hash="cccccccccccccccc",
        ),
    ]
    output = tmp_path / "out"
    first = run_normalize_dedupe(documents, CONFIG, output)
    path = output / "duplicate_calibration.csv"
    stored = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    assert stored
    for row in stored:
        row["researcher_decision"] = "distinct"
        row["researcher_notes"] = "kept " + "|".join(pair_key(row["left_doc_id"], row["right_doc_id"]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=stored[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(stored)
    links_before = (output / "duplicate_links.jsonl").read_bytes()
    review_before = (output / "duplicate_review.csv").read_bytes()
    queue_before = (output / "review_queue.jsonl").read_bytes()

    second = run_normalize_dedupe(list(reversed(documents)), CONFIG, output)
    after_second = path.read_bytes()
    third = run_normalize_dedupe(documents, CONFIG, output)

    assert path.read_bytes() == after_second
    kept = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    assert len(kept) == len(stored)
    assert {row["researcher_decision"] for row in kept} == {"distinct"}
    assert {row["researcher_notes"] for row in kept} == {
        "kept " + "|".join(pair_key(row["left_doc_id"], row["right_doc_id"])) for row in stored
    }
    assert (output / "duplicate_links.jsonl").read_bytes() == links_before
    assert (output / "duplicate_review.csv").read_bytes() == review_before
    assert (output / "review_queue.jsonl").read_bytes() == queue_before
    assert second.link_count == first.link_count
    assert third.link_count == first.link_count
    assert second.pending_review == first.pending_review
    assert third.pending_review == first.pending_review
    assert second.document_count == 3


def test_calibration_decision_survives_a_swapped_pair_order(tmp_path) -> None:
    rows = select_calibration_rows(
        [
            _sim_document("hub", _bits(0, 0)),
            _sim_document("auto", _bits(0, 2)),
        ],
        {"hub": "hub audit", "auto": "auto audit"},
        (),
        CONFIG,
    )
    path = tmp_path / "duplicate_calibration.csv"
    write_calibration_csv(path, rows)
    recorded = []
    for row in csv.DictReader(path.read_text(encoding="utf-8").splitlines()):
        row["left_doc_id"], row["right_doc_id"] = row["right_doc_id"], row["left_doc_id"]
        row["researcher_decision"] = "distinct"
        row["researcher_notes"] = "same pair either way"
        row["hamming_distance"] = "99"
        recorded.append(row)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(recorded[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(recorded)

    write_calibration_csv(path, rows)
    restored = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    assert len(restored) == 1
    assert restored[0]["researcher_decision"] == "distinct"
    assert restored[0]["researcher_notes"] == "same pair either way"
    assert restored[0]["hamming_distance"] == str(rows[0].hamming_distance)
    assert restored[0]["left_doc_id"] == rows[0].left_doc_id


def test_invalid_calibration_decision_leaves_the_file_unchanged(tmp_path) -> None:
    rows = select_calibration_rows(
        [
            _sim_document("hub", _bits(0, 0)),
            _sim_document("auto", _bits(0, 2)),
        ],
        {"hub": "hub audit", "auto": "auto audit"},
        (),
        CONFIG,
    )
    path = tmp_path / "duplicate_calibration.csv"
    write_calibration_csv(path, rows)
    recorded = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    recorded[0]["researcher_decision"] = "maybe"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(recorded[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(recorded)
    rejected = path.read_bytes()
    with pytest.raises(ValueError, match="distinct, or duplicate"):
        write_calibration_csv(path, rows)
    assert path.read_bytes() == rejected
