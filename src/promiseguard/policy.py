"""Deterministic policy and autonomy gateway."""

from __future__ import annotations

from decimal import Decimal

from promiseguard.models import (
    DecisionRecommendation,
    OperatingMode,
    OrderContext,
    PolicyDisposition,
    PolicyEvaluation,
    RecoveryAction,
    RiskAssessment,
)


class PolicyGateway:
    """Apply data-quality, cost, confidence and operating-mode controls."""

    policy_version = "policy-v1"
    max_context_age_minutes = 15
    max_autonomous_cost = Decimal("10.00")
    min_autonomous_benefit = Decimal("5.00")
    min_autonomous_confidence = 0.85

    def evaluate(
        self,
        *,
        order: OrderContext,
        risk: RiskAssessment,
        recommendation: DecisionRecommendation,
        mode: OperatingMode,
    ) -> PolicyEvaluation:
        if order.data_freshness_minutes > self.max_context_age_minutes:
            return PolicyEvaluation(
                disposition=PolicyDisposition.BLOCK,
                policy_version=self.policy_version,
                execution_allowed=False,
                reasons=("STALE_OPERATIONAL_CONTEXT",),
            )

        if risk.data_quality_warnings:
            return PolicyEvaluation(
                disposition=PolicyDisposition.BLOCK,
                policy_version=self.policy_version,
                execution_allowed=False,
                reasons=tuple(risk.data_quality_warnings),
            )

        if recommendation.selected_action is RecoveryAction.TAKE_NO_ACTION:
            return PolicyEvaluation(
                disposition=PolicyDisposition.TAKE_NO_ACTION,
                policy_version=self.policy_version,
                execution_allowed=False,
                reasons=("NO_INTERVENTION_HAS_POSITIVE_INCREMENTAL_VALUE",),
            )

        selected = recommendation.ranked_options[0]
        if mode in {
            OperatingMode.OBSERVE,
            OperatingMode.SHADOW,
            OperatingMode.RECOMMENDATION,
            OperatingMode.APPROVAL,
        }:
            return PolicyEvaluation(
                disposition=PolicyDisposition.REQUEST_APPROVAL,
                policy_version=self.policy_version,
                execution_allowed=False,
                reasons=(f"MODE_{mode.value}_PREVENTS_AUTONOMOUS_EXECUTION",),
            )

        autonomy_conditions = (
            selected.intervention_cost <= self.max_autonomous_cost,
            recommendation.expected_incremental_value_vs_no_action
            >= self.min_autonomous_benefit,
            selected.confidence >= self.min_autonomous_confidence,
            selected.reversible,
        )
        if all(autonomy_conditions):
            return PolicyEvaluation(
                disposition=PolicyDisposition.AUTO_EXECUTE,
                policy_version=self.policy_version,
                execution_allowed=True,
                reasons=("BOUNDED_AUTONOMY_CONDITIONS_SATISFIED",),
            )

        return PolicyEvaluation(
            disposition=PolicyDisposition.REQUEST_APPROVAL,
            policy_version=self.policy_version,
            execution_allowed=False,
            reasons=("BOUNDED_AUTONOMY_CONDITIONS_NOT_SATISFIED",),
        )
