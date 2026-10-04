"""The development annotation pack stays blank, and completed reviews use gold contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.gold.annotate import AnnotationError, assert_exact_span, emit_gold, gold_from_review, validate_pack
from src.gold.load import load_gold_cases, load_gold_documents
from src.pipeline.extraction_development import development_ids, holdout_ids

PACK = Path("data/annotation/dev-starter-2026-10-03")


def test_pack_seats_only_phase4_development_gold_dev_documents() -> None:
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    doc_ids = {row["doc_id"] for row in manifest["documents"]}
    assert 10 <= len(doc_ids) <= 15
    assert doc_ids <= set(development_ids())
    assert not doc_ids & set(holdout_ids())
    assert {row["gold_split"] for row in manifest["documents"]} == {"dev"}
    reserved = json.loads((PACK / "selection.json").read_text(encoding="utf-8"))
    assert reserved["phase4_holdout_text_copied"] is False
    assert not set(reserved["reserved_development_doc_ids"]) & doc_ids


def test_packets_are_blank_and_predictions_are_separate() -> None:
    packets = list((PACK / "packets").glob("*.json"))
    assert len(packets) == 10
    for path in packets:
        packet = json.loads(path.read_text(encoding="utf-8"))
        assert packet["gold_document"]["scope_class"] is None
        assert packet["gold_document"]["reason_code"] is None
        assert packet["gold_document"]["expected_case_count"] is None
        assert packet["gold_cases"] == []
        assert packet["source_text"]
        assert "model_prediction" not in path.read_text(encoding="utf-8")
        assert "seating_scope_class" not in packet
        prediction = json.loads((PACK / "predictions" / path.name).read_text(encoding="utf-8"))
        assert prediction["role"] == "model_prediction_not_a_gold_label"
        assert prediction["doc_id"] == packet["doc_id"]


def test_exact_offsets_reject_a_paraphrase_and_a_shifted_span() -> None:
    text = "I looked for the birthday cake photo."
    assert_exact_span(text, "birthday cake photo", text.index("birthday cake photo"), text.index("birthday cake photo") + len("birthday cake photo"))
    with pytest.raises(AnnotationError):
        assert_exact_span(text, "a cake I remember", 0, 16)
    with pytest.raises(AnnotationError):
        assert_exact_span(text, "birthday cake photo", 0, len("birthday cake photo"))


def test_completed_review_emits_gold_and_a_second_review_is_not_merged(tmp_path: Path) -> None:
    text = "I looked for the birthday cake photo."
    start = text.index("birthday cake photo")
    pack = tmp_path / "pack"
    _packet(pack, text)
    review = _review(text, start, "reviewer-a")
    document, cases = gold_from_review(review, source_text=text, split="dev")
    assert document.expected_case_count == 1
    assert cases[0].expected_evidence == ("birthday cake photo",)
    assert document.adjudicated is False
    (pack / "labels" / "reviewer-a").mkdir(parents=True)
    (pack / "labels" / "reviewer-a" / "doc.json").write_text(
        json.dumps(review),
        encoding="utf-8",
    )
    emitted = tmp_path / "gold"
    assert emit_gold(pack, emitted, holdout_ids()) == 1
    loaded = load_gold_documents(emitted / "documents.jsonl")
    assert loaded[0].split.value == "dev"
    assert load_gold_cases(emitted / "cases.jsonl")[0].doc_id == "doc"
    second = _review(text, start, "reviewer-b")
    second["scope_class"] = "out_of_scope"
    second["reason_code"] = "storage_backup_or_sync"
    second["expected_case_count"] = 0
    second["cases"] = []
    (pack / "labels" / "reviewer-b").mkdir()
    (pack / "labels" / "reviewer-b" / "doc.json").write_text(json.dumps(second), encoding="utf-8")
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    manifest["documents"][0]["double_code"] = True
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    check = validate_pack(pack, holdout_ids())
    assert any("no adjudication" in error for error in check.errors)
    with pytest.raises(AnnotationError):
        emit_gold(pack, tmp_path / "merged", holdout_ids())


def test_holdout_document_is_rejected(tmp_path: Path) -> None:
    holdout = holdout_ids()[0]
    pack = tmp_path / "pack"
    _packet(pack, "text", doc_id=holdout)
    review = _review("text", 0, "reviewer-a")
    review["doc_id"] = holdout
    review["expected_case_count"] = 0
    review["cases"] = []
    (pack / "labels" / "reviewer-a").mkdir(parents=True)
    (pack / "labels" / "reviewer-a" / f"{holdout}.json").write_text(json.dumps(review), encoding="utf-8")
    check = validate_pack(pack, holdout_ids())
    assert check.errors


def test_real_pack_has_no_completed_reviews() -> None:
    check = validate_pack(PACK, holdout_ids())
    assert check.pending
    assert check.documents == 10
    assert check.reviews == 0


def _packet(pack: Path, text: str, doc_id: str = "doc") -> None:
    (pack / "packets").mkdir(parents=True)
    (pack / "packets" / f"{doc_id}.json").write_text(
        json.dumps({"doc_id": doc_id, "gold_split": "dev", "source_text": text}),
        encoding="utf-8",
    )
    (pack / "manifest.json").write_text(
        json.dumps({"documents": [{"doc_id": doc_id, "gold_split": "dev", "double_code": False}]}),
        encoding="utf-8",
    )


def _review(text: str, start: int, labeler: str) -> dict:
    quote = "birthday cake photo"
    return {
        "doc_id": "doc",
        "labeler_id": labeler,
        "labeled_at": "2026-10-04T00:00:00Z",
        "scope_class": "core_incomplete_recall",
        "reason_code": "known_item_with_incomplete_recall",
        "prefilter_should_pass": True,
        "expected_case_count": 1,
        "notes": None,
        "cases": [
            {
                "ordinal": 1,
                "expected_values": {
                    "outcome": {"observation": "stated", "value": "not_found"},
                    "known_item_status": {"observation": None, "value": None},
                },
                "evidence": [
                    {
                        "field_name": "outcome",
                        "quote": quote,
                        "start_char": start,
                        "end_char": start + len(quote),
                    }
                ],
                "notes": None,
            }
        ],
    }
