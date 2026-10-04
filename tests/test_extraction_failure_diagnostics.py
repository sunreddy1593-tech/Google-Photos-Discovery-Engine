"""Safe failure inspection and usage completeness. Synthetic data; no network."""

from __future__ import annotations

import json
import socket
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from src.extract.schema import ExtractionPayload
from src.llm.providers.base import diagnostic_from_exception, provider_failed
from src.llm.providers.groq import GroqProvider
from src.pipeline.extraction import run_extraction
from tests.test_extraction import DOC_ID, TEXT, FakeProvider, derived, jsonl, response, run, valid_decision

SECRET = "gsk-synthetic-secret-not-real"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Failure diagnostic tests must remain offline")

    monkeypatch.setattr(socket, "socket", forbidden)


class Rejected(Exception):
    def __init__(self, generation, *, status=400, finish_reason=None):
        self.status_code = status
        self.body = {"error": {
            "type": "invalid_request_error", "code": "json_validate_failed",
            "message": "Failed to validate JSON", "failed_generation": generation,
            "finish_reason": finish_reason,
        }}
        self.response = SimpleNamespace(headers={"x-request-id": "req-synthetic123"})


@pytest.mark.parametrize(
    "generation,json_state,application_state",
    [
        ("", "empty", "not_checked"),
        (" \n\t", "empty", "not_checked"),
        (None, "not_text", "not_checked"),
        ("{", "invalid_json", "not_checked"),
        ("NaN", "invalid_json", "not_checked"),
        (" " * 65_537, "oversized", "not_checked"),
        (response(DOC_ID, []), "valid_json", "valid"),
        (response(DOC_ID, [{"problem_summary": 123}]), "valid_json", "invalid"),
    ],
    ids=["empty-text", "whitespace", "not-text", "malformed", "nonfinite", "oversized", "valid-empty", "wrong-field-type"],
)
def test_rejected_output_is_inspected_without_becoming_a_completion(generation, json_state, application_state):
    diagnostic = diagnostic_from_exception(
        Rejected(generation), category="invalid_request", response_model=ExtractionPayload,
    )
    summary = diagnostic.rejected_output_summary
    assert summary["json_state"] == json_state
    assert summary["application_state"] == application_state
    if isinstance(generation, str):
        assert summary["character_count"] == len(generation)
    if application_state == "invalid":
        assert summary["validation_errors"] == [{"type": "string_type", "path": ["cases", 0, "problem_summary"]}]
    if json_state == "invalid_json" and generation == "{":
        assert summary["json_error_position"] == 1


def test_unknown_error_keys_values_and_messages_never_enter_summary():
    class Payload(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: int

    generation = json.dumps({"value": TEXT, SECRET: TEXT})
    diagnostic = diagnostic_from_exception(
        Rejected(generation, finish_reason=SECRET), category="invalid_request", response_model=Payload,
    )
    encoded = json.dumps(diagnostic.as_dict())
    assert SECRET not in encoded
    assert TEXT not in encoded
    assert generation not in encoded
    assert diagnostic.finish_reason is None
    assert diagnostic.rejected_output_summary["validation_errors"] == [
        {"type": "int_parsing", "path": ["value"]},
        {"type": "extra_forbidden", "path": ["*"]},
    ]


def test_inspection_is_bounded_and_absent_output_stays_absent():
    generation = response(DOC_ID, [{"problem_summary": 123} for _ in range(40)])
    summary = diagnostic_from_exception(
        Rejected(generation), category="invalid_request", response_model=ExtractionPayload,
    ).rejected_output_summary
    assert summary["validation_error_count"] == 40
    assert len(summary["validation_errors"]) == 32
    error = Rejected(None)
    del error.body["error"]["failed_generation"]
    assert diagnostic_from_exception(error, category="invalid_request").rejected_output_summary is None


@pytest.mark.parametrize("status", [400, 401])
def test_sdk_failure_retains_identity_and_safe_summary_without_retry_or_raw_text(tmp_path, monkeypatch, status):
    captured = []
    clients = []
    generation = response(DOC_ID, [{"problem_summary": 123, "uncertainty_notes": [TEXT, SECRET]}])

    def create(**kwargs):
        captured.append(kwargs)
        raise Rejected(generation, status=status, finish_reason="length")

    def client(**kwargs):
        clients.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setitem(sys.modules, "groq", SimpleNamespace(Groq=client, APIStatusError=Rejected))
    result = run_extraction(
        doc_ids=[DOC_ID], model_decisions=[valid_decision()], human_decisions=[],
        derived_by_id={DOC_ID: derived()}, provider=GroqProvider(SECRET), provider_name="groq",
        model_name="openai/gpt-oss-120b", max_retries=1, call_budget=1,
        cache_dir=tmp_path / "cache", output_dir=tmp_path / "out", api_key=SECRET,
    )
    assert len(captured) == len(clients) == result.provider_calls == 1
    assert clients[0]["max_retries"] == 0
    assert captured[0]["response_format"]["json_schema"]["strict"] is True
    assert "diagnostic_model" not in captured[0]
    destination = Path(result.output_dir)
    failure, = jsonl(destination / "extraction_failures.jsonl")
    identity = failure["request_identity"]
    assert identity["prompt_id"] == "extract"
    assert identity["prompt_version"] == "extract/v2"
    assert identity["model"] == "openai/gpt-oss-120b"
    assert identity["max_tokens"] == 4096
    assert identity["prompt_characters"] == len(captured[0]["messages"][1]["content"])
    assert len(identity["prompt_sha256"]) == len(identity["transmitted_schema_sha256"]) == 64
    assert identity["content_hash"] == derived().content_hash
    assert failure["provider_diagnostic"]["rejected_output_summary"]["application_state"] == "invalid"
    assert failure["provider_diagnostic"]["finish_reason"] == "length"  # Reported, never inferred.
    event, = jsonl(destination / "stage_events.jsonl")
    assert event["detail"]["request_identity"] == identity
    manifest = json.loads((destination / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["tokens"]["provider_calls_without_recorded_usage"] == 1
    assert manifest["tokens"]["usage_totals_complete"] is False
    assert manifest["tokens"]["usage_scope"] == "recorded_provider_usage_only"
    assert manifest["tokens"]["input_tokens"] == manifest["tokens"]["output_tokens"] == 0
    assert jsonl(destination / "retrieval_cases.jsonl") == []
    assert list((tmp_path / "cache").rglob("*.json")) == []
    written = "\n".join(path.read_text(encoding="utf-8") for path in destination.iterdir())
    assert SECRET not in written
    assert TEXT not in written
    assert generation not in written


def test_finish_reason_survives_cache_and_legacy_entries_remain_readable(tmp_path):
    class Finished(FakeProvider):
        def complete_structured(self, *args, **kwargs):
            return replace(super().complete_structured(*args, **kwargs), finish_reason="length")

    provider = Finished(response(DOC_ID, []))
    first = run(tmp_path / "first", provider, [valid_decision()])
    cache = tmp_path / "first" / "cache"
    second = run(tmp_path / "second", provider, [valid_decision()], cache_dir=cache)
    assert provider.calls == 1
    assert second.cache_hits == 1
    for result in (first, second):
        row, = jsonl(Path(result.output_dir) / "extraction_inputs.jsonl")
        assert row["finish_reason"] == "length"
    path, = list(cache.rglob("*.json"))
    entry = json.loads(path.read_text(encoding="utf-8"))
    del entry["finish_reason"]  # A synthetic legacy entry, never a real cache entry.
    path.write_text(json.dumps(entry), encoding="utf-8")
    before = path.read_bytes()
    third = run(tmp_path / "third", provider, [valid_decision()], cache_dir=cache)
    row, = jsonl(Path(third.output_dir) / "extraction_inputs.jsonl")
    assert row["finish_reason"] is None
    assert third.cache_hits == 1
    assert path.read_bytes() == before


def test_unrecorded_usage_counts_failed_retry_and_missing_success_usage(tmp_path):
    from tests.test_llm_gateway import FakeProvider as GatewayFake, _complete, _gateway

    retrying = GatewayFake(failures=[provider_failed("synthetic failure")])
    gateway = _gateway(tmp_path / "retry", retrying, max_retries=2)
    _complete(gateway)
    assert gateway.usage.provider_calls == 2
    assert gateway.usage.provider_calls_without_recorded_usage == 1
    assert gateway.usage.input_tokens == 5

    class NoUsage(GatewayFake):
        def complete_structured(self, *args, **kwargs):
            return replace(super().complete_structured(*args, **kwargs), input_tokens=0, output_tokens=0, usage_reported=False)

    gateway = _gateway(tmp_path / "missing", NoUsage())
    _complete(gateway)
    assert gateway.usage.provider_calls_without_recorded_usage == 1


def test_reported_usage_remains_counted_when_response_text_is_withheld(tmp_path):
    from tests.test_llm_gateway import FakeProvider as GatewayFake, _complete, _gateway

    gateway = _gateway(tmp_path, GatewayFake(text=json.dumps({"value": SECRET})), denylist=(SECRET,))
    result = _complete(gateway)
    assert result.technical_state.value == "provider_error"
    assert result.raw_text is None
    assert gateway.usage.input_tokens == 5
    assert gateway.usage.output_tokens == 3
    assert gateway.usage.provider_calls_without_recorded_usage == 0
    assert list((tmp_path / "cache").rglob("*.json")) == []


def test_single_document_pilot_uses_one_call_and_existing_cache(tmp_path):
    from tests.test_extraction_pilot import EXPECTED, CountingProvider, _decision, _derived, _pilot, CORE

    ids = list(EXPECTED)
    decisions = [_decision(doc_id, CORE) for doc_id in ids]
    docs = {doc_id: _derived(doc_id) for doc_id in ids}
    provider = CountingProvider()
    target = "google_support-d7f386f347b7"
    first = _pilot(tmp_path / "first", provider, ids, decisions, docs, pilot_doc_id=target, call_budget=1)
    assert first.candidates == first.eligible == first.attempted == first.provider_calls == 1
    assert provider.calls == 1
    assert provider.schemas[0]["properties"]["doc_id"]["enum"] == [target]
    second = _pilot(
        tmp_path / "second", provider, ids, decisions, docs, pilot_doc_id=target, call_budget=1,
        cache_dir=tmp_path / "first" / "cache",
    )
    assert second.provider_calls == 0
    assert second.cache_hits == 1
    assert provider.calls == 1


def test_single_document_guards_keep_full_manifest_key_and_output_checks(tmp_path):
    from src.pipeline.extraction_pilot import PilotBoundsError, planned_output_dir
    from tests.test_extraction_pilot import EXPECTED, PILOT_MODEL, CountingProvider, _decision, _derived, _pilot, CORE

    ids = list(EXPECTED)
    decisions = [_decision(doc_id, CORE) for doc_id in ids]
    docs = {doc_id: _derived(doc_id) for doc_id in ids}
    target = "google_support-d7f386f347b7"
    provider = CountingProvider()
    with pytest.raises(PilotBoundsError, match="failed core"):
        _pilot(tmp_path, provider, ids, decisions, docs, pilot_doc_id=EXPECTED[0], call_budget=1)
    with pytest.raises(PilotBoundsError, match="1 external"):
        _pilot(tmp_path, provider, ids, decisions, docs, pilot_doc_id=target, call_budget=5)
    with pytest.raises(PilotBoundsError, match="5 documents"):
        _pilot(tmp_path, provider, [target], decisions, docs, pilot_doc_id=target, call_budget=1)
    with pytest.raises(PilotBoundsError, match="GROQ_API_KEY"):
        _pilot(tmp_path, None, ids, decisions, docs, pilot_doc_id=target, call_budget=1, api_key=None)
    assert not any(tmp_path.iterdir())
    destination = planned_output_dir(
        tmp_path, [target], model_name=PILOT_MODEL, temperature=0.0, max_tokens=64, dry_run=False, offline=False,
    )
    destination.mkdir()
    marker = destination / "partial.jsonl"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(PilotBoundsError, match="output already exists"):
        _pilot(tmp_path, provider, ids, decisions, docs, pilot_doc_id=target, call_budget=1)
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert provider.calls == 0


@pytest.mark.parametrize("limit_options", [[], ["--pilot-max-tokens", "8192"]], ids=["configured", "eight-k"])
def test_single_document_cli_dry_run_preserves_manifest_and_missing_key_refuses_output(tmp_path, capsys, monkeypatch, empty_env, limit_options):
    import main
    from src.core.config import load_settings
    from src.pipeline.extraction_pilot import DEFAULT_MANIFEST

    before = DEFAULT_MANIFEST.read_bytes()
    output = tmp_path / "single"
    args = [
        "run", "--stages", "extract", "--pilot", "--pilot-doc", "google_support-d7f386f347b7",
        "--provider", "groq", "--split", "development", "--call-budget", "1", "--max-retries", "1",
        "--output", str(output), "--cache", str(tmp_path / "cache"),
        *limit_options,
    ]
    assert main.main([*args, "--dry-run"]) == 0
    printed = capsys.readouterr()
    assert "documents            1" in printed.out
    assert "call budget          1" in printed.out
    assert f"max tokens           {8192 if limit_options else 4096}" in printed.out
    assert "provider calls       0" in printed.out
    assert "files written        0" in printed.out
    assert "reddit-23be97c93709" not in printed.out
    assert not output.exists()
    monkeypatch.setattr(main, "load_settings", lambda: load_settings(env_file=empty_env))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert main.main(args) == 1
    assert "GROQ_API_KEY" in capsys.readouterr().err
    assert not output.exists()
    assert DEFAULT_MANIFEST.read_bytes() == before


def test_completion_limit_override_changes_only_decoding_and_cache_identity(tmp_path):
    from tests.test_extraction_pilot import EXPECTED, CountingProvider, _decision, _derived, _pilot, CORE

    class Recorded(CountingProvider):
        def __init__(self):
            super().__init__()
            self.params = []

        def complete_structured(self, prompt, schema, params):
            self.params.append(params)
            return super().complete_structured(prompt, schema, params)

    target = "google_support-d7f386f347b7"
    ids = list(EXPECTED)
    decisions = [_decision(doc_id, CORE) for doc_id in ids]
    docs = {doc_id: _derived(doc_id) for doc_id in ids}
    provider = Recorded()
    options = dict(pilot_doc_id=target, call_budget=1, max_tokens=4096, cache_dir=tmp_path / "cache")
    original = _pilot(tmp_path / "original", provider, ids, decisions, docs, **options)
    before = {path: path.read_bytes() for path in (tmp_path / "cache").rglob("*.json")}
    changed = _pilot(tmp_path / "changed", provider, ids, decisions, docs, pilot_max_tokens=8192, **options)
    assert original.provider_calls == changed.provider_calls == 1
    assert original.run_id != changed.run_id
    assert [params.max_tokens for params in provider.params] == [4096, 8192]
    assert replace(provider.params[1], max_tokens=4096) == provider.params[0]
    assert provider.prompts[0] == provider.prompts[1]
    assert provider.schemas[0] == provider.schemas[1]
    for name, limit in (("original-hit", None), ("changed-hit", 8192)):
        cached = _pilot(tmp_path / name, provider, ids, decisions, docs, pilot_max_tokens=limit, **options)
        assert cached.provider_calls == 0
        assert cached.cache_hits == 1
    assert provider.calls == 2
    assert len(list((tmp_path / "cache").rglob("*.json"))) == 2
    assert all(path.read_bytes() == contents for path, contents in before.items())
    failure_rows = jsonl(Path(changed.output_dir) / "extraction_inputs.jsonl")
    assert failure_rows[0]["request_identity"]["max_tokens"] == 8192


def test_eight_k_failure_uses_one_sdk_attempt_and_stays_failed(tmp_path, monkeypatch):
    from tests.test_extraction_pilot import EXPECTED, _decision, _derived, _pilot, CORE

    captured, clients = [], []
    target = "google_support-d7f386f347b7"
    generation = json.dumps({"doc_id": target, "cases": [{}]})
    message = "max completion tokens reached before generating a valid document"

    def create(**kwargs):
        captured.append(kwargs)
        failure = Rejected(generation)
        failure.body["error"]["message"] = message
        raise failure

    def client(**kwargs):
        clients.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setitem(sys.modules, "groq", SimpleNamespace(Groq=client, APIStatusError=Rejected))
    ids = list(EXPECTED)
    decisions = [_decision(doc_id, CORE) for doc_id in ids]
    docs = {doc_id: _derived(doc_id) for doc_id in ids}
    result = _pilot(
        tmp_path, GroqProvider(SECRET), ids, decisions, docs, pilot_doc_id=target,
        call_budget=1, max_tokens=4096, pilot_max_tokens=8192, api_key=SECRET,
    )
    assert len(captured) == len(clients) == result.provider_calls == 1
    assert clients[0]["max_retries"] == 0
    assert captured[0]["max_tokens"] == 8192
    assert captured[0]["response_format"]["json_schema"]["strict"] is True
    destination = Path(result.output_dir)
    failure, = jsonl(destination / "extraction_failures.jsonl")
    assert failure["request_identity"]["max_tokens"] == 8192
    assert failure["provider_diagnostic"]["error_message"] == message
    assert failure["provider_diagnostic"]["rejected_output_summary"]["validation_errors"] == [
        {"type": "missing", "path": ["cases", 0, "problem_summary"]},
    ]
    assert failure["finish_reason"] is None  # The error message does not supply this metadata.
    assert jsonl(destination / "retrieval_cases.jsonl") == []
    assert jsonl(destination / "checkpoints.jsonl")[0]["status"] == "failed"
    manifest = json.loads((destination / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["tokens"]["usage_totals_complete"] is False
    assert list((tmp_path / "cache").rglob("*.json")) == []


@pytest.mark.parametrize("limit", [0, 4096, 16384, 8192.0, True])
def test_completion_limit_override_refuses_unbounded_values_before_calls(tmp_path, limit):
    from src.pipeline.extraction_pilot import PilotBoundsError
    from tests.test_extraction_pilot import EXPECTED, CountingProvider, _decision, _derived, _pilot, CORE

    ids = list(EXPECTED)
    decisions = [_decision(doc_id, CORE) for doc_id in ids]
    docs = {doc_id: _derived(doc_id) for doc_id in ids}
    provider = CountingProvider()
    with pytest.raises(PilotBoundsError, match="allows only 8192"):
        _pilot(
            tmp_path, provider, ids, decisions, docs, pilot_doc_id="google_support-d7f386f347b7",
            call_budget=1, pilot_max_tokens=limit,
        )
    assert provider.calls == 0
    assert list(tmp_path.iterdir()) == []


def test_eight_k_override_retains_missing_key_and_occupied_directory_guards(tmp_path):
    from src.pipeline.extraction_pilot import PilotBoundsError, planned_output_dir
    from tests.test_extraction_pilot import EXPECTED, PILOT_MODEL, CountingProvider, _decision, _derived, _pilot, CORE

    ids = list(EXPECTED)
    decisions = [_decision(doc_id, CORE) for doc_id in ids]
    docs = {doc_id: _derived(doc_id) for doc_id in ids}
    target = "google_support-d7f386f347b7"
    options = dict(pilot_doc_id=target, pilot_max_tokens=8192, call_budget=1)
    with pytest.raises(PilotBoundsError, match="GROQ_API_KEY"):
        _pilot(tmp_path, None, ids, decisions, docs, api_key=None, **options)
    assert list(tmp_path.iterdir()) == []
    refused = CountingProvider()
    with pytest.raises(PilotBoundsError, match="allows 4"):
        _pilot(tmp_path, refused, ids, decisions, docs, pilot_max_tokens=8192)
    assert refused.calls == 0
    destination = planned_output_dir(
        tmp_path, [target], model_name=PILOT_MODEL, temperature=0.0, max_tokens=8192,
        dry_run=False, offline=False,
    )
    destination.mkdir()
    marker = destination / "partial.jsonl"
    marker.write_text("preserve", encoding="utf-8")
    provider = CountingProvider()
    with pytest.raises(PilotBoundsError, match="output already exists"):
        _pilot(tmp_path, provider, ids, decisions, docs, **options)
    assert marker.read_text(encoding="utf-8") == "preserve"
    assert provider.calls == 0


@pytest.mark.parametrize("options", [[], ["--pilot", "--stages", "prefilter"], ["--diagnostic"]])
def test_completion_limit_cli_refuses_other_execution_modes(options, capsys):
    import main

    assert main.main(["run", "--stages", "extract", "--pilot-max-tokens", "8192", *options]) == 1
    assert "--pilot-max-tokens requires" in capsys.readouterr().err


@pytest.mark.parametrize("options", [[], ["--pilot", "--stages", "prefilter"], ["--pilot", "--diagnostic"]])
def test_single_document_cli_refuses_other_execution_modes(options, capsys):
    import main

    args = ["run", "--stages", "extract", "--pilot-doc", "google_support-d7f386f347b7", *options]
    assert main.main(args) == 1
    assert "--pilot-doc requires" in capsys.readouterr().err


@pytest.mark.parametrize("finish,reported", [("stop", True), ("length", False), (SECRET, True)])
def test_sdk_finish_reason_is_allowlisted_and_missing_usage_is_explicit(monkeypatch, finish, reported):
    from src.llm.providers.base import CompletionParams

    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=response(DOC_ID, [])), finish_reason=finish)],
        usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0) if reported else None,
    )
    monkeypatch.setitem(sys.modules, "groq", SimpleNamespace(
        Groq=lambda **kwargs: SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: completion))),
    ))
    result = GroqProvider(SECRET).complete_structured(
        "synthetic prompt", {"type": "object"}, CompletionParams("openai/gpt-oss-120b", 0.0, 4096, 1),
    )
    assert result.finish_reason == (finish if finish in {"stop", "length"} else None)
    assert result.usage_reported is reported
