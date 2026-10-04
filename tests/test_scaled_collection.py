"""Scaled collection records a blocked source and keeps the other source."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.collect.scaled import dedupe, run_scaled_collection

WHEN = datetime(2026, 10, 4, tzinfo=timezone.utc)


def _row(doc_id: str, platform: str) -> dict[str, object]:
    return {
        "doc_id": doc_id,
        "source_platform": platform,
        "source_type": "post",
        "collection_method": "manual_jsonl",
    }


@pytest.mark.synthetic
def test_dedupe_keeps_one_row_per_document() -> None:
    rows = dedupe([_row("a", "reddit"), _row("a", "reddit"), _row("b", "youtube")])
    assert [row["doc_id"] for row in rows] == ["a", "b"]


@pytest.mark.synthetic
def test_a_failed_source_does_not_stop_the_other(tmp_path) -> None:
    calls: list[str] = []

    def youtube() -> dict[str, object]:
        calls.append("youtube")
        raise RuntimeError("blocked")

    def reddit() -> dict[str, object]:
        calls.append("reddit")
        return {
            "source": "reddit",
            "status": "skipped",
            "reason": "source disabled: Reddit credentials are absent",
            "requests_made": 0,
            "documents_written": 0,
            "stopped_reason": None,
        }

    existing = tmp_path / "existing.jsonl"
    existing.write_text(
        "".join(json.dumps(_row(f"doc-{index}", "google_support")) + "\n" for index in range(3)),
        encoding="utf-8",
    )
    report = run_scaled_collection(
        output_dir=tmp_path / "corpus",
        existing_paths=[existing],
        youtube=youtube,
        reddit=reddit,
        resume=False,
        run_id="scaled-test",
        occurred_at=WHEN,
    )
    assert calls == ["youtube", "reddit"]
    assert report["documents"] == 3
    assert report["by_platform"] == {"google_support": 3}
    assert report["model_stages_run"] is False
    statuses = {row["source"]: row["status"] for row in report["sources"]}
    assert statuses == {"youtube": "failed", "reddit": "skipped"}


@pytest.mark.synthetic
def test_resume_does_not_call_a_finished_source(tmp_path) -> None:
    output = tmp_path / "corpus"
    output.mkdir()
    (output / "checkpoint.json").write_text(
        json.dumps(
            {
                "run_id": "scaled-test",
                "sources": {
                    "youtube": {
                        "source": "youtube",
                        "status": "collected",
                        "reason": "document_limit",
                        "requests_made": 4,
                        "documents_written": 2,
                        "stopped_reason": "document_limit",
                    },
                    "reddit": {
                        "source": "reddit",
                        "status": "skipped",
                        "reason": "source disabled",
                        "requests_made": 0,
                        "documents_written": 0,
                        "stopped_reason": None,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    def fail() -> dict[str, object]:
        raise AssertionError("finished source was called")

    report = run_scaled_collection(
        output_dir=output,
        existing_paths=[],
        youtube=fail,
        reddit=fail,
        resume=True,
        run_id="scaled-test",
        occurred_at=WHEN,
    )
    assert report["documents"] == 0
    assert {row["status"] for row in report["sources"]} == {"collected", "skipped"}


@pytest.mark.synthetic
def test_concentration_is_reported(tmp_path) -> None:
    existing = tmp_path / "existing.jsonl"
    rows = [_row(f"r-{index}", "reddit") for index in range(8)]
    rows += [_row(f"y-{index}", "youtube") for index in range(2)]
    existing.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    report = run_scaled_collection(
        output_dir=tmp_path / "corpus",
        existing_paths=[existing],
        youtube=None,
        reddit=None,
        resume=False,
        run_id="scaled-test",
        occurred_at=WHEN,
    )
    assert report["concentration_over_threshold"] == ["reddit"]
    assert report["corpus_target_met"] is False
