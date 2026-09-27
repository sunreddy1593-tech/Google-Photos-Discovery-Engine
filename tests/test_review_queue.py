"""Duplicate review items are appended, and the CLI prints counts only."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from src.core.config import load_settings
from src.core.ids import raw_text_sha256, source_url_key
from src.models.duplicate_link import DuplicateLink
from src.models.enums import (
    DuplicateDecidedBy,
    DuplicateDetectionMethod,
    DuplicateKind,
    DuplicateReviewState,
    ReasonCode,
)
from src.pipeline.runner import RULESET_INSTANT
from src.review.queue import append_resolution, open_items
from tests.synthetic import make_document

import main


def test_resolution_appends_and_leaves_the_open_item() -> None:
    link = DuplicateLink(
        link_id="link-1",
        doc_id="doc-b",
        canonical_doc_id="doc-a",
        duplicate_kind=DuplicateKind.near,
        similarity=0.9,
        method=DuplicateDetectionMethod.simhash,
        method_version="1.0.0",
        method_detail={"hamming_distance": 5},
        review_state=DuplicateReviewState.pending_review,
        decided_by=DuplicateDecidedBy.rules,
        decided_at=RULESET_INSTANT,
        review_reason_code=ReasonCode.near_duplicate_in_review_band,
    )
    opened = open_items((link,), opened_at=RULESET_INSTANT)
    assert len(opened) == 1
    assert opened[0].state == "open"
    assert opened[0].researcher_decision == ""

    resolved = append_resolution(
        opened,
        opened[0].item_id,
        decision="distinct",
        resolver="researcher",
        resolved_at=datetime(2026, 9, 27, tzinfo=UTC),
    )

    assert len(resolved) == 2
    assert resolved[0].state == "open"
    assert resolved[0].item_id == opened[0].item_id
    assert resolved[1].state == "resolved"
    assert resolved[1].researcher_decision == "distinct"
    assert resolved[1].item_id != resolved[0].item_id


def test_analysis_yaml_keeps_the_adr11_band_under_adr21(config_dir, empty_env) -> None:
    """Hamming 3 and 6 are ADR-11, retained as the ADR-21 default.

    The token minimum and the cross-author guard are ADR-21. ADR-11 is the
    threshold decision; ADR-21 did not replace those two numbers.
    """
    settings = load_settings(config_dir, env_file=empty_env)
    dedupe = settings.analysis.dedupe
    assert dedupe.simhash_duplicate_max == 3
    assert dedupe.simhash_review_band_max == 6
    assert dedupe.min_tokens == 25
    assert dedupe.allow_cross_author_auto is False


def test_cli_prints_counts_and_hides_secrets(
    tmp_path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "super-secret-salt-phase3"
    email = "me@example.com"
    text = f"Please write {email} if the search still cannot find the beach photo."
    url = "https://www.reddit.com/r/googlephotos/comments/cli1/"
    document = make_document(
        doc_id="reddit-cli1",
        source_item_id="cli1",
        raw_text=text,
        raw_text_sha256=raw_text_sha256(text),
        source_url=url,
        source_url_key=source_url_key(url),
    )
    source = tmp_path / "collected_documents.jsonl"
    source.write_text(document.model_dump_json() + "\n", encoding="utf-8")
    output = tmp_path / "out"
    monkeypatch.setenv("AUTHOR_SALT", secret)

    code = main.main(
        [
            "run",
            "--stages",
            "normalize,dedupe",
            "--input",
            str(source),
            "--output",
            str(output),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "Normalize and dedupe complete" in captured.out
    assert "documents            1" in captured.out
    assert secret not in captured.out
    assert secret not in captured.err
    assert email not in captured.out
    written = "\n".join(
        path.read_text(encoding="utf-8") for path in output.iterdir() if path.is_file()
    )
    review = (output / "duplicate_review.csv").read_text(encoding="utf-8")
    audit = "\n".join(
        json.loads(line)["raw_text_audit"]
        for line in (output / "documents_derived.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert secret not in written
    assert email not in review
    assert email not in audit
    assert (output / "duplicate_review.csv").is_file()


def test_cli_rejects_a_later_stage(capsys) -> None:
    code = main.main(["run", "--stages", "extract"])
    captured = capsys.readouterr()
    assert code == 1
    assert "prefilter" in captured.err
