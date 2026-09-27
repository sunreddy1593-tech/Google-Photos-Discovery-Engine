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

    def __init__(self, message: str, state: DecisionTechnicalState) -> None:
        super().__init__(message)
        self.state = state


def unavailable(message: str) -> ProviderCallError:
    return ProviderCallError(message, DecisionTechnicalState.provider_unavailable)


def provider_failed(message: str) -> ProviderCallError:
    return ProviderCallError(message, DecisionTechnicalState.provider_error)


def timed_out(message: str) -> ProviderCallError:
    return ProviderCallError(message, DecisionTechnicalState.timeout)


def rate_limited(message: str) -> ProviderCallError:
    return ProviderCallError(message, DecisionTechnicalState.rate_limited)


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
