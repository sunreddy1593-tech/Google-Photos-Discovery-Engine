"""Cache, repair, retries, and the null provider. No live calls."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from src.core.ids import cache_key
from src.core.versions import SCHEMA_VERSION, TAXONOMY_VERSION
from src.llm.cache import CacheEntry, CacheSecretError, ResponseCache
from src.llm.gateway import ModelGateway
from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.base import CompletionParams, ProviderResponse, timed_out
from src.llm.providers.null import NullProvider
from src.llm.repair import parse_json_document
from src.llm.select import select_provider
from src.models.enums import DecisionTechnicalState
from src.relevance.schema import RelevancePayload


class _Echo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class FakeProvider:
    provider_name = "fake"

    def __init__(self, text: str = '{"value": "ok"}', failures: list | None = None) -> None:
        self.text = text
        self.failures = list(failures or [])
        self.calls = 0

    def complete_structured(self, prompt: str, schema: dict, params: CompletionParams) -> ProviderResponse:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return ProviderResponse(
            text=self.text,
            input_tokens=5,
            output_tokens=3,
            model=params.model,
            provider=self.provider_name,
        )


def _gateway(tmp_path, provider, **overrides) -> ModelGateway:
    settings = dict(
        provider=provider,
        cache=ResponseCache(tmp_path / "cache"),
        provider_name="fake",
        model="claude-sonnet-4-5",
        temperature=0.0,
        max_tokens=100,
        timeout_seconds=5,
        max_retries=3,
        input_usd_per_million=3.0,
        output_usd_per_million=15.0,
        sleeper=lambda _seconds: None,
    )
    settings.update(overrides)
    return ModelGateway(**settings)


def _complete(gateway: ModelGateway, content_hash: str = "hash-1", **overrides):
    args = dict(
        prompt="classify",
        schema={"type": "object"},
        response_model=_Echo,
        content_hash=content_hash,
        prompt_id="relevance",
        prompt_version="relevance/v1",
        ruleset_version="prefilter/v1",
    )
    args.update(overrides)
    return gateway.complete(**args)


def test_null_provider_with_no_key_is_unavailable_and_makes_no_call(tmp_path) -> None:
    gateway = _gateway(tmp_path, NullProvider(), provider_name="null", max_retries=3)
    result = _complete(gateway)
    assert result.technical_state is DecisionTechnicalState.provider_unavailable
    assert result.provider_calls == 0
    assert result.validated is None
    assert list((tmp_path / "cache").rglob("*.json")) == []


def test_offline_selection_does_not_construct_the_live_adapter(monkeypatch) -> None:
    def boom(self, api_key: str) -> None:
        raise AssertionError(api_key)

    monkeypatch.setattr(AnthropicProvider, "__init__", boom)
    provider = select_provider(configured_name="anthropic", api_key="sk-ant-secret", offline=True)
    assert isinstance(provider, NullProvider)


def test_cache_hit_makes_zero_further_provider_calls(tmp_path) -> None:
    provider = FakeProvider()
    gateway = _gateway(tmp_path, provider)
    first = _complete(gateway)
    second = _complete(gateway)
    assert first.technical_state is DecisionTechnicalState.ok
    assert second.from_cache is True
    assert provider.calls == 1
    assert gateway.usage.provider_calls == 1
    assert gateway.usage.cache_hits == 1
    assert second.estimated_cost_usd == 0.0


def test_cache_key_changes_for_every_classification_input() -> None:
    base = dict(
        provider="anthropic",
        model="claude-sonnet-4-5",
        prompt_id="relevance",
        prompt_version="relevance/v1",
        schema_version=SCHEMA_VERSION,
        content_hash_value="abc",
        decoding_params={"max_tokens": 100, "temperature": 0.0},
        ruleset_version="prefilter/v1",
    )
    original = cache_key(**base)
    assert cache_key(**{**base, "provider": "null"}) != original
    assert cache_key(**{**base, "model": "other"}) != original
    assert cache_key(**{**base, "prompt_version": "relevance/v2"}) != original
    assert cache_key(**{**base, "schema_version": "9.0.0"}) != original
    assert cache_key(**{**base, "ruleset_version": "prefilter/v2"}) != original
    assert cache_key(**{**base, "content_hash_value": "def"}) != original
    assert cache_key(**{**base, "decoding_params": {"max_tokens": 100, "temperature": 0.2}}) != original
    assert cache_key(**base, taxonomy_version=None) == original
    assert cache_key(**base, taxonomy_version="v2") != original
    assert TAXONOMY_VERSION == "0-unassigned"


def test_syntax_repair_does_not_change_values() -> None:
    clean = {
        "scope_class": "out_of_scope",
        "confidence": 0.5,
        "note": "full,}",
        "reason_code": "maybe",
    }
    dirty = "```json\n" + json.dumps(clean).replace(
        '"confidence": 0.5', '"confidence": 0.5,'
    ) + "\n```"
    # The replacement above may not create a trailing comma in the object.
    dirty = '```json\n{"scope_class": "out_of_scope", "confidence": 0.5, "note": "full,}", "reason_code": "maybe",}\n```'
    parsed, repaired = parse_json_document(dirty)
    assert repaired is True
    assert parsed == clean
    smart = '{“scope_class”: “out_of_scope”, “confidence”: 0.5,}'
    parsed_smart, _repaired = parse_json_document(smart)
    assert parsed_smart == {"scope_class": "out_of_scope", "confidence": 0.5}
    already = json.dumps({"note": "a “quoted” word"})
    parsed_already, changed = parse_json_document(already)
    assert changed is False
    assert parsed_already["note"] == "a “quoted” word"
    with pytest.raises(json.JSONDecodeError):
        parse_json_document('Here is the answer {"scope_class": "out_of_scope"}')


def test_retries_then_success_and_terminal_failure(tmp_path) -> None:
    flaky = FakeProvider(failures=[timed_out("slow"), timed_out("slow")])
    gateway = _gateway(tmp_path, flaky)
    result = _complete(gateway)
    assert result.technical_state is DecisionTechnicalState.ok
    assert flaky.calls == 3
    assert result.provider_calls == 3

    terminal = FakeProvider(failures=[timed_out("slow"), timed_out("slow"), timed_out("slow"), timed_out("slow")])
    failed = _gateway(tmp_path / "again", terminal)
    outcome = _complete(failed)
    assert outcome.technical_state is DecisionTechnicalState.timeout
    assert terminal.calls == 3
    assert outcome.validated is None
    assert list((tmp_path / "again").rglob("*.json")) == []


def test_dry_run_does_not_call_the_provider(tmp_path) -> None:
    provider = FakeProvider()
    gateway = _gateway(tmp_path, provider)
    result = _complete(gateway, dry_run=True)
    assert result.technical_state is DecisionTechnicalState.skipped_dry_run
    assert provider.calls == 0
    assert list(tmp_path.rglob("*")) == []


def test_cache_refuses_a_secret(tmp_path) -> None:
    cache = ResponseCache(tmp_path)
    entry = CacheEntry(
        cache_key="a" * 64,
        provider="fake",
        model="m",
        prompt_id="relevance",
        prompt_version="relevance/v1",
        schema_version="1.0.0",
        ruleset_version="prefilter/v1",
        content_hash="h",
        decoding_params={},
        request_text="key is sk-ant-test-secret",
        raw_response="{}",
        input_tokens=0,
        output_tokens=0,
        cached_at="2026-09-27T00:00:00+00:00",
    )
    with pytest.raises(CacheSecretError):
        cache.write(entry, denylist=("sk-ant-test-secret",))
    assert list(tmp_path.rglob("*.json")) == []


def test_anthropic_adapter_does_not_put_the_key_in_the_request(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text='{"ok": true}')],
                usage=SimpleNamespace(input_tokens=2, output_tokens=1),
                model=kwargs["model"],
            )

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            captured["api_key"] = api_key
            self.messages = FakeMessages()

    fake = SimpleNamespace(
        Anthropic=FakeClient,
        APITimeoutError=type("APITimeoutError", (Exception,), {}),
        RateLimitError=type("RateLimitError", (Exception,), {}),
        APIConnectionError=type("APIConnectionError", (Exception,), {}),
        APIStatusError=type("APIStatusError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    response = AnthropicProvider("sk-ant-test-secret").complete_structured(
        "classify the post",
        {"type": "object"},
        CompletionParams(model="claude-sonnet-4-5", temperature=0.0, max_tokens=20, timeout_seconds=1),
    )
    assert captured["api_key"] == "sk-ant-test-secret"
    assert "sk-ant-test-secret" not in json.dumps(captured["kwargs"])
    assert response.provider == "anthropic"
    assert response.input_tokens == 2


def test_relevance_payload_rejects_an_invented_scope() -> None:
    parsed, _repaired = parse_json_document('{"scope_class": "maybe",}')
    assert parsed["scope_class"] == "maybe"
    with pytest.raises(Exception):
        RelevancePayload.model_validate(
            {
                "doc_id": "doc-1",
                "scope_class": parsed["scope_class"],
                "reason_code": "other_out_of_scope",
                "reason_summary": "no",
                "confidence": 0.2,
                "evidence": {"quote": "no"},
            }
        )
