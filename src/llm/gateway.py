"""The only path from a stage to a model.

Cache lookup, retry, timeout, token accounting, syntax repair, and strict
model validation live here. A cache hit returns the stored response and does
not call the provider. Dry-run returns before either one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Mapping

from pydantic import BaseModel, ValidationError as PydanticValidationError

from src.core.ids import cache_key
from src.core.logging import get_logger
from src.core.versions import SCHEMA_VERSION
from src.llm.cache import CacheEntry, CacheSecretError, ResponseCache
from src.llm.pricing import estimate_list_price_usd
from src.llm.providers.base import (
    CompletionParams,
    ProviderCallError,
    ProviderDiagnostic,
    ProviderFatalError,
    StructuredProvider,
    safe_finish_reason,
)
from src.llm.repair import parse_json_document
from src.models.enums import DecisionTechnicalState

_RETRYABLE = frozenset(
    {
        DecisionTechnicalState.timeout,
        DecisionTechnicalState.rate_limited,
        DecisionTechnicalState.provider_error,
    }
)
RETRY_AFTER_CAP_SECONDS = 60.0

Sleeper = Callable[[float], None]


@dataclass
class GatewayResult:
    """What one logical completion produced. ``payload`` is set only when the
    response parsed and validated. A failure leaves it null."""

    technical_state: DecisionTechnicalState
    payload: dict[str, Any] | None = None
    validated: BaseModel | None = None
    raw_text: str | None = None
    from_cache: bool = False
    provider_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    repair_applied: bool = False
    message: str = ""
    diagnostic: ProviderDiagnostic | None = None
    finish_reason: str | None = None


@dataclass
class UsageTotals:
    """Reported provider usage, not actual billing. Cache hits add nothing here."""

    provider_calls: int = 0
    provider_calls_without_recorded_usage: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cached_input_tokens: int = 0
    cached_input_reported: bool = False
    latency_seconds: list[float] = field(default_factory=list)
    by_state: dict[str, int] = field(default_factory=dict)

    def add_state(self, state: DecisionTechnicalState) -> None:
        self.by_state[state.value] = self.by_state.get(state.value, 0) + 1


class ProviderBudgetError(RuntimeError):
    """Another provider call would pass the caller's budget."""


class ModelGateway:
    """Content-addressed completions with a bounded retry."""

    def __init__(
        self,
        provider: StructuredProvider,
        cache: ResponseCache,
        *,
        provider_name: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        max_retries: int,
        input_usd_per_million: float,
        output_usd_per_million: float,
        cached_input_usd_per_million: float | None = None,
        schema_version: str = SCHEMA_VERSION,
        denylist: tuple[str, ...] = (),
        sleeper: Sleeper | None = None,
        clock: Callable[[], datetime] | None = None,
        call_budget: int | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.provider_name = provider_name
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(1, max_retries)
        self.input_usd_per_million = input_usd_per_million
        self.output_usd_per_million = output_usd_per_million
        self.cached_input_usd_per_million = cached_input_usd_per_million
        self.schema_version = schema_version
        self.denylist = tuple(secret for secret in denylist if secret)
        self._sleeper = sleeper or _sleep
        self._clock = clock or (lambda: datetime.now(UTC))
        self.call_budget = call_budget
        self.usage = UsageTotals()
        self._log = get_logger("llm.gateway")

    def complete(
        self,
        *,
        prompt: str,
        schema: Mapping[str, Any],
        response_model: type[BaseModel],
        content_hash: str,
        prompt_id: str,
        prompt_version: str,
        decoding: Mapping[str, Any] | None = None,
        ruleset_version: str | None = None,
        taxonomy_version: str | None = None,
        discard_keys: tuple[str, ...] = (),
        dry_run: bool = False,
        unattempted_documents: int = 0,
    ) -> GatewayResult:
        """One completion. ``taxonomy_version`` is omitted by relevance."""
        params_map = _decoding_params(
            self.provider_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            schema=schema,
        )
        if decoding:
            params_map.update(dict(decoding))
        key = cache_key(
            provider=self.provider_name,
            model=self.model,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            schema_version=self.schema_version,
            content_hash_value=content_hash,
            decoding_params=params_map,
            ruleset_version=ruleset_version,
            taxonomy_version=taxonomy_version,
        )
        if dry_run:
            result = GatewayResult(
                technical_state=DecisionTechnicalState.skipped_dry_run,
                message="dry-run",
            )
            self.usage.add_state(result.technical_state)
            return result

        cached = self.cache.read(prompt_id, key)
        if cached is not None:
            self.usage.cache_hits += 1
            result = self._accept_text(
                cached.raw_response,
                response_model,
                discard_keys,
                from_cache=True,
            )
            result.finish_reason = safe_finish_reason(cached.finish_reason)
            self.usage.add_state(result.technical_state)
            self._log.info(
                "cache hit",
                extra={"prompt_id": prompt_id, "cache_key": key[:12]},
            )
            return result

        self.usage.cache_misses += 1
        params = CompletionParams(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout_seconds=self.timeout_seconds,
            diagnostic_model=response_model,
        )
        (
            response_text,
            calls,
            input_tokens,
            cached_input_tokens,
            output_tokens,
            failure,
            diagnostic,
            finish_reason,
        ) = self._call(
            prompt,
            schema,
            params,
            unattempted_documents=unattempted_documents,
        )
        self.usage.provider_calls += calls
        if failure is not None:
            self.usage.add_state(failure)
            self._log.info(
                "provider unavailable" if calls == 0 else "provider call failed",
                extra={
                    "prompt_id": prompt_id,
                    "technical_state": failure.value,
                    "provider_calls": calls,
                    "diagnostic_category": None if diagnostic is None else diagnostic.category,
                    "http_status": None if diagnostic is None else diagnostic.http_status,
                },
            )
            return GatewayResult(
                technical_state=failure,
                provider_calls=calls,
                message=failure.value,
                diagnostic=diagnostic,
            )

        assert response_text is not None
        # Reported numeric usage remains available even when content is withheld.
        cost = self._cost(input_tokens, output_tokens, cached_input_tokens)
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens
        self._remember_cached_input(cached_input_tokens)
        self.usage.estimated_cost_usd += cost
        if self._contains_secret(prompt) or self._contains_secret(response_text):
            self.usage.add_state(DecisionTechnicalState.provider_error)
            self._log.info(
                "provider response withheld",
                extra={"prompt_id": prompt_id, "technical_state": "provider_error"},
            )
            return GatewayResult(
                technical_state=DecisionTechnicalState.provider_error,
                provider_calls=calls,
                message="response withheld",
                finish_reason=finish_reason,
            )
        try:
            self.cache.write(
                CacheEntry(
                    cache_key=key,
                    provider=self.provider_name,
                    model=self.model,
                    prompt_id=prompt_id,
                    prompt_version=prompt_version,
                    schema_version=self.schema_version,
                    ruleset_version=ruleset_version,
                    content_hash=content_hash,
                    decoding_params=dict(sorted(params_map.items())),
                    request_text=prompt,
                    raw_response=response_text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_at=self._clock().isoformat(),
                    finish_reason=finish_reason,
                ),
                denylist=self.denylist,
            )
        except CacheSecretError:
            self.usage.add_state(DecisionTechnicalState.provider_error)
            return GatewayResult(
                technical_state=DecisionTechnicalState.provider_error,
                provider_calls=calls,
                message="response withheld",
            )
        result = self._accept_text(
            response_text,
            response_model,
            discard_keys,
            from_cache=False,
        )
        result.provider_calls = calls
        result.input_tokens = input_tokens
        result.output_tokens = output_tokens
        result.estimated_cost_usd = cost
        result.finish_reason = finish_reason
        self.usage.add_state(result.technical_state)
        return result

    def _call(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        params: CompletionParams,
        *,
        unattempted_documents: int,
    ) -> tuple[
        str | None,
        int,
        int,
        int | None,
        int,
        DecisionTechnicalState | None,
        ProviderDiagnostic | None,
        str | None,
    ]:
        calls = 0
        last_state: DecisionTechnicalState | None = None
        last_diagnostic: ProviderDiagnostic | None = None
        for attempt in range(self.max_retries):
            if (
                self.call_budget is not None
                and self.usage.provider_calls + calls >= self.call_budget
            ):
                self.usage.provider_calls += calls
                raise ProviderBudgetError(
                    f"provider call budget is {self.call_budget}"
                )
            calls += 1
            try:
                response = self.provider.complete_structured(prompt, schema, params)
            except ProviderFatalError as exc:
                self.usage.provider_calls_without_recorded_usage += 1
                self._remember_latency(exc.latency_seconds)
                self.usage.provider_calls += calls
                raise
            except ProviderCallError as exc:
                # The null provider is not a billable call and cannot succeed on retry.
                if self.provider_name == "null":
                    return None, 0, 0, None, 0, exc.state, exc.diagnostic, None
                self.usage.provider_calls_without_recorded_usage += 1
                last_state = exc.state
                last_diagnostic = exc.diagnostic
                self._remember_latency(exc.latency_seconds)
                if not self._should_retry(exc, attempt, calls, unattempted_documents):
                    if self._should_delay_next_document(exc, calls, unattempted_documents):
                        self._sleeper(_retry_wait(exc, attempt))
                    return None, calls, 0, None, 0, exc.state, exc.diagnostic, None
                self._sleeper(_retry_wait(exc, attempt))
                continue
            self._remember_latency(response.latency_seconds)
            if not response.usage_reported:
                self.usage.provider_calls_without_recorded_usage += 1
            return (
                response.text,
                calls,
                response.input_tokens,
                response.cached_input_tokens,
                response.output_tokens,
                None,
                None,
                safe_finish_reason(response.finish_reason),
            )
        return (
            None,
            calls,
            0,
            None,
            0,
            last_state or DecisionTechnicalState.provider_error,
            last_diagnostic,
            None,
        )

    def _should_retry(
        self,
        exc: ProviderCallError,
        attempt: int,
        calls: int,
        unattempted_documents: int,
    ) -> bool:
        """A retry may use only surplus budget beyond one attempt per remaining document."""
        if exc.state not in _RETRYABLE or attempt + 1 == self.max_retries:
            return False
        if self.call_budget is None:
            return True
        remaining = self.call_budget - (self.usage.provider_calls + calls)
        return remaining > unattempted_documents

    def _should_delay_next_document(
        self,
        exc: ProviderCallError,
        calls: int,
        unattempted_documents: int,
    ) -> bool:
        """Retry-After can pause the next document. The pause is not a call."""
        if unattempted_documents <= 0 or exc.retry_after_seconds is None:
            return False
        if exc.state not in _RETRYABLE:
            return False
        if self.call_budget is None:
            return False
        remaining = self.call_budget - (self.usage.provider_calls + calls)
        return remaining <= unattempted_documents

    def _accept_text(
        self,
        raw_text: str,
        response_model: type[BaseModel],
        discard_keys: tuple[str, ...],
        *,
        from_cache: bool,
    ) -> GatewayResult:
        try:
            parsed, repaired = parse_json_document(raw_text)
        except json.JSONDecodeError:
            return GatewayResult(
                technical_state=DecisionTechnicalState.response_parse_failed,
                raw_text=raw_text,
                from_cache=from_cache,
                message="response was not JSON after syntax repair",
            )
        if not isinstance(parsed, dict):
            return GatewayResult(
                technical_state=DecisionTechnicalState.schema_validation_failed,
                raw_text=raw_text,
                from_cache=from_cache,
                repair_applied=repaired,
                message="response JSON was not an object",
            )
        for key in discard_keys:
            parsed.pop(key, None)
        try:
            validated = response_model.model_validate(parsed)
        except PydanticValidationError as exc:
            return GatewayResult(
                technical_state=DecisionTechnicalState.schema_validation_failed,
                payload=parsed,
                raw_text=raw_text,
                from_cache=from_cache,
                repair_applied=repaired,
                message=_schema_message(exc),
            )
        return GatewayResult(
            technical_state=DecisionTechnicalState.ok,
            payload=parsed,
            validated=validated,
            raw_text=raw_text,
            from_cache=from_cache,
            repair_applied=repaired,
        )

    def _remember_latency(self, seconds: float | None) -> None:
        if seconds is not None:
            self.usage.latency_seconds.append(float(seconds))

    def _remember_cached_input(self, cached_input_tokens: int | None) -> None:
        if cached_input_tokens is None:
            return
        if not self.usage.cached_input_reported:
            self.usage.cached_input_tokens = 0
            self.usage.cached_input_reported = True
        self.usage.cached_input_tokens += max(int(cached_input_tokens), 0)

    def _contains_secret(self, text: str) -> bool:
        return any(secret in text for secret in self.denylist)

    def _cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int | None,
    ) -> float:
        return float(
            estimate_list_price_usd(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
                input_usd_per_million=self.input_usd_per_million,
                output_usd_per_million=self.output_usd_per_million,
                cached_input_usd_per_million=self.cached_input_usd_per_million,
            )
        )


def _decoding_params(
    provider_name: str,
    *,
    temperature: float,
    max_tokens: int,
    schema: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Cache identity. Groq records the temperature floor and the transmitted schema."""
    if provider_name == "groq":
        from src.llm.providers.groq import cache_decoding_params

        return cache_decoding_params(
            temperature=temperature,
            max_tokens=max_tokens,
            schema=schema,
        )
    return {"temperature": temperature, "max_tokens": max_tokens}


def _retry_wait(exc: ProviderCallError, attempt: int) -> float:
    """Honor Retry-After when the adapter captured it. The wait stays bounded."""
    if exc.retry_after_seconds is not None:
        return min(max(float(exc.retry_after_seconds), 0.0), RETRY_AFTER_CAP_SECONDS)
    return min(2.0, 0.2 * (2**attempt))


def _schema_message(exc: PydanticValidationError) -> str:
    """Field locations only. Pydantic's input echo can contain the post."""
    parts = []
    for error in exc.errors():
        loc = ".".join(str(item) for item in error.get("loc", ()))
        parts.append(f"{loc}: {error.get('type', 'invalid')}")
    return "; ".join(parts)[:300]


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
