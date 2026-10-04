"""Synthetic cache and nested-evidence isolation through the existing stage."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from src.core.ids import content_hash
from src.llm.providers.base import CompletionParams, ProviderResponse
from src.models.document_derived import DocumentDerived
from src.models.enums import EvidenceOwnerType, ValidationState
from src.pipeline.extraction import run_extraction
from tests.synthetic import NOW, make_decision, make_span

pytestmark = pytest.mark.synthetic
TEXT = "I wanted my cake photo. I forgot the date."
TARGET_QUOTE = "I wanted my cake photo."
FOREIGN_QUOTE = "I searched for my passport scan and missed my flight."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("evidence isolation tests must not use the network")

    monkeypatch.setattr(socket, "socket", forbidden)


def _quote(text: str) -> dict:
    return {"quote": text, "start_char": None, "end_char": None, "speaker": "author"}


def _candidate() -> dict:
    return {
        "problem_summary": "The user wanted a cake photo.",
        "field_evidence": [{"field_name": "problem_summary", **_quote(TARGET_QUOTE)}],
    }


class SyntheticProvider:
    provider_name = "fake"

    def __init__(self, candidate: dict):
        self.candidate = candidate
        self.targets: list[str] = []

    def complete_structured(self, prompt: str, schema: dict, params: CompletionParams):
        target = schema["properties"]["doc_id"]["enum"][0]
        self.targets.append(target)
        return ProviderResponse(
            text=json.dumps({"doc_id": target, "cases": [self.candidate]}),
            input_tokens=4, output_tokens=2, model=params.model, provider="fake",
        )


def _document(doc_id: str) -> DocumentDerived:
    return DocumentDerived(
        doc_id=doc_id, raw_text_audit=TEXT, normalized_text=TEXT.lower(),
        canonical_url="https://example.invalid/synthetic", content_hash=content_hash(TEXT),
        simhash="0", token_count=len(TEXT.split()), normalizer_version="synthetic/v1",
        derived_at=NOW,
    )


def _run(output: Path, cache: Path, provider: SyntheticProvider, ids: tuple[str, ...]):
    return run_extraction(
        doc_ids=list(ids),
        model_decisions=[
            make_decision(doc_id=doc_id, decision_id=f"decision-{doc_id}",
                          validation_state=ValidationState.valid,
                          evidence=(make_span(
                              "scope_class", "I forgot the date.", text=TEXT,
                              doc_id=doc_id, owner_id=f"decision-{doc_id}",
                              owner_type=EvidenceOwnerType.relevance_decision,
                          ),))
            for doc_id in ids
        ],
        human_decisions=[], derived_by_id={doc_id: _document(doc_id) for doc_id in ids},
        output_dir=output, cache_dir=cache, provider=provider, provider_name="fake",
        model_name="synthetic-extraction-model", max_retries=1, call_budget=len(ids),
    )


def _rows(output: str, name: str) -> list[dict]:
    return [json.loads(line) for line in (Path(output) / name).read_text(
        encoding="utf-8").splitlines() if line.strip()]


def test_identical_text_keeps_document_identity_on_cache_miss_and_hit(tmp_path: Path):
    ids = ("reddit-synthetic-left", "reddit-synthetic-right")
    cache = tmp_path / "cache"
    provider = SyntheticProvider(_candidate())
    first = _run(tmp_path / "first", cache, provider, ids)
    assert provider.targets == list(ids)
    assert first.provider_calls == 2
    assert first.cache_misses == 2

    cached_provider = SyntheticProvider(_candidate())
    cached = _run(tmp_path / "cached", cache, cached_provider, ids)
    assert cached_provider.targets == []
    assert cached.provider_calls == 0
    assert cached.cache_hits == 2
    for result in (first, cached):
        assert result.valid_cases == 2
        cases = _rows(result.output_dir, "retrieval_cases.jsonl")
        assert {row["case_id"] for row in cases} == {f"{doc_id}#c01" for doc_id in ids}
        spans = _rows(result.output_dir, "evidence_spans.jsonl")
        assert {row["doc_id"] for row in spans} == set(ids)
        assert len({row["evidence_id"] for row in spans}) == 2
        for span in spans:
            assert span["owner_id"] == f"{span['doc_id']}#c01"
            assert TEXT[span["start_char"]:span["end_char"]] == span["quote"]


@pytest.mark.parametrize("field", ["remembered_cues", "severity"])
def test_foreign_nested_evidence_is_retained_for_review_and_excluded_from_analysis(
    tmp_path: Path, field: str,
):
    candidate = _candidate()
    candidate[field + "_observation"] = "stated"
    if field == "severity":
        candidate.update(severity=5, severity_evidence=[_quote(FOREIGN_QUOTE)])
    else:
        candidate[field] = [{"value": "object_or_subject", "evidence": _quote(FOREIGN_QUOTE)}]
    provider = SyntheticProvider(candidate)
    target = "reddit-synthetic-target"
    result = _run(tmp_path / "output", tmp_path / "cache", provider, (target,))
    assert provider.targets == [target]
    assert result.valid_cases == 0
    assert _rows(result.output_dir, "retrieval_cases.jsonl") == []
    assert _rows(result.output_dir, "case_labels.jsonl") == []
    verdicts = _rows(result.output_dir, "span_validations.jsonl")
    foreign = [row for row in verdicts if row["field_name"] == field]
    assert len(foreign) == 1
    assert foreign[0]["doc_id"] == target
    assert foreign[0]["quote"] == FOREIGN_QUOTE
    assert foreign[0]["ok"] is False
    assert _rows(result.output_dir, "extraction_failures.jsonl")
    assert _rows(result.output_dir, "review_queue.jsonl")
