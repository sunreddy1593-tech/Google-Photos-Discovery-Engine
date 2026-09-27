"""Offline provider. This is the production path when no key is configured."""

from __future__ import annotations

from typing import Any, Mapping

from src.llm.providers.base import (
    CompletionParams,
    ProviderResponse,
    unavailable,
)


class NullProvider:
    """Return a clean unavailable error and make no network call.

    The gateway records ``technical_state = provider_unavailable``. It does not
    retry this error: another attempt would fail the same way.
    """

    provider_name = "null"

    def complete_structured(
        self,
        prompt: str,
        schema: Mapping[str, Any],
        params: CompletionParams,
    ) -> ProviderResponse:
        raise unavailable(
            "no model provider is configured for this run"
        )
