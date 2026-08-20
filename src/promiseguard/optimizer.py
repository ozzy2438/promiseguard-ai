"""Transparent constrained optimiser for recovery options."""

from __future__ import annotations

from decimal import Decimal

from promiseguard.models import (
    DecisionRecommendation,
    RecoveryAction,
    RecoveryOption,
)


class DecisionOptimizer:
    """Rank feasible actions by expected net value with deterministic tie-breaking."""

    optimiser_version = "constrained-score-v2"

    _tie_break_priority = {
        RecoveryAction.TAKE_NO_ACTION: 0,
        RecoveryAction.REROUTE: 1,
        RecoveryAction.CARRIER_UPGRADE: 2,
        RecoveryAction.SPLIT_SHIPMENT: 3,
        RecoveryAction.HUMAN_ESCALATION: 4,
    }

    def select(self, options: tuple[RecoveryOption, ...]) -> DecisionRecommendation:
        feasible = [option for option in options if option.feasible]
        if not feasible:
            raise ValueError("at least one feasible recovery option is required")

        ranked = tuple(
            sorted(
                feasible,
                key=lambda option: (
                    option.expected_net_value,
                    -self._tie_break_priority[option.action],
                ),
                reverse=True,
            )
        )
        selected = ranked[0]
        no_action = next(
            option for option in options if option.action is RecoveryAction.TAKE_NO_ACTION
        )
        rejected = tuple(
            f"{option.action.value}:{','.join(option.constraints)}"
            for option in options
            if not option.feasible
        )
        incremental = selected.expected_net_value - no_action.expected_net_value

        return DecisionRecommendation(
            selected_action=selected.action,
            ranked_options=ranked,
            expected_incremental_value_vs_no_action=Decimal(incremental),
            rejected_options=rejected,
            confidence=selected.confidence,
        )
