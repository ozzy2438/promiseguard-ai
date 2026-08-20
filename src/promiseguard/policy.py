"""Deterministic policy and evidence-bounded autonomy gateway."""

from __future__ import annotations

from collections.abc import Callable
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
    """Apply data-quality, product, cost, confidence and autonomy controls."""

    policy_version = "policy-v3"
    max_context_age_minutes = 15
    max_autonomous_cost = Decimal("10.00")
    min_autonomous_benefit = Decimal("5.00")
    min_autonomous_confidence = 0.85

    def __init__(
        self,
        *,
        kill_switch_active: Callable[[], bool] | None = None,
        autonomy_allowed: Callable[[RecoveryAction], bool] | None = None,
        control_version: Callable[[RecoveryAction], str] | None = None,
    ) -> None:
        self._kill_switch_active = kill_switch_active or (lambda: False)
        self._autonomy_allowed = autonomy_allowed or (lambda _: True)
        self._control_version = control_version or (lambda _: "static-controls-v1")

    def evaluate(
        self,
        *,
        order: OrderContext,
        risk: RiskAssessment,
        recommendation: DecisionRecommendation,
        mode: OperatingMode,
    ) -> PolicyEvaluation:
        action = recommendation.selected_action
        control_version = self._control_version(action)

        if order.data_freshness_minutes > self.max_context_age_minutes:
            return self._result(
                PolicyDisposition.BLOCK,
                control_version,
                False,
                "STALE_OPERATIONAL_CONTEXT",
            )

        if risk.data_quality_warnings:
            return PolicyEvaluation(
                disposition=PolicyDisposition.BLOCK,
                policy_version=self.policy_version,
                control_version=control_version,
                execution_allowed=False,
                reasons=tuple(risk.data_quality_warnings),
            )

        if action is RecoveryAction.TAKE_NO_ACTION:
            return self._result(
                PolicyDisposition.TAKE_NO_ACTION,
                control_version,
                False,
                "NO_INTERVENTION_HAS_POSITIVE_INCREMENTAL_VALUE",
            )

        if order.restricted_product:
            return self._result(
                PolicyDisposition.REQUEST_APPROVAL,
                control_version,
                False,
                "RESTRICTED_PRODUCT_REQUIRES_HUMAN_APPROVAL",
            )

        if mode in {
            OperatingMode.OBSERVE,
            OperatingMode.SHADOW,
            OperatingMode.RECOMMENDATION,
            OperatingMode.APPROVAL,
        }:
            return self._result(
                PolicyDisposition.REQUEST_APPROVAL,
                control_version,
                False,
                f"MODE_{mode.value}_PREVENTS_AUTONOMOUS_EXECUTION",
            )

        if self._kill_switch_active():
            return self._result(
                PolicyDisposition.BLOCK,
                control_version,
                False,
                "GLOBAL_ACTION_KILL_SWITCH_ACTIVE",
            )

        if not self._autonomy_allowed(action):
            return self._result(
                PolicyDisposition.REQUEST_APPROVAL,
                control_version,
                False,
                "ACTION_AUTONOMY_NOT_EARNED",
            )

        selected = next(
            option
            for option in recommendation.ranked_options
            if option.action is recommendation.selected_action
        )
        autonomy_conditions = (
            selected.intervention_cost <= self.max_autonomous_cost,
            recommendation.expected_incremental_value_vs_no_action
            >= self.min_autonomous_benefit,
            selected.confidence >= self.min_autonomous_confidence,
            selected.reversible,
        )
        if all(autonomy_conditions):
            return self._result(
                PolicyDisposition.AUTO_EXECUTE,
                control_version,
                True,
                "BOUNDED_AUTONOMY_CONDITIONS_SATISFIED",
            )

        return self._result(
            PolicyDisposition.REQUEST_APPROVAL,
            control_version,
            False,
            "BOUNDED_AUTONOMY_CONDITIONS_NOT_SATISFIED",
        )

    def _result(
        self,
        disposition: PolicyDisposition,
        control_version: str,
        execution_allowed: bool,
        *reasons: str,
    ) -> PolicyEvaluation:
        return PolicyEvaluation(
            disposition=disposition,
            policy_version=self.policy_version,
            control_version=control_version,
            execution_allowed=execution_allowed,
            reasons=tuple(reasons),
        )
