"""Offline regressions for extraction's rejected nullable anyOf branches."""

from __future__ import annotations

import json
import socket
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.core.ids import cache_key
from src.core.versions import SCHEMA_VERSION, prompt_version
from src.extract.schema import ExtractionCasePayload, ExtractionPayload, extraction_schema
from src.llm.cache import CacheEntry, ResponseCache
from src.llm.providers.groq import (
    cache_decoding_params, groq_request_schema, groq_strict_schema,
)
from src.pipeline.extraction import transmitted_extraction_schema
from src.pipeline.extraction_diagnostic import (
    DIAGNOSTIC_DOC_ID, DIAGNOSTIC_QUOTE, run_extraction_diagnostic, synthetic_document,
)
from src.pipeline.extraction_pilot import PILOT_MODEL
from src.relevance.prompts import relevance_json_schema
from tests.synthetic import NOW

pytestmark = pytest.mark.synthetic


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("nullable-schema tests must not use the network")

    monkeypatch.setattr(socket, "socket", forbidden)


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def test_extraction_nullable_types_preserve_enums_bounds_and_strict_objects():
    application = extraction_schema(DIAGNOSTIC_DOC_ID)
    before = json.dumps(application, sort_keys=True)
    wire = transmitted_extraction_schema(DIAGNOSTIC_DOC_ID, provider_name="groq")
    assert sum("anyOf" in node for node in _nodes(application)) == 13
    assert not any("anyOf" in node for node in _nodes(wire))
    assert groq_strict_schema(wire) == wire
    assert groq_request_schema(wire, doc_id=DIAGNOSTIC_DOC_ID, nullable_scalars=True) == wire
    assert json.dumps(application, sort_keys=True) == before
    fields = wire["$defs"]["ExtractionCasePayload"]["properties"]
    for field, enum in (
        ("known_item_status", "KnownItemStatus"),
        ("target_asset_type", "TargetAssetType"),
        ("outcome", "Outcome"),
    ):
        assert fields[field]["type"] == ["string", "null"]
        assert fields[field]["enum"] == [*application["$defs"][enum]["enum"], None]
    assert fields["severity"]["type"] == ["integer", "null"]
    assert fields["severity"]["minimum"] == 1
    assert fields["severity"]["maximum"] == 5
    assert fields["reformulation_count"]["minimum"] == 0
    for name in ("QuotePayload", "FieldEvidencePayload"):
        for field in ("start_char", "end_char"):
            offset = wire["$defs"][name]["properties"][field]
            assert offset["type"] == ["integer", "null"]
            assert offset["minimum"] == 0
    for node in _nodes(wire):
        if "properties" in node:
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])


@pytest.mark.parametrize("field,bad", [
    ("known_item_status", "invented"), ("target_asset_type", "invented"),
    ("outcome", "invented"), ("severity", 0), ("severity", 6),
    ("reformulation_count", -1),
])
def test_application_constraints_are_not_relaxed(field, bad):
    base = {"problem_summary": "Synthetic example."}
    assert getattr(ExtractionCasePayload.model_validate({**base, field: None}), field) is None
    with pytest.raises(ValidationError):
        ExtractionCasePayload.model_validate({**base, field: bad})


def test_relevance_and_non_scalar_union_conversion_stay_unchanged():
    relevance = relevance_json_schema()
    old = groq_request_schema(relevance, doc_id="synthetic-relevance")
    expected = groq_strict_schema(relevance)
    expected["properties"]["doc_id"] = {"type": "string", "enum": ["synthetic-relevance"]}
    assert old == expected
    application = {
        "type": "object", "$defs": {"Record": {"type": "object", "properties": {}}},
        "properties": {
            "object": {"anyOf": [{"$ref": "#/$defs/Record"}, {"type": "null"}]},
            "multiple": {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]},
            "duplicate_null": {"anyOf": [{"type": "null"}, {"type": "null"}]},
            "constrained": {"anyOf": [{"type": "string", "minLength": 1}, {"type": "null"}], "minLength": 2},
        },
    }
    strict = groq_strict_schema(application)
    assert groq_request_schema(application, doc_id="unused", nullable_scalars=True) == strict


def test_mock_sdk_gets_flattened_schema_and_legacy_cache_is_preserved(monkeypatch, tmp_path):
    document = synthetic_document()
    application = extraction_schema(DIAGNOSTIC_DOC_ID)
    old_wire = groq_request_schema(application, doc_id=DIAGNOSTIC_DOC_ID)
    new_wire = transmitted_extraction_schema(DIAGNOSTIC_DOC_ID, provider_name="groq")
    old_decoding = {**cache_decoding_params(temperature=0.0, max_tokens=64, schema=old_wire),
                    "doc_id": DIAGNOSTIC_DOC_ID}
    shared = dict(provider="groq", model=PILOT_MODEL, prompt_id="extract",
                  prompt_version="extract/v1", schema_version=SCHEMA_VERSION,
                  content_hash_value=document.content_hash)
    old_key = cache_key(**shared, decoding_params=old_decoding)
    new_decoding = {
        **cache_decoding_params(temperature=0.0, max_tokens=64, schema=new_wire),
        "doc_id": DIAGNOSTIC_DOC_ID,
    }
    converted_v1_key = cache_key(**shared, decoding_params=new_decoding)
    new_key = cache_key(
        **{**shared, "prompt_version": prompt_version("extract")}, decoding_params=new_decoding,
    )
    assert len({old_key, converted_v1_key, new_key}) == 3
    cache = ResponseCache(tmp_path / "cache")
    cache.write(CacheEntry(
        cache_key=old_key, provider="groq", model=PILOT_MODEL, prompt_id="extract",
        prompt_version="extract/v1", schema_version=SCHEMA_VERSION, ruleset_version=None,
        content_hash=document.content_hash, decoding_params=old_decoding,
        request_text="old synthetic request", raw_response=json.dumps({"doc_id": DIAGNOSTIC_DOC_ID, "cases": []}),
        input_tokens=0, output_tokens=0, cached_at=NOW.isoformat(),
    ))
    legacy = cache.path_for("extract", old_key).read_bytes()
    calls = []

    def create(**kwargs):
        sent = kwargs["response_format"]["json_schema"]
        assert sent["strict"] is True
        assert sent["schema"] == new_wire
        assert not any("anyOf" in node for node in _nodes(sent["schema"]))
        prompt = kwargs["messages"][1]["content"]
        embedded = json.loads(prompt.split("Transmitted JSON Schema:\n", 1)[1].split("\n\nUNTRUSTED", 1)[0])
        assert embedded == sent["schema"]
        calls.append(kwargs)
        payload = ExtractionPayload.model_validate({"doc_id": DIAGNOSTIC_DOC_ID, "cases": [{
            "problem_summary": "The user forgot the exact date.",
            "field_evidence": [{"field_name": "problem_summary", "quote": DIAGNOSTIC_QUOTE,
                                "speaker": "author", "start_char": None, "end_char": None}],
        }]})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=payload.model_dump_json()))],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2), model=PILOT_MODEL,
        )

    def client(*, api_key, timeout, max_retries):
        assert max_retries == 0
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setitem(sys.modules, "groq", SimpleNamespace(Groq=client))
    result = run_extraction_diagnostic(
        output_dir=tmp_path / "output", cache_dir=cache.root,
        provider_name="groq", model_name=PILOT_MODEL, temperature=0.0, max_tokens=64,
        max_retries=1, call_budget=1, api_key="synthetic-not-a-real-key",
    )
    assert len(calls) == result.provider_calls == 1
    assert result.cache_hits == 0
    assert result.valid_cases == 1
    assert cache.path_for("extract", old_key).read_bytes() == legacy
    assert cache.read("extract", new_key) is not None
