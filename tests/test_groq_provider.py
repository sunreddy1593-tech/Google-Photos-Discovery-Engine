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
)
from src.llm.select import select_provider
from src.models.enums import DecisionTechnicalState, ReasonCode, ScopeClass
from src.pipeline.smoke_run import SmokeRunError, run_smoke
from src.pipeline.stages import PHASE_INSTANT, classify_with_ladder
from src.relevance.lock import HoldoutLocked, authorize_live_classification
from src.relevance.prompts import relevance_json_schema
from src.relevance.schema import RelevancePayload
from src.relevance.split import SplitAssignment

SECRET = "gsk-test-secret-not-real"


class _Limited(Exception):
    def __init__(self, retry_after: str | None) -> None:
        super().__init__(f"limited {SECRET}")
        self.response = SimpleNamespace(headers={"retry-after": retry_after} if retry_after else {})


def _groq_module(create):
    return SimpleNamespace(
        Groq=lambda api_key, timeout: SimpleNamespace(
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
