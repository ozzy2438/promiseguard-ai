"""Counterfactual recovery simulator for the first vertical slice."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from promiseguard.models import (
    OrderContext,
    RecoveryAction,
    RecoveryOption,
    RiskAssessment,
)

_CENTS = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


class RecoverySimulator:
    """Produce reproducible no-action and intervention outcomes."""

    simulator_version = "counterfactual-rules-v1"

    def simulate(
        self, order: OrderContext, risk: RiskAssessment
    ) -> tuple[RecoveryOption, ...]:
        no_action_probability = round(1.0 - risk.failure_probability, 4)
        options = [
            self._build_option(
                action=RecoveryAction.TAKE_NO_ACTION,
                order=order,
                on_time_probability=no_action_probability,
                intervention_cost=Decimal("0"),
                feasible=True,
                reversible=True,
                confidence=risk.confidence,
                constraints=(),
            )
        ]

        reroute_feasible = order.alternative_location_available
        options.append(
            self._build_option(
                action=RecoveryAction.REROUTE,
                order=order,
                on_time_probability=(
                    order.reroute_on_time_probability if reroute_feasible else 0.0
                ),
                intervention_cost=order.reroute_cost,
                feasible=reroute_feasible,
                reversible=True,
                confidence=min(risk.confidence, order.inventory_confidence),
                constraints=(
                    () if reroute_feasible else ("NO_ALTERNATIVE_LOCATION_AVAILABLE",)
                ),
            )
        )

        options.append(
            self._build_option(
                action=RecoveryAction.CARRIER_UPGRADE,
                order=order,
                on_time_probability=order.carrier_upgrade_on_time_probability,
                intervention_cost=order.carrier_upgrade_cost,
                feasible=True,
                reversible=True,
                confidence=risk.confidence,
                constraints=(),
            )
        )

        return tuple(options)

    @staticmethod
    def _build_option(
        *,
        action: RecoveryAction,
        order: OrderContext,
        on_time_probability: float,
        intervention_cost: Decimal,
        feasible: bool,
        reversible: bool,
        confidence: float,
        constraints: tuple[str, ...],
    ) -> RecoveryOption:
        success = Decimal(str(on_time_probability))
        failure = Decimal("1") - success
        expected_margin = _money(order.gross_margin * success)
        expected_failure_cost = _money(
            (order.cancellation_cost + order.support_cost) * failure
        )
        expected_net_value = _money(
            expected_margin - expected_failure_cost - intervention_cost
        )

        if not feasible:
            expected_net_value = Decimal("-999999.00")

        return RecoveryOption(
            action=action,
            feasible=feasible,
            on_time_probability=on_time_probability,
            expected_retained_gross_margin=expected_margin,
            intervention_cost=_money(intervention_cost),
            expected_failure_cost=expected_failure_cost,
            expected_net_value=expected_net_value,
            reversible=reversible,
            confidence=round(confidence, 4),
            constraints=constraints,
            evidence_references=order.source_references,
        )
