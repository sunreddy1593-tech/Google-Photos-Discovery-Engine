"""Gold files, split assignment, and quote validation. Fixtures are synthetic."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.gold.evaluate import validate_gold_quotes
from src.gold.load import GoldSetError, load_gold_cases, load_gold_documents, require_case_counts
from src.gold.match import MATCH_VERSION, MatchSpan, match_cases
from src.gold.split import GOLD_SPLIT_RULE, assign_gold_splits, SplitMember
from src.models.enums import GoldSplit, ReasonCode, ScopeClass
from src.models.gold import GoldCase, GoldDocumentLabel
from tests.synthetic import NOW


def _document(doc_id: str, *, cases: int = 0, split: GoldSplit = GoldSplit.dev) -> GoldDocumentLabel:
    return GoldDocumentLabel(
        doc_id=doc_id,
        split=split,
        scope_class=ScopeClass.core_incomplete_recall,
        reason_code=ReasonCode.known_item_with_incomplete_recall,
        prefilter_should_pass=True,
        expected_case_count=cases,
        labeler_id="reviewer-a",
        labeled_at=NOW,
    )


def _case(doc_id: str, ordinal: int, quote: str) -> GoldCase:
    return GoldCase(
        gold_case_id=f"{doc_id}#g{ordinal:02d}",
        doc_id=doc_id,
        expected_evidence=(quote,),
        labeler_id="reviewer-a",
    )


def test_document_and_case_labels_load_from_separate_files(tmp_path: Path) -> None:
    documents = tmp_path / "documents.jsonl"
    cases = tmp_path / "cases.jsonl"
    documents.write_text(_document("doc-zero").model_dump_json() + "\n", encoding="utf-8")
    cases.write_text(_case("doc-many", 1, "alpha").model_dump_json() + "\n", encoding="utf-8")
    loaded_documents = load_gold_documents(documents)
    loaded_cases = load_gold_cases(cases)
    assert [row.doc_id for row in loaded_documents] == ["doc-zero"]
    assert [row.gold_case_id for row in loaded_cases] == ["doc-many#g01"]
    assert loaded_documents[0].expected_case_count == 0


def test_zero_case_document_is_allowed_and_a_count_mismatch_is_rejected() -> None:
    document = _document("doc-zero", cases=0)
    require_case_counts([document], [])
    with pytest.raises(GoldSetError, match="expects 0"):
        require_case_counts([document], [_case("doc-zero", 1, "alpha")])


def test_case_matching_is_order_independent() -> None:
    text = "ALPHA marker one. BETA marker two."
    gold = (
        _case("doc", 1, "ALPHA marker one"),
        _case("doc", 2, "BETA marker two"),
    )
    extracted = (
        _extracted("case-b", "BETA marker two", text),
        _extracted("case-a", "ALPHA marker one", text),
    )
    forward = match_cases(gold, extracted, text)
    backward = match_cases(tuple(reversed(gold)), tuple(reversed(extracted)), text)
    assert MATCH_VERSION == "evidence-overlap/v1"
    assert {(gold_case.gold_case_id, extracted.case_id) for gold_case, extracted in forward} == {
        ("doc#g01", "case-a"),
        ("doc#g02", "case-b"),
    }
    assert {(gold_case.gold_case_id, extracted.case_id) for gold_case, extracted in backward} == {
        ("doc#g01", "case-a"),
        ("doc#g02", "case-b"),
    }


def test_split_assignment_is_deterministic_and_stratified() -> None:
    members = [
        SplitMember(f"reddit-{index:02d}", "reddit", "core_incomplete_recall")
        for index in range(5)
    ] + [
        SplitMember(f"youtube-{index:02d}", "youtube", "out_of_scope")
        for index in range(5)
    ]
    first = assign_gold_splits(members)
    second = assign_gold_splits(list(reversed(members)))
    assert first == second
    assert GOLD_SPLIT_RULE == "gold-split/v1"
    for prefix in ("reddit-", "youtube-"):
        seats = [split for doc_id, split in first.items() if doc_id.startswith(prefix)]
        assert seats.count(GoldSplit.dev) == 2
        assert seats.count(GoldSplit.holdout) == 3


def test_gold_quotes_must_occur_in_the_document() -> None:
    text = "I looked for the birthday cake photo."
    valid = _case("doc", 1, "birthday cake photo")
    paraphrase = _case("doc", 2, "a paraphrased cake search")
    assert validate_gold_quotes((valid,), {"doc": text}) == 0
    assert validate_gold_quotes((paraphrase,), {"doc": text}) == 1


def _extracted(case_id: str, quote: str, text: str):
    start = text.index(quote)

    class _Case:
        def __init__(self) -> None:
            self.case_id = case_id
            self.spans = (
                MatchSpan(
                    quote=quote,
                    start_char=start,
                    end_char=start + len(quote),
                    validation_state="valid",
                    field_name="problem_summary",
                ),
            )

    return _Case()
