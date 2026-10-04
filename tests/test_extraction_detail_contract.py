"""Synthetic regressions for subject-only detail and document failure reporting."""

import copy
import json
import socket
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.extract.schema import ExtractionCasePayload, extraction_schema
from src.llm.providers.groq import cache_decoding_params
from src.pipeline.extraction import extraction_exit_code, format_extraction_summary, transmitted_extraction_schema
from tests.test_extraction import DOC_ID, FakeProvider, case_body, jsonl, quote, response, run, valid_decision


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Detail contract regressions must remain offline")
    monkeypatch.setattr(socket, "socket", forbidden)


FIELDS = (
    "remembered_cues", "forgotten_information", "query_strategies",
    "system_responses", "workarounds", "impact_signals",
)


def label_schema(schema, field):
    ref = schema["$defs"]["ExtractionCasePayload"]["properties"][field]["items"]["$ref"]
    return schema["$defs"][ref.rsplit("/", 1)[1]]


@pytest.mark.parametrize("field", FIELDS)
def test_non_subject_detail_is_null_in_transport_and_python(field):
    application = extraction_schema(DOC_ID)
    wire = transmitted_extraction_schema(DOC_ID, provider_name="groq")
    label = label_schema(application, field)
    enum_ref = label["properties"]["value"]["$ref"].rsplit("/", 1)[1]
    value = application["$defs"][enum_ref]["enum"][0]
    for schema in (application, wire):
        assert label_schema(schema, field)["properties"]["detail"]["type"] == "null"
    assert "detail" in label_schema(wire, field)["required"]
    body = {**case_body(), field: [{"value": value, "detail": None, "evidence": quote("cake photo")}]}
    assert getattr(ExtractionCasePayload.model_validate(body), field)[0].detail is None
    body[field][0]["detail"] = "Non-subject free text"
    with pytest.raises(ValidationError) as caught:
        ExtractionCasePayload.model_validate(body)
    assert caught.value.errors()[0]["loc"] == (field, 0, "detail")
    assert body[field][0]["detail"] == "Non-subject free text"


def test_subject_detail_and_null_cue_pass_unchanged_application_gate(tmp_path):
    body = {
        **case_body(),
        "target_subjects_observation": "stated",
        "target_subjects": [{"value": "document_or_paperwork", "detail": "Subject interpretation",
                             "evidence": quote("cake photo")}],
        "remembered_cues_observation": "stated",
        "remembered_cues": [{"value": "object_or_subject", "detail": None,
                             "evidence": quote("cake photo")}],
    }
    wire = transmitted_extraction_schema(DOC_ID, provider_name="groq")
    assert label_schema(wire, "target_subjects")["properties"]["detail"]["type"] == ["string", "null"]
    result = run(tmp_path, FakeProvider(response(DOC_ID, [body])), [valid_decision()])
    assert result.valid_cases == 1
    case, = jsonl(Path(result.output_dir) / "retrieval_cases.jsonl")
    assert case["target_subjects"][0]["detail"] == "Subject interpretation"
    assert case["remembered_cues"][0]["detail"] is None


def test_invalid_detail_is_rejected_not_coerced_by_gateway(tmp_path):
    body = {**case_body(), "remembered_cues_observation": "stated", "remembered_cues": [
        {"value": "approximate_time", "detail": "A paraphrase", "evidence": quote("cake photo")},
    ]}
    provider = FakeProvider(response(DOC_ID, [body]))
    result = run(tmp_path, provider, [valid_decision()])
    assert provider.calls == 1
    assert result.by_state == {"schema_validation_failed": 1}
    assert result.valid_cases == 0
    assert jsonl(Path(result.output_dir) / "retrieval_cases.jsonl") == []
    assert extraction_exit_code(result) == 1


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_assembly_schema_failure_is_reported_consistently(tmp_path, mixed, reverse):
    bad_schema = {**case_body(), "reformulation_count": 1, "reformulation_count_observation": "not_stated"}
    cases = [bad_schema]
    if mixed:
        cases.append(case_body(quote_text="Invented quote"))
    if reverse:
        cases.reverse()
    result = run(tmp_path, FakeProvider(response(DOC_ID, cases)), [valid_decision()])
    destination = Path(result.output_dir)
    assert result.by_state == {"schema_validation_failed": 1}
    assert "state schema_validation_failed 1" in format_extraction_summary(result)
    assert extraction_exit_code(result) == 1
    assert result.valid_cases == 0
    event, = jsonl(destination / "stage_events.jsonl")
    assert event["status"] == "failed"
    assert event["reason_code"] == "schema_validation_failed"
    manifest = json.loads((destination / "run_manifest.json").read_text())
    assert manifest["funnel"]["by_state"] == result.by_state
    failures = jsonl(destination / "extraction_failures.jsonl")
    assert {row["error_class"] for row in failures} == (
        {"schema_validation_failed", "evidence_validation_failed"} if mixed else {"schema_validation_failed"}
    )


def test_corrected_wire_schema_separates_cache_identity():
    wire = transmitted_extraction_schema(DOC_ID, provider_name="groq")
    old = copy.deepcopy(wire)
    for field in FIELDS:
        label_schema(old, field)["properties"]["detail"] = {"type": ["string", "null"], "title": "Detail"}
    current = cache_decoding_params(temperature=0.0, max_tokens=8192, schema=wire)
    previous = cache_decoding_params(temperature=0.0, max_tokens=8192, schema=old)
    assert current != previous
