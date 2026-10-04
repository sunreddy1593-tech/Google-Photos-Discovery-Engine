"""Prepared submission exports. Fixtures are synthetic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.export.build import build_submission
from src.export.compare import comparison
from src.export.load import browser_cards, filter_cards, load_submission
from src.export.present import highlight_excerpt
from src.export.privacy import leak_findings
from src.models.export import PublicExportRecord
from src.normalize.privacy import redact

HOLDOUT_TEXT = "HOLDOUT_SECRET_TEXT_SHOULD_NOT_RENDER"
HOLDOUT_NOTE = "HOLDOUT_NOTE_SECRET"
FULL_HASH = "a" * 64
EMAIL = "secret.user@example.com"
PHONE = "415-555-0199"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _fixture(tmp_path: Path) -> Path:
    raw = f"Contact {EMAIL} or {PHONE} about the birthday photo from last summer."
    audit, _spans = redact(raw)
    quote = "birthday photo"
    start = audit.index(quote)
    end = start + len(quote)
    split = tmp_path / "split.csv"
    split.write_text(
        "doc_id,split,stratum,split_version\n"
        "dev-a,development,core_incomplete_recall,relevance-seed-split/v1\n"
        "dev-b,development,out_of_scope,relevance-seed-split/v1\n"
        "dev-empty,development,adjacent_known_item_retrieval,relevance-seed-split/v1\n"
        "hold-1,holdout,core_incomplete_recall,relevance-seed-split/v1\n",
        encoding="utf-8",
    )
    collected = tmp_path / "collected.jsonl"
    _write_jsonl(
        collected,
        [
            _document("dev-a", raw, FULL_HASH),
            _document("dev-b", "The upload failed before I could search.", "b" * 64),
            _document("dev-empty", "I scrolled the album and found no case text.", "d" * 64),
            _document("hold-1", HOLDOUT_TEXT, "c" * 64),
        ],
    )
    derived = tmp_path / "derived.jsonl"
    _write_jsonl(
        derived,
        [
            {"doc_id": "dev-a", "raw_text_audit": audit, "canonical_url": "https://example.com/a", "normalizer_version": "1.0.0"},
            {"doc_id": "dev-b", "raw_text_audit": "The upload failed before I could search.", "canonical_url": "https://example.com/b", "normalizer_version": "1.0.0"},
            {"doc_id": "dev-empty", "raw_text_audit": "I scrolled the album and found no case text.", "canonical_url": "https://example.com/empty", "normalizer_version": "1.0.0"},
            {"doc_id": "hold-1", "raw_text_audit": HOLDOUT_TEXT, "canonical_url": "https://example.com/hold", "normalizer_version": "1.0.0"},
        ],
    )
    links = tmp_path / "links.jsonl"
    _write_jsonl(links, [])
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "doc_id,human_scope_class,human_reason_code,human_notes\n"
        "dev-a,core_incomplete_recall,known_item,\n"
        "dev-b,out_of_scope,no_retrieval_need,\n"
        "dev-empty,adjacent_known_item_retrieval,known_item,\n"
        f"hold-1,core_incomplete_recall,known_item,{HOLDOUT_NOTE}\n",
        encoding="utf-8",
    )
    relevance = tmp_path / "relevance.jsonl"
    _write_jsonl(
        relevance,
        [
            {
                "doc_id": "dev-a",
                "technical_state": "ok",
                "validation_state": "valid",
                "scope_class": "core_incomplete_recall",
                "reason_code": "known_item",
                "reason_summary": "The model says the photo could not be found.",
                "needs_human_review": False,
                "evidence": [
                    {
                        "field_name": "scope_class",
                        "quote": quote,
                        "start_char": start,
                        "end_char": end,
                        "validation_state": "valid",
                    }
                ],
            }
        ],
    )
    run = tmp_path / "extract"
    _write_jsonl(
        run / "extraction_inputs.jsonl",
        [
            {"doc_id": "dev-a", "technical_state": "ok", "scope_class": "core_incomplete_recall"},
            {"doc_id": "dev-b", "technical_state": "provider_error", "scope_class": "out_of_scope"},
            {"doc_id": "dev-empty", "technical_state": "ok", "scope_class": "adjacent_known_item_retrieval"},
        ],
    )
    _write_jsonl(
        run / "extraction_failures.jsonl",
        [
            {
                "doc_id": "dev-b",
                "error_class": "provider_error",
                "reason_codes": ["provider_error"],
                "provider_diagnostic": {
                    "http_status": 400,
                    "error_code": "json_validate_failed",
                    "error_message": "do not copy this message",
                    "rejected_output_summary": {
                        "application_state": "not_checked",
                        "character_count": 0,
                        "json_error_position": 0,
                        "json_state": "invalid_json",
                    },
                },
                "validation_errors": ["do not copy validation prose"],
                "raw_response_ref": "secret-body",
            }
        ],
    )
    _write_jsonl(
        run / "extraction_candidates.jsonl",
        [
            {
                "doc_id": "dev-b",
                "case_id": "dev-b#bad",
                "technical_state": "evidence_validation_failed",
                "case": {
                    "problem_summary": "A summary the model wrote.",
                    "all_evidence_spans": [
                        {
                            "field_name": "problem_summary",
                            "quote": "birthday ... spliced",
                            "start_char": 0,
                            "end_char": 8,
                            "validation_state": "invalid",
                        }
                    ],
                },
                "candidate": {
                    "field_evidence": [
                        {
                            "field_name": "problem_summary",
                            "quote": "upload failed before I could search for a missing sentence",
                        },
                        {"field_name": "outcome", "quote": "The upload failed"},
                    ]
                },
            }
        ],
    )
    _write_jsonl(
        run / "retrieval_cases.jsonl",
        [
            {
                "case_id": "dev-a#c01",
                "doc_id": "dev-a",
                "scope_class": "core_incomplete_recall",
                "validation_state": "valid",
                "prompt_version": "extract/v2",
                "target_asset_type": "photo",
                "target_asset_type_observation": "stated",
                "retrieval_trigger": "search backup",
                "retrieval_trigger_observation": "stated",
                "remembered_cues": [{"value": "time"}],
                "remembered_cues_observation": "stated",
                "query_strategies": [{"value": "metadata_filter"}],
                "query_strategies_observation": "stated",
                "system_responses": [{"value": "no_results"}],
                "system_responses_observation": "stated",
                "outcome": "not_found",
                "outcome_observation": "stated",
                "problem_summary": "cannot find a birthday photo",
                "all_evidence_spans": [
                    {
                        "field_name": "target_asset_type",
                        "quote": quote,
                        "start_char": start,
                        "end_char": end,
                        "validation_state": "valid",
                    }
                ],
            }
        ],
    )
    _write_jsonl(run / "review_queue.jsonl", [])
    manifest = {
        "submission_id": "fixture",
        "frozen_split": "split.csv",
        "not_combined": ["Overlapping imports are not added together."],
        "datasets": [
            {
                "dataset_id": "fixture-dev",
                "description": "Synthetic development dataset.",
                "split_policy": "development_only",
                "collected": "collected.jsonl",
                "derived": "derived.jsonl",
                "links": "links.jsonl",
                "labels": "labels.csv",
                "relevance": "relevance.jsonl",
                "reviews": ["extract/review_queue.jsonl"],
                "corrections": "missing-corrections.jsonl",
                "extraction_run": {"run_id": "run-1", "path": "extract"},
                "limitations": ["This fixture is not a population."],
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _document(doc_id: str, raw_text: str, author_hash: str) -> dict[str, object]:
    return {
        "doc_id": doc_id,
        "source_platform": "google_support",
        "source_type": "support_thread",
        "evidence_tier": "direct_user",
        "source_name": "Google Photos Help",
        "source_url": f"https://example.com/{doc_id}",
        "published_at": "2024-01-02T00:00:00+00:00",
        "collected_at": "2024-02-03T00:00:00+00:00",
        "author_hash": author_hash,
        "raw_text": raw_text,
    }


@pytest.mark.synthetic
def test_export_hides_holdout_and_keeps_quote_offsets(tmp_path: Path) -> None:
    manifest = _fixture(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    destination = tmp_path / "export"
    build_submission(manifest, destination, root=tmp_path)
    after = {path: path.read_bytes() for path in before}
    assert after == before

    text = "\n".join(path.read_text(encoding="utf-8") for path in destination.rglob("*") if path.is_file())
    assert HOLDOUT_TEXT not in text
    assert HOLDOUT_NOTE not in text
    assert EMAIL not in text
    assert PHONE not in text
    assert FULL_HASH not in text
    assert "do not copy this message" not in text
    assert "do not copy validation prose" not in text
    assert "secret-body" not in text
    assert "raw_text" not in text
    assert leak_findings(json.loads((destination / "index.json").read_text(encoding="utf-8"))) == []

    loaded = load_submission(destination)
    assert loaded["ok"] is True
    summary = loaded["datasets"]["fixture-dev"]["summary"]
    assert summary["documents"] == 3
    assert summary["withheld_evaluation_documents"] == 1
    assert summary["extraction_attempts"] == 3
    assert summary["stored_cases"] == 1
    assert summary["automatically_valid_cases"] == 1
    assert summary["semantically_approved_cases"] == 0
    assert summary["failed_attempts"] == 1
    assert summary["empty_responses"] == 1
    assert summary["human_relevance_labels"] == 3
    assert summary["human_labeled_out_of_scope"] == 1

    case = PublicExportRecord.model_validate(loaded["datasets"]["fixture-dev"]["cases"][0])
    span = case.evidence_spans[0]
    assert case.excerpt[span.excerpt_start_char : span.excerpt_end_char] == span.quote
    assert span.document_start_char - case.excerpt_start_char == span.excerpt_start_char
    assert case.excerpt_is_full_text is False
    assert "<mark>" in highlight_excerpt(case.excerpt, [span.model_dump()])
    assert case.author_key == FULL_HASH[:12]

    cards = browser_cards(loaded["datasets"]["fixture-dev"])
    failed = [card for card in cards if card.get("attempt_kind") == "failed"]
    empty = [card for card in cards if card.get("attempt_kind") == "empty_response"]
    assert failed[0]["enters_conclusions"] is False
    assert empty[0]["enters_conclusions"] is False
    assert "birthday ... spliced" in failed[0]["rejected_model_text"]
    assert "upload failed before I could search for a missing sentence" in failed[0]["rejected_model_text"]
    assert "The upload failed" not in failed[0]["rejected_model_text"]
    assert comparison(cards, approved_only=True)["case_count"] == 0
    inspection = comparison(cards, approved_only=False)
    assert inspection["core"]["case_count"] == 1
    assert inspection["adjacent"]["case_count"] == 0
    shown = filter_cards(cards, source="reddit")
    assert shown == []
    assert len(filter_cards(cards, review_status="automatically valid; not semantically approved")) == 1


@pytest.mark.synthetic
def test_missing_export_is_an_empty_state(tmp_path: Path) -> None:
    loaded = load_submission(tmp_path / "absent")
    assert loaded["ok"] is False
    assert "Prepared export is missing" in loaded["message"]
