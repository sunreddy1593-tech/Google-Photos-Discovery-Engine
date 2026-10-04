"""Groq adapter tests. The suite never calls the live API."""

from __future__ import annotations

import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.core.ids import cache_key
from src.core.versions import RULESET_VERSION, SCHEMA_VERSION
from src.llm.cache import ResponseCache
from src.llm.gateway import ModelGateway, ProviderBudgetError
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.pricing import estimate_list_price_usd
from src.llm.providers.base import (
    CompletionParams,
    ProviderCallError,
    ProviderFatalError,
    authentication_failed,
    rate_limited,
)
from src.llm.providers.groq import (
    GROQ_ZERO_TEMPERATURE,
    GroqProvider,
    cache_decoding_params,
    effective_temperature,
    groq_request_schema,
    groq_strict_schema,
    transmitted_schema_sha256,
)
from src.llm.select import select_provider
from src.models.enums import DecisionTechnicalState, OffsetState, ReasonCode, ScopeClass
from src.pipeline.smoke_run import SmokeRunError, run_smoke
from src.pipeline.stages import PHASE_INSTANT, classify_with_ladder
from src.relevance.lock import HoldoutLocked, authorize_live_classification
from src.core.versions import prompt_version
from src.relevance.prompts import relevance_json_schema, render_relevance_prompt
from src.relevance.schema import RelevancePayload
from src.relevance.split import SplitAssignment

SECRET = "gsk-test-secret-not-real"


class _Limited(Exception):
    def __init__(self, retry_after: str | None) -> None:
        super().__init__(f"limited {SECRET}")
        self.response = SimpleNamespace(headers={"retry-after": retry_after} if retry_after else {})


def _groq_module(create):
    return SimpleNamespace(
        Groq=lambda api_key, timeout, max_retries=0: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
        APITimeoutError=type("APITimeoutError", (Exception,), {}),
        RateLimitError=_Limited,
        APIConnectionError=type("APIConnectionError", (Exception,), {}),
        APIStatusError=type("APIStatusError", (Exception,), {}),
        APIError=type("APIError", (Exception,), {}),
    )


def _completion(text: str, *, prompt_tokens: int = 11, completion_tokens: int = 7):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        model="openai/gpt-oss-120b",
    )


def test_shipped_groq_configuration(config_dir: Path, empty_env: Path) -> None:
    from src.core.config import load_settings

    settings = load_settings(config_dir, env_file=empty_env)
    provider, model, env_name = settings.models.relevance_choice(None)
    assert provider == "groq"
    assert model == "openai/gpt-oss-120b"
    assert env_name == "GROQ_API_KEY"
    assert settings.models.api_key_env == "GROQ_API_KEY"
    assert settings.models.groq_relevance_model == "openai/gpt-oss-120b"
    assert settings.models.anthropic_relevance_model == "claude-sonnet-4-5"
    assert settings.models.estimated_input_usd_per_million == 0.15
    assert settings.models.estimated_cached_input_usd_per_million == 0.075
    assert settings.models.estimated_output_usd_per_million == 0.60
    assert settings.models.list_price_source == (
        "Groq published list price for openai/gpt-oss-120b"
    )
    assert settings.models.list_price_retrieved_on == "2026-09-30"
    assert settings.secrets.groq_api_key is None
    anthropic, anthropic_model, anthropic_env = settings.models.relevance_choice("anthropic")
    assert anthropic == "anthropic"
    assert anthropic_model == "claude-sonnet-4-5"
    assert anthropic_env == "ANTHROPIC_API_KEY"


def test_missing_groq_key_fails_before_a_directory(tmp_path: Path) -> None:
    from src.core.config import Secrets
    from src.core.errors import ConfigError

    empty = tmp_path / "empty.env"
    empty.write_text("\n", encoding="utf-8")
    secrets = Secrets(_env_file=str(empty))
    assert secrets.groq_api_key is None
    with pytest.raises(ConfigError, match="GROQ_API_KEY") as raised:
        secrets.require("groq_api_key", needed_for="the relevance smoke")
    assert SECRET not in str(raised.value)
    pool = (
        SplitAssignment("core-00", "development", "core_incomplete_recall"),
        SplitAssignment("core-01", "development", "core_incomplete_recall"),
        SplitAssignment("adjacent-00", "development", "adjacent_known_item_retrieval"),
        SplitAssignment("adjacent-01", "development", "adjacent_known_item_retrieval"),
        SplitAssignment("out-00", "development", "out_of_scope"),
        SplitAssignment("out-01", "development", "out_of_scope"),
    )
    ids = tuple(row.doc_id for row in pool)
    parent = tmp_path / "smoke"
    with pytest.raises(SmokeRunError, match="API key is not set"):
        run_smoke(
            [],
            [],
            [],
            pool,
            ids,
            output_parent=parent,
            historical_dir=tmp_path / "historical",
            cache_dir=tmp_path / "cache",
            provider="groq",
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=32,
            dry_run=False,
            api_key=None,
        )
    assert not parent.exists()


def test_groq_request_uses_json_schema_and_hides_the_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def create(**kwargs):
        captured["kwargs"] = kwargs
        captured["client_key_seen"] = SECRET
        return _completion('{"ok": true}')

    monkeypatch.setitem(sys.modules, "groq", _groq_module(create))
    response = GroqProvider(SECRET).complete_structured(
        "classify the post",
        relevance_json_schema(),
        CompletionParams(
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=32,
            timeout_seconds=5,
        ),
    )
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["model"] == "openai/gpt-oss-120b"
    assert kwargs["temperature"] == GROQ_ZERO_TEMPERATURE
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["name"] == "relevance_payload"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    wire = kwargs["response_format"]["json_schema"]["schema"]
    evidence = _evidence_object(wire)
    assert set(evidence["required"]) == {"quote", "start_char", "end_char"}
    assert evidence["required"] == list(evidence["properties"])
    for obj in _schema_objects(wire):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    encoded = json.dumps(kwargs)
    assert SECRET not in encoded
    assert "human_scope_class" not in encoded
    assert "human_notes" not in encoded
    assert response.provider == "groq"
    assert response.model == "openai/gpt-oss-120b"
    assert response.input_tokens == 11
    assert response.output_tokens == 7
    assert response.requested_temperature == 0.0
    assert response.effective_temperature == GROQ_ZERO_TEMPERATURE
    assert response.latency_seconds is not None and response.latency_seconds >= 0


def test_strict_schema_keeps_null_offsets_and_application_rules() -> None:
    application = relevance_json_schema()
    loose = _evidence_object(application)
    assert loose["required"] == ["quote"]
    wire = groq_strict_schema(application)
    assert _evidence_object(application)["required"] == ["quote"]
    evidence = _evidence_object(wire)
    assert evidence["required"] == ["quote", "start_char", "end_char"]
    for name in ("start_char", "end_char"):
        encoded = json.dumps(evidence["properties"][name])
        assert '"type": "null"' in encoded or '"null"' in encoded
    for obj in _schema_objects(wire):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    payload = RelevancePayload.model_validate(
        {
            "doc_id": "doc-1",
            "scope_class": "core_incomplete_recall",
            "reason_code": "known_item_query_unformulable",
            "reason_summary": "The user could not turn the memory into a search.",
            "confidence": 0.9,
            "evidence": {"quote": "no idea what to even type"},
        }
    )
    assert payload.evidence.start_char is None
    assert payload.evidence.end_char is None
    text = "I know the photo is somewhere but I have no idea what to even type."
    from src.core.ids import raw_text_sha256, source_url_key
    from src.normalize.derive import derive_document
    from tests.synthetic import make_document

    document = make_document(
        doc_id="doc-1",
        title="A public title",
        raw_text=text,
        raw_text_sha256=raw_text_sha256(text),
        source_url="https://www.reddit.com/r/googlephotos/comments/doc-1/",
        source_url_key=source_url_key("https://www.reddit.com/r/googlephotos/comments/doc-1"),
        source_item_id="doc-1",
        author_hash="cafebabecafebabe",
    )
    derived = derive_document(document, derived_at=PHASE_INSTANT)
    outcome = classify_with_ladder(
        payload,
        audit=derived.raw_text_audit,
        redactions=derived.redaction_spans,
        content_hash=derived.content_hash,
        model_name="openai/gpt-oss-120b",
        prefilter=None,
        confidence_review_below=0.7,
        decided_at=PHASE_INSTANT,
        expected_doc_id="doc-1",
    )
    assert outcome.decision.technical_state is DecisionTechnicalState.ok
    assert outcome.decision.evidence[0].offset_state is OffsetState.repaired_unique
    assert outcome.decision.evidence[0].repair_applied is True
    assert outcome.decision.evidence[0].start_char is not None
    without = cache_decoding_params(temperature=0.0, max_tokens=4096)
    with_schema = cache_decoding_params(
        temperature=0.0,
        max_tokens=4096,
        schema=application,
    )
    assert "transmitted_schema_sha256" not in without
    assert with_schema["transmitted_schema_sha256"] == transmitted_schema_sha256(application)
    shared = dict(
        provider="groq",
        model="openai/gpt-oss-120b",
        prompt_id="relevance",
        prompt_version="relevance/v1",
        schema_version=SCHEMA_VERSION,
        content_hash_value="abc",
        ruleset_version=RULESET_VERSION,
    )
    assert cache_key(decoding_params=without, **shared) != cache_key(
        decoding_params=with_schema,
        **shared,
    )


def test_groq_prompt_matches_response_schema_and_leaves_old_cache(monkeypatch, tmp_path: Path) -> None:
    from src.relevance.lock import build_prompt_lock, write_prompt_lock

    application = relevance_json_schema()
    loose = _evidence_object(application)
    assert loose["required"] == ["quote"]
    wire = groq_strict_schema(application)
    assert groq_strict_schema(wire) == wire
    evidence = _evidence_object(wire)
    assert evidence["required"] == ["quote", "start_char", "end_char"]
    for name in ("start_char", "end_char"):
        encoded_field = json.dumps(evidence["properties"][name])
        assert '"null"' in encoded_field
    audit = "A public sentence with no private label."
    prompt = render_relevance_prompt(doc_id="doc-1", raw_text_audit=audit, schema=wire)
    embedded = json.loads(prompt.split("JSON schema:\n", 1)[1].split("\n\nUSER_POST\n", 1)[0])
    assert embedded == wire
    assert "set that key to null" in prompt
    assert "Do not omit start_char or end_char" in prompt
    assert "Do not invent indexes" in prompt
    assert "are optional" not in prompt
    assert "human_scope_class" not in prompt
    assert "human_notes" not in prompt
    assert prompt_version("relevance") == "relevance/v5"
    assert "Prompt relevance/v5." in prompt

    captured: dict[str, object] = {}

    def create(**kwargs):
        captured["kwargs"] = kwargs
        return _completion("{}")

    monkeypatch.setitem(sys.modules, "groq", _groq_module(create))
    GroqProvider(SECRET).complete_structured(
        prompt,
        wire,
        CompletionParams(
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=32,
            timeout_seconds=5,
        ),
    )
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    sent = kwargs["response_format"]["json_schema"]["schema"]
    assert sent == embedded
    request_text = json.dumps(kwargs)
    assert SECRET not in request_text
    assert "human_scope_class" not in request_text
    assert "human_notes" not in request_text

    shared = dict(
        provider="groq",
        model="openai/gpt-oss-120b",
        prompt_id="relevance",
        schema_version=SCHEMA_VERSION,
        content_hash_value="abc",
        ruleset_version=RULESET_VERSION,
        decoding_params=cache_decoding_params(temperature=0.0, max_tokens=32, schema=wire),
    )
    assert cache_key(prompt_version="relevance/v1", **shared) != cache_key(
        prompt_version="relevance/v2",
        **shared,
    )
    assert cache_key(prompt_version="relevance/v2", **shared) != cache_key(
        prompt_version="relevance/v3",
        **shared,
    )
    assert cache_key(prompt_version="relevance/v3", **shared) != cache_key(
        prompt_version="relevance/v4",
        **shared,
    )
    assert cache_key(prompt_version="relevance/v4", **shared) != cache_key(
        prompt_version="relevance/v5",
        **shared,
    )
    lock = build_prompt_lock(
        provider="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=32,
        transmitted_schema_sha256=transmitted_schema_sha256(wire),
    )
    lock["prompt_version"] = "relevance/v1"
    path = tmp_path / "old-lock.json"
    write_prompt_lock(path, lock)
    with pytest.raises(HoldoutLocked, match="prompt id and version"):
        authorize_live_classification(
            split_name="holdout",
            holdout_unlocked=True,
            lock_path=path,
            provider="groq",
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=32,
            transmitted_schema_sha256=transmitted_schema_sha256(wire),
        )


def test_relevance_v5_rules_change_identity_without_labels(monkeypatch, tmp_path: Path) -> None:
    from src.relevance.lock import build_prompt_lock, write_prompt_lock

    audit = "I searched for the edited photos and the search returned nothing."
    wire = groq_request_schema(relevance_json_schema(), doc_id="doc-v5")
    prompt = render_relevance_prompt(doc_id="doc-v5", raw_text_audit=audit, schema=wire)
    assert prompt_version("relevance") == "relevance/v5"
    assert "Prompt relevance/v5." in prompt
    for phrase in (
        "An unsuccessful formulated search does not, by itself, show that inability.",
        "A filename is not required.",
        "previously surfaced Memories",
        "An approximate date range is not, by itself, a forgotten date",
        "Organization advice or a feature request can address a real retrieval problem",
        "They do not establish deletion, corruption, backup failure, or incomplete memory.",
        "the selected text must support the scope and reason",
        "Use reason_summary to explain the whole-document basis",
    ):
        assert phrase in prompt
    for forbidden in (
        "human_notes",
        "human_scope_class",
        "human_reason_code",
        "Camaro",
        "google_support-d7f386f347b7",
        "google_support-e1e5277da7e8",
    ):
        assert forbidden not in prompt
    embedded = json.loads(prompt.split("JSON schema:\n", 1)[1].split("\n\nUSER_POST\n", 1)[0])
    assert embedded == wire
    assert embedded["properties"]["doc_id"]["enum"] == ["doc-v5"]

    captured: dict[str, object] = {}

    def create(**kwargs):
        captured["kwargs"] = kwargs
        return _completion("{}")

    monkeypatch.setitem(sys.modules, "groq", _groq_module(create))
    GroqProvider(SECRET).complete_structured(
        prompt,
        wire,
        CompletionParams(
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=32,
            timeout_seconds=5,
        ),
    )
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    request_text = json.dumps(kwargs)
    assert kwargs["response_format"]["json_schema"]["schema"] == embedded
    assert SECRET not in request_text
    assert "human_notes" not in request_text
    assert "human_scope_class" not in request_text
    assert "human_reason_code" not in request_text

    shared = dict(
        provider="groq",
        model="openai/gpt-oss-120b",
        prompt_id="relevance",
        schema_version=SCHEMA_VERSION,
        content_hash_value="abc",
        ruleset_version=RULESET_VERSION,
        decoding_params=cache_decoding_params(temperature=0.0, max_tokens=32, schema=wire),
    )
    assert cache_key(prompt_version="relevance/v4", **shared) != cache_key(
        prompt_version="relevance/v5",
        **shared,
    )
    digest = transmitted_schema_sha256(relevance_json_schema())
    lock = build_prompt_lock(
        provider="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=32,
        transmitted_schema_sha256=digest,
    )
    assert lock["prompt_version"] == "relevance/v5"
    assert "doc-v5" not in json.dumps(lock)
    stale = dict(lock)
    stale["prompt_version"] = "relevance/v4"
    path = tmp_path / "v4-lock.json"
    write_prompt_lock(path, stale)
    with pytest.raises(HoldoutLocked, match="prompt id and version"):
        authorize_live_classification(
            split_name="holdout",
            holdout_unlocked=True,
            lock_path=path,
            provider="groq",
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=32,
            transmitted_schema_sha256=digest,
        )
    mismatched = dict(lock)
    mismatched["prompt_hash"] = "0" * 64
    hash_path = tmp_path / "stale-hash-lock.json"
    write_prompt_lock(hash_path, mismatched)
    with pytest.raises(HoldoutLocked, match="prompt hash"):
        authorize_live_classification(
            split_name="holdout",
            holdout_unlocked=True,
            lock_path=hash_path,
            provider="groq",
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=32,
            transmitted_schema_sha256=digest,
        )


def test_document_id_enum_is_per_request_and_a_wrong_id_still_fails(monkeypatch) -> None:
    first_id = "app_store-5e60a403ce06"
    second_id = "app_store-b42c080472ee"
    application = relevance_json_schema()
    assert "enum" not in application["properties"]["doc_id"]
    first = groq_request_schema(application, doc_id=first_id)
    second = groq_request_schema(application, doc_id=second_id)
    assert first["properties"]["doc_id"] == {"type": "string", "enum": [first_id]}
    assert second["properties"]["doc_id"] == {"type": "string", "enum": [second_id]}
    audit = "I know the photo is somewhere but I have no idea what to even type."
    prompt = render_relevance_prompt(doc_id=first_id, raw_text_audit=audit, schema=first)
    embedded = json.loads(prompt.split("JSON schema:\n", 1)[1].split("\n\nUSER_POST\n", 1)[0])
    assert embedded == first
    assert f"doc_id must be exactly {first_id}" in prompt
    assert second_id not in prompt

    captured: dict[str, object] = {}

    def create(**kwargs):
        captured["kwargs"] = kwargs
        return _completion("{}")

    monkeypatch.setitem(sys.modules, "groq", _groq_module(create))
    GroqProvider(SECRET).complete_structured(
        prompt,
        first,
        CompletionParams(
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=32,
            timeout_seconds=5,
        ),
    )
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["response_format"]["json_schema"]["schema"] == embedded
    assert "human_scope_class" not in json.dumps(kwargs)

    quote = "no idea what to even type"
    from src.core.ids import raw_text_sha256, source_url_key
    from src.normalize.derive import derive_document
    from tests.synthetic import make_document

    document = make_document(
        doc_id=first_id,
        title="A public title",
        raw_text=audit,
        raw_text_sha256=raw_text_sha256(audit),
        source_url=f"https://www.reddit.com/r/googlephotos/comments/{first_id}/",
        source_url_key=source_url_key(f"https://www.reddit.com/r/googlephotos/comments/{first_id}"),
        source_item_id=first_id,
        author_hash="cafebabecafebabe",
    )
    derived = derive_document(document, derived_at=PHASE_INSTANT)
    wrong = RelevancePayload.model_validate(
        {
            "doc_id": "doc1",
            "scope_class": "core_incomplete_recall",
            "reason_code": "known_item_query_unformulable",
            "reason_summary": "The user could not turn the memory into a search.",
            "confidence": 0.9,
            "evidence": {"quote": quote, "start_char": None, "end_char": None},
        }
    )
    rejected = classify_with_ladder(
        wrong,
        audit=derived.raw_text_audit,
        redactions=derived.redaction_spans,
        content_hash=derived.content_hash,
        model_name="openai/gpt-oss-120b",
        prefilter=None,
        confidence_review_below=0.7,
        decided_at=PHASE_INSTANT,
        expected_doc_id=first_id,
    )
    assert rejected.decision.technical_state is DecisionTechnicalState.schema_validation_failed
    assert rejected.decision.doc_id == first_id
    assert rejected.decision.evidence == ()
    assert "did not match" in rejected.failure_message
    matched = wrong.model_copy(update={"doc_id": first_id})
    repaired = classify_with_ladder(
        matched,
        audit=derived.raw_text_audit,
        redactions=derived.redaction_spans,
        content_hash=derived.content_hash,
        model_name="openai/gpt-oss-120b",
        prefilter=None,
        confidence_review_below=0.7,
        decided_at=PHASE_INSTANT,
        expected_doc_id=first_id,
    )
    assert repaired.decision.technical_state is DecisionTechnicalState.ok
    assert repaired.decision.evidence[0].offset_state is OffsetState.repaired_unique

    shared = dict(
        provider="groq",
        model="openai/gpt-oss-120b",
        prompt_id="relevance",
        prompt_version="relevance/v3",
        schema_version=SCHEMA_VERSION,
        content_hash_value=derived.content_hash,
        ruleset_version=RULESET_VERSION,
    )
    first_key = cache_key(
        decoding_params=cache_decoding_params(temperature=0.0, max_tokens=32, schema=first),
        **shared,
    )
    second_key = cache_key(
        decoding_params=cache_decoding_params(temperature=0.0, max_tokens=32, schema=second),
        **shared,
    )
    previous = cache_key(
        decoding_params=cache_decoding_params(
            temperature=0.0,
            max_tokens=32,
            schema=groq_strict_schema(application),
        ),
        **{**shared, "prompt_version": "relevance/v2"},
    )
    assert first_key != second_key
    assert first_key != previous
    template = transmitted_schema_sha256(application)
    assert template != transmitted_schema_sha256(first)
    from src.relevance.lock import build_prompt_lock as build_lock

    lock = build_lock(
        provider="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=32,
        transmitted_schema_sha256=template,
    )
    assert first_id not in json.dumps(lock)
    assert lock["prompt_version"] == "relevance/v5"


def test_groq_holdout_lock_records_the_transmitted_schema(tmp_path: Path) -> None:
    from src.relevance.lock import build_prompt_lock, write_prompt_lock

    digest = transmitted_schema_sha256(relevance_json_schema())
    path = tmp_path / "lock.json"
    write_prompt_lock(
        path,
        build_prompt_lock(
            provider="groq",
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=4096,
            transmitted_schema_sha256=digest,
        ),
    )
    assert authorize_live_classification(
        split_name="holdout",
        holdout_unlocked=True,
        lock_path=path,
        provider="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=4096,
        transmitted_schema_sha256=digest,
    ) == "holdout"
    with pytest.raises(HoldoutLocked, match="transmitted schema"):
        authorize_live_classification(
            split_name="holdout",
            holdout_unlocked=True,
            lock_path=path,
            provider="groq",
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=4096,
            transmitted_schema_sha256="0" * 64,
        )


def test_diagnostic_runner_stops_after_one_provider_call(tmp_path: Path) -> None:
    from src.core.ids import raw_text_sha256, source_url_key
    from src.llm.cache import CacheEntry
    from src.normalize.derive import derive_document
    from src.pipeline.diagnostic_run import (
        DIAGNOSTIC_CALL_BUDGET,
        choose_diagnostic_document,
        relevance_cache_key,
        run_one_document,
    )
    from tests.synthetic import make_document

    def pair(doc_id: str, text: str):
        url = f"https://www.reddit.com/r/googlephotos/comments/{doc_id}/"
        document = make_document(
            doc_id=doc_id,
            title="A public title",
            raw_text=text,
            raw_text_sha256=raw_text_sha256(text),
            source_url=url,
            source_url_key=source_url_key(url),
            source_item_id=doc_id,
            author_hash="cafebabecafebabe",
        )
        return document, derive_document(document, derived_at=PHASE_INSTANT)

    first, first_derived = pair(
        "doc-a",
        "I know the photo is somewhere but I have no idea what to even type.",
    )
    second, second_derived = pair(
        "doc-b",
        "I searched the exact keyword beach and the photo still did not appear.",
    )
    assignments = (
        SplitAssignment("doc-a", "development", "core_incomplete_recall"),
        SplitAssignment("doc-b", "development", "adjacent_known_item_retrieval"),
    )
    schema = relevance_json_schema()
    cache = ResponseCache(tmp_path / "cache")
    key = relevance_cache_key(
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=32,
        content_hash=first_derived.content_hash,
        schema=schema,
    )
    cache.write(
        CacheEntry(
            cache_key=key,
            provider="groq",
            model="openai/gpt-oss-120b",
            prompt_id="relevance",
            prompt_version="relevance/v1",
            schema_version=SCHEMA_VERSION,
            ruleset_version=RULESET_VERSION,
            content_hash=first_derived.content_hash,
            decoding_params={},
            request_text="cached",
            raw_response="{}",
            input_tokens=0,
            output_tokens=0,
            cached_at="2026-09-30T00:00:00+00:00",
        )
    )
    chosen = choose_diagnostic_document(
        ("doc-a", "doc-b"),
        [first, second],
        [first_derived, second_derived],
        [],
        assignments,
        cache_dir=tmp_path / "cache",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=32,
    )
    assert chosen == "doc-b"

    class _Once:
        provider_name = "groq"

        def __init__(self) -> None:
            self.calls = 0

        def complete_structured(self, prompt, schema, params):
            self.calls += 1
            raise rate_limited("the provider rate-limited the request")

    provider = _Once()
    historical = tmp_path / "historical"
    historical.mkdir()
    (historical / "relevance_decisions.jsonl").write_text("keep\n", encoding="utf-8")
    (historical / "relevance_seed_review.csv").write_text("keep\n", encoding="utf-8")
    before = (historical / "relevance_decisions.jsonl").read_bytes()
    output_dir, result = run_one_document(
        [second],
        [second_derived],
        [],
        doc_id="doc-b",
        output_parent=tmp_path / "diagnostic",
        historical_dir=historical,
        cache_dir=tmp_path / "cache",
        provider="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=32,
        timeout_seconds=5,
        api_key=None,
        project_root=tmp_path,
        input_usd_per_million=0.15,
        output_usd_per_million=0.60,
        cached_input_usd_per_million=0.075,
        list_price_source="test",
        list_price_retrieved_on="2026-09-30",
        provider_instance=provider,
    )
    assert provider.calls == 1
    assert result.provider_calls == DIAGNOSTIC_CALL_BUDGET
    assert (historical / "relevance_decisions.jsonl").read_bytes() == before
    assert (output_dir / "relevance_decisions.jsonl").is_file()


def _schema_objects(node: object) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []

    def walk(item: object) -> None:
        if isinstance(item, list):
            for child in item:
                walk(child)
            return
        if not isinstance(item, dict):
            return
        properties = item.get("properties")
        if isinstance(properties, dict):
            found.append(item)
        for child in item.values():
            walk(child)

    walk(node)
    return found


def _evidence_object(schema: dict[str, object]) -> dict[str, object]:
    for obj in _schema_objects(schema):
        properties = obj.get("properties")
        if isinstance(properties, dict) and {"quote", "start_char", "end_char"} <= set(properties):
            return obj
    raise AssertionError("evidence object was not in the schema")


def test_sdk_rate_limit_sends_one_http_request(monkeypatch) -> None:
    """A 429 must not be retried inside the SDK. The gateway owns retries."""
    pytest.importorskip("groq")
    import httpx

    from groq._base_client import SyncHttpxClientWrapper

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            429,
            headers={"retry-after": "2"},
            json={"error": {"message": "rate limit reached", "type": "rate_limit_exceeded"}},
        )

    transport = httpx.MockTransport(handler)

    class _OneShotClient(SyncHttpxClientWrapper):
        def __init__(self, **kwargs: object) -> None:
            kwargs["transport"] = transport
            super().__init__(**kwargs)

    monkeypatch.setattr("groq._base_client.SyncHttpxClientWrapper", _OneShotClient)
    with pytest.raises(ProviderCallError, match="rate-limited") as raised:
        GroqProvider("gsk-test-not-a-real-key").complete_structured(
            "classify the post",
            {"type": "object", "properties": {}},
            CompletionParams(
                model="openai/gpt-oss-120b",
                temperature=0.0,
                max_tokens=8,
                timeout_seconds=1,
            ),
        )
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert raised.value.retry_after_seconds == 2
    assert "gsk-test-not-a-real-key" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_status_diagnostic_is_kept_and_secrets_are_not(tmp_path: Path, monkeypatch) -> None:
    from datetime import UTC, datetime

    from src.llm.providers.base import ProviderDiagnostic, diagnostic_from_exception
    from src.pipeline.stages import _relevance_event, _write_failures
    from src.relevance.classifier import failure_outcome

    class StatusRejected(Exception):
        def __init__(self) -> None:
            super().__init__(f"vendor said {SECRET}")
            self.status_code = 400
            self.body = {
                "error": {
                    "message": f"invalid schema {SECRET}",
                    "type": "invalid_request_error",
                }
            }
            self.response = SimpleNamespace(headers={"x-request-id": "req-1234abcd"})

    diagnostic = diagnostic_from_exception(StatusRejected(), category="invalid_request")
    assert diagnostic.category == "invalid_request"
    assert diagnostic.sdk_exception_class == "StatusRejected"
    assert diagnostic.http_status == 400
    assert diagnostic.provider_error_type == "invalid_request_error"
    assert diagnostic.request_id == "req-1234abcd"
    encoded = json.dumps(diagnostic.as_dict())
    assert SECRET not in encoded
    assert "vendor said" not in encoded
    assert diagnostic.error_message == "invalid schema [redacted]"

    class _RawBody(Exception):
        status_code = 500
        body = f"<html>{SECRET}</html>"
        response = SimpleNamespace(headers={"x-request-id": SECRET})

    raw = diagnostic_from_exception(_RawBody(), category="server_error")
    assert raw.http_status == 500
    assert raw.provider_error_type is None
    assert raw.request_id is None
    assert SECRET not in json.dumps(raw.as_dict())

    class _APIStatus(Exception):
        def __init__(self) -> None:
            super().__init__(SECRET)
            self.status_code = 400
            self.body = {"error": {"type": "invalid_request_error", "message": SECRET}}
            self.response = SimpleNamespace(headers={"x-request-id": "req-abcdef12"})

    def create(**_kwargs):
        raise _APIStatus()

    module = _groq_module(create)
    module.APIStatusError = _APIStatus
    monkeypatch.setitem(sys.modules, "groq", module)
    with pytest.raises(ProviderCallError, match="returned an error") as raised:
        GroqProvider(SECRET).complete_structured(
            "classify",
            {"type": "object"},
            CompletionParams(
                model="openai/gpt-oss-120b",
                temperature=0.0,
                max_tokens=8,
                timeout_seconds=1,
            ),
        )
    assert raised.value.diagnostic is not None
    assert raised.value.diagnostic.category == "invalid_request"
    assert raised.value.diagnostic.http_status == 400
    assert SECRET not in str(raised.value)
    assert SECRET not in json.dumps(raised.value.diagnostic.as_dict())
    assert raised.value.__cause__ is None

    outcome = failure_outcome(
        doc_id="doc-1",
        content_hash="hash",
        model_name="openai/gpt-oss-120b",
        state=DecisionTechnicalState.provider_error,
        decided_at=datetime(2026, 9, 30, tzinfo=UTC),
        message="provider_error",
        diagnostic=ProviderDiagnostic(
            category="invalid_request",
            http_status=400,
            provider_error_type=SECRET,
            request_id="req-1234abcd",
        ),
    )
    path = tmp_path / "relevance_failures.jsonl"
    _write_failures(path, [outcome], (SECRET,))
    stored = path.read_text(encoding="utf-8")
    assert SECRET not in stored
    row = json.loads(stored)
    assert row["message"] == "provider_error"
    assert row["provider_diagnostic"] is None
    assert row["technical_state"] == "provider_error"

    clean = failure_outcome(
        doc_id="doc-1",
        content_hash="hash",
        model_name="openai/gpt-oss-120b",
        state=DecisionTechnicalState.provider_error,
        decided_at=datetime(2026, 9, 30, tzinfo=UTC),
        message="provider_error",
        diagnostic=diagnostic,
    )
    event = _relevance_event("run", clean)
    assert event.detail["provider_diagnostic"]["http_status"] == 400
    assert event.detail["provider_diagnostic"]["request_id"] == "req-1234abcd"
    assert SECRET not in json.dumps(event.detail)


def test_schema_explanation_survives_without_key_or_source_text(monkeypatch) -> None:
    from src.llm.providers.base import diagnostic_from_exception

    source = "I know the photo is somewhere but I have no idea what to even type."
    explanation = (
        "Invalid schema at /properties/evidence/start_char: "
        "additionalProperties must be false"
    )

    class Explained(Exception):
        def __init__(self) -> None:
            super().__init__(f"vendor said {SECRET}")
            self.status_code = 400
            self.body = {
                "error": {
                    "message": (
                        f"{explanation}. Authorization: Bearer {SECRET}. post={source}"
                    ),
                    "type": "invalid_request_error",
                    "code": "json_validate_failed",
                    "param": "response_format.json_schema.schema",
                    "failed_generation": source,
                }
            }
            self.response = SimpleNamespace(headers={"x-request-id": "req-1234abcd"})

    diagnostic = diagnostic_from_exception(
        Explained(),
        category="invalid_request",
        redact=(source, SECRET),
    )
    encoded = json.dumps(diagnostic.as_dict())
    assert diagnostic.error_code == "json_validate_failed"
    assert diagnostic.error_param == "response_format.json_schema.schema"
    assert diagnostic.error_message is not None
    assert "/properties/evidence/start_char" in diagnostic.error_message
    assert "additionalProperties must be false" in diagnostic.error_message
    assert SECRET not in encoded
    assert source not in encoded
    assert "failed_generation" not in encoded
    assert "vendor said" not in encoded

    def create(**_kwargs):
        raise Explained()

    module = _groq_module(create)
    module.APIStatusError = Explained
    monkeypatch.setitem(sys.modules, "groq", module)
    prompt = f"Classify the fenced post.\nUSER_POST\n{source}\nUSER_POST\n"
    with pytest.raises(ProviderCallError, match="returned an error") as raised:
        GroqProvider(SECRET).complete_structured(
            prompt,
            {"type": "object", "properties": {}},
            CompletionParams(
                model="openai/gpt-oss-120b",
                temperature=0.0,
                max_tokens=8,
                timeout_seconds=1,
            ),
        )
    kept = raised.value.diagnostic
    assert kept is not None and kept.error_message is not None
    assert "/properties/evidence/start_char" in kept.error_message
    assert SECRET not in json.dumps(kept.as_dict())
    assert source not in json.dumps(kept.as_dict())
    assert raised.value.__cause__ is None


def test_rate_limit_maps_without_the_key_and_retries_count(monkeypatch, tmp_path: Path) -> None:
    calls = {"n": 0}

    def create(**_kwargs):
        calls["n"] += 1
        raise _Limited("4")

    monkeypatch.setitem(sys.modules, "groq", _groq_module(create))
    with pytest.raises(ProviderCallError, match="rate-limited") as raised:
        GroqProvider(SECRET).complete_structured(
            "classify",
            {"type": "object"},
            CompletionParams(
                model="openai/gpt-oss-120b",
                temperature=0.0,
                max_tokens=8,
                timeout_seconds=1,
            ),
        )
    assert raised.value.state is DecisionTechnicalState.rate_limited
    assert raised.value.retry_after_seconds == 4
    assert SECRET not in str(raised.value)
    assert raised.value.__cause__ is None

    provider_calls = {"n": 0}
    waits: list[float] = []

    class RetryProvider:
        provider_name = "groq"

        def complete_structured(self, prompt, schema, params):
            provider_calls["n"] += 1
            raise rate_limited("the provider rate-limited the request", retry_after_seconds=1.5)

    gateway = ModelGateway(
        RetryProvider(),
        ResponseCache(tmp_path / "cache"),
        provider_name="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=8,
        timeout_seconds=1,
        max_retries=10,
        input_usd_per_million=0,
        output_usd_per_million=0,
        call_budget=6,
        sleeper=waits.append,
    )
    exhausted = gateway.complete(
        prompt="classify",
        schema={"type": "object"},
        response_model=RelevancePayload,
        content_hash="hash-1",
        prompt_id="relevance",
        prompt_version="relevance/v1",
        ruleset_version=RULESET_VERSION,
        unattempted_documents=0,
    )
    assert exhausted.technical_state is DecisionTechnicalState.rate_limited
    assert provider_calls["n"] == 6
    assert gateway.usage.provider_calls == 6
    assert waits == [1.5, 1.5, 1.5, 1.5, 1.5]
    with pytest.raises(ProviderBudgetError):
        gateway.complete(
            prompt="classify",
            schema={"type": "object"},
            response_model=RelevancePayload,
            content_hash="hash-2",
            prompt_id="relevance",
            prompt_version="relevance/v1",
            ruleset_version=RULESET_VERSION,
            unattempted_documents=0,
        )
    assert provider_calls["n"] == 6


def test_groq_and_anthropic_cache_keys_differ() -> None:
    shared = dict(
        model="openai/gpt-oss-120b",
        prompt_id="relevance",
        prompt_version="relevance/v1",
        schema_version=SCHEMA_VERSION,
        content_hash_value="abc",
        ruleset_version=RULESET_VERSION,
    )
    groq_key = cache_key(
        provider="groq",
        decoding_params=cache_decoding_params(temperature=0.0, max_tokens=4096),
        **shared,
    )
    anthropic_key = cache_key(
        provider="anthropic",
        decoding_params={"temperature": 0.0, "max_tokens": 4096},
        **shared,
    )
    assert groq_key != anthropic_key
    assert effective_temperature(0.0) == GROQ_ZERO_TEMPERATURE
    assert cache_decoding_params(temperature=0.0, max_tokens=4096)["temperature"] == (
        GROQ_ZERO_TEMPERATURE
    )


def test_invalid_pairing_and_bad_evidence_stay_technical_failures() -> None:
    audit = "I could not remember the exact date"
    start = audit.index("could not remember")
    quote = audit[start:start + len("could not remember")]
    paired = RelevancePayload.model_validate(
        {
            "doc_id": "doc-1",
            "scope_class": "core_incomplete_recall",
            "reason_code": "deletion_or_corruption",
            "reason_summary": "A remembered photo could not be retrieved.",
            "confidence": 0.9,
            "evidence": {"quote": quote, "start_char": start, "end_char": start + len(quote)},
        }
    )
    bad_pair = classify_with_ladder(
        paired,
        audit=audit,
        redactions=(),
        content_hash="hash",
        model_name="openai/gpt-oss-120b",
        prefilter=None,
        confidence_review_below=0.7,
        decided_at=PHASE_INSTANT,
        expected_doc_id="doc-1",
    )
    assert bad_pair.decision.scope_class is None
    assert bad_pair.decision.technical_state is DecisionTechnicalState.schema_validation_failed
    assert bad_pair.decision.scope_class is not ScopeClass.out_of_scope

    invented = RelevancePayload.model_validate(
        {
            "doc_id": "doc-1",
            "scope_class": "out_of_scope",
            "reason_code": "deletion_or_corruption",
            "reason_summary": "The post is about storage.",
            "confidence": 0.4,
            "evidence": {"quote": "photos I never wrote", "start_char": 0, "end_char": 4},
        }
    )
    bad_evidence = classify_with_ladder(
        invented,
        audit=audit,
        redactions=(),
        content_hash="hash",
        model_name="openai/gpt-oss-120b",
        prefilter=None,
        confidence_review_below=0.7,
        decided_at=PHASE_INSTANT,
        expected_doc_id="doc-1",
    )
    assert bad_evidence.decision.scope_class is None
    assert bad_evidence.decision.technical_state is DecisionTechnicalState.evidence_validation_failed
    assert bad_evidence.decision.reason_code is not ReasonCode.deletion_or_corruption
    assert ReasonCode.evidence_validation_failed in bad_evidence.review_reasons


def test_holdout_stays_locked_and_anthropic_still_constructs() -> None:
    with pytest.raises(HoldoutLocked):
        authorize_live_classification(
            split_name="holdout",
            holdout_unlocked=False,
            lock_path=None,
            provider="groq",
            model="openai/gpt-oss-120b",
            temperature=0.0,
            max_tokens=4096,
        )
    selected = select_provider(configured_name="anthropic", api_key="sk-ant-test", offline=False)
    assert isinstance(selected, AnthropicProvider)
    groq = select_provider(configured_name="groq", api_key=SECRET, offline=False)
    assert isinstance(groq, GroqProvider)
    offline = select_provider(configured_name="groq", api_key=SECRET, offline=True)
    assert offline.provider_name == "null"


def test_dry_run_prints_no_key(tmp_path: Path, monkeypatch, capsys) -> None:
    from src.relevance.seed import SeedRow, write_seed_review
    from src.relevance.split import ensure_split_manifest
    from main import main

    rows = []
    for index in range(12):
        rows.append(_seed(f"core-{index:02d}", "core_incomplete_recall", "known_item_with_incomplete_recall"))
    for index in range(14):
        rows.append(_seed(f"adjacent-{index:02d}", "adjacent_known_item_retrieval", "known_item_with_precise_recall_failure"))
    for index in range(24):
        rows.append(_seed(f"out-{index:02d}", "out_of_scope", "storage_backup_or_sync"))
    seed = tmp_path / "seed.csv"
    write_seed_review(seed, rows)
    manifest = tmp_path / "split.csv"
    ensure_split_manifest(manifest, seed)

    class _Models:
        temperature = 0.0
        max_tokens = 4096

        def relevance_choice(self, override=None):
            return ("groq", "openai/gpt-oss-120b", "GROQ_API_KEY")

    class _Secrets:
        groq_api_key = SECRET

    monkeypatch.setattr(
        "main.load_settings",
        lambda: SimpleNamespace(models=_Models(), secrets=_Secrets()),
    )
    code = main(
        [
            "smoke",
            "--dry-run",
            "--manifest",
            str(tmp_path / "smoke.csv"),
            "--split-manifest",
            str(manifest),
            "--output",
            str(tmp_path / "out"),
            "--historical",
            str(tmp_path / "historical"),
            "--cache",
            str(tmp_path / "cache"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert SECRET not in captured.out
    assert SECRET not in captured.err
    assert "provider calls       0" in captured.out
    assert "openai/gpt-oss-120b" in captured.out
    assert not (tmp_path / "out").exists()
    smoke = (tmp_path / "smoke.csv").read_text(encoding="utf-8")
    assert "human_notes" not in smoke
    assert smoke.count("\n") == 7


def test_list_price_matches_known_token_counts() -> None:
    mixed = estimate_list_price_usd(
        input_tokens=1_000_000,
        cached_input_tokens=400_000,
        output_tokens=100_000,
        input_usd_per_million=Decimal("0.15"),
        cached_input_usd_per_million=Decimal("0.075"),
        output_usd_per_million=Decimal("0.60"),
    )
    # 600,000 * 0.15 + 400,000 * 0.075 + 100,000 * 0.60, per million tokens.
    assert mixed == Decimal("0.09") + Decimal("0.03") + Decimal("0.06")
    assert mixed == Decimal("0.18")
    unavailable = estimate_list_price_usd(
        input_tokens=2_000_000,
        cached_input_tokens=None,
        output_tokens=500_000,
        input_usd_per_million=Decimal("0.15"),
        cached_input_usd_per_million=Decimal("0.075"),
        output_usd_per_million=Decimal("0.60"),
    )
    assert unavailable == Decimal("0.60")
    explicit_zero = estimate_list_price_usd(
        input_tokens=1_000_000,
        cached_input_tokens=0,
        output_tokens=0,
        input_usd_per_million=Decimal("0.15"),
        cached_input_usd_per_million=Decimal("0.075"),
        output_usd_per_million=Decimal("0.60"),
    )
    assert explicit_zero == Decimal("0.15")


def test_gateway_estimates_list_price_without_a_billed_cost(tmp_path: Path) -> None:
    from pydantic import BaseModel

    class _Ok(BaseModel):
        ok: bool

    from src.llm.providers.base import ProviderResponse

    class _PricedProvider:
        provider_name = "groq"

        def complete_structured(self, prompt, schema, params):
            return ProviderResponse(
                text='{"ok": true}',
                input_tokens=1_000_000,
                output_tokens=100_000,
                cached_input_tokens=400_000,
                model=params.model,
                provider=self.provider_name,
            )

    gateway = ModelGateway(
        _PricedProvider(),
        ResponseCache(tmp_path / "cache"),
        provider_name="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=8,
        timeout_seconds=1,
        max_retries=1,
        input_usd_per_million=0.15,
        output_usd_per_million=0.60,
        cached_input_usd_per_million=0.075,
    )
    result = gateway.complete(
        prompt="classify",
        schema={"type": "object"},
        response_model=_Ok,
        content_hash="priced",
        prompt_id="relevance",
        prompt_version="relevance/v1",
        ruleset_version=RULESET_VERSION,
    )
    assert result.estimated_cost_usd == float(Decimal("0.18"))
    assert gateway.usage.cached_input_tokens == 400_000
    assert not hasattr(result, "actual_billed_cost_usd")


def test_cached_tokens_are_optional_and_credentials_are_fatal(monkeypatch) -> None:
    def create(**_kwargs):
        return _completion(
            '{"ok": true}',
            prompt_tokens=1_000_000,
            completion_tokens=10,
        )

    module = _groq_module(create)
    completion = create()
    completion.usage.prompt_tokens_details = SimpleNamespace(cached_tokens=250_000)

    def create_cached(**_kwargs):
        return completion

    monkeypatch.setitem(sys.modules, "groq", _groq_module(create_cached))
    cached = GroqProvider(SECRET).complete_structured(
        "classify",
        {"type": "object"},
        CompletionParams(model="openai/gpt-oss-120b", temperature=0.0, max_tokens=8, timeout_seconds=1),
    )
    assert cached.input_tokens == 1_000_000
    assert cached.cached_input_tokens == 250_000

    def create_plain(**_kwargs):
        return _completion('{"ok": true}', prompt_tokens=80, completion_tokens=5)

    monkeypatch.setitem(sys.modules, "groq", _groq_module(create_plain))
    plain = GroqProvider(SECRET).complete_structured(
        "classify",
        {"type": "object"},
        CompletionParams(model="openai/gpt-oss-120b", temperature=0.0, max_tokens=8, timeout_seconds=1),
    )
    assert plain.cached_input_tokens is None

    class _Auth(Exception):
        def __init__(self) -> None:
            super().__init__(f"invalid {SECRET}")
            self.status_code = 401

    def create_auth(**_kwargs):
        raise _Auth()

    auth_module = _groq_module(create_auth)
    auth_module.AuthenticationError = _Auth
    monkeypatch.setitem(sys.modules, "groq", auth_module)
    with pytest.raises(ProviderFatalError, match="rejected the credentials") as raised:
        GroqProvider(SECRET).complete_structured(
            "classify",
            {"type": "object"},
            CompletionParams(model="openai/gpt-oss-120b", temperature=0.0, max_tokens=8, timeout_seconds=1),
        )
    assert SECRET not in str(raised.value)
    assert raised.value.__cause__ is None


def test_smoke_reserves_one_attempt_per_document(tmp_path: Path) -> None:
    pool, selected, documents, derived = _smoke_documents()
    waits: list[float] = []

    class _LimitedDocs:
        provider_name = "groq"

        def __init__(self) -> None:
            self.calls = 0
            self.prompts: list[str] = []

        def complete_structured(self, prompt, schema, params):
            self.calls += 1
            self.prompts.append(prompt)
            raise rate_limited(
                "the provider rate-limited the request",
                retry_after_seconds=120,
            )

    provider = _LimitedDocs()
    finished = run_smoke(
        documents,
        derived,
        [],
        pool,
        selected,
        output_parent=tmp_path / "smoke",
        historical_dir=tmp_path / "historical",
        cache_dir=tmp_path / "cache",
        provider="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=32,
        dry_run=False,
        provider_instance=provider,
        sleeper=waits.append,
        max_retries=10,
        input_usd_per_million=0.15,
        cached_input_usd_per_million=0.075,
        output_usd_per_million=0.60,
        list_price_source="Groq published list price for openai/gpt-oss-120b",
        list_price_retrieved_on="2026-09-30",
    )
    assert provider.calls == 6
    assert finished.provider_calls == 6
    assert _attempt_counts(provider.prompts, selected) == {doc_id: 1 for doc_id in selected}
    assert waits == [60.0, 60.0, 60.0, 60.0, 60.0]
    stored = [
        json.loads(line)
        for line in (finished.output_dir / "relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert {row["doc_id"] for row in stored} == set(selected)
    assert {row["technical_state"] for row in stored} == {"rate_limited"}
    assert {row["scope_class"] for row in stored} == {None}
    manifest = json.loads((finished.output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    recorded = manifest["model_call"]
    assert recorded["actual_billed_cost_usd"] is None
    assert recorded["free_tier_usage"] is False
    assert recorded["estimated_list_price_usd"] == 0.0
    assert recorded["list_price_retrieved_on"] == "2026-09-30"
    assert SECRET not in json.dumps(manifest)


def test_surplus_budget_retries_only_the_spare_attempts(tmp_path: Path) -> None:
    from src.pipeline.stages import run_phase4

    pool, selected, documents, derived = _smoke_documents()

    class _AlwaysLimited:
        provider_name = "groq"

        def __init__(self) -> None:
            self.calls = 0
            self.prompts: list[str] = []

        def complete_structured(self, prompt, schema, params):
            self.calls += 1
            self.prompts.append(prompt)
            raise rate_limited("the provider rate-limited the request")

    provider = _AlwaysLimited()
    result = run_phase4(
        documents,
        derived,
        [],
        output_dir=tmp_path / "surplus",
        stages=["relevance"],
        provider_name="groq",
        model_name="openai/gpt-oss-120b",
        provider=provider,
        provider_call_budget=8,
        max_retries=10,
        sleeper=lambda _seconds: None,
        model_call={"provider": "groq"},
    )
    counts = _attempt_counts(provider.prompts, selected)
    first = min(selected)
    assert provider.calls == 8
    assert result.provider_calls == 8
    assert counts[first] == 3
    assert all(count == 1 for doc_id, count in counts.items() if doc_id != first)


def test_invalid_credentials_stop_before_later_documents(tmp_path: Path) -> None:
    from src.pipeline.stages import run_phase4

    _pool, selected, documents, derived = _smoke_documents()

    class _Rejected:
        provider_name = "groq"

        def __init__(self) -> None:
            self.calls = 0

        def complete_structured(self, prompt, schema, params):
            self.calls += 1
            raise authentication_failed(f"the provider rejected the credentials {SECRET}")

    provider = _Rejected()
    with pytest.raises(ProviderFatalError, match="rejected the credentials") as raised:
        run_phase4(
            documents,
            derived,
            [],
            output_dir=tmp_path / "fatal",
            stages=["relevance"],
            provider_name="groq",
            model_name="openai/gpt-oss-120b",
            provider=provider,
            provider_call_budget=8,
            max_retries=10,
        )
    assert SECRET not in str(raised.value)
    assert provider.calls == 1
    stored = [
        json.loads(line)
        for line in (tmp_path / "fatal" / "relevance_decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(stored) == 1
    assert stored[0]["doc_id"] == min(selected)
    assert stored[0]["technical_state"] == "provider_error"
    assert stored[0]["scope_class"] is None
    assert SECRET not in (tmp_path / "fatal" / "relevance_decisions.jsonl").read_text(encoding="utf-8")


def test_dry_run_still_makes_zero_provider_calls(tmp_path: Path) -> None:
    pool, selected, _documents, _derived = _smoke_documents()

    class _Boom:
        provider_name = "groq"
        calls = 0

        def complete_structured(self, prompt, schema, params):
            self.calls += 1
            raise AssertionError("dry run called the provider")

    provider = _Boom()
    finished = run_smoke(
        [],
        [],
        [],
        pool,
        selected,
        output_parent=tmp_path / "smoke",
        historical_dir=tmp_path / "historical",
        cache_dir=tmp_path / "cache",
        provider="groq",
        model="openai/gpt-oss-120b",
        temperature=0.0,
        max_tokens=32,
        dry_run=True,
        provider_instance=provider,
    )
    assert provider.calls == 0
    assert finished.provider_calls == 0
    assert finished.dry_run is True
    assert not finished.output_dir.exists()


def _smoke_documents():
    from src.core.ids import raw_text_sha256, source_url_key
    from src.normalize.derive import derive_document
    from src.pipeline.stages import PHASE_INSTANT
    from src.relevance.smoke import select_smoke_ids
    from tests.synthetic import make_document

    pool = (
        SplitAssignment("core-00", "development", "core_incomplete_recall"),
        SplitAssignment("core-01", "development", "core_incomplete_recall"),
        SplitAssignment("adjacent-00", "development", "adjacent_known_item_retrieval"),
        SplitAssignment("adjacent-01", "development", "adjacent_known_item_retrieval"),
        SplitAssignment("out-00", "development", "out_of_scope"),
        SplitAssignment("out-01", "development", "out_of_scope"),
    )
    selected = select_smoke_ids(pool)
    documents = []
    derived = []
    for doc_id in selected:
        text = f"Hello from the park [{doc_id}]"
        url = f"https://www.reddit.com/r/googlephotos/comments/{doc_id}/"
        document = make_document(
            doc_id=doc_id,
            title="A public title",
            raw_text=text,
            raw_text_sha256=raw_text_sha256(text),
            source_url=url,
            source_url_key=source_url_key(url),
            source_item_id=doc_id,
            author_hash="cafebabecafebabe",
        )
        documents.append(document)
        derived.append(derive_document(document, derived_at=PHASE_INSTANT))
    return pool, selected, documents, derived


def _attempt_counts(prompts: list[str], doc_ids: tuple[str, ...]) -> dict[str, int]:
    found: list[str] = []
    for prompt in prompts:
        hits = [doc_id for doc_id in doc_ids if f"[{doc_id}]" in prompt]
        assert len(hits) == 1
        found.append(hits[0])
    return dict(Counter(found))


def _seed(doc_id: str, scope: str, reason: str) -> "SeedRow":
    from src.relevance.seed import SeedRow

    return SeedRow(
        doc_id=doc_id,
        source_platform="reddit",
        source_type="post",
        title=doc_id,
        privacy_safe_excerpt="excerpt",
        prefilter_route="classify",
        prefilter_reason_codes="retained_for_recall",
        human_scope_class=scope,
        human_reason_code=reason,
        human_notes="note",
    )
