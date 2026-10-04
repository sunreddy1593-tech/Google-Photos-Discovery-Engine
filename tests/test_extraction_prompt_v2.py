"""Approved evidence instructions and unchanged gates. Synthetic data only."""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest

from src.core.versions import PROMPT_VERSIONS, prompt_version
from src.extract.extractor import assemble_cases
from src.extract.prompts import build_extraction_prompt
from src.extract.schema import ExtractionPayload
from src.pipeline.extraction import transmitted_extraction_schema
from tests.test_extraction import (
    DOC_ID, NOW, TEXT, FakeProvider, case_body, derived, jsonl, quote,
    response, run, valid_decision,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Prompt regressions must remain offline")

    monkeypatch.setattr(socket, "socket", forbidden)


def render(version, document=None):
    document = document or derived()
    return build_extraction_prompt(
        document, prompt_version=version,
        transmitted_schema=transmitted_extraction_schema(document.doc_id, provider_name="groq"),
    )


def test_v1_rendering_is_preserved_as_the_historical_baseline():
    # Freeze the schema input: the request schema can be corrected independently
    # of the historical instruction template.
    historical = build_extraction_prompt(
        derived(), prompt_version="extract/v1",
        transmitted_schema={"properties": {"doc_id": {"enum": [DOC_ID]}}},
    )
    assert hashlib.sha256(historical.encode()).hexdigest() == "b8211deba8f03662e0a3193bd3ce1eb7baf107852c5e6a312330a096b882436c"
    assert "Every evidence quote must be one continuous target substring" not in historical


def test_v2_contains_approved_rules_and_identical_target_and_wire_schema():
    assert prompt_version("extract") == "extract/v2"
    assert prompt_version("relevance") == "relevance/v5"
    current = render("extract/v2")
    assert current.startswith("Extraction prompt: extract/v2\n")
    for rule in (
        "problem_summary is an interpretation, but it always requires a separate",
        "Never join non-adjacent passages into one",
        "unless those characters appear at\nthat exact position in the target",
        "For not_stated or not_applicable, return the existing required empty value",
        "Check that problem_summary has its required supporting entry for every case",
    ):
        assert rule in current
    baseline_schema = render("extract/v1").split("Transmitted JSON Schema:\n", 1)[1]
    current_schema = current.split("Transmitted JSON Schema:\n", 1)[1]
    assert current_schema == baseline_schema
    wire, target = current_schema.split("\n\nUNTRUSTED TARGET DOCUMENT (JSON-encoded quoted data):\n")
    assert json.loads(wire)["properties"]["doc_id"]["enum"] == [DOC_ID]
    assert json.loads(target) == {"doc_id": DOC_ID, "raw_text_audit": TEXT}
    assert not any(name in current for name in ("human_scope_class", "human_notes", "expected_answer"))


@pytest.mark.parametrize("version", ["extract/v99", "relevance/v5"])
def test_unimplemented_prompt_versions_are_refused(version):
    with pytest.raises(ValueError, match="unsupported extraction prompt"):
        render(version)


@pytest.mark.parametrize("kind", [
    "source-ascii-ellipsis", "source-unicode-ellipsis", "inserted-ellipsis",
    "spliced-quote", "missing-summary-evidence", "summary-as-own-quote",
    "not-stated-with-evidence", "not-applicable-with-evidence",
])
def test_v2_does_not_relax_existing_evidence_gates(kind):
    text = TEXT
    body = case_body()
    if kind == "source-ascii-ellipsis":
        text = "I wanted my cake photo... I searched and found nothing."
        body = case_body(quote_text="I wanted my cake photo...")
    elif kind == "source-unicode-ellipsis":
        text = "I wanted my cake photo… I searched and found nothing."
        body = case_body(quote_text="I wanted my cake photo…")
    elif kind == "inserted-ellipsis":
        body = case_body(quote_text="I wanted my cake photo...")
    elif kind == "spliced-quote":
        body = case_body(quote_text="I wanted my cake photo. I forgot the date.")
    elif kind == "missing-summary-evidence":
        body["field_evidence"] = []
    elif kind == "summary-as-own-quote":
        body = case_body(quote_text=body["problem_summary"])
    else:
        body["retrieval_trigger_observation"] = "not_stated" if kind.startswith("not-stated") else "not_applicable"
        body["field_evidence"].append({"field_name": "retrieval_trigger", **quote("I wanted my cake photo.")})
    document = derived(text=text)
    payload = ExtractionPayload.model_validate({"doc_id": DOC_ID, "cases": [body]})
    result, = assemble_cases(
        payload, document, valid_decision(), model_name="synthetic-model",
        prompt_version="extract/v2", extracted_at=NOW,
    )
    assert result.record_validation.ok is kind.startswith("source-")
    assert result.requires_review is not kind.startswith("source-")


def test_interpreted_summary_has_separate_verbatim_support():
    payload = ExtractionPayload.model_validate({"doc_id": DOC_ID, "cases": [case_body()]})
    result, = assemble_cases(
        payload, derived(), valid_decision(), model_name="synthetic-model",
        prompt_version="extract/v2", extracted_at=NOW,
    )
    assert result.record_validation.ok
    evidence, = result.external_spans
    assert evidence.field_name == "problem_summary"
    assert evidence.quote in TEXT
    assert evidence.quote != result.case.problem_summary


def test_version_change_isolates_cache_run_and_case_fingerprint(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    provider = FakeProvider(response(DOC_ID, [case_body()]))
    monkeypatch.setitem(PROMPT_VERSIONS, "extract", "extract/v1")
    historical = run(tmp_path / "v1", provider, [valid_decision()], cache_dir=cache)
    baseline = {path: path.read_bytes() for path in cache.rglob("*.json")}
    old_case, = jsonl(Path(historical.output_dir) / "retrieval_cases.jsonl")
    monkeypatch.setitem(PROMPT_VERSIONS, "extract", "extract/v2")
    current = run(tmp_path / "v2", provider, [valid_decision()], cache_dir=cache)
    new_case, = jsonl(Path(current.output_dir) / "retrieval_cases.jsonl")
    assert current.provider_calls == 1
    assert current.cache_hits == 0
    assert current.run_id != historical.run_id
    assert new_case["prompt_version"] == "extract/v2"
    assert old_case["prompt_version"] == "extract/v1"
    assert old_case["extraction_fingerprint"] != new_case["extraction_fingerprint"]
    old_input, = jsonl(Path(historical.output_dir) / "extraction_inputs.jsonl")
    new_input, = jsonl(Path(current.output_dir) / "extraction_inputs.jsonl")
    assert old_input["request_identity"]["transmitted_schema_sha256"] == new_input["request_identity"]["transmitted_schema_sha256"]
    assert old_input["request_identity"]["prompt_sha256"] != new_input["request_identity"]["prompt_sha256"]
    replay = run(tmp_path / "v2-hit", provider, [valid_decision()], cache_dir=cache)
    assert replay.provider_calls == 0
    assert replay.cache_hits == 1
    assert provider.calls == 2
    assert len(list(cache.rglob("*.json"))) == 2
    assert all(path.read_bytes() == value for path, value in baseline.items())


@pytest.mark.parametrize("version", ["extract/v1", "extract/v99"])
def test_bounded_paths_require_the_approved_active_version(tmp_path, monkeypatch, version):
    from src.pipeline.extraction_diagnostic import DiagnosticBoundsError
    from src.pipeline.extraction_pilot import PilotBoundsError
    from tests.test_extraction_diagnostic import _run as diagnostic
    from tests.test_extraction_pilot import CountingProvider, _five, _pilot

    monkeypatch.setitem(PROMPT_VERSIONS, "extract", version)
    provider = CountingProvider()
    ids, decisions, docs = _five()
    with pytest.raises(PilotBoundsError, match="requires extract/v2"):
        _pilot(tmp_path / "pilot", provider, ids, decisions, docs)
    with pytest.raises(DiagnosticBoundsError, match="requires extract/v2"):
        diagnostic(tmp_path / "diagnostic", provider)
    assert provider.calls == 0
    assert list(tmp_path.iterdir()) == []
