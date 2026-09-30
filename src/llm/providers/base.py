"""Provider protocol and the errors the gateway knows how to record.

Nothing in this module imports a vendor SDK. Adapters translate vendor
exceptions into :class:`ProviderCallError` so the rest of the pipeline never
sees a vendor type.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from src.core.errors import ProviderError
from src.models.enums import DecisionTechnicalState


class ProviderCallError(ProviderError):
    """A provider call did not return usable text.

    ``state`` is the technical state the stage stores. It is never a scope
    class.
    """

    def __init__(
        self,
        message: str,
        state: DecisionTechnicalState,
        *,
        retry_after_seconds: float | None = None,
        latency_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.state = state
        self.retry_after_seconds = retry_after_seconds
        self.latency_seconds = latency_seconds


def unavailable(message: str, *, latency_seconds: float | None = None) -> ProviderCallError:
    return ProviderCallError(
        message,
        DecisionTechnicalState.provider_unavailable,
        latency_seconds=latency_seconds,
    )


def provider_failed(message: str, *, latency_seconds: float | None = None) -> ProviderCallError:
    return ProviderCallError(
        message,
        DecisionTechnicalState.provider_error,
        latency_seconds=latency_seconds,
    )


def timed_out(message: str, *, latency_seconds: float | None = None) -> ProviderCallError:
    return ProviderCallError(
        message,
        DecisionTechnicalState.timeout,
        latency_seconds=latency_seconds,
    )


def rate_limited(
    message: str,
    *,
    retry_after_seconds: float | None = None,
    latency_seconds: float | None = None,
) -> ProviderCallError:
    return ProviderCallError(
        message,
        DecisionTechnicalState.rate_limited,
        retry_after_seconds=retry_after_seconds,
        latency_seconds=latency_seconds,
    )


class ProviderFatalError(ProviderCallError):
    """A failure that will reject every later document, such as bad credentials.

    The gateway does not retry it, and the stage stops the run after recording
    the document that hit it.
    """


def authentication_failed(
    message: str,
    *,
    latency_seconds: float | None = None,
) -> ProviderFatalError:
    return ProviderFatalError(
        message,
        DecisionTechnicalState.provider_error,
        latency_seconds=latency_seconds,
    )


@dataclass(frozen=True)
class CompletionParams:
    """Decoding and transport settings that the cache key and the adapter share.

    ``timeout_seconds`` does not enter the cache key. It does not change the
    text a successful call returns.
    """

    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: float


@dataclass(frozen=True)
class ProviderResponse:
    """Raw provider text plus token counts. Not a research record."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str
    latency_seconds: float | None = None
    requested_temperature: float | None = None
    effective_temperature: float | None = None
    cached_input_tokens: int | None = None


class StructuredProvider(Protocol):
    """One method. The gateway owns cache, retry, repair, and validation."""

    provider_name: str

    def complete_structured(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        params: CompletionParams,
    ) -> ProviderResponse:
        """Return raw text that should match ``schema``. Raise ProviderCallError."""
