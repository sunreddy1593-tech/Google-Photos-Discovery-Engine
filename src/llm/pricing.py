"""List-price estimates. These figures are not invoices and not billed cost."""

from __future__ import annotations

from decimal import Decimal

# Published Groq list price for openai/gpt-oss-120b, retrieved 2026-09-30.
# The numbers estimate list price only. They do not report free-tier usage
# and they are not copied into actual billed cost.
GROQ_GPT_OSS_120B_LIST_PRICE = {
    "model": "openai/gpt-oss-120b",
    "input_usd_per_million": Decimal("0.15"),
    "cached_input_usd_per_million": Decimal("0.075"),
    "output_usd_per_million": Decimal("0.60"),
    "source": "Groq published list price for openai/gpt-oss-120b",
    "retrieved_on": "2026-09-30",
}


def estimate_list_price_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int | None = None,
    input_usd_per_million: float | Decimal,
    output_usd_per_million: float | Decimal,
    cached_input_usd_per_million: float | Decimal | None = None,
) -> Decimal:
    """Estimate list price for one response.

    ``cached_input_tokens`` counts only when the provider reported them and a
    cached-input rate is configured. Otherwise every input token uses the
    normal input rate. The result is an estimate, never an actual billed cost.
    """
    prompt = max(int(input_tokens), 0)
    completion = max(int(output_tokens), 0)
    cached = 0
    if cached_input_tokens is not None and cached_input_usd_per_million is not None:
        cached = min(max(int(cached_input_tokens), 0), prompt)
    uncached = prompt - cached
    input_rate = _rate(input_usd_per_million)
    output_rate = _rate(output_usd_per_million)
    cached_rate = _rate(cached_input_usd_per_million or 0)
    return (
        Decimal(uncached) * input_rate
        + Decimal(cached) * cached_rate
        + Decimal(completion) * output_rate
    ) / Decimal(1_000_000)


def _rate(value: float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
