"""Phase 4 runner: dry-run, resume, manifest, seed sheet, and no network."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime

import pytest

from src.core.ids import raw_text_sha256, source_url_key
from src.models.duplicate_link import DuplicateLink
from src.models.enums import (
    DecisionTechnicalState,
    DuplicateDecidedBy,
    DuplicateDetectionMethod,
    DuplicateKind,
    DuplicateReviewState,
    ReasonCode,
    ScopeClass,
)
from src.normalize.derive import derive_document
from src.pipeline.stages import PHASE_INSTANT, format_phase4_summary, run_phase4
from src.relevance.seed import SeedReviewError, SeedRow, write_seed_review
from src.review.queue import ReviewItem, append_resolution
from tests.synthetic import make_document

OBVIOUS = "My backup failed overnight and the photos are not syncing."
MIXED = "I can't find the photo from the trip. My backup failed and storage is full."
PLAIN = "Hello from the park with nothing to retrieve."
SECRET = "super-secret-salt-value"
AUTHOR = "cafebabecafebabe"


def _document(doc_id: str, text: str):
    url = f"https://www.reddit.com/r/googlephotos/comments/{doc_id}/"
    document = make_document(
        doc_id=doc_id,
        title="A public title",
        raw_text=text,
        raw_text_sha256=raw_text_sha256(text),
        source_url=url,
        source_url_key=source_url_key(url),
        source_item_id=doc_id,
        author_hash=AUTHOR,
    )
    return document, derive_document(document, derived_at=PHASE_INSTANT)


def _bundle():
    rows = [
        _document("doc-a", PLAIN),
        _document("doc-b", OBVIOUS),
        _document("doc-c", MIXED),
        _document("doc-d", "A second copy that should not be classified."),
    ]
    documents = [row[0] for row in rows]
    derived = [row[1] for row in rows]
    link = DuplicateLink(
        link_id="link-d",
        doc_id="doc-d",
        canonical_doc_id="doc-a",
        duplicate_kind=DuplicateKind.exact_text,
        similarity=1.0,
        method=DuplicateDetectionMethod.simhash,
        method_version="1.0.0",
        review_state=DuplicateReviewState.auto_confirmed,
        decided_by=DuplicateDecidedBy.rules,
        decided_at=PHASE_INSTANT,
    )
    return documents, derived, (link,)


class RecordingProvider:
    provider_name = "fake"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0
        self.prompts: list[str] = []

    def complete_structured(self, prompt, schema, params):
        from src.llm.providers.base import ProviderResponse

        self.calls += 1
        self.prompts.append(prompt)
        if self.text == "raise":
            raise AssertionError("provider should not be called")
        return ProviderResponse(
            text=self.text,
            input_tokens=8,
            output_tokens=4,
            model=params.model,
            provider=self.provider_name,
        )


def _response(doc_id: str, text: str, quote: str) -> str:
    start = text.index(quote)
    return json.dumps(
        {
            "doc_id": doc_id,
            "scope_class": "core_incomplete_recall",
            "reason_code": "known_item_with_incomplete_recall",
            "reason_summary": "A remembered photo could not be retrieved.",
            "confidence": 0.4,
            "is_relevant": False,
            "evidence": {"quote": quote, "start_char": start, "end_char": start + len(quote)},
        }
    )


def _run(tmp_path, **overrides):
    documents, derived, links = _bundle()
    args = dict(
        documents=documents,
        derived=derived,
        links=links,
        output_dir=tmp_path / "phase4",
        stages=["prefilter", "relevance"],
        offline=True,
        provider_name="anthropic",
        model_name="claude-sonnet-4-5",
        api_key="sk-ant-test-secret",
        author_salt=SECRET,
        confidence_review_below=0.7,
        config_hash="abc",
        project_root=tmp_path,
    )
    args.update(overrides)
    return run_phase4(**args)


def test_dry_run_writes_nothing_and_calls_no_provider(tmp_path) -> None:
    provider = RecordingProvider("raise")
    before = sorted(path.name for path in tmp_path.rglob("*"))
    result = _run(tmp_path, dry_run=True, provider=provider, stages=["prefilter", "relevance"])
    after = sorted(path.name for path in tmp_path.rglob("*"))
    assert provider.calls == 0
    assert result.files_written == ()
    assert after == before
    assert result.obvious_exclusion_count == 1
    assert result.mixed_retained == 1
    assert "sk-ant-test-secret" not in format_phase4_summary(result)
    assert SECRET not in format_phase4_summary(result)
    assert AUTHOR not in format_phase4_summary(result)


def test_null_provider_run_records_unavailable_and_does_not_use_the_network(tmp_path, monkeypatch) -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("live network call")

    monkeypatch.setattr(socket, "create_connection", blocked)
    result = _run(tmp_path, stages=["prefilter", "relevance"], offline=True, provider=None)
    assert result.provider_calls == 0
    assert result.relevance_by_state.get("provider_unavailable") == result.relevance_attempted
    assert result.relevance_attempted == result.classify_count
    assert "out_of_scope" not in result.relevance_by_scope
    decisions = [
        json.loads(line)
        for line in (tmp_path / "phase4" / "relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert decisions
    assert all(row["scope_class"] is None for row in decisions)
    assert all(row["evidence"] == [] for row in decisions)
    assert all(row["technical_state"] == "provider_unavailable" for row in decisions)
    blob = (tmp_path / "phase4").read_text() if False else "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "phase4").rglob("*")
        if path.is_file() and path.suffix != ".csv"
    )
    seed = (tmp_path / "phase4" / "relevance_seed_review.csv").read_text(encoding="utf-8")
    assert SECRET not in blob and SECRET not in seed
    assert AUTHOR not in blob and AUTHOR not in seed
    assert "sk-ant-test-secret" not in blob


def test_resume_skips_completed_relevance_work(tmp_path) -> None:
    documents, derived, links = _bundle()
    provider = RecordingProvider(_response("doc-a", PLAIN, "Hello from the park"))
    first = run_phase4(
        documents,
        derived,
        links,
        output_dir=tmp_path / "phase4",
        stages=["relevance"],
        provider=provider,
        provider_name="fake",
        model_name="claude-sonnet-4-5",
        offline=False,
        project_root=tmp_path,
    )
    assert provider.calls == first.relevance_attempted
    cache = tmp_path / "cache"
    if cache.exists():
        for path in cache.rglob("*.json"):
            path.unlink()
    again = RecordingProvider("raise")
    second = run_phase4(
        documents,
        derived,
        links,
        output_dir=tmp_path / "phase4",
        stages=["relevance"],
        provider=again,
        provider_name="fake",
        model_name="claude-sonnet-4-5",
        offline=False,
        resume=first.run_id,
        project_root=tmp_path,
    )
    assert again.calls == 0
    assert second.provider_calls == 0


def test_manifest_funnel_counts(tmp_path) -> None:
    result = _run(tmp_path, stages=["prefilter"])
    manifest = json.loads((tmp_path / "phase4" / "run_manifest.json").read_text(encoding="utf-8"))
    funnel = manifest["funnel"]["prefilter"]
    assert funnel["obvious_exclusion_candidate"] == 1
    assert funnel["mixed_retained"] == 1
    assert funnel["skipped_non_canonical"] == 1
    assert funnel["classify"] == 2
    assert funnel["drop_reasons"] == {"storage_backup_or_sync": 1}
    assert "volatile_fields_excluded" in manifest
    assert manifest["cache"]["provider_calls"] == 0
    assert SECRET not in json.dumps(manifest)
    assert AUTHOR not in json.dumps(manifest)


def test_seed_sheet_is_private_ordered_and_keeps_human_fields(tmp_path) -> None:
    text = "Please write nobody@example.invalid if you agree. Nothing else."
    document, derived = _document("doc-b", text)
    other, other_derived = _document("doc-a", PLAIN)
    from src.relevance.rules import prefilter_document

    rows = [
        _seed(document, derived, prefilter_document(document.doc_id, derived.normalized_text)),
        _seed(other, other_derived, prefilter_document(other.doc_id, other_derived.normalized_text)),
    ]
    path = tmp_path / "relevance_seed_review.csv"
    write_seed_review(path, list(reversed(rows)))
    stored = path.read_text(encoding="utf-8")
    assert "nobody@example.invalid" not in stored
    assert AUTHOR not in stored
    assert SECRET not in stored
    assert "model" not in stored.splitlines()[0]
    assert "prediction" not in stored
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        loaded = list(csv.DictReader(handle))
    assert [row["doc_id"] for row in loaded] == ["doc-a", "doc-b"]
    assert all(row["human_scope_class"] == "" for row in loaded)
    assert all(row["human_reason_code"] == "" for row in loaded)
    assert all(row["human_notes"] == "" for row in loaded)
    header = list(loaded[0])
    loaded[0]["human_scope_class"] = "core_incomplete_recall"
    loaded[0]["human_reason_code"] = "known_item_with_incomplete_recall"
    loaded[0]["human_notes"] = "kept note"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(loaded)
    write_seed_review(path, rows)
    with path.open(encoding="utf-8", newline="") as handle:
        again = list(csv.DictReader(handle))
    kept = next(row for row in again if row["doc_id"] == loaded[0]["doc_id"])
    assert kept["human_scope_class"] == "core_incomplete_recall"
    assert kept["human_reason_code"] == "known_item_with_incomplete_recall"
    assert kept["human_notes"] == "kept note"
    assert [row["doc_id"] for row in again] == ["doc-a", "doc-b"]

    good = path.read_text(encoding="utf-8")
    with path.open(encoding="utf-8", newline="") as handle:
        bad = list(csv.DictReader(handle))
    bad[0]["human_scope_class"] = "core"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(bad)
    invalid = path.read_text(encoding="utf-8")
    with pytest.raises(SeedReviewError):
        write_seed_review(path, rows)
    assert path.read_text(encoding="utf-8") == invalid
    assert path.read_text(encoding="utf-8") != good


def test_resume_preserves_a_human_resolution(tmp_path) -> None:
    documents, derived, links = _bundle()
    provider = RecordingProvider(_response("doc-c", MIXED, "I can't find the photo"))
    run_phase4(
        documents,
        derived,
        links,
        output_dir=tmp_path / "phase4",
        stages=["relevance"],
        provider=provider,
        provider_name="fake",
        model_name="claude-sonnet-4-5",
        offline=False,
        project_root=tmp_path,
    )
    queue_path = tmp_path / "phase4" / "review_queue.jsonl"
    items = [ReviewItem.model_validate_json(line) for line in queue_path.read_text(encoding="utf-8").splitlines()]
    opened = next(item for item in items if item.state == "open")
    resolved = append_resolution(
        items,
        opened.item_id,
        decision="accept",
        resolver="researcher",
        resolved_at=datetime(2026, 9, 27, tzinfo=UTC),
    )
    queue_path.write_text(
        "".join(item.model_dump_json() + "\n" for item in resolved),
        encoding="utf-8",
    )
    run_phase4(
        documents,
        derived,
        links,
        output_dir=tmp_path / "phase4",
        stages=["relevance"],
        provider=provider,
        provider_name="fake",
        model_name="claude-sonnet-4-5",
        offline=False,
        resume=None,
        project_root=tmp_path,
    )
    again = queue_path.read_text(encoding="utf-8")
    assert "researcher" in again
    assert "accept" in again


def test_prompt_sent_to_the_provider_is_the_audit_text(tmp_path) -> None:
    text = "Email nobody@example.invalid about the park."
    document, derived = _document("doc-z", text)
    assert "nobody@example.invalid" not in derived.raw_text_audit
    provider = RecordingProvider(
        _response("doc-z", derived.raw_text_audit, "about the park")
    )
    run_phase4(
        [document],
        [derived],
        [],
        output_dir=tmp_path / "phase4",
        stages=["relevance"],
        provider=provider,
        provider_name="fake",
        model_name="claude-sonnet-4-5",
        offline=False,
        project_root=tmp_path,
    )
    assert provider.prompts
    assert "nobody@example.invalid" not in provider.prompts[0]
    assert document.raw_text not in provider.prompts[0]
    decision = json.loads(
        (tmp_path / "phase4" / "relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert decision["technical_state"] == DecisionTechnicalState.ok.value
    assert decision["is_relevant"] is True
    assert decision["confidence"] == 0.4
    assert ReasonCode.low_confidence.value in (tmp_path / "phase4" / "review_queue.jsonl").read_text(encoding="utf-8")


def _seed(document, derived, prefilter) -> SeedRow:
    from src.relevance.seed import seed_row_from_prefilter

    return seed_row_from_prefilter(
        doc_id=document.doc_id,
        source_platform=document.source_platform.value,
        source_type=document.source_type.value,
        title=document.title,
        raw_text_audit=derived.raw_text_audit,
        prefilter=prefilter,
    )


def _labeled(doc_id: str, title: str, scope: str, reason: str, notes: str) -> SeedRow:
    return SeedRow(
        doc_id=doc_id,
        source_platform="reddit",
        source_type="post",
        title=title,
        privacy_safe_excerpt=f"excerpt for {doc_id}",
        prefilter_route="classify",
        prefilter_reason_codes="retained_for_recall",
        human_scope_class=scope,
        human_reason_code=reason,
        human_notes=notes,
    )


def _read_seed(path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_completed_human_labels_are_accepted(tmp_path) -> None:
    rows = [
        _labeled(
            "doc-a",
            "Alpha",
            "core_incomplete_recall",
            "known_item_with_incomplete_recall",
            "core note",
        ),
        _labeled(
            "doc-b",
            "Beta",
            "adjacent_known_item_retrieval",
            "known_item_with_precise_recall_failure",
            "adjacent note",
        ),
        _labeled(
            "doc-c",
            "Gamma",
            "out_of_scope",
            "storage_backup_or_sync",
            "exclusion note",
        ),
    ]
    path = tmp_path / "relevance_seed_review.csv"
    write_seed_review(path, list(reversed(rows)))
    stored = {row["doc_id"]: row for row in _read_seed(path)}
    assert stored["doc-a"]["human_notes"] == "core note"
    assert stored["doc-b"]["human_reason_code"] == "known_item_with_precise_recall_failure"
    assert stored["doc-c"]["human_scope_class"] == "out_of_scope"


def test_invalid_scope_reason_pairs_review_codes_and_free_text_are_rejected(tmp_path) -> None:
    path = tmp_path / "relevance_seed_review.csv"
    approved = [
        _labeled(
            "doc-a",
            "Alpha",
            "core_incomplete_recall",
            "known_item_query_unformulable",
            "kept",
        )
    ]
    write_seed_review(path, approved)
    original = path.read_text(encoding="utf-8")
    rejected = [
        ("core_incomplete_recall", "storage_backup_or_sync", "inclusion with an exclusion code"),
        ("out_of_scope", "known_item_with_incomplete_recall", "exclusion with an inclusion code"),
        ("adjacent_known_item_retrieval", "low_confidence", "review code"),
        ("out_of_scope", "not a reason code", "free text"),
        ("core", "known_item_with_incomplete_recall", "unknown scope"),
    ]
    for scope, reason, _label in rejected:
        import csv

        with path.open(encoding="utf-8", newline="") as handle:
            loaded = list(csv.DictReader(handle))
        loaded[0]["human_scope_class"] = scope
        loaded[0]["human_reason_code"] = reason
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(loaded[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(loaded)
        snapshot = path.read_text(encoding="utf-8")
        with pytest.raises(SeedReviewError):
            write_seed_review(path, approved)
        assert path.read_text(encoding="utf-8") == snapshot
        path.write_text(original, encoding="utf-8")


def test_missing_and_duplicate_doc_ids_are_rejected(tmp_path) -> None:
    path = tmp_path / "relevance_seed_review.csv"
    blank = _labeled("doc-a", "Alpha", "out_of_scope", "account_access", "note")
    write_seed_review(path, [blank])
    original = path.read_text(encoding="utf-8")
    with pytest.raises(SeedReviewError, match="empty doc_id"):
        write_seed_review(
            path,
            [_labeled("  ", "Alpha", "out_of_scope", "account_access", "note")],
        )
    assert path.read_text(encoding="utf-8") == original
    with pytest.raises(SeedReviewError, match="repeats doc_id"):
        write_seed_review(
            path,
            [
                _labeled("doc-a", "Alpha", "out_of_scope", "account_access", "one"),
                _labeled("doc-a", "Other", "out_of_scope", "account_access", "two"),
            ],
        )
    assert path.read_text(encoding="utf-8") == original

    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        loaded = list(csv.DictReader(handle))
    duplicate = loaded + [dict(loaded[0])]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(loaded[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(duplicate)
    snapshot = path.read_text(encoding="utf-8")
    with pytest.raises(SeedReviewError, match="repeats doc_id"):
        write_seed_review(path, [blank])
    assert path.read_text(encoding="utf-8") == snapshot


def test_regeneration_keeps_human_fields_on_the_same_document(tmp_path) -> None:
    approved = [
        _labeled(
            "doc-b",
            "Beta title",
            "adjacent_known_item_retrieval",
            "known_item_retrieval_journey_described",
            "beta note",
        ),
        _labeled(
            "doc-a",
            "Alpha title",
            "core_incomplete_recall",
            "known_item_cue_not_recognized",
            "alpha note",
        ),
    ]
    path = tmp_path / "relevance_seed_review.csv"
    write_seed_review(path, approved)
    before = {row["doc_id"]: row for row in _read_seed(path)}
    regenerated = list(reversed(approved))
    write_seed_review(path, regenerated)
    after = {row["doc_id"]: row for row in _read_seed(path)}
    assert list(after) == ["doc-a", "doc-b"]
    for doc_id, row in after.items():
        assert row["human_scope_class"] == before[doc_id]["human_scope_class"]
        assert row["human_reason_code"] == before[doc_id]["human_reason_code"]
        assert row["human_notes"] == before[doc_id]["human_notes"]
        assert row["title"] == before[doc_id]["title"]
        assert row["privacy_safe_excerpt"] == before[doc_id]["privacy_safe_excerpt"]
        assert row["prefilter_route"] == before[doc_id]["prefilter_route"]
        assert row["prefilter_reason_codes"] == before[doc_id]["prefilter_reason_codes"]
        assert row["source_platform"] == before[doc_id]["source_platform"]
        assert row["source_type"] == before[doc_id]["source_type"]
    assert after["doc-a"]["human_notes"] == "alpha note"
    assert after["doc-b"]["title"] == "Beta title"
    assert after["doc-a"]["title"] != after["doc-b"]["title"]


def test_scope_classes_remain_distinct_in_storage() -> None:
    assert ScopeClass.core_incomplete_recall.value != ScopeClass.adjacent_known_item_retrieval.value
    assert ScopeClass.out_of_scope.value not in {
        ScopeClass.core_incomplete_recall.value,
        ScopeClass.adjacent_known_item_retrieval.value,
    }
