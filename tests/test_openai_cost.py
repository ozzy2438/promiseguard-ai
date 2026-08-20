from __future__ import annotations

from decimal import Decimal

import pytest

from promiseguard.openai_cost import (
    UnknownModelPricingError,
    conservative_token_estimate,
    cost_for_usage,
    estimated_run_cost,
)
from promiseguard.openai_models import AgentTokenUsage


def test_gpt_5_nano_cost_is_lower_than_gpt_4o_mini_for_same_usage() -> None:
    usage = AgentTokenUsage(
        input_tokens=10_000,
        cached_input_tokens=2_000,
        output_tokens=1_000,
        total_tokens=11_000,
    )

    nano = cost_for_usage(model="gpt-5-nano", usage=usage)
    mini = cost_for_usage(model="gpt-4o-mini", usage=usage)

    assert nano == Decimal("0.000810")
    assert mini == Decimal("0.001950")
    assert nano < mini


def test_conservative_estimate_reserves_output_ceiling() -> None:
    estimated_tokens, cost = estimated_run_cost(
        model="gpt-5-nano",
        input_text="bounded context" * 100,
        max_output_tokens=320,
    )

    assert estimated_tokens == conservative_token_estimate("bounded context" * 100)
    assert cost > Decimal("0")
    assert cost < Decimal("0.001")


def test_unknown_model_is_rejected_instead_of_guessing_price() -> None:
    with pytest.raises(UnknownModelPricingError):
        cost_for_usage(
            model="unreviewed-model",
            usage=AgentTokenUsage(
                input_tokens=10,
                cached_input_tokens=0,
                output_tokens=5,
                total_tokens=15,
            ),
        )
