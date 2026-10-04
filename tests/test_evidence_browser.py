"""Local evidence browser. Fixtures are synthetic; one test reads saved development outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.browse.page import render_page
from src.browse.snapshot import BrowserPaths, build_snapshot

HOLDOUT_TEXT = "HOLDOUT_SECRET_TEXT_SHOULD_NOT_RENDER"
HOLD_AUDIT = "HOLDOUT_AUDIT_SECRET_SHOULD_NOT_RENDER"


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _paths(tmp_path: Path) -> BrowserPaths:
    split = tmp_path / "split.csv"
    split.write_text(
        "doc_id,split,stratum,split_version\n"
        "dev-a,development,core_incomplete_recall,relevance-seed-split/v1\n"
        "dev-b,development,core_incomplete_recall,relevance-seed-split/v1\n"
        "hold-1,holdout,core_incomplete_recall,relevance-seed-split/v1\n",
        encoding="utf-8",
    )
    audit = "I cannot find the birthday photo from last summer in my backup."
    quote = "birthday photo"
    start = audit.index(quote)
    end = start + len(quote)
    _write_jsonl(
        tmp_path / "collected.jsonl",
        [
            {
                "doc_id": "dev-a",
                "raw_text": "I cannot find the birthday photo from last summer in my backup.",
                "source_platform": "google_support",
                "source_url": "https://support.google.com/photos/thread/example",
                "source_type": "support_thread",
            },
            {
                "doc_id": "dev-b",
                "raw_text": "same text as the canonical document for duplicate counting",
                "source_platform": "google_support",
                "source_url": "https://support.google.com/photos/thread/copy",
                "source_type": "support_thread",
            },
            {
                "doc_id": "hold-1",
                "raw_text": HOLDOUT_TEXT,
                "source_platform": "reddit",
                "source_url": "https://example.invalid/holdout",
                "source_type": "forum_post",
            },
        ],
    )
    _write_jsonl(
        tmp_path / "derived.jsonl",
        [
            {"doc_id": "dev-a", "raw_text_audit": audit},
            {"doc_id": "dev-b", "raw_text_audit": "duplicate audit"},
            {"doc_id": "hold-1", "raw_text_audit": HOLD_AUDIT},
        ],
    )
    _write_jsonl(
        tmp_path / "links.jsonl",
        [
            {
                "doc_id": "dev-b",
                "canonical_doc_id": "dev-a",
                "review_state": "auto_confirmed",
            }
        ],
    )
    (tmp_path / "labels.csv").write_text(
        "doc_id,human_scope_class\n"
        "dev-a,core_incomplete_recall\n"
        "dev-b,out_of_scope\n"
        "hold-1,core_incomplete_recall\n",
        encoding="utf-8",
    )
    _write_jsonl(tmp_path / "relevance.jsonl", [])
    _write_jsonl(tmp_path / "human.jsonl", [])
    run = tmp_path / "extract"
    _write_jsonl(
        run / "extraction_inputs.jsonl",
        [
            {"doc_id": "dev-a", "technical_state": "ok", "scope_class": "core_incomplete_recall"},
            {"doc_id": "dev-b", "technical_state": "provider_error", "scope_class": "adjacent_known_item_retrieval"},
        ],
    )
    _write_jsonl(
        run / "extraction_failures.jsonl",
        [{"doc_id": "dev-b", "case_id": "dev-b#u1", "error_class": "provider_error"}],
    )
    _write_jsonl(
        run / "retrieval_cases.jsonl",
        [
            {
                "case_id": "dev-a#c01",
                "doc_id": "dev-a",
                "scope_class": "core_incomplete_recall",
                "validation_state": "valid",
                "target_asset_type": "photo",
                "target_asset_type_observation": "stated",
                "retrieval_trigger": "search backup",
                "retrieval_trigger_observation": "stated",
                "outcome": "not_found",
                "outcome_observation": "stated",
                "remembered_cues": [{"value": "time"}],
                "remembered_cues_observation": "stated",
                "query_strategies": [{"value": "metadata_filter"}],
                "query_strategies_observation": "stated",
                "system_responses": [{"value": "no_results"}],
                "system_responses_observation": "stated",
                "problem_summary": "cannot find a birthday photo",
                "problem_summary_observation": "stated",
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
    _write_jsonl(
        run / "review_queue.jsonl",
        [
            {
                "item_id": "open-b",
                "target_id": "dev-b",
                "state": "open",
                "reason_code": "provider_unavailable",
            }
        ],
    )
    _write_jsonl(tmp_path / "p4.jsonl", [])
    _write_jsonl(tmp_path / "p3.jsonl", [])
    return BrowserPaths(
        collected=tmp_path / "collected.jsonl",
        derived=tmp_path / "derived.jsonl",
        links=tmp_path / "links.jsonl",
        split=split,
        labels=tmp_path / "labels.csv",
        relevance=tmp_path / "relevance.jsonl",
        human_relevance=tmp_path / "human.jsonl",
        extraction=run,
        phase4_reviews=tmp_path / "p4.jsonl",
        phase3_reviews=tmp_path / "p3.jsonl",
        corrections=tmp_path / "corrections.jsonl",
    )


@pytest.mark.synthetic
def test_browser_hides_holdout_and_keeps_failures_out_of_conclusions(tmp_path: Path) -> None:
    snapshot = build_snapshot(_paths(tmp_path))
    page = render_page(snapshot)

    assert snapshot.withheld_holdout == 1
    assert snapshot.collected == 2
    assert snapshot.analysis_documents == 1
    assert snapshot.confirmed_duplicates == 1
    assert snapshot.failed == 1
    assert snapshot.automatically_valid == 1
    assert snapshot.semantically_approved == 0
    assert snapshot.groups == ()
    assert snapshot.core.model_cases == 1
    assert snapshot.adjacent.model_cases == 0
    assert snapshot.core.sources == (("google_support", 1),)
    assert HOLDOUT_TEXT not in page
    assert HOLD_AUDIT not in page
    assert "not semantically approved" in page
    assert "No extraction case is semantically approved" in page
    assert "birthday photo" in page
    assert "<mark>" in page
    assert "dev-b" in page
    assert "research conclusion" in page
    card = next(item for item in snapshot.cards if item.case_id == "dev-a#c01")
    assert card.enters_conclusions is False
    assert card.quotes[0].offset_matches is True


@pytest.mark.synthetic
def test_open_semantic_finding_blocks_approval_and_preserves_model_output(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    collected = paths.collected.read_text(encoding="utf-8").replace("dev-a", "google_support-d7f386f347b7")
    paths.collected.write_text(collected, encoding="utf-8")
    for name in ("derived.jsonl",):
        path = tmp_path / name
        path.write_text(path.read_text(encoding="utf-8").replace("dev-a", "google_support-d7f386f347b7"), encoding="utf-8")
    split = paths.split.read_text(encoding="utf-8").replace("dev-a", "google_support-d7f386f347b7")
    paths.split.write_text(split, encoding="utf-8")
    labels = paths.labels.read_text(encoding="utf-8").replace("dev-a", "google_support-d7f386f347b7")
    paths.labels.write_text(labels, encoding="utf-8")
    links = paths.links.read_text(encoding="utf-8").replace("dev-a", "google_support-d7f386f347b7")
    paths.links.write_text(links, encoding="utf-8")
    case_path = paths.extraction / "retrieval_cases.jsonl"
    case_path.write_text(case_path.read_text(encoding="utf-8").replace("dev-a", "google_support-d7f386f347b7"), encoding="utf-8")
    inputs = paths.extraction / "extraction_inputs.jsonl"
    inputs.write_text(inputs.read_text(encoding="utf-8").replace("dev-a", "google_support-d7f386f347b7"), encoding="utf-8")
    paths.corrections.write_text(
        json.dumps(
            {
                "case_id": "google_support-d7f386f347b7#c01",
                "field": "semantic_approval",
                "original_value": "automatically valid",
                "corrected_value": "approved",
                "reviewer": "reviewer",
                "note": "fixture",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = case_path.read_text(encoding="utf-8")
    snapshot = build_snapshot(paths)

    assert snapshot.corrections[0].corrected_value == "approved"
    assert snapshot.semantically_approved == 0
    assert snapshot.groups == ()
    assert case_path.read_text(encoding="utf-8") == before
    assert "search backup" in render_page(snapshot)


@pytest.mark.synthetic
def test_missing_inputs_render_empty_states(tmp_path: Path) -> None:
    snapshot = build_snapshot(
        BrowserPaths(
            collected=tmp_path / "missing.jsonl",
            derived=tmp_path / "missing-derived.jsonl",
            links=tmp_path / "missing-links.jsonl",
            split=tmp_path / "missing-split.csv",
            labels=tmp_path / "missing-labels.csv",
            relevance=tmp_path / "missing-relevance.jsonl",
            human_relevance=tmp_path / "missing-human.jsonl",
            extraction=tmp_path / "missing-extract",
            phase4_reviews=tmp_path / "missing-p4.jsonl",
            phase3_reviews=tmp_path / "missing-p3.jsonl",
            corrections=tmp_path / "missing-corrections.jsonl",
        )
    )
    page = render_page(snapshot)

    assert snapshot.collected == 0
    assert snapshot.automatically_valid == 0
    assert "No stored extraction evidence" in page
    assert "No automatically valid core case" in page
    assert "No human corrections are recorded" in page


def test_saved_development_outputs_are_not_treated_as_conclusions() -> None:
    snapshot = build_snapshot()
    page = render_page(snapshot)
    holdout = set()
    split = Path("data/interim/phase4/relevance_split_manifest.csv")
    for line in split.read_text(encoding="utf-8").splitlines()[1:]:
        doc_id, split_name, *_rest = line.split(",")
        if split_name == "holdout":
            holdout.add(doc_id)

    assert snapshot.withheld_holdout == 15
    assert snapshot.collected == 35
    assert snapshot.analysis_documents == 35
    assert snapshot.automatically_valid == 2
    assert snapshot.semantically_approved == 0
    assert snapshot.failed == 2
    assert snapshot.core.model_cases == 2
    assert snapshot.adjacent.model_cases == 0
    assert snapshot.groups == ()
    assert snapshot.corrections == ()
    assert {card.doc_id for card in snapshot.cards}.isdisjoint(holdout)
    assert "search backup" in page
    assert "car search option" in page
    assert "spliced" in page.lower() or "ellipsis" in page
    assert "not semantically approved" in page
    assert "No extraction case is semantically approved" in page
    assert "retrieval_trigger must be the stated reason" in page
