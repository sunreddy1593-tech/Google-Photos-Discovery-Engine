"""Choose a provider without reading the environment.

The key is passed in by the caller, which got it from ``core.config``. An
offline run and a missing key both select the null provider. They do not raise.
"""

from __future__ import annotations

from src.llm.providers.anthropic import AnthropicProvider
from src.llm.providers.base import StructuredProvider
from src.llm.providers.groq import GroqProvider
from src.llm.providers.null import NullProvider


def select_provider(
    *,
    configured_name: str,
    api_key: str | None,
    offline: bool,
) -> StructuredProvider:
    """Return the adapter for this run. Offline never constructs a live client."""
    if offline or configured_name == "null" or not api_key:
        return NullProvider()
    if configured_name == "anthropic":
        return AnthropicProvider(api_key)
    if configured_name == "groq":
        return GroqProvider(api_key)
    return NullProvider()
