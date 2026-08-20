"""Conservative token-cost estimation and actual OpenAI usage pricing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_UP
from math import ceil

from promiseguard.openai_models import AgentTokenUsage

_USD_QUANTUM = Decimal("0.000001")
_MILLION = Decimal("1000000")


class UnknownModelPricingError(ValueError):
    """Raised when a model lacks an explicit, reviewed pricing entry."""


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input_per_million_usd: Decimal
    cached_input_per_million_usd: Decimal
    output_per_million_usd: Decimal


_MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-5-nano": ModelPricing(Decimal("0.05"), Decimal("0.005"), Decimal("0.40")),
    "gpt-4.1-nano": ModelPricing(Decimal("0.10"), Decimal("0.025"), Decimal("0.40")),
    "gpt-4o-mini": ModelPricing(Decimal("0.15"), Decimal("0.075"), Decimal("0.60")),
}


def pricing_for_model(model: str) -> ModelPricing:
    """Return pricing for an alias or dated snapshot without guessing."""

    for known, pricing in _MODEL_PRICING.items():
        if model == known or model.startswith(f"{known}-"):
            return pricing
    raise UnknownModelPricingError(
        f"model {model!r} has no reviewed pricing entry; configure a supported model"
    )


def conservative_token_estimate(text: str) -> int:
    """Reserve one token per three UTF-8 bytes as a conservative upper estimate."""

    return max(1, ceil(len(text.encode("utf-8")) / 3))


def estimated_run_cost(
    *,
    model: str,
    input_text: str,
    max_output_tokens: int,
) -> tuple[int, Decimal]:
    input_tokens = conservative_token_estimate(input_text)
    usage = AgentTokenUsage(
        input_tokens=input_tokens,
        cached_input_tokens=0,
        output_tokens=max_output_tokens,
        total_tokens=input_tokens + max_output_tokens,
    )
    return input_tokens, cost_for_usage(model=model, usage=usage)


def cost_for_usage(*, model: str, usage: AgentTokenUsage) -> Decimal:
    pricing = pricing_for_model(model)
    uncached_input = usage.input_tokens - usage.cached_input_tokens
    amount = (
        Decimal(uncached_input) * pricing.input_per_million_usd
        + Decimal(usage.cached_input_tokens) * pricing.cached_input_per_million_usd
        + Decimal(usage.output_tokens) * pricing.output_per_million_usd
    ) / _MILLION
    return amount.quantize(_USD_QUANTUM, rounding=ROUND_UP)
